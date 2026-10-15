# -*- coding: utf-8 -*-
"""S05 - Gop ket qua TotalSpineSeg (514 ca Kaggle + BN 515 chay CPU) va QC phan doan.

Kiem tra moi ca (chi tiet: README muc 4):
  geom            mask cung kich thuoc / spacing / goc / huong voi anh goc
  missing_vert    thieu dot L1-L5 (41-45) hoac xuong cung (50)
  missing_disc    thieu dia L1-L2 .. L5-S (92-95, 100); T12-L1 (91) khong bat buoc
  missing_canal   thieu ong song (2)
  order           thu tu dau -> chan theo z trong tam sai
  fragmented      khoi lien lon nhat < 90 % the tich nhan (dia) / < 70 % (dot)
  volume_outlier  (canh bao) the tich lech > 4 MAD so voi trung vi 515 ca, hoac < 25 % trung vi
  transitional    co dot L6 (6 dot that lung) -> loai khoi phan tich theo tang
use_level = qc_pass va khong transitional -> dung cho buoc 8 (ghep theo tang).

Chay (tu thu muc totalspineseg/):  python src/s05_tss_qc.py
"""
import random
import shutil
import sys
import zipfile
from multiprocessing import Pool
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import SimpleITK as sitk

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import OUTPUTS, NIFTI, TABLES, FIGURES, SEED

ZIP = OUTPUTS / "kaggle" / "tss_sag_results.zip"
# Ca chay lai tren CPU sau khi sua quy tac chon series o buoc 2 - GHI DE ket qua Kaggle:
#   515: Kaggle dung series phong to (FOV 160 mm) -> that bai; doi sang FOV 280 mm
#   420, 542: Kaggle dung series dat sai vung (nguc / lech xuong chau); doi sang series
#             gan vung anh axial
LOCAL_RERUNS = [OUTPUTS / "tss_pilot" / "sag_0515" / "output",
                OUTPUTS / "tss_pilot" / "sag_0420_0542" / "output"]
TSS = OUTPUTS / "tss" / "sag"
PARTS = ["step2_output", "step1_levels", "preview"]

NAMES = {1: "cord", 2: "canal", 41: "L1", 42: "L2", 43: "L3", 44: "L4", 45: "L5",
         50: "sacrum", 91: "T12-L1", 92: "L1-L2", 93: "L2-L3", 94: "L3-L4",
         95: "L4-L5", 100: "L5-S1"}
VERTS = [41, 42, 43, 44, 45, 50]
DISCS = [92, 93, 94, 95, 100]
# thu tu tu dau xuong chan
ORDER = [41, 92, 42, 93, 43, 94, 44, 95, 45, 100, 50]
LUMBAR = [41, 42, 43, 44, 45, 91, 92, 93, 94, 95, 100]
# Nguong khoi lien lon nhat: dia gan nhu luon lien 1 khoi (5 % thap nhat >= 0,999);
# mask DOT gom ca cung sau (cuong, mo gai) - tren lat day 4,8 mm, o cac lat lech ben cung
# sau tach khoi than dot -> 10-14 % the tich roi la binh thuong. Lan dau dung 0,9 cho ca
# hai -> 323 ca bi gan co sai.
FRAG_MIN_DISC, FRAG_MIN_VERT = 0.9, 0.7
STATS_LABELS = [1, 2] + LUMBAR + [50]


# ----------------------------------------------------------------- gop ket qua
def collect():
    if TSS.exists():
        shutil.rmtree(TSS)
    for p in PARTS:
        (TSS / p).mkdir(parents=True)
    with zipfile.ZipFile(ZIP) as z:
        for m in z.infolist():
            parts = Path(m.filename).parts       # ('tss_sag', 'step2_output', '0001.nii.gz')
            if len(parts) == 3 and parts[1] in PARTS and not m.is_dir():
                (TSS / parts[1] / parts[2]).write_bytes(z.read(m))
    for run in LOCAL_RERUNS:
        assert (run / "step2_output").exists(), f"Chua co ket qua chay lai: {run}"
        for p in PARTS:
            for f in (run / p).glob("*"):
                shutil.copy2(f, TSS / p / f.name)   # ghi de file cung ten tu Kaggle
    n = len(list((TSS / "step2_output").glob("*.nii.gz")))
    print(f"Da gop {n} mask -> {TSS}")
    return n


# ----------------------------------------------------------------- QC 1 ca
def qc_case(pid):
    m = sitk.ReadImage(str(TSS / "step2_output" / f"{pid:04d}.nii.gz"), sitk.sitkUInt8)
    img = sitk.ImageFileReader()
    img.SetFileName(str(NIFTI / "sag" / f"{pid:04d}.nii.gz"))
    img.ReadImageInformation()
    geom_ok = (m.GetSize() == img.GetSize()
               and np.allclose(m.GetSpacing(), img.GetSpacing(), atol=1e-3)
               and np.allclose(m.GetOrigin(), img.GetOrigin(), atol=1e-2)
               and np.allclose(m.GetDirection(), img.GetDirection(), atol=1e-3))

    shp = sitk.LabelShapeStatisticsImageFilter()
    shp.Execute(m)
    present = set(shp.GetLabels())
    stats = []
    for lab in STATS_LABELS:
        if lab not in present:
            continue
        vol = shp.GetPhysicalSize(lab)
        cx, cy, cz = shp.GetCentroid(lab)            # mm, he LPS (z+ = len dau)
        frac = np.nan
        if lab in LUMBAR:
            cc = sitk.RelabelComponent(sitk.ConnectedComponent(m == lab), sortByObjectSize=True)
            s2 = sitk.LabelShapeStatisticsImageFilter()
            s2.Execute(cc)
            frac = s2.GetPhysicalSize(1) / vol
        stats.append({"patient_id": pid, "label": lab, "name": NAMES[lab],
                      "volume_mm3": vol, "cx": cx, "cy": cy, "cz": cz, "largest_cc_frac": frac})

    z = {s["label"]: s["cz"] for s in stats}
    seq = [z[l] for l in ORDER if l in z]
    order_ok = all(a > b for a, b in zip(seq, seq[1:]))
    frag = [NAMES[s["label"]] for s in stats if s["label"] in LUMBAR and s["largest_cc_frac"]
            < (FRAG_MIN_VERT if s["label"] in VERTS else FRAG_MIN_DISC)]
    row = {
        "patient_id": pid,
        "geom": not geom_ok,
        "missing_vert": ",".join(NAMES[l] for l in VERTS if l not in present),
        "missing_disc": ",".join(NAMES[l] for l in DISCS if l not in present),
        "missing_canal": 2 not in present,
        "order": not order_ok,
        "fragmented": ",".join(frag),
        "has_T12_L1": 91 in present,
        # 6 dot that lung (L6 = 46): khong chac bac si dem tang tu tren hay tu duoi
        "transitional": 46 in present,
        "n_labels": len(present),
    }
    return row, stats


