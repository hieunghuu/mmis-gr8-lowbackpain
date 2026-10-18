# -*- coding: utf-8 -*-
"""Đường dẫn và cấu hình dùng chung cho mọi script trong src/."""
import sys
from pathlib import Path

# In được tiếng Việt trên console Windows (mặc định cp1252)
try:
    sys.stdout.reconfigure(encoding="utf-8")
except AttributeError:
    pass

CODE = Path(__file__).resolve().parents[1]          # pipeline/
ROOT = CODE.parent                                   # gốc repo
DATA = ROOT / "data"           # Windows không phân biệt hoa/thường; Linux thì có
MRI_DIR = DATA / "MRI_Data" / "01_MRI_Data"
REPORT_XLSX = DATA / "Radiologists Report.xlsx"

OUTPUTS = CODE / "outputs"
TABLES = OUTPUTS / "tables"
FIGURES = OUTPUTS / "figures"
# bảng và hình chia theo nhóm, trùng tên thư mục con trong src/
T_DICOM, F_DICOM = TABLES / "dicom", FIGURES / "dicom"
T_SEG, F_SEG = TABLES / "segmentation", FIGURES / "segmentation"
T_NLP = TABLES / "nlp"
T_MEAS, F_MEAS = TABLES / "measurements", FIGURES / "measurements"
T_ANALYSIS, F_ANALYSIS = TABLES / "analysis", FIGURES / "analysis"
NIFTI = OUTPUTS / "nifti"
GOLD_DIR = CODE / "annotations"      # nhãn chuẩn vàng cho NLP (s06 tạo mẫu, s08 chấm)

for _d in (T_DICOM, T_SEG, T_NLP, T_MEAS, T_ANALYSIS,
           F_DICOM, F_SEG, F_MEAS, F_ANALYSIS, NIFTI):
    _d.mkdir(parents=True, exist_ok=True)

SEED = 2026
