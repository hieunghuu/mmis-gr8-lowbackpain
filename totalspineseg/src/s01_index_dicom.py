# -*- coding: utf-8 -*-
"""S01 - Lập chỉ mục header DICOM của toàn bộ MRI_Data (không đọc pixel).

Mỗi file .ima -> 1 dòng trong outputs/tables/1_dicom/dicom_index.csv.

* patient_id lấy từ TÊN THƯ MỤC (0001 -> 1), vì tag PatientID đã bị ẩn danh (rỗng).
* Mặt cắt (plane) tính từ ImageOrientationPatient: pháp tuyến = tích có hướng của
  vector hàng và vector cột; trục nào lớn nhất thì là mặt cắt đó
  (x -> SAG, y -> COR, z -> AX). Không tin tên thư mục.
* Trọng số (weighting) lấy từ SeriesDescription (t1/t2), kiểm tra chéo bằng
  EchoTime: T2 có TE dài (> 60 ms), T1 có TE ngắn.
* Localizer và POSDISP (ảnh phụ trợ) được đánh cờ để loại ở bước sau.

Chạy (từ thư mục totalspineseg/):  python src/s01_index_dicom.py
Chỉ in lại tóm tắt:        python src/s01_index_dicom.py --summary
"""
import sys
from multiprocessing import Pool
from pathlib import Path

import numpy as np
import pandas as pd
import pydicom

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import MRI_DIR, T_DICOM

PLANES = np.array(["SAG", "COR", "AX"])


def _float_list(v, n):
    try:
        out = [float(x) for x in v]
        return out if len(out) == n else [np.nan] * n
    except (TypeError, ValueError):
        return [np.nan] * n


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return np.nan


def read_header(path):
    path = Path(path)
    series_dir = path.parent.name
    rec = {
        "patient_id": int(path.parents[2].name),
        "study_dir": path.parents[1].name,
        "series_dir": series_dir,
        "file": path.name,
    }
    try:
        d = pydicom.dcmread(path, stop_before_pixels=True)
    except Exception as e:  # file hỏng
        rec["error"] = str(e)[:200]
        return rec

    iop = _float_list(d.get("ImageOrientationPatient"), 6)
    ipp = _float_list(d.get("ImagePositionPatient"), 3)
    ps = _float_list(d.get("PixelSpacing"), 2)
    normal = np.cross(iop[:3], iop[3:])
    plane = PLANES[int(np.nanargmax(np.abs(normal)))] if np.isfinite(normal).all() else "UNK"

    desc = str(d.get("SeriesDescription", ""))
    dl = desc.lower()
    te = _num(d.get("EchoTime"))
    weighting = "T2" if "t2" in dl else "T1" if "t1" in dl else "UNK"
    age = str(d.get("PatientAge", ""))

    rec.update({
        "instance": int(d.get("InstanceNumber", 0) or 0),
        "series_desc": desc,
        "series_number": int(d.get("SeriesNumber", 0) or 0),
        "study_uid": str(d.get("StudyInstanceUID", "")),
        "series_uid": str(d.get("SeriesInstanceUID", "")),
        "age": int(age[:3]) if age[:3].isdigit() else np.nan,
        "sex": str(d.get("PatientSex", "")),
        "rows": int(d.get("Rows", 0) or 0),
        "cols": int(d.get("Columns", 0) or 0),
        "px_row_mm": ps[0], "px_col_mm": ps[1],
        "slice_thickness": _num(d.get("SliceThickness")),
        "spacing_between": _num(d.get("SpacingBetweenSlices")),
        "slice_location": _num(d.get("SliceLocation")),
        "echo_time": te,
        "rep_time": _num(d.get("RepetitionTime")),
        "field_t": _num(d.get("MagneticFieldStrength")),
        "plane": plane,
        "weighting": weighting,
        "weighting_te_ok": (weighting == "T2" and te > 60) or (weighting == "T1" and te <= 60),
        "is_localizer": "localizer" in dl or series_dir.upper().startswith("LOCALIZER"),
        "is_posdisp": series_dir.upper().startswith("POSDISP"),
    })
    for i, k in enumerate(["iop_rx", "iop_ry", "iop_rz", "iop_cx", "iop_cy", "iop_cz"]):
        rec[k] = iop[i]
    for i, k in enumerate(["ipp_x", "ipp_y", "ipp_z"]):
        rec[k] = ipp[i]
    for i, k in enumerate(["normal_x", "normal_y", "normal_z"]):
        rec[k] = normal[i]
    return rec


