# -*- coding: utf-8 -*-
"""S02 - Chọn series T2 TSE SAG + T2 TSE AX cho mỗi bệnh nhân, chuyển sang NIfTI.

Quy tắc chọn (dựa trên dicom_index.csv của s01)
-----------------------------------------------
* Chỉ xét ảnh chính (bỏ localizer, POSDISP), tên series chứa "t2_tse"
  (bỏ t2_tirm/STIR, trufi, ciss... vì độ tương phản khác).
* Mặt cắt lấy theo HƯỚNG THỰC TẾ (cột plane từ ImageOrientationPatient), không theo tên.
* SAG: ưu tiên study "L-SPINE*", rồi trường nhìn (FOV = Rows x PixelSpacing) >= 250 mm,
  rồi series có nhiều lát nhất, hòa thì lấy series chụp SAU (SeriesNumber lớn hơn -
  thường là chụp lại vì lần đầu bị rung). Điều kiện FOV loại ảnh chụp phóng to
  (vd BN 515: t2_tse_sag_448, FOV 160 mm, 25 lát) - không đủ mốc giải phẫu để
  TotalSpineSeg đánh số tầng.
  Trước số lát còn xét: tâm series SAG cách tâm vùng ảnh axial (cùng study) <= 100 mm.
  Ảnh axial luôn chụp tại các đĩa thắt lưng, nên điều kiện này loại series SAG đặt ở
  vùng khác (vd BN 420: series ngực C7-T12, lệch 237 mm; BN 542: lệch xuống chậu 109 mm).
  Dùng ngưỡng (không xếp "gần nhất") để không đổi lựa chọn của các BN có series chụp
  lại cùng vị trí (chỉ lệch vài mm).
* AX: ưu tiên CÙNG study với SAG đã chọn (để chung hệ tọa độ), rồi study L-SPINE,
  rồi nhiều lát nhất, rồi series chụp sau.

Tách khối axial
---------------
Một series T2 AX thường gồm 3-5 khối, mỗi khối nghiêng song song một đĩa đệm.
Lát được gom khối theo hướng (ImageOrientationPatient làm tròn 2 chữ số), rồi tách
tiếp khi có khoảng nhảy vị trí lớn (2 khối cho 2 đĩa có thể trùng góc nghiêng).
Mỗi khối -> 1 file NIfTI riêng. Trong 1 series SAG nếu có >1 hướng thì giữ khối lớn nhất.

Ghi NIfTI
---------
Lát sắp theo vị trí thật dọc pháp tuyến (ImagePositionPatient . normal), không theo
InstanceNumber. Hướng, gốc, spacing lấy từ header -> SimpleITK tự đổi LPS sang RAS
khi ghi .nii.gz. Kiểm tra khoảng cách giữa các lát có đều không.

Đầu ra
------
outputs/nifti/sag/0001.nii.gz
outputs/nifti/ax/0001_b1.nii.gz, 0001_b2.nii.gz ... (b1 = khối cao nhất, gần đầu)
outputs/tables/series_selected.csv     - series chọn cho mỗi BN + lý do
outputs/tables/nifti_volumes.csv       - mỗi file NIfTI 1 dòng (kích thước, spacing, QC)
outputs/figures/qc_s02_geometry.png    - vị trí các khối axial chiếu lên ảnh sagittal

Chạy (từ thư mục totalspineseg/):  python src/s02_select_convert.py
"""
import sys
from multiprocessing import Pool
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pydicom
import SimpleITK as sitk

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import MRI_DIR, TABLES, FIGURES, NIFTI

SAG_DIR = NIFTI / "sag"
AX_DIR = NIFTI / "ax"
IOP = ["iop_rx", "iop_ry", "iop_rz", "iop_cx", "iop_cy", "iop_cz"]
MIN_SAG_FOV_MM = 250      # 510/515 series SAG chuẩn có FOV 280 mm
MAX_SAG_AX_DIST_MM = 100  # tâm SAG phải gần vùng ảnh axial (các đĩa thắt lưng)
QC_PATIENTS = [1, 2, 100, 230, 300, 450]


