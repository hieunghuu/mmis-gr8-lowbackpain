# -*- coding: utf-8 -*-
"""S06 - Buoc 5a: tach 80 ghi chu chuan vang (gold) + tao file Excel de nhom gan nhan.

* Moi ghi chu xep vao 1 nhom bang regex don gian, DOC LAP voi bo rule (uu tien tu tren
  xuong): uncommon (tu khoa benh it gap) > multi (>= 2 tang) > single (1 tang) > no_level.
* Lay mau phan tang THEO TI LE (seed 2026): 80 ghi chu chia dung ti le tung nhom.
* KHONG in noi dung ghi chu ra man hinh - giu tap gold "chua ai nhin" khi viet rule (5b).

Dau ra
  outputs/tables/nlp_split.csv        patient_id, stratum, split (dev / gold)
  data/gold/gold_annotation.xlsx      HuongDan / ViDu / Notes / Labels (+ sheet an Lists)

Chi tiet thiet ke: README muc 5.5 (quy uoc) va 5.7 (chia du lieu).
Chay (tu thu muc totalspineseg/):  python src/s06_gold_sample.py
"""
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.worksheet.datavalidation import DataValidation

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import CODE, REPORT_XLSX, TABLES, SEED

GOLD_DIR = CODE / "data" / "gold"
N_GOLD = 80

LEVEL_RE = re.compile(r"\b(?:t12|l[1-5])\s*[-/ ]\s*(?:l?[1-5]|s1?)\b", re.I)
UNCOMMON_RE = re.compile(
    r"listhesis|schmorl|modic|end.?plate|ha?emangioma|marrow|tarlov|fracture|wedg|sequest|"
    r"extru|facet|flavum|scolio|annul|tear|desicca|dehydrat|osteophyt|cyst", re.I)

LEVELS = ["T12-L1", "L1-L2", "L2-L3", "L3-L4", "L4-L5", "L5-S1", "UNSPEC"]
VERTEBRAE = ["", "T12", "L1", "L2", "L3", "L4", "L5", "S1"]
FINDINGS = ["disc_bulge", "disc_protrusion", "disc_herniation", "thecal_sac_compression",
            "nerve_root_compression", "foraminal_stenosis", "spinal_canal_stenosis",
            "annular_tear", "disc_desiccation", "muscle_spasm", "spondylolisthesis",
            "endplate_degeneration", "schmorl_nodes", "bone_marrow_lesion",
            "ligamentum_flavum_hypertrophy", "facet_arthropathy", "scoliosis",
            "tarlov_cyst", "vertebral_fracture", "osteophyte", "disc_space_narrowing",
            "other", "none"]
PRESENT = ["TRUE", "FALSE"]
SEVERITY = ["unspecified", "mild", "moderate", "severe"]
SIDE = ["unspecified", "left", "right", "bilateral", "central"]
COLS = ["patient_id", "level", "vertebra", "root", "finding", "present", "severity", "side", "comment"]

# Vi du gan nhan mau - lay ghi chu dau tien trong danh sach thuoc TAP DEV
EXAMPLES = {
    4: [("UNSPEC", "", "", "muscle_spasm", "TRUE", "unspecified", "unspecified", "Q7: khong nhac tang"),
        ("L4-L5", "", "", "disc_bulge", "TRUE", "unspecified", "unspecified", "1 menh de nhac 2 tang -> gan ca 2"),
        ("L4-L5", "", "", "thecal_sac_compression", "TRUE", "mild", "unspecified", "mildly compressing"),
        ("L4-L5", "", "", "nerve_root_compression", "TRUE", "unspecified", "bilateral", "Q2 encroaching; Q11 so nhieu"),
        ("L5-S1", "", "", "disc_bulge", "TRUE", "unspecified", "unspecified", ""),
        ("L5-S1", "", "", "thecal_sac_compression", "TRUE", "mild", "unspecified", ""),
        ("L5-S1", "", "", "nerve_root_compression", "TRUE", "unspecified", "bilateral", "")],
    1: [("L4-L5", "", "", "disc_bulge", "TRUE", "unspecified", "left", "more to the left side"),
        ("L4-L5", "", "", "thecal_sac_compression", "TRUE", "unspecified", "unspecified", ""),
        ("L4-L5", "", "", "nerve_root_compression", "TRUE", "unspecified", "left", "left nerve root"),
        ("L4-L5", "", "", "foraminal_stenosis", "TRUE", "unspecified", "right", "narrowing right neural foramen"),
        ("L4-L5", "", "", "annular_tear", "TRUE", "unspecified", "left", "ke thua tang L4-L5 tu cau truoc")],
}