# ----------------------------------------------------------------- hinh preview
def montage(pids, out, title):
    if not pids:
        return
    n = len(pids)
    cols = min(n, 10)
    rows = (n + cols - 1) // cols
    fig, axes = plt.subplots(rows, cols, figsize=(2.2 * cols, 2.4 * rows))
    axes = np.atleast_1d(axes).ravel()
    for ax, pid in zip(axes, pids):
        f = TSS / "preview" / f"{pid:04d}_sag_0.5_step2_output_tags.jpg"
        if f.exists():
            ax.imshow(plt.imread(f))
        ax.set_title(f"BN {pid:04d}", fontsize=8)
    for ax in axes:
        ax.axis("off")
    fig.suptitle(title, fontsize=10)
    fig.tight_layout()
    fig.savefig(out, dpi=110)
    plt.close(fig)
    print(f"Da luu {out}")


def main():
    collect()
    pids = sorted(int(f.name[:4]) for f in (TSS / "step2_output").glob("*.nii.gz"))
    with Pool(8) as pool:
        res = pool.map(qc_case, pids, chunksize=8)
    qc = pd.DataFrame([r for r, _ in res])
    st = pd.DataFrame([s for _, ss in res for s in ss])

    # canh bao the tich bat thuong (so voi phan bo 515 ca, theo tung nhan)
    g = st.groupby("label").volume_mm3
    med = g.transform("median")
    mad = g.transform(lambda v: np.median(np.abs(v - np.median(v)))) * 1.4826
    st["volume_outlier"] = st.label.isin(LUMBAR) & (
        ((st.volume_mm3 - med).abs() > 4 * mad) | (st.volume_mm3 < 0.25 * med))
    vo = st[st.volume_outlier].groupby("patient_id").name.agg(",".join)
    qc["volume_outlier"] = qc.patient_id.map(vo).fillna("")

    hard = ["geom", "missing_vert", "missing_disc", "missing_canal", "order", "fragmented"]
    flag = lambda r, c: bool(r[c]) if not isinstance(r[c], str) else r[c] != ""
    qc["issues"] = qc.apply(lambda r: ";".join(
        c + (f"({r[c]})" if isinstance(r[c], str) else "") for c in hard if flag(r, c)), axis=1)
    qc["qc_pass"] = qc.issues == ""
    # dung cho phan tich THEO TANG (buoc 8): dat QC va khong co dot chuyen tiep
    qc["use_level"] = qc.qc_pass & ~qc.transitional
    qc.to_csv(TABLES / "tss_qc.csv", index=False)
    st.to_csv(TABLES / "tss_label_stats.csv", index=False)

    print("\n=== TOM TAT QC ===")
    print(f"So ca: {len(qc)} | DAT: {qc.qc_pass.sum()} | LOI: {(~qc.qc_pass).sum()}")
    for c in hard:
        k = qc.apply(lambda r: flag(r, c), axis=1)
        print(f"  {c:15s} {int(k.sum()):4d}  {qc[k].patient_id.tolist()[:15]}")
    print(f"  {'volume_outlier':15s} {int((qc.volume_outlier != '').sum()):4d} (canh bao, khong loai)")
    print(f"Co dia T12-L1: {qc.has_T12_L1.sum()} / {len(qc)}")
    print(f"Dot chuyen tiep (L6): {qc.transitional.sum()} {qc[qc.transitional].patient_id.tolist()}")
    print(f"=> Dung cho phan tich theo tang (use_level): {qc.use_level.sum()} / {len(qc)}")
    print("\nThe tich trung vi (mm3):")
    print(st[st.label.isin(LUMBAR + [50, 2])].groupby("name").volume_mm3.median().round(0)
            .reindex([NAMES[l] for l in [2] + ORDER + [91]]).to_string())

    random.seed(SEED)
    montage(sorted(random.sample(pids, 20)), FIGURES / "qc_s05_random.png",
            "TotalSpineSeg - 20 ca ngau nhien (seed 2026)")
    flagged = qc[~qc.qc_pass | qc.transitional].patient_id.tolist()
    flagged += qc[qc.qc_pass & (qc.volume_outlier != "")].patient_id.tolist()
    montage(flagged[:20], FIGURES / "qc_s05_flagged.png",
            "TotalSpineSeg - ca loi / dot chuyen tiep (truoc), canh bao the tich (sau)")


if __name__ == "__main__":
    main()
