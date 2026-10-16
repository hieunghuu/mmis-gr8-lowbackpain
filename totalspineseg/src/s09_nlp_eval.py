# -*- coding: utf-8 -*-
"""S09 - Bước 5d: chấm bộ rule NLP trên bộ gold và tạo nhãn cuối cho bước 8 (README mục 5.11).

Ba cách chấm:
  tầng - khẳng định       (patient, level, finding), present = TRUE        -> chỉ số chính
  bệnh nhân - khẳng định  (patient, finding) có ít nhất 1 dòng khẳng định
  bệnh nhân - phủ định    (patient, finding) có dòng phủ định và KHÔNG có dòng khẳng định
Không chấm nhãn other, none (rule không sinh hai nhãn này).

Đầu vào:  outputs/tables/5_nlp/nlp_findings_long_all.csv  (chạy trước: python src/s07_nlp_extract.py --all)
          data/gold/gold_labels_llm.csv
Đầu ra:   outputs/tables/5_nlp/nlp_eval_summary.csv      micro / macro theo từng cách chấm
          outputs/tables/5_nlp/nlp_eval_per_finding.csv  P / R / F1 từng bệnh
          outputs/tables/5_nlp/nlp_eval_errors.csv       mọi FP / FN ở mức tầng, kèm câu gốc
          outputs/tables/5_nlp/labels_level.csv          nhãn cuối theo tầng (515 ghi chú)
          outputs/tables/5_nlp/labels_patient.csv        nhãn cuối theo bệnh nhân

Chạy (từ thư mục totalspineseg/):  python src/s09_nlp_eval.py
"""
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import CODE, REPORT_XLSX, T_NLP

GOLD = CODE / "data" / "gold" / "gold_labels_llm.csv"
SKIP = {"other", "none"}
LEVELS = ["T12-L1", "L1-L2", "L2-L3", "L3-L4", "L4-L5", "L5-S1", "UNSPEC"]


def prf(tp, fp, fn):
    p = tp / (tp + fp) if tp + fp else float("nan")
    r = tp / (tp + fn) if tp + fn else float("nan")
    f = 2 * p * r / (p + r) if tp and (p + r) else (0.0 if tp + fp + fn else float("nan"))
    return p, r, f


def patient_status(df):
    """(patient, finding) -> 'affirmed' nếu có dòng khẳng định, ngược lại 'negated'."""
    g = df.groupby(["patient_id", "finding"]).present.any()
    return g.map({True: "affirmed", False: "negated"})


def score(gold_keys, pred_keys, findings, key_finding):
    """gold_keys, pred_keys: set các tuple; key_finding: hàm lấy tên bệnh từ tuple."""
    rows = []
    for f in findings:
        g = {k for k in gold_keys if key_finding(k) == f}
        p = {k for k in pred_keys if key_finding(k) == f}
        tp, fp, fn = len(g & p), len(p - g), len(g - p)
        rows.append({"finding": f, "gold": len(g), "pred": len(p), "tp": tp, "fp": fp, "fn": fn,
                     **dict(zip(["precision", "recall", "f1"], prf(tp, fp, fn)))})
    t = pd.DataFrame(rows)
    tp, fp, fn = t.tp.sum(), t.fp.sum(), t.fn.sum()
    micro = dict(zip(["precision", "recall", "f1"], prf(tp, fp, fn)))
    has_gold = t[t.gold > 0]
    macro = {m: has_gold[m].mean() for m in ["precision", "recall", "f1"]}
    return t, {"tp": tp, "fp": fp, "fn": fn, **{f"micro_{k}": v for k, v in micro.items()},
               **{f"macro_{k}": v for k, v in macro.items()}, "n_findings": len(has_gold)}


def final_labels(pred):
    """Nhãn cuối từ kết quả rule trên cả 515 ghi chú."""
    findings = sorted(pred.finding.unique())
    pos = pred[pred.present]
    lvl = (pos.assign(v=1).pivot_table(index=["patient_id", "level"], columns="finding",
                                       values="v", aggfunc="max", fill_value=0)
              .reindex(columns=findings, fill_value=0))
    neg = (pred[~pred.present].groupby(["patient_id", "level"]).size().rename("n_negated"))
    lvl = lvl.join(neg, how="outer").fillna(0).astype(int).reset_index()
    lvl["level"] = pd.Categorical(lvl.level, LEVELS, ordered=True)
    lvl = lvl.sort_values(["patient_id", "level"])

    notes = pd.read_excel(REPORT_XLSX)
    notes.columns = ["patient_id", "note"]
    all_ids = notes.dropna(subset=["note"]).patient_id.astype(int)
    pat = (pos.assign(v=1).pivot_table(index="patient_id", columns="finding", values="v",
                                        aggfunc="max", fill_value=0)
              .reindex(index=all_ids, columns=findings, fill_value=0))
    pat["n_findings"] = pat[findings].sum(axis=1)
    pat["normal_study"] = pat.n_findings == 0
    n_lv = pos[pos.level != "UNSPEC"].groupby("patient_id")["level"].nunique()
    pat["multilevel"] = n_lv.reindex(pat.index).fillna(0).astype(int) >= 2
    return lvl, pat.reset_index()


