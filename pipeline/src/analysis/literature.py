# -*- coding: utf-8 -*-
"""Ngưỡng y văn của các số đo s09 - nơi DUY NHẤT khai báo, dùng chung cho s12 và ai/analyze.py.

Cố ý không import gì: ai/analyze.py (worker của BE) nạp file này, nên không được kéo theo s10 / s11
(scikit-learn, scipy.stats) vào môi trường BE. Nguồn và giới hạn: pipeline/README.md mục 7.
"""

# số đo -> (quy tắc, đơn vị, [(ngưỡng, ý nghĩa)] từ nặng đến nhẹ)
LIT_CUTOFFS = {
    "canal_ap_mm": ("<", "mm", [(10, "hẹp tuyệt đối"), (12, "hẹp tương đối")]),
    "canal_csa_approx_mm2": ("<", "mm²", [(75, "hẹp tuyệt đối (Schönström)"), (100, "hẹp tương đối (Schönström)")]),
    "listhesis_mm": (">=", "mm", [(3, "mốc lâm sàng, không phải định nghĩa chẩn đoán")]),
}

# số đo -> (trích dẫn hiển thị, link). Nhãn ghi rõ mức chắc chắn: chỉ Schönström 1984 đã xác nhận đúng là
# bài đề ra mốc (~75 mm²); hai nguồn còn lại là bài gắn với mốc / nguồn minh họa - pipeline/README.md mục 7.
LIT_SOURCES = {
    "canal_ap_mm": ("Verbiest, J Bone Joint Surg Br 1954 (mốc mm theo nguồn thứ cấp)",
                    "https://doi.org/10.1302/0301-620X.36B2.230"),
    "canal_csa_approx_mm2": ("Schönström và cs., Spine 1984 - diện tích tới hạn ~75 mm²",
                             "https://pubmed.ncbi.nlm.nih.gov/6495030/"),
    "listhesis_mm": ("Ví dụ nghiên cứu dùng mốc 3 mm: Front Surg 2022 (không phải bài đề xuất)",
                     "https://doi.org/10.3389/fsurg.2022.860865"),
}
