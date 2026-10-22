# -*- coding: utf-8 -*-
""" AI trước segmentation: DICOM (zip một study hoặc thư mục) -> NIfTI sagittal T2 cho segment().

Worker của BE gọi trước segment():
  convert(src, out_path) -> dict thông tin series đã chọn | raise ConvertError

* Không cần biết cấu trúc thư mục trong zip: đọc header mọi file, gom theo (StudyInstanceUID,
  SeriesInstanceUID). File không phải ảnh DICOM (DICOMDIR, txt...) bị bỏ qua.
* Chọn series như s02 (pipeline/src/dicom/s02_select_convert.py), nhưng dựa trên header thay vì tên
  thư mục để chạy được với máy khác:
  - T2 = EchoTime > 60 ms, bỏ STIR / TIRM / FLAIR / TrueFISP / CISS (độ tương phản khác);
  - bỏ localizer và ảnh dẫn xuất (ImageType DERIVED: POSDISP, MPR...);
  - mặt cắt tính từ ImageOrientationPatient, chỉ lấy sagittal;
  - ưu tiên: study L-SPINE > trường nhìn >= 250 mm > tâm gần vùng ảnh axial (<= 100 mm) >
    nhiều lát nhất > chụp sau.
* Ghi NIfTI bằng chính build_volume() của s02 -> cùng hình học với 515 ca dùng để học ngưỡng.
* File DICOM giải nén vào thư mục tạm và bị XÓA ngay sau khi chuyển (header DICOM chứa thông tin
  cá nhân, NIfTI thì không). File trong zip được ghi với tên phẳng, không dùng đường dẫn trong zip
  -> không có lỗi zip-slip.

Lỗi: INVALID_ZIP (không đọc được / quá lớn), NO_DICOM (không có ảnh DICOM), NO_SAGITTAL_T2 (không
có series sagittal T2 phù hợp), CONVERSION_FAILED (không dựng được ảnh 3D).

Thử trên máy:  python ai/dicom_to_nifti.py <study.zip | thư_mục> <ảnh.nii.gz>
"""
import re
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd
import pydicom
import SimpleITK as sitk

SRC = Path(__file__).resolve().parents[1] / "pipeline" / "src"
sys.path.insert(0, str(SRC))
from dicom.s02_select_convert import MAX_SAG_AX_DIST_MM, MIN_SAG_FOV_MM, build_volume

MAX_UNZIPPED_MB = 2048     # một study thắt lưng ~20 MB; chặn zip bomb
MAX_FILES = 20000
MIN_T2_TE_MS = 60          # T2: TE dài; T1 / PD: TE ngắn
EXCLUDE_DESC = re.compile(r"stir|tirm|flair|trufi|ciss|localizer|scout|survey", re.I)


class ConvertError(Exception):
    """code: INVALID_ZIP | NO_DICOM | NO_SAGITTAL_T2 | CONVERSION_FAILED."""

    def __init__(self, code, message):
        super().__init__(message)
        self.code, self.message = code, message


def _extract(zip_path, dest):
    try:
        with zipfile.ZipFile(zip_path) as z:
            members = [m for m in z.infolist() if not m.is_dir()]
            if len(members) > MAX_FILES or sum(m.file_size for m in members) > MAX_UNZIPPED_MB * 2**20:
                raise ConvertError("INVALID_ZIP", f"Zip quá lớn (tối đa {MAX_FILES} file, {MAX_UNZIPPED_MB} MB)")
            for i, m in enumerate(members):
                with z.open(m) as src, open(dest / f"{i:06d}", "wb") as dst:
                    shutil.copyfileobj(src, dst)
    except (zipfile.BadZipFile, OSError) as e:
        raise ConvertError("INVALID_ZIP", f"Không đọc được file zip: {e}") from None
    return sorted(dest.iterdir())


def _header(f):
    try:
        d = pydicom.dcmread(f, stop_before_pixels=True)
        iop = [float(x) for x in d.ImageOrientationPatient]
        ipp = [float(x) for x in d.ImagePositionPatient]
        px = [float(x) for x in d.PixelSpacing]
        rows, cols = int(d.Rows), int(d.Columns)
    except Exception:            # không phải DICOM, hoặc không phải ảnh (DICOMDIR, SR...)
        return None
    te = d.get("EchoTime")
    # tọa độ z (đầu-chân, mm) của TÂM lát - cùng công thức s02 (tính từng file: khối axial nghiêng khác nhau)
    center_z = ipp[2] + rows / 2 * px[0] * iop[5] + cols / 2 * px[1] * iop[2]
    normal = np.cross(iop[:3], iop[3:])
    return {"file": f, "center_z": center_z, "pos": float(np.dot(ipp, normal)),
            "plane": "SAG COR AX".split()[int(np.argmax(np.abs(normal)))],
            "study_uid": str(d.get("StudyInstanceUID", "")),
            "study_desc": str(d.get("StudyDescription", "")), "series_uid": str(d.get("SeriesInstanceUID", "")),
            "series_number": int(d.get("SeriesNumber", 0) or 0), "desc": str(d.get("SeriesDescription", "")),
            "derived": "DERIVED" in [str(t).upper() for t in d.get("ImageType", [])],
            "te": float(te) if te not in (None, "") else np.nan,
            "rows": rows, "cols": cols, "px_row": px[0], "px_col": px[1], "iop": iop, "ipp": ipp,
            "orient_key": tuple(np.round(iop, 2))}


