# -*- coding: utf-8 -*-
"""S10 - Bước 8: ghép số đo ảnh (bước 7) với nhãn văn bản (bước 5d) và phân tích (README mục 8).

* Bảng ghép: (patient_id, level) của 513 ca use_level x 6 tầng; tầng không có trong bảng nhãn
  -> mọi bệnh = 0 ("không được nhắc", nhãn yếu - Q10).
* Mỗi số đo chuẩn hóa z TRONG TỪNG TẦNG trước khi gộp (tầng khác nhau sẵn về kích thước, mà
  bệnh lại tập trung ở L4-L5, L5-S1).
* Mỗi cặp số đo <-> nhãn: trung vị, AUC theo chiều kỳ vọng, Mann-Whitney, ngưỡng Youden.
* Ca lệch (trong cùng tầng): "nghi bỏ sót" = không ghi nhưng bất thường hơn trung vị nhóm có
  ghi; "số đo không ủng hộ" = có ghi nhưng bình thường hơn trung vị nhóm không ghi.

Chạy (từ thư mục pipeline/):  python src/analysis/s10_level_analysis.py
"""
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.stats import mannwhitneyu, spearmanr
from sklearn.metrics import roc_auc_score, roc_curve

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))   # src/
from common import F_ANALYSIS, T_ANALYSIS, T_MEAS, T_NLP, T_SEG

LEVELS = ["T12-L1", "L1-L2", "L2-L3", "L3-L4", "L4-L5", "L5-S1"]
MAIN_LEVELS = ["L4-L5", "L5-S1"]
LUMBAR = ["L1-L2", "L2-L3", "L3-L4", "L4-L5", "L5-S1"]
MEASURES = ["disc_height_mm", "dhi", "disc_csf_ratio", "disc_vb_ratio", "disc_post_bulge_mm",
            "canal_ap_mm", "canal_csa_approx_mm2", "listhesis_mm"]

# (nhãn, số đo, chiều kỳ vọng ở tầng có bệnh: -1 thấp hơn / +1 cao hơn, nhóm)
PAIRS = [
    ("disc_desiccation", "disc_csf_ratio", -1, "trực tiếp"),
    ("disc_desiccation", "disc_vb_ratio", -1, "trực tiếp"),
    ("disc_space_narrowing", "dhi", -1, "trực tiếp"),
    ("disc_space_narrowing", "disc_height_mm", -1, "trực tiếp"),
    ("disc_displacement", "disc_post_bulge_mm", +1, "trực tiếp"),
    ("disc_bulge", "disc_post_bulge_mm", +1, "trực tiếp"),
    ("disc_protrusion", "disc_post_bulge_mm", +1, "trực tiếp"),
    ("disc_herniation", "disc_post_bulge_mm", +1, "trực tiếp"),
    ("thecal_sac_compression", "canal_ap_mm", -1, "trực tiếp"),
    ("thecal_sac_compression", "canal_csa_approx_mm2", -1, "trực tiếp"),
    ("spinal_canal_stenosis", "canal_ap_mm", -1, "trực tiếp"),
    ("spinal_canal_stenosis", "canal_csa_approx_mm2", -1, "trực tiếp"),
    ("spondylolisthesis", "listhesis_mm", +1, "trực tiếp"),
    ("foraminal_stenosis", "disc_post_bulge_mm", +1, "gián tiếp"),
    ("foraminal_stenosis", "dhi", -1, "gián tiếp"),
    ("nerve_root_compression", "disc_post_bulge_mm", +1, "gián tiếp"),
]
# cặp chính cho hình và cho phân tích ca lệch
MAIN_PAIRS = [("disc_desiccation", "disc_csf_ratio", -1), ("disc_space_narrowing", "dhi", -1),
              ("disc_displacement", "disc_post_bulge_mm", +1), ("thecal_sac_compression", "canal_ap_mm", -1),
              ("spondylolisthesis", "listhesis_mm", +1)]