GUIDE = [
    "HUONG DAN GAN NHAN BO CHUAN VANG (gold) - 80 ghi chu",
    "",
    "1. Doc tung ghi chu o sheet Notes. Moi PHAT HIEN duoc nhac -> 1 dong o sheet Labels.",
    "2. Ghi ca phat hien BI PHU DINH (vd 'No evidence of disc herniation') voi present = FALSE.",
    "3. Ghi chu khong co phat hien nao -> 1 dong finding = none.",
    "4. Mot menh de nhac nhieu tang (vd 'at L4/L5 & L5/S1') -> moi tang 1 dong.",
    "5. Cau khong co tang nhung noi tiep cau truoc co tang -> dung tang cua cau truoc.",
    "6. Khong co tang nao -> level = UNSPEC.",
    "7. Dot don le: 'Lt S1 nerve root' -> cot root = S1 (khong phai tang);",
    "   'L2 vertebral body' -> cot vertebra = L2, level = UNSPEC (tru khi menh de co tang dia).",
    "8. Chon gia tri tu danh sach tha xuong (khong go tay) cho level, finding, present, severity, side.",
    "9. Phan van -> van ghi, them giai thich o cot comment.",
    "10. Gan nhan DOC LAP: 2 nguoi gan rieng (gold_labels_A.xlsx, gold_labels_B.xlsx), khong trao doi",
    "    truoc khi xong; sau do so sanh, ban va thong nhat thanh gold_labels_final.xlsx.",
    "",
    "QUY UOC (giong README muc 5.5):",
    "Q1  'abutting' (cham) thecal sac / nerve root -> KHONG phai chen ep (present = FALSE).",
    "Q2  'encroaching (exit) nerve roots' -> nerve_root_compression = TRUE.",
    "Q3  'sequestrated / extruded disc fragment' -> disc_herniation = TRUE.",
    "Q4  'protrusion on top of disc bulge' -> ghi CA HAI disc_protrusion va disc_bulge.",
    "Q5  'compressing ... exit canal' -> foraminal_stenosis = TRUE.",
    "Q6  'adequate spinal canal' -> spinal_canal_stenosis, present = FALSE.",
    "Q7  Khong nhac tang -> UNSPEC.",
    "Q8  'multilevel ... noticeably at L3-L4 & L4-L5' -> chi ghi cac tang duoc neu ten.",
    "Q9  Tang dung de dinh vi ('below L4/L5 level') -> ghi tang dia duoc neu.",
    "Q10 Tang khong duoc nhac -> khong ghi gi (khong tu suy dien la binh thuong).",
    "Q11 'nerve roots' / 'exit nerve roots' (so nhieu) khong noi ben -> side = bilateral.",
    "",
    "MUC DO: mild/mildly/minimal/small -> mild; moderate; severe/significant/marked -> severe; khong co -> unspecified.",
    "BEN: left/lt; right/rt; both/bilateral; central/median; khong co -> unspecified.",
    "",
    "NHAN (finding): " + ", ".join(FINDINGS),
    "  other = phat hien khong thuoc danh sach (ghi ro trong comment).",
]


def stratify(notes):
    n_lv = notes.apply(lambda s: len({m.lower().replace(" ", "") for m in LEVEL_RE.findall(s)}))
    st = pd.Series("single", index=notes.index)
    st[n_lv == 0] = "no_level"
    st[n_lv >= 2] = "multi"
    st[notes.str.contains(UNCOMMON_RE)] = "uncommon"
    return st


def allocate(sizes, n):
    """Chia n theo ti le (phuong phap so du lon nhat)."""
    raw = sizes / sizes.sum() * n
    alloc = np.floor(raw).astype(int)
    for k in (raw - alloc).sort_values(ascending=False).index[: n - alloc.sum()]:
        alloc[k] += 1
    return alloc


def sheet_table(ws, header, rows, widths):
    ws.append(header)
    for c in ws[1]:
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = PatternFill("solid", fgColor="44546A")
    for r in rows:
        ws.append(list(r))
    for col, w in zip("ABCDEFGHI", widths):
        ws.column_dimensions[col].width = w
    for row in ws.iter_rows(min_row=2):
        for c in row:
            c.alignment = Alignment(wrap_text=True, vertical="top")
    ws.freeze_panes = "A2"


