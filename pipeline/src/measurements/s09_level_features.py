# -*- coding: utf-8 -*-
"""S09 - Bước 7: tính số đo theo tầng đĩa đệm từ mask TotalSpineSeg (README mục 7).

Đo trên mặt phẳng sagittal của các lát GIỮA (lát nhiều voxel ống sống nhất và 2 lát kề),
trong tọa độ mm thật. Mỗi tầng có hệ trục riêng: u = trục dài của đĩa (PCA, trước -> sau),
v = vuông góc (chân -> đầu). Thân đốt = phần nhãn đốt nằm trước ống sống (bỏ mỏm gai).

Chạy (từ thư mục pipeline/):  python src/measurements/s09_level_features.py
"""
import sys
from multiprocessing import Pool
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import SimpleITK as sitk
from scipy import ndimage

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))   # src/
from common import OUTPUTS, NIFTI, F_MEAS, T_DICOM, T_MEAS, T_SEG

TSS = OUTPUTS / "tss" / "sag" / "step2_output"
# tầng -> (nhãn đĩa, nhãn đốt trên, nhãn đốt dưới)
LEVELS = {"T12-L1": (91, 32, 41), "L1-L2": (92, 41, 42), "L2-L3": (93, 42, 43),
          "L3-L4": (94, 43, 44), "L4-L5": (95, 44, 45), "L5-S1": (100, 45, 50)}
CANAL = (1, 2)            # tủy + ống sống (ở T12-L1, L1-L2 còn tủy sống)
BAND_MM = 2.0             # dải +-2 mm quanh tâm đĩa để đo ống sống
BODY_BAND_MM = 6.0        # phần thân đốt sát đĩa để lấy mép sau
MIN_PX = 20
QC_PATIENTS = [1, 100, 300, 450]


def largest_cc(mask):
    lab, n = ndimage.label(mask)
    if n <= 1:
        return mask
    sizes = ndimage.sum(mask, lab, range(1, n + 1))
    return lab == (np.argmax(sizes) + 1)


def slice_coords(img, k, shape):
    """Tọa độ vật lý (y, z) LPS của mỗi pixel trong lát k."""
    o = np.array(img.GetOrigin())
    d = np.array(img.GetDirection()).reshape(3, 3)
    sx, sy, sz = img.GetSpacing()
    rr, cc = np.mgrid[0:shape[0], 0:shape[1]]
    p = (o[:, None, None] + d[:, 0, None, None] * cc * sx + d[:, 1, None, None] * rr * sy
         + d[:, 2, None, None] * k * sz)
    return p[1], p[2]


def disc_axes(y, z):
    pts = np.column_stack([y, z])
    c = pts.mean(0)
    w, vec = np.linalg.eigh(np.cov((pts - c).T))
    e1 = vec[:, np.argmax(w)]
    if e1[0] < 0:            # +u = phía sau (y LPS dương)
        e1 = -e1
    ev = np.array([-e1[1], e1[0]])
    if ev[1] < 0:            # +v = lên đầu (z LPS dương)
        ev = -ev
    return c, e1, ev


def proj(y, z, c, e1, ev):
    p = np.column_stack([y, z]) - c
    return p @ e1, p @ ev


def area_over_length(u, px_area):
    if len(u) < MIN_PX:
        return np.nan, np.nan
    L = u.max() - u.min()
    return (len(u) * px_area / L if L > 0 else np.nan), L