# cặp cho biểu đồ ROC: bỏ trượt đốt (số đo ở L5-S1 không dùng được - xem README mục 8)
ROC_PAIRS = [("disc_desiccation", "disc_csf_ratio", -1), ("disc_space_narrowing", "dhi", -1),
             ("disc_displacement", "disc_post_bulge_mm", +1), ("spinal_canal_stenosis", "canal_ap_mm", -1),
             ("thecal_sac_compression", "canal_ap_mm", -1)]
VN = {"disc_desiccation": "Mất nước đĩa", "disc_space_narrowing": "Hẹp khoang đĩa",
      "disc_displacement": "Phồng / lồi / thoát vị", "disc_bulge": "Phồng đĩa", "disc_protrusion": "Lồi đĩa",
      "disc_herniation": "Thoát vị đĩa", "thecal_sac_compression": "Chèn ép bao màng cứng",
      "spinal_canal_stenosis": "Hẹp ống sống", "spondylolisthesis": "Trượt đốt sống",
      "foraminal_stenosis": "Hẹp lỗ liên hợp", "nerve_root_compression": "Chèn ép rễ",
      "disc_csf_ratio": "tín hiệu đĩa / DNT", "disc_vb_ratio": "tín hiệu đĩa / thân đốt", "dhi": "DHI",
      "disc_height_mm": "chiều cao đĩa (mm)", "disc_post_bulge_mm": "nhô sau (mm)",
      "canal_ap_mm": "ống sống trước–sau (mm)", "canal_csa_approx_mm2": "diện tích ống sống (mm²)",
      "listhesis_mm": "độ trượt (mm)"}

# Bảng màu (đã kiểm tra bằng validate_palette.js): nhóm không ghi / có ghi; 5 màu cho ROC
C_NO, C_YES = "#2a78d6", "#eb6834"
SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4"]
INK, INK2, GRID, SURFACE = "#0b0b0b", "#52514e", "#e6e5e1", "#fcfcfb"


def build_dataset():
    lf = pd.read_csv(T_MEAS / "level_features.csv")
    lf = lf[lf.use_level & lf.level.isin(LEVELS)].copy()
    lab = pd.read_csv(T_NLP / "labels_level.csv")
    findings = [c for c in lab.columns if c not in ("patient_id", "level", "n_negated")]
    df = lf.merge(lab, on=["patient_id", "level"], how="left")
    df[findings] = df[findings].fillna(0).astype(int)
    df["disc_displacement"] = df[["disc_bulge", "disc_protrusion", "disc_herniation"]].max(axis=1)
    for m in MEASURES:   # z trong từng tầng
        g = df.groupby("level")[m]
        df[m + "_z"] = (df[m] - g.transform("mean")) / g.transform("std")
    return df


def assoc_row(y, x, direction):
    ok = ~np.isnan(x)
    y, x = y[ok], x[ok]
    n_pos, n_neg = int(y.sum()), int((1 - y).sum())
    if n_pos < 5 or n_neg < 5:
        return None
    s = direction * x
    auc = roc_auc_score(y, s)
    p = mannwhitneyu(x[y == 1], x[y == 0], alternative="two-sided").pvalue
    fpr, tpr, thr = roc_curve(y, s)
    j = np.argmax(tpr - fpr)
    return {"n_pos": n_pos, "n_neg": n_neg, "median_pos": float(np.median(x[y == 1])),
            "median_neg": float(np.median(x[y == 0])), "auc": auc, "p_value": p,
            "youden_threshold": float(direction * thr[j]), "sensitivity": tpr[j], "specificity": 1 - fpr[j]}


def associations(df):
    rows = []
    for label, m, d, kind in PAIRS:
        scopes = [("gộp 6 tầng (z)", df, m + "_z")] + [(lv, df[df.level == lv], m) for lv in MAIN_LEVELS]
        for scope, sub, col in scopes:
            r = assoc_row(sub[label].to_numpy(), sub[col].to_numpy(dtype=float), d)
            if r:
                if scope.startswith("gộp"):   # ngưỡng trên thang z không có ý nghĩa lâm sàng
                    r["youden_threshold"] = np.nan
                rows.append({"label": label, "measure": m, "direction": d, "kind": kind, "scope": scope, **r})
    return pd.DataFrame(rows)


