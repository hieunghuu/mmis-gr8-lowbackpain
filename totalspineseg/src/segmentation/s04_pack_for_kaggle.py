# -*- coding: utf-8 -*-
"""S04 - Đóng gói ảnh NIfTI sagittal để upload lên Kaggle (chạy TotalSpineSeg trên GPU).

Lý do: trên CPU máy nhà TotalSpineSeg mất ~15 phút/ca (s03) -> 515 ca ~5 ngày.
Kaggle Notebook GPU nhanh hơn nhiều và miễn phí.

Đầu ra: outputs/kaggle/lumbar_sag_nifti.zip  (515 file 0001.nii.gz ... ở gốc zip)
Upload file zip này thành một Kaggle Dataset (PRIVATE), rồi chạy notebook
kaggle/tss_kaggle.ipynb. Hướng dẫn đầy đủ: kaggle/README.md

Chạy (từ thư mục totalspineseg/):  python src/segmentation/s04_pack_for_kaggle.py
"""
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))   # src/
from common import NIFTI, OUTPUTS

OUT = OUTPUTS / "kaggle" / "lumbar_sag_nifti.zip"


def main():
    files = sorted((NIFTI / "sag").glob("*.nii.gz"))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    # .nii.gz đã nén sẵn -> ZIP_STORED (không nén lại, nhanh hơn, kích thước như nhau)
    with zipfile.ZipFile(OUT, "w", compression=zipfile.ZIP_STORED) as z:
        for f in files:
            z.write(f, arcname=f.name)
    with zipfile.ZipFile(OUT) as z:
        names = z.namelist()
        bad = z.testzip()
    print(f"{len(names)} file -> {OUT} ({OUT.stat().st_size / 2**30:.2f} GB), "
          f"kiểm tra zip: {'OK' if bad is None else 'LỖI ' + bad}")


if __name__ == "__main__":
    main()