# ----------------------------------------------------------------- chọn series
def load_candidates():
    df = pd.read_csv(TABLES / "dicom_index.csv", low_memory=False)
    df = df[~df.is_localizer & ~df.is_posdisp
            & df.series_desc.str.lower().str.contains("t2_tse")
            & df.plane.isin(["SAG", "AX"])].copy()
    df["lspine"] = df.study_dir.str.upper().str.startswith("L-SPINE")
    df["fov_mm"] = df.rows * df.px_row_mm
    # tọa độ z (đầu-chân, mm) của TÂM lát = gốc + nửa hàng x hướng cột + nửa cột x hướng hàng
    df["center_z"] = (df.ipp_z + df.rows / 2 * df.px_row_mm * df.iop_cz
                      + df.cols / 2 * df.px_col_mm * df.iop_rz)
    df["orient_key"] = df[IOP].round(2).astype(str).agg(",".join, axis=1)
    return df


def series_table(df):
    return (df.groupby(["patient_id", "plane", "study_dir", "series_dir"])
              .agg(series_number=("series_number", "first"),
                   series_desc=("series_desc", "first"),
                   lspine=("lspine", "first"),
                   fov_mm=("fov_mm", "first"),
                   center_z=("center_z", "mean"),
                   n_files=("file", "size"),
                   # đếm vị trí lát khác nhau, vì có series bị lưu trùng mỗi lát 2 lần
                   n_slices=("slice_location", lambda s: s.round(1).nunique()),
                   n_blocks=("orient_key", "nunique"))
              .reset_index())


def choose(st):
    rows = []
    for pid, g in st.groupby("patient_id"):
        sag = g[g.plane == "SAG"].copy()
        sag["fov_ok"] = sag.fov_mm >= MIN_SAG_FOV_MM
        # tâm vùng ảnh axial của từng study (trung bình theo số lát)
        axg = g[g.plane == "AX"]
        ax_z = ((axg.center_z * axg.n_files).groupby(axg.study_dir).sum()
                / axg.n_files.groupby(axg.study_dir).sum())
        sag["dist_ax_mm"] = (sag.center_z - sag.study_dir.map(ax_z)).abs()
        sag["near_ax"] = sag.dist_ax_mm.fillna(0) <= MAX_SAG_AX_DIST_MM
        sag = sag.sort_values(["lspine", "fov_ok", "near_ax", "n_slices", "series_number"],
                              ascending=False)
        s = sag.iloc[0]
        ax = g[g.plane == "AX"].copy()
        ax["same_study"] = ax.study_dir == s.study_dir
        ax = ax.sort_values(["same_study", "lspine", "n_slices", "series_number"],
                            ascending=False)
        a = ax.iloc[0]
        rows.append({
            "patient_id": pid,
            "study_dir": s.study_dir,
            "sag_series": s.series_dir, "sag_desc": s.series_desc,
            "sag_n_slices": s.n_slices, "sag_fov_mm": round(s.fov_mm, 1),
            "sag_dist_ax_mm": round(s.dist_ax_mm, 1),
            "sag_n_candidates": len(sag),
            "ax_study_dir": a.study_dir,
            "ax_series": a.series_dir, "ax_desc": a.series_desc,
            "ax_n_slices": a.n_slices, "ax_n_blocks": a.n_blocks,
            "ax_n_candidates": len(ax), "ax_same_study": bool(a.same_study),
        })
    return pd.DataFrame(rows)