MIN_AUC_DISCORD = 0.7   # chỉ xét ca lệch ở tầng mà số đo thực sự phân biệt được


def discordance(df):
    """Ca lệch trong cùng tầng. Bỏ qua 'nghi bỏ sót' nếu bác sĩ đã ghi bệnh đó ở UNSPEC (không nói
    tầng, vd "dissicating disc material"); chỉ xét tầng có AUC >= MIN_AUC_DISCORD."""
    lab = pd.read_csv(T_NLP / "labels_level.csv")
    lab["disc_displacement"] = lab[["disc_bulge", "disc_protrusion", "disc_herniation"]].max(axis=1)
    unspec = lab[lab.level == "UNSPEC"].set_index("patient_id")
    rows, detail = [], []
    for label, m, d in MAIN_PAIRS:
        noted_unspec = set(unspec.index[unspec[label] == 1]) if label in unspec else set()
        for lv in LEVELS:
            sub = df[(df.level == lv) & df[m].notna()]
            pos, neg = sub[sub[label] == 1], sub[sub[label] == 0]
            if len(pos) < 5:
                continue
            auc = roc_auc_score(sub[label], d * sub[m])
            med_pos, med_neg = pos[m].median(), neg[m].median()
            neg_eval = neg[~neg.patient_id.isin(noted_unspec)]
            missed = neg_eval[d * neg_eval[m] > d * med_pos]
            unsup = pos[d * pos[m] < d * med_neg]
            valid = auc >= MIN_AUC_DISCORD
            if not valid:
                missed, unsup = missed.iloc[0:0], unsup.iloc[0:0]
            rows.append({"label": label, "measure": m, "level": lv, "level_auc": auc, "valid": valid,
                         "n_unspec_excluded": len(neg) - len(neg_eval),
                         "n_labeled": len(pos), "n_unlabeled": len(neg_eval),
                         "median_labeled": med_pos, "median_unlabeled": med_neg,
                         "suspect_missed": len(missed),
                         "suspect_missed_pct_of_unlabeled": 100 * len(missed) / len(neg_eval) if valid else np.nan,
                         "unsupported": len(unsup),
                         "unsupported_pct_of_labeled": 100 * len(unsup) / len(pos) if valid else np.nan})
            detail += [{"type": "nghi bỏ sót", "label": label, "measure": m, "level": lv,
                        "patient_id": r.patient_id, "value": r[m]} for _, r in missed.iterrows()]
            detail += [{"type": "số đo không ủng hộ", "label": label, "measure": m, "level": lv,
                        "patient_id": r.patient_id, "value": r[m]} for _, r in unsup.iterrows()]
    return pd.DataFrame(rows), pd.DataFrame(detail)


def patient_level(df):
    pf = pd.read_csv(T_MEAS / "patient_features.csv")
    lp = pd.read_csv(T_NLP / "labels_patient.csv")
    qc = pd.read_csv(T_SEG / "tss_qc.csv")[["patient_id", "use_level"]]
    sig = df[df.level.isin(LUMBAR)].groupby("patient_id").disc_csf_ratio.mean().rename("mean_disc_csf_ratio")
    p = pf.merge(lp, on="patient_id").merge(qc, on="patient_id").merge(sig, on="patient_id", how="left")
    p = p[p.use_level]
    out = []
    a = p.dropna(subset=["lordosis_deg"])
    r = assoc_row(a.muscle_spasm.to_numpy(), a.lordosis_deg.to_numpy(dtype=float), -1)
    out.append({"analysis": "góc ưỡn ↔ co cứng cơ (AUC, chiều: thấp hơn)", **r})
    for col, name in [("mean_disc_csf_ratio", "tuổi ↔ tín hiệu đĩa/DNT trung bình L1–S1"),
                      ("n_findings", "tuổi ↔ số phát hiện")]:
        b = p.dropna(subset=["age", col])
        rho, pv = spearmanr(b.age, b[col])
        out.append({"analysis": name + " (Spearman)", "n_pos": len(b), "rho": rho, "p_value": pv})
    b = p.dropna(subset=["age"])
    for lo, hi in [(0, 30), (30, 40), (40, 50), (50, 60), (60, 120)]:
        g = b[(b.age >= lo) & (b.age < hi)]
        out.append({"analysis": f"nhóm tuổi {lo}–{hi - 1 if hi < 120 else '+'}", "n_pos": len(g),
                    "median_pos": g.mean_disc_csf_ratio.median(), "desiccation_pct": 100 * g.disc_desiccation.mean(),
                    "n_findings_mean": g.n_findings.mean()})
    return pd.DataFrame(out), p


