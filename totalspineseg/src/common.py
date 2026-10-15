# -*- coding: utf-8 -*-
"""Duong dan va cau hinh dung chung cho moi script trong src/."""
import sys
from pathlib import Path

# In duoc tieng Viet tren console Windows (mac dinh cp1252)
try:
    sys.stdout.reconfigure(encoding="utf-8")
except AttributeError:
    pass

CODE = Path(__file__).resolve().parents[1]          # Assignment/Code
ROOT = CODE.parent                                   # Assignment
DATA = ROOT / "Data"
MRI_DIR = DATA / "MRI_Data" / "01_MRI_Data"
REPORT_XLSX = DATA / "Radiologists Report.xlsx"

OUTPUTS = CODE / "outputs"
TABLES = OUTPUTS / "tables"
FIGURES = OUTPUTS / "figures"
NIFTI = OUTPUTS / "nifti"

for _d in (TABLES, FIGURES, NIFTI):
    _d.mkdir(parents=True, exist_ok=True)

SEED = 2026
