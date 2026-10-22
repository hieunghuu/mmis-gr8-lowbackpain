# -*- coding: utf-8 -*-
""" AI sau segmentation: mask TotalSpineSeg + ảnh -> số đo theo tầng + gợi ý bệnh (README pipeline mục 6).

Worker của BE gọi sau segment():
  analyze(input_path, mask_path) -> dict (trường result.analysis) | raise AnalysisError

* Số đo: measure_case() của s09 - cùng cách đo với 513 bệnh nhân dùng để học ngưỡng.
* Gợi ý: bảng quy tắc threshold_rules.csv (s11), chỉ các dòng use = True. Mỗi (bệnh, tầng) dùng
  MỘT quy tắc: ưu tiên ngưỡng riêng của tầng, không có mới dùng ngưỡng z chung; nhiều quy tắc thì
  lấy quy tắc có cận dưới KTC AUC cao nhất -> số liệu kiểm chứng chéo đi kèm vẫn đúng cho quy tắc đó.
  Bỏ qua quy tắc có PPV kiểm chứng chéo < MIN_PPV (dưới 1 lần đúng / 20 lần báo); với ngưỡng z chung
  dùng PPV TẠI TẦNG ĐÓ (threshold_cv_by_level.csv) - tránh gợi ý ở tầng gần như không có ca bệnh
  (vd hẹp lỗ liên hợp ở T12-L1, PPV 0,006) - và báo số liệu của tầng đó.
* QC không đạt (thiếu đốt / đĩa, 6 đốt thắt lưng, thứ tự sai) -> vẫn trả số đo nhưng KHÔNG gợi ý,
  vì không chắc đánh số tầng.
* Chỉ dùng cho ảnh sagittal T2 cột sống thắt lưng, mask cùng lưới với ảnh (segment với iso=False).

Thử trên máy demo:  python ai/analyze.py <ảnh.nii.gz> <mask.nii.gz>
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import SimpleITK as sitk

SRC = Path(__file__).resolve().parents[1] / "pipeline" / "src"
sys.path.insert(0, str(SRC))
from common import T_ANALYSIS
from measurements.s09_level_features import measure_case
from analysis.literature import LIT_CUTOFFS, LIT_SOURCES

MEASURES = ["disc_height_mm", "dhi", "disc_csf_ratio", "disc_vb_ratio", "disc_post_bulge_mm",
            "canal_ap_mm", "canal_csa_approx_mm2", "listhesis_mm"]
NAMES = {41: "L1", 42: "L2", 43: "L3", 44: "L4", 45: "L5", 50: "sacrum",
         92: "L1-L2", 93: "L2-L3", 94: "L3-L4", 95: "L4-L5", 100: "L5-S1"}
VERTS = [41, 42, 43, 44, 45, 50]
DISCS = [92, 93, 94, 95, 100]
ORDER = [41, 92, 42, 93, 43, 94, 44, 95, 45, 100, 50]     # từ đầu xuống chân
PCTS = [5, 10, 25, 50, 75, 90, 95]
MIN_PPV = 0.05
DISCLAIMER = "Gợi ý từ số đo trên ảnh, không phải chẩn đoán; bác sĩ cần xem lại."


class AnalysisError(Exception):
    """code: GEOMETRY_MISMATCH | NOT_SAGITTAL | ANALYSIS_FAILED."""

    def __init__(self, code, message):
        super().__init__(message)
        self.code, self.message = code, message


def _load_rules():
    rules = pd.read_csv(T_ANALYSIS / "threshold_rules.csv")
    rules = rules[rules.use].copy()
    rules["per_level"] = rules.scope != "z_all"
    rules = rules.sort_values(["per_level", "auc_ci_low"], ascending=False)
    ref = pd.read_csv(T_ANALYSIS / "measure_reference.csv").set_index(["measure", "level"])
    cv_lv = pd.read_csv(T_ANALYSIS / "threshold_cv_by_level.csv").set_index(["label", "measure", "level"])
    return rules, ref, cv_lv


RULES, REF, CV_LEVEL = _load_rules()


def _check(img, mask):
    """Kiểm tra hình học + QC nhãn; trả về danh sách cảnh báo (rỗng = đạt)."""
    if (mask.GetSize() != img.GetSize() or not np.allclose(mask.GetSpacing(), img.GetSpacing(), atol=1e-3)
            or not np.allclose(mask.GetOrigin(), img.GetOrigin(), atol=1e-2)):
        raise AnalysisError("GEOMETRY_MISMATCH", "Mask không cùng lưới với ảnh (cần segment với iso=False)")
    d = np.array(img.GetDirection()).reshape(3, 3)
    if np.argmax(np.abs(d[:, 2])) != 0:          # pháp tuyến lát phải theo trục trái-phải
        raise AnalysisError("NOT_SAGITTAL", "Chỉ phân tích được ảnh sagittal (mặt cắt dọc)")

    shp = sitk.LabelShapeStatisticsImageFilter()
    shp.Execute(mask)
    present = set(shp.GetLabels())
    warnings = []
    miss = [NAMES[l] for l in VERTS + DISCS if l not in present]
    if miss:
        warnings.append({"code": "MISSING_STRUCTURE", "message": "Thiếu cấu trúc: " + ", ".join(miss)})
    if 46 in present:
        warnings.append({"code": "TRANSITIONAL_VERTEBRA",
                         "message": "Có 6 đốt thắt lưng (đốt chuyển tiếp) - kiểm tra đánh số tầng"})
    z = [shp.GetCentroid(l)[2] for l in ORDER if l in present]
    if any(a <= b for a, b in zip(z, z[1:])):
        warnings.append({"code": "LEVEL_ORDER", "message": "Thứ tự đốt / đĩa không hợp lệ"})
    return warnings


def _num(x, nd=3):
    return None if x is None or not np.isfinite(x) else round(float(x), nd)


def _percentile(value, measure, level):
    r = REF.loc[(measure, level)]
    return int(round(np.interp(value, [r[f"p{p}"] for p in PCTS], PCTS)))   # ngoài [p5, p95] -> 5 / 95


def _literature(measure, value):
    """Mức của value theo ngưỡng y văn (s12), vd "theo y văn: < 10 mm - hẹp tuyệt đối"; None nếu không có ngưỡng.
    Thang đo s09 lệch y văn (đường kính ống sống, độ trượt thấp hơn ~2 mm) -> chỉ để tham khảo."""
    if measure not in LIT_CUTOFFS:
        return None
    rule, unit, bands = LIT_CUTOFFS[measure]
    sign = "<" if rule == "<" else "≥"
    for thr, name in bands:
        if (value < thr) if rule == "<" else (value >= thr):
            return f"theo y văn: {sign} {thr} {unit} - {name}"
    return f"theo y văn: chưa tới ngưỡng {sign} {bands[-1][0]} {unit}"


def _suggest(level, measures):
    out = []
    cand = RULES[(RULES.scope == level) | (RULES.scope == "z_all")]
    for label, g in cand.groupby("label", sort=False):
        for _, r in g.iterrows():                 # đã sắp: riêng tầng trước, cận dưới KTC cao trước
            v = measures.get(r.measure)
            if v is None:
                continue
            ref = REF.loc[(r.measure, level)]
            perf = CV_LEVEL.loc[(label, r.measure, level)] if r.scope == "z_all" else r
            if not perf.cv_ppv >= MIN_PPV:        # NaN (tầng không có ca bệnh) cũng bị bỏ
                continue
            x = (v - ref["mean"]) / ref["std"] if r.scope == "z_all" else v
            if (x <= r.threshold) if r.rule == "<=" else (x >= r.threshold):
                out.append({"label": label, "label_vi": r.label_vi, "measure": r.measure,
                            "measure_vi": r.measure_vi, "value": v, "rule": r.rule,
                            "threshold": _num(r.threshold), "threshold_unit": r.threshold_unit,
                            "percentile": _percentile(v, r.measure, level), "confidence": r.confidence,
                            "sensitivity": _num(perf.cv_sens, 2), "specificity": _num(perf.cv_spec, 2),
                            "ppv": _num(perf.cv_ppv, 2), "literature": _literature(r.measure, v),
                            "literature_source": dict(zip(("citation", "url"), LIT_SOURCES[r.measure]))
                            if r.measure in LIT_SOURCES else None})
            break                                 # mỗi (bệnh, tầng) chỉ xét 1 quy tắc đủ điều kiện
    return out


def analyze(input_path, mask_path):
    try:
        img = sitk.ReadImage(str(input_path))
        mask = sitk.ReadImage(str(mask_path), sitk.sitkUInt8)
        warnings = _check(img, mask)
        res = measure_case(mask_path, input_path)
    except AnalysisError:
        raise
    except Exception as e:
        raise AnalysisError("ANALYSIS_FAILED", f"Không đo được: {e}") from None

    ok = not warnings
    levels = []
    for row in res["rows"]:
        measures = {m: _num(row.get(m)) for m in MEASURES}
        measures = {m: v for m, v in measures.items() if v is not None}
        levels.append({"level": row["level"], "missing": row.get("missing"), "measures": measures,
                       "suggestions": _suggest(row["level"], measures) if ok else []})
    return {"qc": {"ok": ok, "warnings": warnings},
            "levels": levels,
            "lordosis_deg": _num(res["patient"]["lordosis_deg"], 1),
            "disclaimer": DISCLAIMER,
            "error": None}


if __name__ == "__main__":
    print(json.dumps(analyze(sys.argv[1], sys.argv[2]), ensure_ascii=False, indent=2))