def main():
    pred = pd.read_csv(T_NLP / "nlp_findings_long_all.csv")
    gold = pd.read_csv(GOLD)
    gold = gold[~gold.finding.isin(SKIP)]
    gold_ids = set(gold.patient_id)
    pg = pred[pred.patient_id.isin(gold_ids)]
    findings = sorted(set(gold.finding) | set(pg.finding))

    # 1. tầng - khẳng định
    gk = set(map(tuple, gold[gold.present][["patient_id", "level", "finding"]].values))
    pk = set(map(tuple, pg[pg.present][["patient_id", "level", "finding"]].values))
    t_lvl, s_lvl = score(gk, pk, findings, lambda k: k[2])
    # 2-3. bệnh nhân - khẳng định / phủ định
    gs, ps = patient_status(gold), patient_status(pg)
    t_pa, s_pa = score({k for k, v in gs.items() if v == "affirmed"},
                       {k for k, v in ps.items() if v == "affirmed"}, findings, lambda k: k[1])
    t_pn, s_pn = score({k for k, v in gs.items() if v == "negated"},
                       {k for k, v in ps.items() if v == "negated"}, findings, lambda k: k[1])

    # độ đúng mức độ / bên trên các cặp khẳng định khớp ở mức tầng
    key = ["patient_id", "level", "finding"]
    m = (gold[gold.present].drop_duplicates(key)
         .merge(pg[pg.present].drop_duplicates(key), on=key, suffixes=("_gold", "_rule")))
    sev_acc = (m.severity_gold.fillna("unspecified") == m.severity_rule).mean()
    side_acc = (m.side_gold.fillna("unspecified") == m.side_rule).mean()

    summary = pd.DataFrame([{"scheme": "tầng – khẳng định", **s_lvl},
                            {"scheme": "bệnh nhân – khẳng định", **s_pa},
                            {"scheme": "bệnh nhân – phủ định", **s_pn}])
    summary["severity_acc"] = [sev_acc, None, None]
    summary["side_acc"] = [side_acc, None, None]
    summary.to_csv(T_NLP / "nlp_eval_summary.csv", index=False)
    per = pd.concat([t_lvl.assign(scheme="tầng – khẳng định"), t_pa.assign(scheme="bệnh nhân – khẳng định"),
                     t_pn.assign(scheme="bệnh nhân – phủ định")])
    per.to_csv(T_NLP / "nlp_eval_per_finding.csv", index=False)

    # lỗi ở mức tầng (khẳng định), kèm câu gốc
    notes = pd.read_excel(REPORT_XLSX)
    notes.columns = ["patient_id", "note"]
    notes = notes.dropna(subset=["note"]).assign(patient_id=lambda d: d.patient_id.astype(int))
    ev = pg[pg.present].drop_duplicates(key).set_index(key).evidence
    cm = gold[gold.present].drop_duplicates(key).set_index(key).comment
    err = ([{"type": "FP", "patient_id": k[0], "level": k[1], "finding": k[2],
             "rule_evidence": ev.get(k, ""), "gold_comment": ""} for k in sorted(pk - gk)]
           + [{"type": "FN", "patient_id": k[0], "level": k[1], "finding": k[2],
               "rule_evidence": "", "gold_comment": cm.get(k, "")} for k in sorted(gk - pk)])
    err = pd.DataFrame(err).merge(notes, on="patient_id", how="left")
    err.to_csv(T_NLP / "nlp_eval_errors.csv", index=False)

    lvl, pat = final_labels(pred)
    lvl.to_csv(T_NLP / "labels_level.csv", index=False)
    pat.to_csv(T_NLP / "labels_patient.csv", index=False)

    pd.set_option("display.width", 160)
    print(f"=== Bước 5d: chấm trên {len(gold_ids)} ghi chú gold ({len(gold)} dòng nhãn, bỏ other/none) ===")
    show = ["scheme", "tp", "fp", "fn", "micro_precision", "micro_recall", "micro_f1", "macro_f1"]
    print(summary[show].round(3).to_string(index=False))
    print(f"Cặp khẳng định khớp ở mức tầng: {len(m)} | đúng mức độ {sev_acc:.1%} | đúng bên {side_acc:.1%}")
    print("\nTầng – khẳng định, theo bệnh (có trong gold):")
    print(t_lvl[t_lvl.gold > 0].sort_values("gold", ascending=False)
          [["finding", "gold", "pred", "tp", "fp", "fn", "precision", "recall", "f1"]].round(3).to_string(index=False))
    print(f"\nLỗi mức tầng: FP {(err.type == 'FP').sum()} | FN {(err.type == 'FN').sum()} -> nlp_eval_errors.csv")
    print(f"Nhãn cuối: labels_level.csv {len(lvl)} dòng | labels_patient.csv {len(pat)} bệnh nhân "
          f"(bình thường {int(pat.normal_study.sum())}, nhiều tầng {int(pat.multilevel.sum())})")


if __name__ == "__main__":
    main()