# ----------------------------------------------------------------- ghi NIfTI
def build_volume(files):
    """Danh sách file .ima cùng hướng -> sitk.Image 3D đúng hình học."""
    ds = [pydicom.dcmread(f) for f in files]
    iop = np.array(ds[0].ImageOrientationPatient, float)
    r, c = iop[:3], iop[3:]
    n = np.cross(r, c)
    pos = np.array([np.array(d.ImagePositionPatient, float) @ n for d in ds])
    order = np.argsort(pos, kind="stable")
    ds = [ds[i] for i in order]
    pos = pos[order]
    # 19 BN có mỗi lát bị lưu 2 lần (pixel giống hệt, chỉ khác SOPInstanceUID):
    # bỏ lát trùng vị trí, giữ bản đầu tiên
    keep = np.r_[True, np.diff(pos) > 0.01]
    n_dup = int((~keep).sum())
    ds = [d for d, k in zip(ds, keep) if k]
    pos = pos[keep]

    arr = np.stack([d.pixel_array.astype(np.float32)
                    * float(getattr(d, "RescaleSlope", 1) or 1)
                    + float(getattr(d, "RescaleIntercept", 0) or 0) for d in ds])
    gaps = np.diff(pos)
    dz = float(np.median(gaps)) if len(gaps) else float(ds[0].SliceThickness)
    uniform = bool(len(gaps) == 0 or np.abs(gaps - dz).max() < 0.1)

    img = sitk.GetImageFromArray(arr.astype(np.int16))   # (z, hàng, cột)
    ps = [float(x) for x in ds[0].PixelSpacing]           # [giữa hàng, giữa cột]
    img.SetSpacing((ps[1], ps[0], dz))
    img.SetOrigin(tuple(float(x) for x in ds[0].ImagePositionPatient))
    img.SetDirection(tuple(np.column_stack([r, c, n]).ravel()))
    qc = {"n_slices": len(ds), "n_dup_dropped": n_dup, "rows": arr.shape[1], "cols": arr.shape[2],
          "sp_x": ps[1], "sp_y": ps[0], "sp_z": dz,
          "gap_uniform": uniform, "gap_max_dev": float(np.abs(gaps - dz).max()) if len(gaps) else 0.0,
          "normal_x": n[0], "normal_y": n[1], "normal_z": n[2],
          "center_z": float(np.mean([np.array(d.ImagePositionPatient, float)[2] for d in ds]))}
    return img, qc


def convert_patient(args):
    sel, files_sag, ax_blocks = args
    pid = sel["patient_id"]
    out = []
    try:
        img, qc = build_volume(files_sag)
        path = SAG_DIR / f"{pid:04d}.nii.gz"
        sitk.WriteImage(img, str(path), useCompression=True)
        out.append({"patient_id": pid, "kind": "sag", "block": 0, "file": path.name, **qc})

        built = [build_volume(f) for f in ax_blocks]
        built.sort(key=lambda t: -t[1]["center_z"])          # b1 = khối cao nhất
        for i, (img, qc) in enumerate(built, 1):
            path = AX_DIR / f"{pid:04d}_b{i}.nii.gz"
            sitk.WriteImage(img, str(path), useCompression=True)
            out.append({"patient_id": pid, "kind": "ax", "block": i, "file": path.name, **qc})
    except Exception as e:
        out.append({"patient_id": pid, "kind": "error", "error": str(e)[:300]})
    return out


def split_by_gap(g):
    """Hai khối cho 2 đĩa khác nhau có thể trùng góc nghiêng -> bị gom chung.
    Tách tiếp khi khoảng cách giữa 2 lát liền kề > 1,5 lần khoảng cách thường."""
    n = np.cross(g[IOP[:3]].values[0], g[IOP[3:]].values[0])
    pos = g[["ipp_x", "ipp_y", "ipp_z"]].values @ n
    g = g.assign(_pos=pos).sort_values("_pos")
    # bỏ vị trí trùng (lát lưu 2 lần) trước khi tính khoảng cách
    u = np.unique(g._pos.round(2).values)
    if len(u) < 3:
        return [g]
    gaps = np.diff(u)
    cuts = u[1:][gaps > 1.5 * np.median(gaps)]
    block_id = np.searchsorted(cuts, g._pos.round(2).values, side="right")
    return [b for _, b in g.groupby(block_id)]


def jobs(sel, cand):
    for _, s in sel.iterrows():
        pid = s.patient_id
        c = cand[cand.patient_id == pid]
        sag = c[(c.study_dir == s.study_dir) & (c.series_dir == s.sag_series)]
        # SAG có >1 hướng: giữ khối lớn nhất
        sag = sag[sag.orient_key == sag.orient_key.value_counts().idxmax()]
        ax = c[(c.study_dir == s.ax_study_dir) & (c.series_dir == s.ax_series)]
        root = MRI_DIR / f"{pid:04d}"
        f = lambda g: [root / r.study_dir / r.series_dir / r.file for r in g.itertuples()]
        blocks = [b for _, g in ax.groupby("orient_key") for b in split_by_gap(g)]
        yield (s.to_dict(), f(sag), [f(b) for b in blocks])