def main():
    files = sorted(MRI_DIR.glob("*/*/*/*.ima"))
    print(f"Tìm thấy {len(files):,} file .ima trong {MRI_DIR}")
    with Pool() as pool:
        recs = pool.map(read_header, files, chunksize=200)
    df = pd.DataFrame(recs).sort_values(
        ["patient_id", "study_dir", "series_number", "instance"]).reset_index(drop=True)
    out = T_DICOM / "dicom_index.csv"
    df.to_csv(out, index=False)
    print(f"Đã ghi {out} ({len(df):,} dòng)")
    summarize(df)


def axial_blocks(g):
    """Số khối nghiêng trong 1 series axial = số hướng lát khác nhau."""
    return g[["iop_cx", "iop_cy", "iop_cz"]].round(2).drop_duplicates().shape[0]


def summarize(df):
    print("\n=== TÓM TẮT ===")
    if "error" in df:
        print(f"File lỗi không đọc được: {df['error'].notna().sum()}")
    main_imgs = df[~df.is_localizer & ~df.is_posdisp]
    print(f"Bệnh nhân: {df.patient_id.nunique()}")
    print(f"Lát cắt: tổng {len(df):,} | localizer {df.is_localizer.sum():,} | "
          f"posdisp {df.is_posdisp.sum():,} | ảnh chính {len(main_imgs):,}")
    print("\nẢnh chính theo mặt cắt x trọng số (số lát):")
    print(pd.crosstab(main_imgs.plane, main_imgs.weighting).to_string())

    bad = main_imgs[~main_imgs.weighting_te_ok]
    print(f"\nLát có tên series mâu thuẫn với EchoTime: {len(bad)}")
    if len(bad):
        print(bad.groupby(["series_desc"]).size().head(10).to_string())

    studies = df.groupby("patient_id").study_dir.nunique()
    print(f"\nBệnh nhân có >1 study: {(studies > 1).sum()}")

    # Chuỗi chính cần dùng: T2 TSE (không phải TIRM/STIR, TrueFISP, CISS...).
    # Xét trên MỌI study, vì thứ tự tên thư mục không nói lên study nào là cột sống
    # (vd BN 230 có study ABDOMEN_ đứng trước L-SPINE_).
    t2 = main_imgs[main_imgs.series_desc.str.lower().str.contains("t2_tse")]
    has_sag = t2[t2.plane == "SAG"].groupby("patient_id").series_dir.nunique()
    has_ax = t2[t2.plane == "AX"].groupby("patient_id").series_dir.nunique()
    pids = df.patient_id.unique()
    print(f"Có T2 TSE SAG: {has_sag.reindex(pids).gt(0).sum()} / {len(pids)} "
          f"(>1 series: {(has_sag > 1).sum()})")
    print(f"Có T2 TSE AX : {has_ax.reindex(pids).gt(0).sum()} / {len(pids)} "
          f"(>1 series: {(has_ax > 1).sum()})")
    missing = sorted(set(pids) - set(has_sag.index))
    if missing:
        print(f"  Thiếu T2 TSE SAG: {missing}")
    missing = sorted(set(pids) - set(has_ax.index))
    if missing:
        print(f"  Thiếu T2 TSE AX : {missing}")
    mislabeled = t2[t2.series_desc.str.lower().str.contains("sag") & (t2.plane != "SAG")]
    print(f"Lát tên 'sag' nhưng hướng thực tế KHÔNG phải SAG: {len(mislabeled)} "
          f"(BN {sorted(mislabeled.patient_id.unique())})")

    blocks = t2[t2.plane == "AX"].groupby(["patient_id", "series_dir"]).apply(
        axial_blocks, include_groups=False)
    print("\nSố khối nghiêng trong mỗi series T2 AX (số series):")
    print(blocks.value_counts().sort_index().to_string())

    n_sag = t2[t2.plane == "SAG"].groupby(["patient_id", "series_dir"]).size()
    print(f"\nSố lát mỗi series T2 SAG: min {n_sag.min()}, trung vị {n_sag.median():.0f}, max {n_sag.max()}")


if __name__ == "__main__":
    if "--summary" in sys.argv:   # chỉ in lại tóm tắt từ CSV đã có
        summarize(pd.read_csv(T_DICOM / "dicom_index.csv", low_memory=False))
    else:
        main()