# ----------------------------------------------------------------- biểu đồ
def _style(ax):
    ax.set_facecolor(SURFACE)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(INK2)
    ax.tick_params(colors=INK2, labelsize=8)
    ax.yaxis.grid(True, color=GRID, lw=0.8)
    ax.set_axisbelow(True)


def fig_boxplots(df, assoc):
    pairs = [(l, m, d) for l, m, d, k in PAIRS if (l, m) in
             {("disc_desiccation", "disc_csf_ratio"), ("disc_space_narrowing", "dhi"),
              ("disc_bulge", "disc_post_bulge_mm"), ("disc_protrusion", "disc_post_bulge_mm"),
              ("thecal_sac_compression", "canal_ap_mm"), ("spinal_canal_stenosis", "canal_ap_mm"),
              ("spondylolisthesis", "listhesis_mm"), ("foraminal_stenosis", "disc_post_bulge_mm")}]
    fig, axs = plt.subplots(2, 4, figsize=(15, 7.6), facecolor=SURFACE)
    for ax, (label, m, d) in zip(axs.ravel(), pairs):
        z = df[m + "_z"]
        data = [z[(df[label] == 0) & z.notna()], z[(df[label] == 1) & z.notna()]]
        bp = ax.boxplot(data, widths=0.5, patch_artist=True, showfliers=False,
                        medianprops={"color": INK, "lw": 1.5}, whiskerprops={"color": INK2},
                        capprops={"color": INK2})
        for patch, c in zip(bp["boxes"], (C_NO, C_YES)):
            patch.set_facecolor(c)
            patch.set_alpha(0.85)
            patch.set_edgecolor(SURFACE)
        ax.set_xticks([1, 2], [f"Không ghi\n(n={len(data[0])})", f"Có ghi\n(n={len(data[1])})"], color=INK2)
        r = assoc[(assoc.label == label) & (assoc.measure == m) & (assoc.scope == "gộp 6 tầng (z)")].iloc[0]
        ax.set_title(f"{VN[label]}\n{VN[m]}", fontsize=9.5, color=INK)
        ax.text(0.03, 0.97, f"AUC {r.auc:.2f}", transform=ax.transAxes, va="top", fontsize=9, color=INK,
                fontweight="bold")
        ax.set_ylabel("z trong tầng", fontsize=8, color=INK2)
        _style(ax)
    fig.suptitle("Số đo từ ảnh ở tầng bác sĩ có ghi bệnh so với không ghi (513 BN, chuẩn hóa z trong từng tầng)",
                 fontsize=11, color=INK)
    fig.tight_layout()
    fig.savefig(F_ANALYSIS / "assoc_boxplots.png", dpi=130, facecolor=SURFACE)
    plt.close(fig)


