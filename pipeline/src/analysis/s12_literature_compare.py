# -*- coding: utf-8 -*-
"""S12 - Đặt ngưỡng học từ dữ liệu (s11) cạnh ngưỡng y văn, trên cùng 513 bệnh nhân.

Ngưỡng y văn là cố định (không học từ dữ liệu này) -> chấm thẳng trên toàn bộ dữ liệu, không cần
kiểm chứng chéo; ngưỡng s11 dùng số liệu kiểm chứng chéo (cv_*) để so cho công bằng.

Chỉ các số đo CÓ ngưỡng y văn dạng số:
  * đường kính trước-sau ống sống (giữa sagittal): < 10 mm hẹp tuyệt đối, < 12 mm hẹp tương đối
    (một số nguồn dùng 13 mm khi đo trên CT);
  * diện tích cắt ngang bao màng cứng (Schönström): < 75 mm² tuyệt đối, < 100 mm² tương đối.
    canal_csa_approx_mm2 của s09 chỉ XẤP XỈ (dựng từ ảnh sagittal, gồm cả tủy) -> lệch là dự kiến;
  * trượt đốt >= 3 mm: mốc lâm sàng hay dùng (mất vững / chỉ định mổ), KHÔNG phải định nghĩa chẩn đoán.
Mất nước đĩa, hẹp khoang đĩa, phồng / lồi đĩa không có ngưỡng số chuẩn (phân độ hình thái) -> không so.

Đầu ra: outputs/tables/analysis/literature_compare.csv
Chạy (từ thư mục pipeline/):  python src/analysis/s12_literature_compare.py
"""
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))   # src/
from common import T_ANALYSIS
from analysis.s10_level_analysis import LEVELS, VN, build_dataset
from analysis.s11_threshold_rules import MIN_POS, confusion

# số đo -> (quy tắc, đơn vị, [(ngưỡng, ý nghĩa)] từ nặng đến nhẹ). ai/analyze.py dùng chung bảng này.
LIT_CUTOFFS = {
    "canal_ap_mm": ("<", "mm", [(10, "hẹp tuyệt đối"), (12, "hẹp tương đối")]),
    "canal_csa_approx_mm2": ("<", "mm²", [(75, "hẹp tuyệt đối (Schönström)"), (100, "hẹp tương đối (Schönström)")]),
    "listhesis_mm": (">=", "mm", [(3, "mốc lâm sàng, không phải định nghĩa chẩn đoán")]),
}
LIT_LABELS = {"canal_ap_mm": ["spinal_canal_stenosis", "thecal_sac_compression"],
              "canal_csa_approx_mm2": ["spinal_canal_stenosis", "thecal_sac_compression"],
              "listhesis_mm": ["spondylolisthesis"]}
# (bệnh, số đo, quy tắc, ngưỡng, tên ngưỡng)
LITERATURE = [(label, m, rule, thr, f"{m} {rule} {thr} {unit} ({name})")
              for m, (rule, unit, bands) in LIT_CUTOFFS.items() for label in LIT_LABELS[m] for thr, name in bands]


def main():
    df = build_dataset()
    rules = pd.read_csv(T_ANALYSIS / "threshold_rules.csv").set_index(["label", "measure", "scope"])
    rows = []
    for label, m, rule, thr, name in LITERATURE:
        for lv in LEVELS:
            d = df[(df.level == lv) & df[m].notna()]
            if d[label].sum() < MIN_POS:      # cùng điều kiện s11 dùng để học ngưỡng riêng tầng
                continue
            flag = (d[m] < thr) if rule == "<" else (d[m] >= thr)
            lit = confusion(d[label].values, flag.values)
            key = (label, m, lv)
            data = rules.loc[key] if key in rules.index else None
            rows.append({
                "label": label, "label_vi": VN[label], "measure": m, "level": lv, "n_pos": int(d[label].sum()),
                "median_pos": d.loc[d[label] == 1, m].median(), "median_neg": d.loc[d[label] == 0, m].median(),
                "lit_rule": name, "lit_sens": lit["sens"], "lit_spec": lit["spec"], "lit_ppv": lit["ppv"],
                "lit_flag_rate": lit["flag_rate"],
                "data_threshold": None if data is None else data.threshold,
                "data_use": None if data is None else bool(data.use),
                "data_cv_sens": None if data is None else data.cv_sens,
                "data_cv_spec": None if data is None else data.cv_spec,
                "data_cv_ppv": None if data is None else data.cv_ppv,
            })
    out = pd.DataFrame(rows)
    out.to_csv(T_ANALYSIS / "literature_compare.csv", index=False)

    show = out[["label_vi", "level", "n_pos", "median_pos", "median_neg", "lit_rule", "lit_sens", "lit_spec",
                "lit_ppv", "lit_flag_rate", "data_threshold", "data_cv_sens", "data_cv_spec", "data_cv_ppv"]]
    with pd.option_context("display.width", 250, "display.max_rows", 100):
        print(show.round(2).to_string(index=False))
    print("\nĐã lưu literature_compare.csv")


if __name__ == "__main__":
    main()