def measure_slice(M, I, img, k, disc, up, lo, bodies, px_area, sz, keep_pts=False):
    """Đo 1 tầng trên 1 lát. Trả về dict số đo (hoặc None)."""
    dm = M[k] == disc
    if dm.sum() < MIN_PX:
        return None
    Y, Z = slice_coords(img, k, M[k].shape)
    c, e1, ev = disc_axes(Y[dm], Z[dm])
    u, v = proj(Y[dm], Z[dm], c, e1, ev)
    h, L = area_over_length(u, px_area)
    third = L / 3
    ant, post = u < u.min() + third, u > u.max() - third
    r = {"disc_height_mm": h,
         "disc_height_ant_mm": ant.sum() * px_area / third,
         "disc_height_post_mm": post.sum() * px_area / third}
    disc_post = np.percentile(u, 98)
    cm = np.isin(M[k], CANAL)
    cu, cv = proj(Y[cm], Z[cm], c, e1, ev) if cm.any() else (np.array([]), np.array([]))

    # thân đốt kề. Nhãn đốt gồm cả cung sau/mỏm gai (ở lát giữa, và còn nối với thân đốt qua
    # cuống ở ~55 % số đốt) -> CHỈ giữ pixel nằm TRƯỚC thành trước của ống sống.
    edges = {}
    for name, lab in (("upper", up), ("lower", lo)):
        bm = bodies.get(lab)
        if bm is None or bm[k].sum() < MIN_PX:
            continue
        bu, bv = proj(Y[bm[k]], Z[bm[k]], c, e1, ev)
        in_range = (cv >= bv.min()) & (cv <= bv.max())
        if in_range.sum() >= 5:
            front = bu < np.percentile(cu[in_range], 2)
            if front.sum() >= MIN_PX:
                bu, bv = bu[front], bv[front]
        near = bv < bv.min() + BODY_BAND_MM if name == "upper" else bv > bv.max() - BODY_BAND_MM
        if near.sum() < 5:
            continue
        edges[name] = {"post": np.percentile(bu[near], 98), "depth": np.ptp(bu[near]),
                       "height": np.ptp(bv)}
    if "upper" in edges:
        r["vb_upper_height_mm"] = edges["upper"]["height"]
    if "lower" in edges:
        r["vb_lower_height_mm"] = edges["lower"]["height"]
    if len(edges) == 2:
        up_e, lo_e = edges["upper"], edges["lower"]
        r["disc_post_bulge_mm"] = disc_post - (up_e["post"] + lo_e["post"]) / 2
        r["listhesis_mm"] = lo_e["post"] - up_e["post"]
        r["listhesis_pct"] = 100 * r["listhesis_mm"] / lo_e["depth"] if lo_e["depth"] > 0 else np.nan

    # ống sống trong dải +-2 mm quanh tâm đĩa
    if cm.sum():
        band = np.abs(cv) <= BAND_MM
        r["canal_ap_mm"] = band.sum() * px_area / (2 * BAND_MM) if band.sum() else np.nan
        # tín hiệu dịch não tủy: phân vị 75 của ống sống trong +-10 mm
        csf = I[k][cm][np.abs(cv) <= 10]
        csf_sig = np.percentile(csf, 75) if len(csf) > 10 else np.nan
    else:
        csf_sig = np.nan

    core = ndimage.binary_erosion(dm)
    disc_sig = np.median(I[k][core]) if core.sum() >= 5 else np.median(I[k][dm])
    r["disc_csf_ratio"] = disc_sig / csf_sig if csf_sig and csf_sig > 0 else np.nan
    bm = bodies.get(up)
    if bm is not None and bm[k].sum() >= MIN_PX:
        body_k = bm[k].copy()
        if cm.any():          # chỉ phần thân đốt (trước ống sống) cho tín hiệu
            ya = np.percentile(Y[cm], 2)
            body_k &= Y < ya
        vb_core = ndimage.binary_erosion(body_k if body_k.sum() >= MIN_PX else bm[k], iterations=2)
        vb_sig = np.median(I[k][vb_core if vb_core.sum() >= 5 else bm[k]])
        r["disc_vb_ratio"] = disc_sig / vb_sig if vb_sig > 0 else np.nan
    r["_axis"] = e1
    if keep_pts:
        r["_pts"] = {"c": c, "e1": e1, "ev": ev, "disc_post": disc_post,
                     "edges": edges, "L": L}
    return r


def canal_csa(M, img, c, e1, ev, px_area, sz):
    """Diện tích cắt ngang ống sống XẤP XỈ: thể tích ống sống trong dải / chiều cao dải."""
    n = 0
    for k in range(M.shape[0]):
        cm = np.isin(M[k], CANAL)
        if not cm.any():
            continue
        Y, Z = slice_coords(img, k, M[k].shape)
        _, cv = proj(Y[cm], Z[cm], c, e1, ev)
        n += (np.abs(cv) <= BAND_MM).sum()
    return n * px_area * sz / (2 * BAND_MM) if n else np.nan


def process(pid, keep_pts=False):
    return measure_case(TSS / f"{pid:04d}.nii.gz", NIFTI / "sag" / f"{pid:04d}.nii.gz", keep_pts, pid)


