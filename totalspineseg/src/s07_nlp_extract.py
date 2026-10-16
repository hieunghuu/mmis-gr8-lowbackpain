# -*- coding: utf-8 -*-
"""S07 - Bước 5b: chạy bộ rule (nlp_rules.py) trên ghi chú bác sĩ.

Mặc định CHỈ chạy tập dev (435 ghi chú) - tập gold không được nhìn khi phát triển rule.
Dùng --all ở bước 5d (sau khi đã chốt rule) để chạy cả 515 ghi chú.

Đầu ra (hậu tố _dev hoặc _all):
  outputs/tables/5_nlp/nlp_findings_long_<tập>.csv   mỗi phát hiện 1 dòng
  outputs/tables/5_nlp/nlp_sentences_<tập>.csv       mỗi câu 1 dòng (tầng gán, số phát hiện)
  outputs/tables/5_nlp/nlp_unmatched_<tập>.csv       câu KHÔNG khớp bệnh nào -> đọc để bổ sung mẫu
  outputs/tables/5_nlp/nlp_typo_hits_<tập>.csv       số lần sửa từng lỗi chính tả

Chạy (từ thư mục totalspineseg/):  python src/s07_nlp_extract.py [--all]
"""
import re
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import REPORT_XLSX, T_NLP
import nlp_rules

# câu tiêu đề / không mang thông tin bệnh - không tính là "chưa khớp"
TRIVIAL = re.compile(r"^(?:l\.?s\.?s|lss|lumbo-?sacral|lumbar|l-?spine|mri|spine|of|\W)*"
                     r"(?:mri|study|spine)?\W*$")


def main():
    which = "all" if "--all" in sys.argv else "dev"
    d = pd.read_excel(REPORT_XLSX)
    d.columns = ["patient_id", "note"]
    d = d.dropna(subset=["note"])
    d["patient_id"] = d.patient_id.astype(int)
    split = pd.read_csv(T_NLP / "nlp_split.csv")
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

    fl.to_csv(T_NLP / f"nlp_findings_long_{which}.csv", index=False)
    sl.to_csv(T_NLP / f"nlp_sentences_{which}.csv", index=False)
    um.to_csv(T_NLP / f"nlp_unmatched_{which}.csv", index=False)
    pd.Series(nlp_rules.TYPO_HITS, name="n").rename_axis("pattern").to_csv(
        T_NLP / f"nlp_typo_hits_{which}.csv")

    print(f"=== Rule trên tập {which}: {d.patient_id.nunique()} ghi chú, {len(sl)} câu ===")
    print(f"Phát hiện: {len(fl)} dòng | khẳng định {fl.present.sum()} | phủ định {(~fl.present).sum()}")
    print(f"Câu chưa khớp bệnh nào (không tính tiêu đề): {len(um)} / {len(sl)}")
    print(f"Dòng có tầng kế thừa từ câu trước: {int(fl.level_inherited.sum())}")
    print(f"Sửa lỗi chính tả: {sum(nlp_rules.TYPO_HITS.values())} lần, {len(nlp_rules.TYPO_HITS)} mẫu")
    pos = fl[fl.present]
    tab = pd.DataFrame({
        "BN_khẳng_định": pos.groupby("finding").patient_id.nunique(),
        "BN_phủ_định": fl[~fl.present].groupby("finding").patient_id.nunique(),
    }).fillna(0).astype(int).sort_values("BN_khẳng_định", ascending=False)
    print("\nSố bệnh nhân theo bệnh:")
    print(tab.to_string())
    print("\nPhát hiện khẳng định theo tầng:")
    print(pos.level.value_counts().reindex(nlp_rules.VALID_LEVELS + ["UNSPEC"]).fillna(0)
          .astype(int).to_string())


if __name__ == "__main__":
    main()