def fig_roc(df):
    fig, ax = plt.subplots(figsize=(6.6, 6), facecolor=SURFACE)
    ax.plot([0, 1], [0, 1], color=GRID, lw=1.2, ls="--")
    for (label, m, d), c in zip(ROC_PAIRS, SERIES):
        sub = df[df[m + "_z"].notna()]
        y, s = sub[label].to_numpy(), d * sub[m + "_z"].to_numpy()
        fpr, tpr, _ = roc_curve(y, s)
        auc = roc_auc_score(y, s)
        ax.plot(fpr, tpr, color=c, lw=2, label=f"{VN[label]} – {VN[m]} (AUC {auc:.2f})")
        i = np.searchsorted(fpr, 0.32)
        ax.annotate(VN[label], (fpr[i], tpr[i]), xytext=(6, -10), textcoords="offset points",
                    fontsize=8, color=INK)   # nhãn trực tiếp (3 màu có tương phản < 3:1)
    ax.set_xlabel("1 − độ đặc hiệu", color=INK2)
    ax.set_ylabel("Độ nhạy", color=INK2)
    ax.set_title("ROC: số đo ảnh phân biệt tầng bác sĩ có ghi bệnh (gộp, z trong tầng)", fontsize=10, color=INK)
    ax.legend(fontsize=7.5, loc="lower right", frameon=False, labelcolor=INK)
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1.01)
    _style(ax)
    ax.xaxis.grid(True, color=GRID, lw=0.8)
    fig.tight_layout()
    fig.savefig(F_ANALYSIS / "roc.png", dpi=130, facecolor=SURFACE)
    plt.close(fig)


def fig_patient(p):
    fig, axs = plt.subplots(1, 2, figsize=(12, 4.6), facecolor=SURFACE)
    a = p.dropna(subset=["age", "mean_disc_csf_ratio"])
    axs[0].scatter(a.age, a.mean_disc_csf_ratio, s=12, color=C_NO, alpha=0.5, edgecolor="none")
    bins = np.arange(15, 95, 10)
    mid = a.groupby(pd.cut(a.age, bins), observed=True).mean_disc_csf_ratio.median()
    axs[0].plot([b.mid for b in mid.index], mid.values, color=INK, lw=2, marker="o", ms=5, label="trung vị theo nhóm 10 tuổi")
    rho, pv = spearmanr(a.age, a.mean_disc_csf_ratio)
    axs[0].set_title(f"Tuổi và tín hiệu đĩa (trung bình L1–S1)  ·  Spearman ρ = {rho:.2f}", fontsize=10, color=INK)
    axs[0].set_xlabel("Tuổi", color=INK2)
    axs[0].set_ylabel("Tín hiệu đĩa / dịch não tủy", color=INK2)
    axs[0].legend(fontsize=8, frameon=False, labelcolor=INK)
    b = p.dropna(subset=["lordosis_deg"])
    data = [b.lordosis_deg[b.muscle_spasm == 0], b.lordosis_deg[b.muscle_spasm == 1]]
    bp = axs[1].boxplot(data, widths=0.5, patch_artist=True, showfliers=False,
                        medianprops={"color": INK, "lw": 1.5}, whiskerprops={"color": INK2}, capprops={"color": INK2})
    for patch, c in zip(bp["boxes"], (C_NO, C_YES)):
        patch.set_facecolor(c)
        patch.set_alpha(0.85)
        patch.set_edgecolor(SURFACE)
    axs[1].set_xticks([1, 2], [f"Không ghi co cứng cơ\n(n={len(data[0])})", f"Có ghi co cứng cơ\n(n={len(data[1])})"],
                      color=INK2)
    auc = roc_auc_score(b.muscle_spasm, -b.lordosis_deg)
    axs[1].set_title(f"Góc ưỡn thắt lưng theo nhận xét \"muscle spasm\"  ·  AUC {auc:.2f}", fontsize=10, color=INK)
    axs[1].set_ylabel("Góc giữa đĩa L1-L2 và L5-S1 (độ)", color=INK2)
    for ax in axs:
        _style(ax)
    fig.tight_layout()
    fig.savefig(F_ANALYSIS / "patient.png", dpi=130, facecolor=SURFACE)
    plt.close(fig)