# ----------------------------------------------------------------- QC hình học
def axial_line_on_sag(sag, ax):
    """Giao tuyến giữa lát giữa của khối axial và ảnh sagittal, theo tọa độ pixel sag."""
    mid = ax.GetSize()[2] // 2
    cx, cy = (ax.GetSize()[0] - 1) / 2, (ax.GetSize()[1] - 1) / 2
    pts = []
    for t in np.linspace(-cy, cy, 40):     # đi dọc hướng cột của ảnh axial (trước -> sau)
        p = ax.TransformContinuousIndexToPhysicalPoint((cx, cy + t, mid))
        i = sag.TransformPhysicalPointToContinuousIndex(p)
        pts.append((i[0], i[1]))
    return np.array(pts)


def qc_figure(vols):
    pids = [p for p in QC_PATIENTS if p in set(vols.patient_id)]
    fig, axes = plt.subplots(1, len(pids), figsize=(3.2 * len(pids), 4))
    for axp, pid in zip(np.atleast_1d(axes), pids):
        sag = sitk.ReadImage(str(SAG_DIR / f"{pid:04d}.nii.gz"))
        # đọc lại từ NIfTI (RAS) để kiểm tra luôn việc ghi file
        a = sitk.GetArrayFromImage(sag)
        mid = a.shape[0] // 2
        axp.imshow(a[mid], cmap="gray",
                   vmax=np.percentile(a[mid], 99.5))
        for f in sorted(AX_DIR.glob(f"{pid:04d}_b*.nii.gz")):
            line = axial_line_on_sag(sag, sitk.ReadImage(str(f)))
            axp.plot(line[:, 0], line[:, 1], lw=1.5)
            axp.text(line[-1, 0] + 3, line[-1, 1], f.stem.split("_")[1].replace(".nii", ""),
                     color="yellow", fontsize=7, va="center")
        axp.set_title(f"BN {pid:04d}", fontsize=9)
        axp.axis("off")
    fig.suptitle("Vị trí các khối axial (vạch màu) chiếu lên lát sagittal giữa", fontsize=10)
    fig.tight_layout()
    out = FIGURES / "qc_s02_geometry.png"
    fig.savefig(out, dpi=130)
    print(f"Đã lưu {out}")


# ----------------------------------------------------------------- main
def main():
    SAG_DIR.mkdir(parents=True, exist_ok=True)
    AX_DIR.mkdir(parents=True, exist_ok=True)
    cand = load_candidates()
    sel = choose(series_table(cand))
    sel.to_csv(TABLES / "series_selected.csv", index=False)
    print(f"Đã chọn series cho {len(sel)} bệnh nhân -> series_selected.csv")

    with Pool(8) as pool:
        res = pool.map(convert_patient, list(jobs(sel, cand)), chunksize=4)
    vols = pd.DataFrame([r for rs in res for r in rs])
    vols.to_csv(TABLES / "nifti_volumes.csv", index=False)

    print("\n=== TÓM TẮT ===")
    err = vols[vols.kind == "error"]
    print(f"Lỗi: {len(err)}")
    if len(err):
        print(err[["patient_id", "error"]].to_string(index=False))
    ok = vols[vols.kind != "error"]
    dup = ok[ok.n_dup_dropped > 0]
    print(f"BN có lát bị lưu trùng (đã bỏ): {dup.patient_id.nunique()} "
          f"({int(dup.n_dup_dropped.sum())} lát)")
    print(f"File NIfTI: SAG {(ok.kind == 'sag').sum()} | AX {(ok.kind == 'ax').sum()} khối")
    print(f"BN có >1 ứng viên SAG: {(sel.sag_n_candidates > 1).sum()} | "
          f">1 ứng viên AX: {(sel.ax_n_candidates > 1).sum()} | "
          f"AX khác study với SAG: {(~sel.ax_same_study).sum()}")
    print("\nSố khối axial / BN:")
    print(ok[ok.kind == "ax"].groupby("patient_id").size().value_counts().sort_index().to_string())
    print("\nSố lát mỗi khối axial:")
    print(ok[ok.kind == "ax"].n_slices.value_counts().sort_index().to_string())
    for k in ["sag", "ax"]:
        v = ok[ok.kind == k]
        print(f"\n{k.upper()}: lát {v.n_slices.min()}-{v.n_slices.max()} | "
              f"pixel {v.sp_x.min():.2f}-{v.sp_x.max():.2f} mm | "
              f"khoảng cách lát {v.sp_z.min():.2f}-{v.sp_z.max():.2f} mm | "
              f"không đều: {(~v.gap_uniform.astype(bool)).sum()}")
    qc_figure(ok)


if __name__ == "__main__":
    main()
