# -*- coding: utf-8 -*-
"""S00 - Dong goi / tai mask TotalSpineSeg dung chung qua GitHub Release.

Mask 515 ca ton ~2,7 gio GPU (Kaggle) + 30 phut CPU de tao lai (buoc 3) -> chia se san qua
release `v0.1-tss-masks` cua repo hieunghuu/mmis-gr8-lowbackpain.

  --pack [--commit X] Dong goi outputs/tss/sag/ -> outputs/release/*.zip (nguoi tao release)
  --fetch             Tai tss_sag_masks_515.zip tu release, kiem tra SHA-256, giai nen vao
                      outputs/tss/sag/ (step2_output/, step1_levels/) + tss_qc.csv
  --fetch --previews  Tai them anh preview (1 anh/ca) vao outputs/tss/sag/preview/

Chay (tu thu muc goc code):  python src/s00_shared_data.py --fetch
"""
import argparse
import datetime as dt
import hashlib
import json
import shutil
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import CODE, OUTPUTS, TABLES

REPO = "hieunghuu/mmis-gr8-lowbackpain"
TAG = "v0.1-tss-masks"
BASE_URL = f"https://github.com/{REPO}/releases/download/{TAG}"
MASKS_ZIP = "tss_sag_masks_515.zip"
PREVIEWS_ZIP = "tss_sag_previews_515.zip"
TSS = OUTPUTS / "tss" / "sag"
RELEASE_DIR = OUTPUTS / "release"
PREVIEW_SUFFIX = "_sag_0.5_step2_output_tags.jpg"


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def git_commit():
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=CODE,
                              capture_output=True, text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


# ----------------------------------------------------------------- dong goi
def pack(commit=None):
    masks = sorted((TSS / "step2_output").glob("*.nii.gz"))
    levels = sorted((TSS / "step1_levels").glob("*.nii.gz"))
    previews = sorted((TSS / "preview").glob(f"*{PREVIEW_SUFFIX}"))
    assert len(masks) == 515 and len(levels) == 515, (len(masks), len(levels))
    RELEASE_DIR.mkdir(parents=True, exist_ok=True)

    files = {f"step2_output/{p.name}": p for p in masks}
    files.update({f"step1_levels/{p.name}": p for p in levels})
    files["tss_qc.csv"] = TABLES / "tss_qc.csv"
    manifest = {
        "tag": TAG, "created": dt.date.today().isoformat(), "code_commit": commit or git_commit(),
        "n_cases": len(masks),
        "source": "TotalSpineSeg (neuropoly) tren T2 TSE SAG; 512 ca Kaggle T4 + BN 420, 515, 542 "
                  "chay lai tren CPU sau khi sua quy tac chon series (README buoc 2, 4)",
        "labels": "1 tuy, 2 ong song, 41-45 L1-L5, 46 L6, 50 xuong cung, 91 T12-L1, 92-95 L1-L2..L4-L5, "
                  "96 L5-L6, 100 L5-S1",
        "qc": "tss_qc.csv: qc_pass 514/515, use_level 513/515 (BN 113, 245 co 6 dot that lung)",
        "sha256": {k: sha256(p) for k, p in files.items()},
    }
    # ZIP_STORED: .nii.gz da nen san
    with zipfile.ZipFile(RELEASE_DIR / MASKS_ZIP, "w", zipfile.ZIP_STORED) as z:
        for arc, p in files.items():
            z.write(p, arc)
        z.writestr("MANIFEST.json", json.dumps(manifest, ensure_ascii=False, indent=1))
    with zipfile.ZipFile(RELEASE_DIR / PREVIEWS_ZIP, "w", zipfile.ZIP_STORED) as z:
        for p in previews:
            z.write(p, f"preview/{p.name}")
    for name in (MASKS_ZIP, PREVIEWS_ZIP):
        p = RELEASE_DIR / name
        print(f"{name}: {p.stat().st_size / 2**20:.1f} MB  sha256={sha256(p)}")
    print(f"masks {len(masks)} | levels {len(levels)} | previews {len(previews)} | commit {manifest['code_commit']}")


# ----------------------------------------------------------------- tai ve
def download(name, dest):
    url = f"{BASE_URL}/{name}"
    print(f"Tai {url}")
    with urllib.request.urlopen(url) as r, open(dest, "wb") as f:
        shutil.copyfileobj(r, f)
    return dest


def fetch(previews):
    RELEASE_DIR.mkdir(parents=True, exist_ok=True)
    zpath = download(MASKS_ZIP, RELEASE_DIR / MASKS_ZIP)
    with zipfile.ZipFile(zpath) as z:
        manifest = json.loads(z.read("MANIFEST.json"))
        for arc, digest in manifest["sha256"].items():
            data = z.read(arc)
            if hashlib.sha256(data).hexdigest() != digest:
                raise SystemExit(f"Sai SHA-256: {arc} - tai lai")
            out = TABLES / arc if arc == "tss_qc.csv" else TSS / arc
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(data)
    print(f"Da giai nen {manifest['n_cases']} ca vao {TSS} (code commit {manifest['code_commit']}, "
          f"tao ngay {manifest['created']}); SHA-256 khop {len(manifest['sha256'])} file")
    if previews:
        zpath = download(PREVIEWS_ZIP, RELEASE_DIR / PREVIEWS_ZIP)
        with zipfile.ZipFile(zpath) as z:
            z.extractall(TSS)
        print(f"Da giai nen preview vao {TSS / 'preview'}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--pack", action="store_true")
    g.add_argument("--fetch", action="store_true")
    ap.add_argument("--previews", action="store_true")
    ap.add_argument("--commit", help="commit cua code da tao mask (khi thu muc khong phai repo git)")
    a = ap.parse_args()
    pack(a.commit) if a.pack else fetch(a.previews)


if __name__ == "__main__":
    main()