def _series(headers):
    """Mỗi (series, mặt cắt) 1 dòng, như series_table() của s02: thống kê trên MỌI file (series axial gồm
    nhiều khối nghiêng khác nhau); riêng file để dựng ảnh chỉ giữ hướng chiếm đa số (như jobs() của s02)."""
    rows = []
    for (study, uid, plane), g in pd.DataFrame(headers).groupby(["study_uid", "series_uid", "plane"]):
        h = g.iloc[0]
        main = g[g.orient_key == g.orient_key.value_counts().idxmax()]
        rows.append({"study_uid": study, "series_uid": uid, "plane": plane, "study_desc": h.study_desc,
                     "desc": h.desc, "series_number": h.series_number, "te": g.te.median(),
                     "derived": bool(g.derived.any()), "fov_mm": h.rows * h.px_row, "center_z": g.center_z.mean(),
                     "n_files": len(g), "n_slices": g.pos.round(1).nunique(), "files": list(main.file)})
    return pd.DataFrame(rows)


def _choose(st):
    t2 = st[(st.te > MIN_T2_TE_MS) & ~st.derived & ~st.desc.str.contains(EXCLUDE_DESC)]
    sag = t2[t2.plane == "SAG"].copy()
    if sag.empty:
        found = ", ".join(f"{r.desc or '?'} ({r.plane})" for r in st.itertuples())
        raise ConvertError("NO_SAGITTAL_T2", f"Không có series T2 sagittal. Có: {found}")
    ax = t2[t2.plane == "AX"]
    ax_z = (ax.center_z * ax.n_files).groupby(ax.study_uid).sum() / ax.n_files.groupby(ax.study_uid).sum()
    sag["lspine"] = sag.study_desc.str.upper().str.startswith("L-SPINE")
    sag["fov_ok"] = sag.fov_mm >= MIN_SAG_FOV_MM
    sag["dist_ax_mm"] = (sag.center_z - sag.study_uid.map(ax_z)).abs()
    sag["near_ax"] = sag.dist_ax_mm.fillna(0) <= MAX_SAG_AX_DIST_MM     # không có axial -> không xét
    sag = sag.sort_values(["lspine", "fov_ok", "near_ax", "n_slices", "series_number"], ascending=False)
    return sag.iloc[0], len(sag)


def convert(src, out_path):
    src, out_path = Path(src), Path(out_path)
    with tempfile.TemporaryDirectory() as tmp:
        files = [f for f in src.rglob("*") if f.is_file()] if src.is_dir() else _extract(src, Path(tmp))
        headers = [h for h in map(_header, files) if h]
        if not headers:
            raise ConvertError("NO_DICOM", f"Không có ảnh DICOM nào trong {len(files)} file")
        st = _series(headers)
        s, n_cand = _choose(st)
        try:
            vol, qc = build_volume(s.files)
        except Exception as e:
            raise ConvertError("CONVERSION_FAILED", f"Không dựng được ảnh 3D từ {s.desc}: {e}") from None
        out_path.parent.mkdir(parents=True, exist_ok=True)
        sitk.WriteImage(vol, str(out_path), useCompression=True)
    return {"series_description": s.desc, "series_number": int(s.series_number), "n_series": st.series_uid.nunique(),
            "n_sag_t2_candidates": n_cand, "fov_mm": round(float(s.fov_mm), 1),
            "dist_ax_mm": None if pd.isna(s.dist_ax_mm) else round(float(s.dist_ax_mm), 1),
            "n_slices": qc["n_slices"], "n_dup_dropped": qc["n_dup_dropped"], "gap_uniform": qc["gap_uniform"],
            "spacing_mm": [round(qc["sp_x"], 3), round(qc["sp_y"], 3), round(qc["sp_z"], 3)]}


if __name__ == "__main__":
    print(convert(sys.argv[1], sys.argv[2]))
