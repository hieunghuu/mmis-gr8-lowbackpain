# -*- coding: utf-8 -*-
"""S03 - Chay thu TotalSpineSeg tren vai ca de do thoi gian, RAM va xem ket qua.

TotalSpineSeg cai trong moi truong rieng totalspineseg/.venv-tss (Python 3.12):
    uv venv .venv-tss --python 3.12
    uv pip install --python .venv-tss/Scripts/python.exe torch --index-url https://download.pytorch.org/whl/cpu
    uv pip install --python .venv-tss/Scripts/python.exe "totalspineseg[nnunetv2]"
    uv pip install --python .venv-tss/Scripts/python.exe "kornia<0.8"
(kornia 0.8.x bo kornia.core.Tensor ma auglab - phu thuoc cua TotalSpineSeg - can,
 gay ImportError khi nap mo hinh.)
Trong so mo hinh tu tai lan dau vao totalspineseg/.tss_data.

Script nay chay bang Python chinh, goi totalspineseg nhu mot tien trinh con va lay
mau RAM (tong ca cay tien trinh) moi 0,5 giay.

Chay (tu thu muc totalspineseg/):
    python src/s03_tss_pilot.py sag 1 2 100 230 300     # anh sagittal
    python src/s03_tss_pilot.py ax 1                     # moi khoi axial cua BN 1
Ket qua: outputs/tss_pilot/<ten>/  + 1 dong log trong outputs/tables/tss_pilot_log.csv
"""
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pandas as pd
import psutil

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import CODE, NIFTI, OUTPUTS, TABLES

TSS_EXE = CODE / ".venv-tss" / "Scripts" / "totalspineseg.exe"
TSS_DATA = CODE / ".tss_data"
PILOT = OUTPUTS / "tss_pilot"


def run_monitored(cmd):
    """Chay lenh, tra ve (ma thoat, giay, RAM dinh GB cua ca cay tien trinh)."""
    t0 = time.time()
    proc = subprocess.Popen(cmd)
    p = psutil.Process(proc.pid)
    peak = 0
    while proc.poll() is None:
        try:
            rss = p.memory_info().rss + sum(c.memory_info().rss
                                            for c in p.children(recursive=True))
            peak = max(peak, rss)
        except psutil.Error:
            pass
        time.sleep(0.5)
    return proc.returncode, time.time() - t0, peak / 2**30


def main():
    kind, pids = sys.argv[1], [int(x) for x in sys.argv[2:]]
    name = f"{kind}_" + "_".join(f"{p:04d}" for p in pids)
    inp, out = PILOT / name / "input", PILOT / name / "output"
    if inp.exists():
        shutil.rmtree(inp)
    inp.mkdir(parents=True)
    src = NIFTI / kind
    files = [f for p in pids for f in sorted(src.glob(f"{p:04d}*.nii.gz"))]
    for f in files:
        shutil.copy2(f, inp / f.name)
    print(f"{len(files)} file -> {inp}")

    cmd = [str(TSS_EXE), str(inp), str(out), "--data-dir", str(TSS_DATA),
           "--device", "cpu"]
    print(" ".join(cmd))
    code, secs, peak = run_monitored(cmd)
    print(f"\nMa thoat {code} | {secs:.0f} giay ({secs / len(files):.0f} giay/file) | "
          f"RAM dinh {peak:.2f} GB / {psutil.virtual_memory().total / 2**30:.1f} GB")

    log = TABLES / "tss_pilot_log.csv"
    row = pd.DataFrame([{"run": name, "kind": kind, "n_files": len(files),
                         "exit_code": code, "seconds": round(secs, 1),
                         "sec_per_file": round(secs / len(files), 1),
                         "peak_ram_gb": round(peak, 2),
                         "time": time.strftime("%Y-%m-%d %H:%M")}])
    row.to_csv(log, mode="a", header=not log.exists(), index=False)


if __name__ == "__main__":
    main()
