# -*- coding: utf-8 -*-
"""S02 - Chon series T2 TSE SAG + T2 TSE AX cho moi benh nhan, chuyen sang NIfTI.

Quy tac chon (dua tren dicom_index.csv cua s01)
-----------------------------------------------
* Chi xet anh chinh (bo localizer, POSDISP), ten series chua "t2_tse"
  (bo t2_tirm/STIR, trufi, ciss... vi do tuong phan khac).
* Mat cat lay theo HUONG THUC TE (cot plane tu ImageOrientationPatient), khong theo ten.
* SAG: uu tien study "L-SPINE*", roi truong nhin (FOV = Rows x PixelSpacing) >= 250 mm,
  roi series co nhieu lat nhat, hoa thi lay series chup SAU (SeriesNumber lon hon -
  thuong la chup lai vi lan dau bi rung). Dieu kien FOV loai anh chup phong to
  (vd BN 515: t2_tse_sag_448, FOV 160 mm, 25 lat) - khong du moc giai phau de
  TotalSpineSeg danh so tang.
  Truoc so lat con xet: tam series SAG cach tam vung anh axial (cung study) <= 100 mm.
  Anh axial luon chup tai cac dia that lung, nen dieu kien nay loai series SAG dat o
  vung khac (vd BN 420: series nguc C7-T12, lech 237 mm; BN 542: lech xuong chau 109 mm).
  Dung nguong (khong xep "gan nhat") de khong doi lua chon cua cac BN co series chup
  lai cung vi tri (chi lech vai mm).
* AX: uu tien CUNG study voi SAG da chon (de chung he toa do), roi study L-SPINE,
  roi nhieu lat nhat, roi series chup sau.

Tach khoi axial
---------------
Mot series T2 AX thuong gom 3-5 khoi, moi khoi nghieng song song mot dia dem.
Lat duoc gom khoi theo huong (ImageOrientationPatient lam tron 2 chu so), roi tach
tiep khi co khoang nhay vi tri lon (2 khoi cho 2 dia co the trung goc nghieng).
Moi khoi -> 1 file NIfTI rieng. Trong 1 series SAG neu co >1 huong thi giu khoi lon nhat.

Ghi NIfTI
---------
Lat sap theo vi tri that doc phap tuyen (ImagePositionPatient . normal), khong theo
InstanceNumber. Huong, goc, spacing lay tu header -> SimpleITK tu doi LPS sang RAS
khi ghi .nii.gz. Kiem tra khoang cach giua cac lat co deu khong.

Dau ra
------
outputs/nifti/sag/0001.nii.gz
outputs/nifti/ax/0001_b1.nii.gz, 0001_b2.nii.gz ... (b1 = khoi cao nhat, gan dau)
outputs/tables/series_selected.csv     - series chon cho moi BN + ly do
outputs/tables/nifti_volumes.csv       - moi file NIfTI 1 dong (kich thuoc, spacing, QC)
outputs/figures/qc_s02_geometry.png    - vi tri cac khoi axial chieu len anh sagittal

Chay (tu thu muc totalspineseg/):  python src/s02_select_convert.py
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
MIN_SAG_FOV_MM = 250      # 510/515 series SAG chuan co FOV 280 mm
MAX_SAG_AX_DIST_MM = 100  # tam SAG phai gan vung anh axial (cac dia that lung)
QC_PATIENTS = [1, 2, 100, 230, 300, 450]


# ----------------------------------------------------------------- chon series
def load_candidates():
    df = pd.read_csv(TABLES / "dicom_index.csv", low_memory=False)
    df = df[~df.is_localizer & ~df.is_posdisp
            & df.series_desc.str.lower().str.contains("t2_tse")
            & df.plane.isin(["SAG", "AX"])].copy()
    df["lspine"] = df.study_dir.str.upper().str.startswith("L-SPINE")
    df["fov_mm"] = df.rows * df.px_row_mm
    # toa do z (dau-chan, mm) cua TAM lat = goc + nua hang x huong cot + nua cot x huong hang
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
                   # dem vi tri lat khac nhau, vi co series bi luu trung moi lat 2 lan
                   n_slices=("slice_location", lambda s: s.round(1).nunique()),
                   n_blocks=("orient_key", "nunique"))
              .reset_index())


def choose(st):
    rows = []
    for pid, g in st.groupby("patient_id"):
        sag = g[g.plane == "SAG"].copy()
        sag["fov_ok"] = sag.fov_mm >= MIN_SAG_FOV_MM
        # tam vung anh axial cua tung study (trung binh theo so lat)
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
    """Danh sach file .ima cung huong -> sitk.Image 3D dung hinh hoc."""
    ds = [pydicom.dcmread(f) for f in files]
    iop = np.array(ds[0].ImageOrientationPatient, float)
    r, c = iop[:3], iop[3:]
    n = np.cross(r, c)
    pos = np.array([np.array(d.ImagePositionPatient, float) @ n for d in ds])
    order = np.argsort(pos, kind="stable")
    ds = [ds[i] for i in order]
    pos = pos[order]
    # 19 BN co moi lat bi luu 2 lan (pixel giong het, chi khac SOPInstanceUID):
    # bo lat trung vi tri, giu ban dau tien
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

    img = sitk.GetImageFromArray(arr.astype(np.int16))   # (z, hang, cot)
    ps = [float(x) for x in ds[0].PixelSpacing]           # [giua hang, giua cot]
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
        built.sort(key=lambda t: -t[1]["center_z"])          # b1 = khoi cao nhat
        for i, (img, qc) in enumerate(built, 1):
            path = AX_DIR / f"{pid:04d}_b{i}.nii.gz"
            sitk.WriteImage(img, str(path), useCompression=True)
            out.append({"patient_id": pid, "kind": "ax", "block": i, "file": path.name, **qc})
    except Exception as e:
        out.append({"patient_id": pid, "kind": "error", "error": str(e)[:300]})
    return out


def split_by_gap(g):
    """Hai khoi cho 2 dia khac nhau co the trung goc nghieng -> bi gom chung.
    Tach tiep khi khoang cach giua 2 lat lien ke > 1,5 lan khoang cach thuong."""
    n = np.cross(g[IOP[:3]].values[0], g[IOP[3:]].values[0])
    pos = g[["ipp_x", "ipp_y", "ipp_z"]].values @ n
    g = g.assign(_pos=pos).sort_values("_pos")
    # bo vi tri trung (lat luu 2 lan) truoc khi tinh khoang cach
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
        # SAG co >1 huong: giu khoi lon nhat
        sag = sag[sag.orient_key == sag.orient_key.value_counts().idxmax()]
        ax = c[(c.study_dir == s.ax_study_dir) & (c.series_dir == s.ax_series)]
        root = MRI_DIR / f"{pid:04d}"
        f = lambda g: [root / r.study_dir / r.series_dir / r.file for r in g.itertuples()]
        blocks = [b for _, g in ax.groupby("orient_key") for b in split_by_gap(g)]
        yield (s.to_dict(), f(sag), [f(b) for b in blocks])


# ----------------------------------------------------------------- QC hinh hoc
def axial_line_on_sag(sag, ax):
    """Giao tuyen giua lat giua cua khoi axial va anh sagittal, theo toa do pixel sag."""
    mid = ax.GetSize()[2] // 2
    cx, cy = (ax.GetSize()[0] - 1) / 2, (ax.GetSize()[1] - 1) / 2
    pts = []
    for t in np.linspace(-cy, cy, 40):     # di doc huong cot cua anh axial (truoc -> sau)
        p = ax.TransformContinuousIndexToPhysicalPoint((cx, cy + t, mid))
        i = sag.TransformPhysicalPointToContinuousIndex(p)
        pts.append((i[0], i[1]))
    return np.array(pts)


def qc_figure(vols):
    pids = [p for p in QC_PATIENTS if p in set(vols.patient_id)]
    fig, axes = plt.subplots(1, len(pids), figsize=(3.2 * len(pids), 4))
    for axp, pid in zip(np.atleast_1d(axes), pids):
        sag = sitk.ReadImage(str(SAG_DIR / f"{pid:04d}.nii.gz"))
        # doc lai tu NIfTI (RAS) de kiem tra luon viec ghi file
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
    fig.suptitle("Vi tri cac khoi axial (vach mau) chieu len lat sagittal giua", fontsize=10)
    fig.tight_layout()
    out = FIGURES / "qc_s02_geometry.png"
    fig.savefig(out, dpi=130)
    print(f"Da luu {out}")


# ----------------------------------------------------------------- main
def main():
    SAG_DIR.mkdir(parents=True, exist_ok=True)
    AX_DIR.mkdir(parents=True, exist_ok=True)
    cand = load_candidates()
    sel = choose(series_table(cand))
    sel.to_csv(TABLES / "series_selected.csv", index=False)
    print(f"Da chon series cho {len(sel)} benh nhan -> series_selected.csv")

    with Pool(8) as pool:
        res = pool.map(convert_patient, list(jobs(sel, cand)), chunksize=4)
    vols = pd.DataFrame([r for rs in res for r in rs])
    vols.to_csv(TABLES / "nifti_volumes.csv", index=False)

    print("\n=== TOM TAT ===")
    err = vols[vols.kind == "error"]
    print(f"Loi: {len(err)}")
    if len(err):
        print(err[["patient_id", "error"]].to_string(index=False))
    ok = vols[vols.kind != "error"]
    dup = ok[ok.n_dup_dropped > 0]
    print(f"BN co lat bi luu trung (da bo): {dup.patient_id.nunique()} "
          f"({int(dup.n_dup_dropped.sum())} lat)")
    print(f"File NIfTI: SAG {(ok.kind == 'sag').sum()} | AX {(ok.kind == 'ax').sum()} khoi")
    print(f"BN co >1 ung vien SAG: {(sel.sag_n_candidates > 1).sum()} | "
          f">1 ung vien AX: {(sel.ax_n_candidates > 1).sum()} | "
          f"AX khac study voi SAG: {(~sel.ax_same_study).sum()}")
    print("\nSo khoi axial / BN:")
    print(ok[ok.kind == "ax"].groupby("patient_id").size().value_counts().sort_index().to_string())
    print("\nSo lat moi khoi axial:")
    print(ok[ok.kind == "ax"].n_slices.value_counts().sort_index().to_string())
    for k in ["sag", "ax"]:
        v = ok[ok.kind == k]
        print(f"\n{k.upper()}: lat {v.n_slices.min()}-{v.n_slices.max()} | "
              f"pixel {v.sp_x.min():.2f}-{v.sp_x.max():.2f} mm | "
              f"khoang cach lat {v.sp_z.min():.2f}-{v.sp_z.max():.2f} mm | "
              f"khong deu: {(~v.gap_uniform.astype(bool)).sum()}")
    qc_figure(ok)


if __name__ == "__main__":
    main()
