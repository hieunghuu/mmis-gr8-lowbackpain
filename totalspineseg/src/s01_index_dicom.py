# -*- coding: utf-8 -*-
"""S01 - Lap chi muc header DICOM cua toan bo MRI_Data (khong doc pixel).

Moi file .ima -> 1 dong trong outputs/tables/dicom_index.csv.

* patient_id lay tu TEN THU MUC (0001 -> 1), vi tag PatientID da bi an danh (rong).
* Mat cat (plane) tinh tu ImageOrientationPatient: phap tuyen = tich co huong cua
  vector hang va vector cot; truc nao lon nhat thi la mat cat do
  (x -> SAG, y -> COR, z -> AX). Khong tin ten thu muc.
* Trong so (weighting) lay tu SeriesDescription (t1/t2), kiem tra cheo bang
  EchoTime: T2 co TE dai (> 60 ms), T1 co TE ngan.
* Localizer va POSDISP (anh phu tro) duoc danh co de loai o buoc sau.

Chay (tu thu muc totalspineseg/):  python src/s01_index_dicom.py
Chi in lai tom tat:        python src/s01_index_dicom.py --summary
"""
import sys
from multiprocessing import Pool
from pathlib import Path

import numpy as np
import pandas as pd
import pydicom

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import MRI_DIR, TABLES

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
    except Exception as e:  # file hong
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
    print(f"Tim thay {len(files):,} file .ima trong {MRI_DIR}")
    with Pool() as pool:
        recs = pool.map(read_header, files, chunksize=200)
    df = pd.DataFrame(recs).sort_values(
        ["patient_id", "study_dir", "series_number", "instance"]).reset_index(drop=True)
    out = TABLES / "dicom_index.csv"
    df.to_csv(out, index=False)
    print(f"Da ghi {out} ({len(df):,} dong)")
    summarize(df)


def axial_blocks(g):
    """So khoi nghieng trong 1 series axial = so huong lat khac nhau."""
    return g[["iop_cx", "iop_cy", "iop_cz"]].round(2).drop_duplicates().shape[0]


def summarize(df):
    print("\n=== TOM TAT ===")
    if "error" in df:
        print(f"File loi khong doc duoc: {df['error'].notna().sum()}")
    main_imgs = df[~df.is_localizer & ~df.is_posdisp]
    print(f"Benh nhan: {df.patient_id.nunique()}")
    print(f"Lat cat: tong {len(df):,} | localizer {df.is_localizer.sum():,} | "
          f"posdisp {df.is_posdisp.sum():,} | anh chinh {len(main_imgs):,}")
    print("\nAnh chinh theo mat cat x trong so (so lat):")
    print(pd.crosstab(main_imgs.plane, main_imgs.weighting).to_string())

    bad = main_imgs[~main_imgs.weighting_te_ok]
    print(f"\nLat co ten series mau thuan voi EchoTime: {len(bad)}")
    if len(bad):
        print(bad.groupby(["series_desc"]).size().head(10).to_string())

    studies = df.groupby("patient_id").study_dir.nunique()
    print(f"\nBenh nhan co >1 study: {(studies > 1).sum()}")

    # Chuoi chinh can dung: T2 TSE (khong phai TIRM/STIR, TrueFISP, CISS...).
    # Xet tren MOI study, vi thu tu ten thu muc khong noi len study nao la cot song
    # (vd BN 230 co study ABDOMEN_ dung truoc L-SPINE_).
    t2 = main_imgs[main_imgs.series_desc.str.lower().str.contains("t2_tse")]
    has_sag = t2[t2.plane == "SAG"].groupby("patient_id").series_dir.nunique()
    has_ax = t2[t2.plane == "AX"].groupby("patient_id").series_dir.nunique()
    pids = df.patient_id.unique()
    print(f"Co T2 TSE SAG: {has_sag.reindex(pids).gt(0).sum()} / {len(pids)} "
          f"(>1 series: {(has_sag > 1).sum()})")
    print(f"Co T2 TSE AX : {has_ax.reindex(pids).gt(0).sum()} / {len(pids)} "
          f"(>1 series: {(has_ax > 1).sum()})")
    missing = sorted(set(pids) - set(has_sag.index))
    if missing:
        print(f"  Thieu T2 TSE SAG: {missing}")
    missing = sorted(set(pids) - set(has_ax.index))
    if missing:
        print(f"  Thieu T2 TSE AX : {missing}")
    mislabeled = t2[t2.series_desc.str.lower().str.contains("sag") & (t2.plane != "SAG")]
    print(f"Lat ten 'sag' nhung huong thuc te KHONG phai SAG: {len(mislabeled)} "
          f"(BN {sorted(mislabeled.patient_id.unique())})")

    blocks = t2[t2.plane == "AX"].groupby(["patient_id", "series_dir"]).apply(
        axial_blocks, include_groups=False)
    print("\nSo khoi nghieng trong moi series T2 AX (so series):")
    print(blocks.value_counts().sort_index().to_string())

    n_sag = t2[t2.plane == "SAG"].groupby(["patient_id", "series_dir"]).size()
    print(f"\nSo lat moi series T2 SAG: min {n_sag.min()}, trung vi {n_sag.median():.0f}, max {n_sag.max()}")


if __name__ == "__main__":
    if "--summary" in sys.argv:   # chi in lai tom tat tu CSV da co
        summarize(pd.read_csv(TABLES / "dicom_index.csv", low_memory=False))
    else:
        main()
