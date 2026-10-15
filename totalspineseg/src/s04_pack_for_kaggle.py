# -*- coding: utf-8 -*-
"""S04 - Dong goi anh NIfTI sagittal de upload len Kaggle (chay TotalSpineSeg tren GPU).

Ly do: tren CPU may nha TotalSpineSeg mat ~15 phut/ca (s03) -> 515 ca ~5 ngay.
Kaggle Notebook GPU nhanh hon nhieu va mien phi.

Dau ra: outputs/kaggle/lumbar_sag_nifti.zip  (515 file 0001.nii.gz ... o goc zip)
Upload file zip nay thanh mot Kaggle Dataset (PRIVATE), roi chay notebook
kaggle/tss_kaggle.ipynb. Huong dan day du: kaggle/README.md

Chay (tu thu muc totalspineseg/):  python src/s04_pack_for_kaggle.py
"""
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import NIFTI, OUTPUTS

OUT = OUTPUTS / "kaggle" / "lumbar_sag_nifti.zip"


def main():
    files = sorted((NIFTI / "sag").glob("*.nii.gz"))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    # .nii.gz da nen san -> ZIP_STORED (khong nen lai, nhanh hon, kich thuoc nhu nhau)
    with zipfile.ZipFile(OUT, "w", compression=zipfile.ZIP_STORED) as z:
        for f in files:
            z.write(f, arcname=f.name)
    with zipfile.ZipFile(OUT) as z:
        names = z.namelist()
        bad = z.testzip()
    print(f"{len(names)} file -> {OUT} ({OUT.stat().st_size / 2**30:.2f} GB), "
          f"kiem tra zip: {'OK' if bad is None else 'LOI ' + bad}")


if __name__ == "__main__":
    main()
