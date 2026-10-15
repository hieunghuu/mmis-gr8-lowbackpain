# -*- coding: utf-8 -*-
"""S07 - Buoc 5b: chay bo rule (nlp_rules.py) tren ghi chu bac si.

Mac dinh CHI chay tap dev (435 ghi chu) - tap gold khong duoc nhin khi phat trien rule.
Dung --all o buoc 5d (sau khi da chot rule) de chay ca 515 ghi chu.

Dau ra (hau to _dev hoac _all):
  outputs/tables/nlp_findings_long_<tap>.csv   moi phat hien 1 dong
  outputs/tables/nlp_sentences_<tap>.csv       moi cau 1 dong (tang gan, so phat hien)
  outputs/tables/nlp_unmatched_<tap>.csv       cau KHONG khop benh nao -> doc de bo sung mau
  outputs/tables/nlp_typo_hits_<tap>.csv       so lan sua tung loi chinh ta

Chay (tu thu muc totalspineseg/):  python src/s07_nlp_extract.py [--all]
"""
import re
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import REPORT_XLSX, TABLES
import nlp_rules

# cau tieu de / khong mang thong tin benh - khong tinh la "chua khop"
TRIVIAL = re.compile(r"^(?:l\.?s\.?s|lss|lumbo-?sacral|lumbar|l-?spine|mri|spine|of|\W)*"
                     r"(?:mri|study|spine)?\W*$")


def main():
    which = "all" if "--all" in sys.argv else "dev"
    d = pd.read_excel(REPORT_XLSX)
    d.columns = ["patient_id", "note"]
    d = d.dropna(subset=["note"])
    d["patient_id"] = d.patient_id.astype(int)
    split = pd.read_csv(TABLES / "nlp_split.csv")
    d = d.merge(split, on="patient_id")
    if which == "dev":
        d = d[d.split == "dev"]

    rows, sents = [], []
    for r in d.itertuples():
        fs, ss = nlp_rules.extract(r.note)
        rows += [{"patient_id": r.patient_id, **f} for f in fs]
        sents += [{"patient_id": r.patient_id, **s} for s in ss]
    fl, sl = pd.DataFrame(rows), pd.DataFrame(sents)
    um = sl[(sl.n_findings == 0) & ~sl.text.str.match(TRIVIAL)]

    fl.to_csv(TABLES / f"nlp_findings_long_{which}.csv", index=False)
    sl.to_csv(TABLES / f"nlp_sentences_{which}.csv", index=False)
    um.to_csv(TABLES / f"nlp_unmatched_{which}.csv", index=False)
    pd.Series(nlp_rules.TYPO_HITS, name="n").rename_axis("pattern").to_csv(
        TABLES / f"nlp_typo_hits_{which}.csv")

    print(f"=== Rule tren tap {which}: {d.patient_id.nunique()} ghi chu, {len(sl)} cau ===")
    print(f"Phat hien: {len(fl)} dong | khang dinh {fl.present.sum()} | phu dinh {(~fl.present).sum()}")
    print(f"Cau chua khop benh nao (khong tinh tieu de): {len(um)} / {len(sl)}")
    print(f"Dong co tang ke thua tu cau truoc: {int(fl.level_inherited.sum())}")
    print(f"Sua loi chinh ta: {sum(nlp_rules.TYPO_HITS.values())} lan, {len(nlp_rules.TYPO_HITS)} mau")
    pos = fl[fl.present]
    tab = pd.DataFrame({
        "BN_khang_dinh": pos.groupby("finding").patient_id.nunique(),
        "BN_phu_dinh": fl[~fl.present].groupby("finding").patient_id.nunique(),
    }).fillna(0).astype(int).sort_values("BN_khang_dinh", ascending=False)
    print("\nSo benh nhan theo benh:")
    print(tab.to_string())
    print("\nPhat hien khang dinh theo tang:")
    print(pos.level.value_counts().reindex(nlp_rules.VALID_LEVELS + ["UNSPEC"]).fillna(0)
          .astype(int).to_string())


if __name__ == "__main__":
    main()