def build_workbook(gold, example_pid, example_note):
    wb = Workbook()
    ws = wb.active
    ws.title = "HuongDan"
    for line in GUIDE:
        ws.append([line])
    ws["A1"].font = Font(bold=True, size=13)
    ws.column_dimensions["A"].width = 120

    ws = wb.create_sheet("ViDu")
    ws.append([f"Ghi chu mau (BN {example_pid}, thuoc tap DEV - khong nam trong 80 ghi chu gold):"])
    ws.append([example_note])
    ws["A2"].alignment = Alignment(wrap_text=True)
    ws.row_dimensions[2].height = 75
    ws.append([])
    ws.append(COLS)
    for c in ws[4]:
        c.font = Font(bold=True)
    for r in EXAMPLES[example_pid]:
        ws.append([example_pid, *r])
    for col, w in zip("ABCDEFGHI", [11, 9, 9, 7, 28, 9, 12, 12, 45]):
        ws.column_dimensions[col].width = w

    ws = wb.create_sheet("Notes")
    sheet_table(ws, ["patient_id", "note"], gold[["patient_id", "note"]].itertuples(index=False),
                [11, 110])

    lists = wb.create_sheet("Lists")
    for j, vals in enumerate([LEVELS, VERTEBRAE, FINDINGS, PRESENT, SEVERITY, SIDE]):
        for i, v in enumerate(vals, 1):
            lists.cell(row=i, column=j + 1, value=v)
    lists.sheet_state = "hidden"

    ws = wb.create_sheet("Labels")
    sheet_table(ws, COLS, [], [11, 9, 9, 7, 28, 9, 12, 12, 45])
    n_rows = 1000
    dv_specs = [("A", None), ("B", ("A", len(LEVELS))), ("C", ("B", len(VERTEBRAE))),
                ("E", ("C", len(FINDINGS))), ("F", ("D", len(PRESENT))),
                ("G", ("E", len(SEVERITY))), ("H", ("F", len(SIDE)))]
    for col, src in dv_specs:
        if src is None:   # patient_id: chi cho chon dung 80 ma o sheet Notes
            dv = DataValidation(type="list", formula1=f"=Notes!$A$2:$A${len(gold) + 1}",
                                allow_blank=True)
        else:
            lc, n = src
            dv = DataValidation(type="list", formula1=f"=Lists!${lc}$1:${lc}${n}", allow_blank=True)
        dv.error, dv.errorTitle = "Gia tri khong hop le - chon tu danh sach", "Loi nhap"
        ws.add_data_validation(dv)
        dv.add(f"{col}2:{col}{n_rows}")
    wb.move_sheet("Labels", offset=-1)          # Labels dung truoc Lists (an)
    return wb


def main():
    d = pd.read_excel(REPORT_XLSX)
    d.columns = ["patient_id", "note"]
    d = d.dropna(subset=["note"]).reset_index(drop=True)
    d["patient_id"] = d.patient_id.astype(int)
    d["stratum"] = stratify(d.note.astype(str))

    sizes = d.stratum.value_counts()
    alloc = allocate(sizes, N_GOLD)
    rng = np.random.default_rng(SEED)
    gold_ids = []
    for s, k in alloc.items():
        ids = d.loc[d.stratum == s, "patient_id"].to_numpy()
        gold_ids += rng.choice(ids, size=k, replace=False).tolist()
    d["split"] = np.where(d.patient_id.isin(gold_ids), "gold", "dev")
    d[["patient_id", "stratum", "split"]].sort_values("patient_id").to_csv(
        TABLES / "nlp_split.csv", index=False)

    example_pid = next(p for p in EXAMPLES if p in set(d.loc[d.split == "dev", "patient_id"]))
    example_note = d.loc[d.patient_id == example_pid, "note"].iloc[0]
    gold = d[d.split == "gold"].sort_values("patient_id")
    GOLD_DIR.mkdir(parents=True, exist_ok=True)
    out = GOLD_DIR / "gold_annotation.xlsx"
    build_workbook(gold, example_pid, example_note).save(out)

    print("=== Buoc 5a ===")
    print(pd.DataFrame({"so_ghi_chu": sizes, "lay_vao_gold": alloc}).to_string())
    print(f"dev: {(d.split == 'dev').sum()} | gold: {(d.split == 'gold').sum()}")
    neg = d.note.str.contains(r"\bno\b|without|\bnot\b", case=False, regex=True)
    print(f"Gold co cau phu dinh: {int((neg & (d.split == 'gold')).sum())} / {N_GOLD}")
    print(f"Vi du mau: BN {example_pid} (tap dev)")
    print(f"Da ghi {TABLES / 'nlp_split.csv'}")
    print(f"Da ghi {out}")


if __name__ == "__main__":
    main()