def measure_case(mask_path, image_path, keep_pts=False, pid=None):
    """Đo một ca bất kỳ từ file mask + ảnh sagittal (dùng chung cho s09 và ai/analyze.py)."""
    m = sitk.ReadImage(str(mask_path), sitk.sitkUInt8)
    img = sitk.ReadImage(str(image_path), sitk.sitkFloat32)
    M, I = sitk.GetArrayFromImage(m), sitk.GetArrayFromImage(img)
    sx, sy, sz = img.GetSpacing()
    px_area = sx * sy
    canal_px = np.isin(M, CANAL).sum(axis=(1, 2))
    k_mid = int(np.argmax(canal_px))
    mids = [k for k in (k_mid - 1, k_mid, k_mid + 1) if 0 <= k < M.shape[0]]
    labs = {l for v in LEVELS.values() for l in v[1:]}
    bodies = {l: largest_cc(M == l) for l in labs if (M == l).any()}

    rows, pts = [], {}
    axes = {}
    for lv, (disc, up, lo) in LEVELS.items():
        row = {"patient_id": pid, "level": lv}
        if not (M == disc).any():
            row["missing"] = "disc"
            rows.append(row)
            continue
        row["disc_volume_mm3"] = float((M == disc).sum() * px_area * sz)
        per = [measure_slice(M, I, img, k, disc, up, lo, bodies, px_area, sz,
                             keep_pts=keep_pts and k == k_mid) for k in mids]
        per = [p for p in per if p]
        if not per:
            row["missing"] = "mid_slices"
            rows.append(row)
            continue
        keys = {k for p in per for k in p if not k.startswith("_")}
        for key in keys:
            vals = [p[key] for p in per if key in p and np.isfinite(p[key])]
            row[key] = float(np.median(vals)) if vals else np.nan
        mid = next((p for p in per if "_pts" in p), None) or per[len(per) // 2]
        axes[lv] = mid["_axis"]
        if keep_pts and "_pts" in mid:
            pts[lv] = mid["_pts"]
        # diện tích ống sống xấp xỉ: dùng trục của lát giữa
        dm = M[k_mid] == disc
        if dm.sum() >= MIN_PX:
            Y, Z = slice_coords(img, k_mid, M[k_mid].shape)
            c, e1, ev = disc_axes(Y[dm], Z[dm])
            row["canal_csa_approx_mm2"] = canal_csa(M, img, c, e1, ev, px_area, sz)
        hu, hl = row.get("vb_upper_height_mm"), row.get("vb_lower_height_mm")
        if lv == "L5-S1":
            hl = None                      # xương cùng không có "chiều cao thân đốt"
        hs = [h for h in (hu, hl) if h is not None and np.isfinite(h)]
        row["dhi"] = row.get("disc_height_mm", np.nan) / np.mean(hs) if hs else np.nan
        rows.append(row)

    lordosis = np.nan
    if "L1-L2" in axes and "L5-S1" in axes:
        cosang = abs(float(np.dot(axes["L1-L2"], axes["L5-S1"])))
        lordosis = float(np.degrees(np.arccos(min(1.0, cosang))))
    out = {"rows": rows, "patient": {"patient_id": pid, "lordosis_deg": lordosis, "k_mid": k_mid}}
    if keep_pts:
        out["pts"], out["img"], out["M"], out["I"], out["k_mid"] = pts, img, M, I, k_mid
    return out


# ----------------------------------------------------------------- hình QC
def to_pixel(img, k, y, z):
    """(y, z) vật lý trên lát k -> (cột, hàng) pixel."""
    o = np.array(img.GetOrigin())
    d = np.array(img.GetDirection()).reshape(3, 3)
    sx, sy, sz = img.GetSpacing()
    A = np.array([[d[1, 0] * sx, d[1, 1] * sy], [d[2, 0] * sx, d[2, 1] * sy]])
    b = np.array([y, z]) - (o[[1, 2]] + d[[1, 2], 2] * k * sz)
    return np.linalg.solve(A, b)


def qc_overlay(pids):
    fig, axs = plt.subplots(1, len(pids), figsize=(4.2 * len(pids), 4.6))
    for ax, pid in zip(axs, pids):
        o = process(pid, keep_pts=True)
        k, I, img, M = o["k_mid"], o["I"], o["img"], o["M"]
        ax.imshow(I[k], cmap="gray", vmax=np.percentile(I[k], 99.5))
        ax.contour(np.isin(M[k], CANAL), levels=[0.5], colors="cyan", linewidths=0.6)
        for lv, p in o["pts"].items():
            c, e1, ev = p["c"], p["e1"], p["ev"]
            for vec, col in ((e1, "yellow"), (ev, "lime")):
                a = to_pixel(img, k, *(c - vec * p["L"] / 2))
                b = to_pixel(img, k, *(c + vec * p["L"] / 2))
                ax.plot([a[0], b[0]], [a[1], b[1]], color=col, lw=0.8)
            dp = to_pixel(img, k, *(c + e1 * p["disc_post"]))
            ax.plot(*dp, "r.", ms=5)
            for e in p["edges"].values():
                bp = to_pixel(img, k, *(c + e1 * e["post"]))
                ax.plot(*bp, "m+", ms=6)
            ax.text(*to_pixel(img, k, *(c - e1 * p["L"] * 0.9)), lv, color="white", fontsize=6)
        ax.set_title(f"BN {pid:04d} - lát giữa {k}", fontsize=9)
        ax.axis("off")
    fig.suptitle("Trục u (vàng) / v (xanh lá) của từng đĩa, mép sau đĩa (đỏ), mép sau thân đốt (tím), "
                 "ống sống (cyan)", fontsize=9)
    fig.tight_layout()
    fig.savefig(F_MEAS / "qc_overlay.png", dpi=120)
    plt.close(fig)


def qc_distributions(lf):
    cols = ["disc_height_mm", "dhi", "disc_csf_ratio", "disc_post_bulge_mm",
            "canal_ap_mm", "canal_csa_approx_mm2", "listhesis_mm", "vb_upper_height_mm"]
    order = list(LEVELS)
    fig, axs = plt.subplots(2, 4, figsize=(16, 7))
    for ax, col in zip(axs.ravel(), cols):
        data = [lf.loc[lf.level == lv, col].dropna() for lv in order]
        ax.boxplot(data, tick_labels=[l.replace("-", "\n") for l in order], showfliers=False)
        ax.set_title(col, fontsize=9)
        ax.tick_params(labelsize=7)
    fig.suptitle("Phân bố số đo theo tầng (513 ca use_level)", fontsize=10)
    fig.tight_layout()
    fig.savefig(F_MEAS / "qc_distributions.png", dpi=110)
    plt.close(fig)


def main():
    qc = pd.read_csv(T_SEG / "tss_qc.csv")
    pids = qc.patient_id.tolist()
    with Pool(8) as pool:
        res = pool.map(process, pids, chunksize=4)
    lf = pd.DataFrame([r for o in res for r in o["rows"]])
    lf = lf.merge(qc[["patient_id", "use_level"]], on="patient_id")
    pf = pd.DataFrame([o["patient"] for o in res])

    sel = pd.read_csv(T_DICOM / "series_selected.csv")
    di = pd.read_csv(T_DICOM / "dicom_index.csv", low_memory=False,
                     usecols=["patient_id", "study_dir", "series_dir", "age", "sex"])
    demo = (di.merge(sel[["patient_id", "study_dir", "sag_series"]],
                     left_on=["patient_id", "study_dir", "series_dir"],
                     right_on=["patient_id", "study_dir", "sag_series"])
              .groupby("patient_id")[["age", "sex"]].first().reset_index())
    pf = pf.merge(demo, on="patient_id", how="left")

    cols = ["patient_id", "level", "use_level", "missing", "disc_volume_mm3", "disc_height_mm",
            "disc_height_ant_mm", "disc_height_post_mm", "dhi", "disc_csf_ratio", "disc_vb_ratio",
            "disc_post_bulge_mm", "canal_ap_mm", "canal_csa_approx_mm2", "listhesis_mm",
            "listhesis_pct", "vb_upper_height_mm", "vb_lower_height_mm"]
    lf = lf.reindex(columns=cols)
    lf.to_csv(T_MEAS / "level_features.csv", index=False)
    pf.to_csv(T_MEAS / "patient_features.csv", index=False)

    use = lf[lf.use_level]
    print(f"=== Bước 7: {lf.patient_id.nunique()} BN, {len(lf)} dòng (use_level: {use.patient_id.nunique()} BN) ===")
    print("Thiếu theo tầng:", lf.groupby("level").missing.apply(lambda s: s.notna().sum()).to_dict())
    print("\nTrung vị theo tầng (use_level):")
    show = ["disc_height_mm", "dhi", "disc_csf_ratio", "disc_post_bulge_mm", "canal_ap_mm",
            "canal_csa_approx_mm2", "listhesis_mm", "vb_upper_height_mm"]
    print(use.groupby("level")[show].median().reindex(list(LEVELS)).round(2).to_string())
    print("\nNaN (use_level):", use[show].isna().sum().to_dict())
    print(f"\nGóc ưỡn (L1-L2 vs L5-S1): trung vị {pf.lordosis_deg.median():.1f} độ, "
          f"IQR {pf.lordosis_deg.quantile(.25):.1f}-{pf.lordosis_deg.quantile(.75):.1f}")
    print(f"Tuổi: {pf.age.min():.0f}-{pf.age.max():.0f}, trung vị {pf.age.median():.0f}; "
          f"nữ {(pf.sex == 'F').mean() * 100:.1f}%")
    qc_distributions(use)
    qc_overlay(QC_PATIENTS)
    print("Đã lưu level_features.csv, patient_features.csv, qc_overlay.png, qc_distributions.png")


if __name__ == "__main__":
    main()
