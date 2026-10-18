# -*- coding: utf-8 -*-
"""S11 - Học ngưỡng số đo -> gợi ý bệnh theo tầng từ ảnh, và kiểm chứng chéo.

Bệnh nhân mới chỉ có ảnh -> TotalSpineSeg -> số đo theo tầng -> so với ngưỡng học từ 513 bệnh
nhân -> "nghi <bệnh> tại <tầng>". Script này tạo bảng ngưỡng (quy tắc gợi ý) và đo xem ngưỡng
đúng đến đâu trên bệnh nhân CHƯA dùng để học.

* Hai loại ngưỡng cho mỗi cặp bệnh <-> số đo (danh sách cặp lấy từ s10):
  - riêng theo tầng: giá trị gốc tại một tầng, chỉ khi tầng đó có >= MIN_POS tầng có bệnh;
  - z chung: số đo chuẩn hóa z trong từng tầng, một ngưỡng dùng cho cả 6 tầng (cho các tầng
    trên, nơi quá ít ca có bệnh để học ngưỡng riêng).
* Ngưỡng = Youden (max độ nhạy + độ đặc hiệu - 1) trên phần dữ liệu học.
* Mỗi gợi ý chỉ dựa trên MỘT số đo, thứ duy nhất được học là ngưỡng -> AUC không phụ thuộc việc
  học (kiểm chứng chéo không đổi AUC). Vì vậy:
  - AUC báo cáo kèm khoảng tin cậy 95 % (bootstrap theo bệnh nhân, N_BOOT lần) - cặp ít ca bệnh
    có khoảng rộng;
  - kiểm chứng chéo 5 lần, lặp 5 lần, chia THEO BỆNH NHÂN (mọi tầng của một bệnh nhân cùng một
    phần) đo độ nhạy / độ đặc hiệu / PPV của NGƯỠNG đã học trên bệnh nhân chưa thấy. Trung bình /
    độ lệch chuẩn để tính z cũng chỉ lấy từ phần học (tránh rò rỉ dữ liệu).
* Cặp được dùng để gợi ý khi cận dưới khoảng tin cậy AUC >= MIN_AUC_LOW; độ tin cậy "cao" khi
  >= HIGH_AUC_LOW.

Đầu ra (outputs/tables/analysis/):
  threshold_rules.csv        ngưỡng cuối (học trên cả 513 BN) + số liệu kiểm chứng - bảng quy tắc gợi ý
  threshold_cv_by_level.csv  ngưỡng z chung: số liệu kiểm chứng tách theo từng tầng
  measure_reference.csv      trung bình, độ lệch chuẩn, phân vị của từng số đo theo tầng (tính z,
                             hiển thị "thấp hơn x % bệnh nhân cùng tầng")

Chạy (từ thư mục pipeline/):  python src/analysis/s11_threshold_rules.py
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score, roc_curve
from sklearn.model_selection import StratifiedGroupKFold

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))   # src/
from common import SEED, T_ANALYSIS
from analysis.s10_level_analysis import LEVELS, MEASURES, PAIRS, VN, build_dataset

MIN_POS = 10          # số tầng có bệnh tối thiểu để học ngưỡng riêng cho một tầng
MIN_AUC_LOW = 0.70    # cận dưới KTC 95 % của AUC tối thiểu để dùng cặp cho gợi ý
HIGH_AUC_LOW = 0.80   # từ mức này: độ tin cậy "cao"
N_SPLITS, N_REPEATS = 5, 5
N_BOOT = 1000
PCTS = [5, 10, 25, 50, 75, 90, 95]


def youden(y, s):
    """Ngưỡng trên điểm s (điểm cao = bệnh) tối đa J = độ nhạy + độ đặc hiệu - 1."""
    fpr, tpr, thr = roc_curve(y, s)
    j = int(np.argmax(tpr - fpr))
    return float(thr[j]), float(tpr[j]), float(1 - fpr[j])


def confusion(y, flag):
    tp = int((flag & (y == 1)).sum()); fn = int((~flag & (y == 1)).sum())
    fp = int((flag & (y == 0)).sum()); tn = int((~flag & (y == 0)).sum())
    return {"sens": tp / (tp + fn) if tp + fn else np.nan, "spec": tn / (tn + fp) if tn + fp else np.nan,
            "ppv": tp / (tp + fp) if tp + fp else np.nan, "flag_rate": (tp + fp) / len(y)}


def z_by_level(train, test, m):
    """z trong từng tầng, trung bình / độ lệch chuẩn chỉ lấy từ phần học."""
    st = train.groupby("level")[m].agg(["mean", "std"])
    zt = lambda d: (d[m] - d.level.map(st["mean"])) / d.level.map(st["std"])
    return zt(train), zt(test)


def score(d, label, m, direction, scope):
    """Bảng con (y, nhóm, tầng, giá trị) cho một cặp và một phạm vi."""
    d = d[d[m].notna()]
    if scope != "z_all":
        d = d[d.level == scope]
    return d[["patient_id", "level", label, m]].rename(columns={label: "y", m: "x"})


def cross_validate(d, label, m, direction, scope):
    """Gộp dự đoán trên phần kiểm tra cho mỗi lần lặp; trả về chỉ số trung bình + bảng dự đoán."""
    per_rep, preds = [], []
    for rep in range(N_REPEATS):
        cv = StratifiedGroupKFold(n_splits=N_SPLITS, shuffle=True, random_state=SEED + rep)
        out = []
        for tr_idx, te_idx in cv.split(d, d.y, groups=d.patient_id):
            tr, te = d.iloc[tr_idx].copy(), d.iloc[te_idx].copy()
            if scope == "z_all":
                tr["x"], te["x"] = z_by_level(tr.rename(columns={"x": m}), te.rename(columns={"x": m}), m)
            s_tr, s_te = direction * tr.x.values, direction * te.x.values
            thr, _, _ = youden(tr.y.values, s_tr)
            te = te.assign(s=s_te, flag=s_te >= thr, rep=rep)
            out.append(te)
        o = pd.concat(out)
        r = confusion(o.y.values, o.flag.values)
        r["auc"] = roc_auc_score(o.y, o.s)
        per_rep.append(r)
        preds.append(o)
    pr = pd.DataFrame(per_rep)
    res = {f"cv_{k}": pr[k].mean() for k in ["sens", "spec", "ppv", "flag_rate"]}
    res["cv_j"] = res["cv_sens"] + res["cv_spec"] - 1
    return res, pd.concat(preds)


def auc_ci(d, direction, scope, ref, m):
    """KTC 95 % của AUC: bootstrap theo bệnh nhân (giữ nguyên mọi tầng của bệnh nhân được bốc)."""
    x = d.x.values
    if scope == "z_all":
        x = ((d.x - d.level.map(ref.loc[m, "mean"])) / d.level.map(ref.loc[m, "std"])).values
    s, y, pids = direction * x, d.y.values, d.patient_id.values
    uniq = np.unique(pids)
    rows_of = {p: np.flatnonzero(pids == p) for p in uniq}
    rng = np.random.default_rng(SEED)
    aucs = []
    for _ in range(N_BOOT):
        idx = np.concatenate([rows_of[p] for p in rng.choice(uniq, len(uniq))])
        if 0 < y[idx].sum() < len(idx):
            aucs.append(roc_auc_score(y[idx], s[idx]))
    return np.percentile(aucs, [2.5, 97.5])


def fit_final(d, direction, scope, ref, m):
    """Ngưỡng cuối trên toàn bộ dữ liệu (giá trị gốc với ngưỡng theo tầng, z với ngưỡng chung)."""
    x = d.x.values
    if scope == "z_all":
        x = ((d.x - d.level.map(ref.loc[m, "mean"])) / d.level.map(ref.loc[m, "std"])).values
    s = direction * x
    thr, sens, spec = youden(d.y.values, s)
    return {"threshold": direction * thr, "auc_insample": roc_auc_score(d.y, s),
            "sens_insample": sens, "spec_insample": spec}


def reference(df):
    rows = []
    for m in MEASURES:
        for lv, g in df.groupby("level"):
            v = g[m].dropna()
            r = {"measure": m, "level": lv, "n": len(v), "mean": v.mean(), "std": v.std()}
            r.update({f"p{p}": np.percentile(v, p) for p in PCTS})
            rows.append(r)
    return pd.DataFrame(rows)


def main():
    df = build_dataset()
    ref = reference(df)
    ref_idx = ref.set_index(["measure", "level"])[["mean", "std"]]
    rows, by_level = [], []
    for label, m, direction, kind in PAIRS:
        scopes = [lv for lv in LEVELS if df.loc[df.level == lv, label].sum() >= MIN_POS] + ["z_all"]
        for scope in scopes:
            d = score(df, label, m, direction, scope)
            if d.y.sum() < MIN_POS:
                continue
            cv, preds = cross_validate(d, label, m, direction, scope)
            final = fit_final(d, direction, scope, ref_idx, m)
            final["auc_ci_low"], final["auc_ci_high"] = auc_ci(d, direction, scope, ref_idx, m)
            rows.append({"label": label, "label_vi": VN[label], "measure": m, "measure_vi": VN[m],
                         "direction": direction, "rule": "<=" if direction < 0 else ">=", "kind": kind,
                         "scope": scope, "threshold_unit": "z" if scope == "z_all" else "gốc",
                         "n_pos": int(d.y.sum()), "n_neg": int((d.y == 0).sum()), **final, **cv})
            if scope == "z_all":   # z chung: tách số liệu kiểm chứng theo tầng
                for lv, g in preds.groupby("level"):
                    reps = [confusion(gg.y.values, gg.flag.values) for _, gg in g.groupby("rep")]
                    r = pd.DataFrame(reps).mean()
                    by_level.append({"label": label, "measure": m, "level": lv,
                                     "n_pos": int(g.y.sum() / N_REPEATS), **{f"cv_{k}": r[k] for k in r.index}})
    th = pd.DataFrame(rows)
    th["use"] = th.auc_ci_low >= MIN_AUC_LOW
    th["confidence"] = np.where(th.auc_ci_low >= HIGH_AUC_LOW, "cao", np.where(th.use, "vừa", "không dùng"))
    th["optimism_j"] = th.sens_insample + th.spec_insample - 1 - th.cv_j
    th.to_csv(T_ANALYSIS / "threshold_rules.csv", index=False)
    pd.DataFrame(by_level).to_csv(T_ANALYSIS / "threshold_cv_by_level.csv", index=False)
    ref.to_csv(T_ANALYSIS / "measure_reference.csv", index=False)

    show = th[["label_vi", "measure_vi", "scope", "rule", "threshold", "n_pos", "auc_insample", "auc_ci_low",
               "cv_sens", "cv_spec", "cv_ppv", "optimism_j", "confidence"]]
    with pd.option_context("display.width", 200, "display.max_rows", 100):
        print(show.round(3).to_string(index=False))
    print(f"\n{int(th.use.sum())}/{len(th)} cặp đủ mạnh để gợi ý (cận dưới KTC 95 % của AUC >= {MIN_AUC_LOW}).")
    print("Đã lưu threshold_rules.csv, threshold_cv_by_level.csv, measure_reference.csv")


if __name__ == "__main__":
    main()
