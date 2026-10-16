# -*- coding: utf-8 -*-
"""Đường dẫn và cấu hình dùng chung cho mọi script trong src/."""
import sys
from pathlib import Path

# In được tiếng Việt trên console Windows (mặc định cp1252)
try:
    sys.stdout.reconfigure(encoding="utf-8")
except AttributeError:
    pass

CODE = Path(__file__).resolve().parents[1]          # totalspineseg/
ROOT = CODE.parent                                   # gốc repo
DATA = ROOT / "data"           # Windows không phân biệt hoa/thường; Linux thì có
MRI_DIR = DATA / "MRI_Data" / "01_MRI_Data"
REPORT_XLSX = DATA / "Radiologists Report.xlsx"

OUTPUTS = CODE / "outputs"
TABLES = OUTPUTS / "tables"
# bảng kết quả chia theo bước của pipeline
T_DICOM = TABLES / "1_dicom"
T_SEG = TABLES / "3_segmentation"
T_NLP = TABLES / "5_nlp"
T_MEAS = TABLES / "7_measurements"
T_ANALYSIS = TABLES / "8_analysis"
FIGURES = OUTPUTS / "figures"
NIFTI = OUTPUTS / "nifti"

for _d in (T_DICOM, T_SEG, T_NLP, T_MEAS, T_ANALYSIS, FIGURES, NIFTI):
    _d.mkdir(parents=True, exist_ok=True)

SEED = 2026