def fig_discordance(dis):
    d = dis[dis.level.isin(MAIN_LEVELS) & dis.valid].copy()
    d["name"] = d.apply(lambda r: f"{VN[r.label]}\n{r.level}", axis=1)
    fig, ax = plt.subplots(figsize=(12, 4.8), facecolor=SURFACE)
    x = np.arange(len(d))
    ax.bar(x - 0.21, d.suspect_missed_pct_of_unlabeled, width=0.4, color=C_YES,
           label="Nghi bỏ sót: % tầng KHÔNG ghi có số đo như ca bệnh điển hình")
    ax.bar(x + 0.21, d.unsupported_pct_of_labeled, width=0.4, color=C_NO,
           label="Số đo không ủng hộ: % tầng CÓ ghi có số đo như ca bình thường")
    for i, r in enumerate(d.itertuples()):
        ax.text(i - 0.21, r.suspect_missed_pct_of_unlabeled + 0.8, f"{r.suspect_missed}", ha="center", fontsize=7, color=INK2)
        ax.text(i + 0.21, r.unsupported_pct_of_labeled + 0.8, f"{r.unsupported}", ha="center", fontsize=7, color=INK2)
    ax.set_xticks(x, d.name, fontsize=7.5, color=INK2)
    ax.set_ylabel("%", color=INK2)
    ax.set_ylim(0, max(d.suspect_missed_pct_of_unlabeled.max(), d.unsupported_pct_of_labeled.max()) * 1.25)
    ax.set_title("Lệch giữa số đo ảnh và báo cáo – L4-L5, L5-S1, chỉ cặp có AUC tại tầng ≥ 0,7 "
                 "(số trên cột = số tầng)", fontsize=10, color=INK)
    ax.legend(fontsize=8, frameon=False, labelcolor=INK, loc="upper right")
    _style(ax)
    fig.tight_layout()
    fig.savefig(F_ANALYSIS / "discordance.png", dpi=130, facecolor=SURFACE)
    plt.close(fig)


def main():
    df = build_dataset()
    df.to_csv(T_ANALYSIS / "analysis_level_dataset.csv", index=False)
    assoc = associations(df)
    assoc.to_csv(T_ANALYSIS / "analysis_assoc.csv", index=False)
    dis, dis_detail = discordance(df)
    dis.to_csv(T_ANALYSIS / "analysis_discordance.csv", index=False)
    dis_detail.to_csv(T_ANALYSIS / "analysis_discordance_cases.csv", index=False)
    pat, p = patient_level(df)
    pat.to_csv(T_ANALYSIS / "analysis_patient.csv", index=False)

    pd.set_option("display.width", 200)
    print(f"=== Bước 8: {df.patient_id.nunique()} BN, {len(df)} tầng ===")
    show = assoc[assoc.scope == "gộp 6 tầng (z)"][["label", "measure", "kind", "n_pos", "auc", "p_value"]]
    print("\nAUC gộp (z trong tầng):")
    print(show.round({"auc": 3}).to_string(index=False))
    print("\nTheo tầng chính (giá trị gốc):")
    lv = assoc[assoc.scope.isin(MAIN_LEVELS) & assoc.set_index(["label", "measure"]).index.isin(
        [(l, m) for l, m, _ in MAIN_PAIRS])]
    print(lv[["label", "measure", "scope", "n_pos", "median_pos", "median_neg", "auc", "youden_threshold",
              "sensitivity", "specificity"]].round(3).to_string(index=False))
    print("\nCa lệch (L4-L5, L5-S1):")
    print(dis[dis.level.isin(MAIN_LEVELS)][["label", "level", "level_auc", "valid", "n_unspec_excluded", "n_labeled", "suspect_missed",
          "suspect_missed_pct_of_unlabeled", "unsupported", "unsupported_pct_of_labeled"]].round(1).to_string(index=False))
    print("\nMức bệnh nhân:")
    print(pat.round(3).to_string(index=False))

    fig_boxplots(df, assoc)
    fig_roc(df)
    fig_patient(p)
    fig_discordance(dis)
    print("\nĐã lưu bảng analysis_*.csv và hình figures/analysis/*.png")


if __name__ == "__main__":
    main()
