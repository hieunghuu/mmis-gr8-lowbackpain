# -*- coding: utf-8 -*-
"""S03 - Chạy thử TotalSpineSeg trên vài ca để đo thời gian, RAM và xem kết quả.

TotalSpineSeg cài trong môi trường riêng totalspineseg/.venv-tss (Python 3.12):
    uv venv .venv-tss --python 3.12
    uv pip install --python .venv-tss/Scripts/python.exe torch --index-url https://download.pytorch.org/whl/cpu
    uv pip install --python .venv-tss/Scripts/python.exe "totalspineseg[nnunetv2]"
    uv pip install --python .venv-tss/Scripts/python.exe "kornia<0.8"
(macOS/Linux: thay .venv-tss/Scripts/python.exe bằng .venv-tss/bin/python. Hoặc cài thẳng vào
 venv đang chạy script (Python 3.12) - script tìm totalspineseg cạnh sys.executable.)
(kornia 0.8.x bỏ kornia.core.Tensor mà auglab - phụ thuộc của TotalSpineSeg - cần,
 gây ImportError khi nạp mô hình.)
Trọng số mô hình tự tải lần đầu vào totalspineseg/.tss_data.

Script này chạy bằng Python chính, gọi totalspineseg như một tiến trình con và lấy
mẫu RAM (tổng cả cây tiến trình) mỗi 0,5 giây.

Chạy (từ thư mục totalspineseg/):
    python src/segmentation/s03_tss_pilot.py sag 1 2 100 230 300     # ảnh sagittal
    python src/segmentation/s03_tss_pilot.py ax 1                     # mọi khối axial của BN 1
Kết quả: outputs/tss_pilot/<tên>/  + 1 dòng log trong outputs/tables/segmentation/tss_pilot_log.csv
"""
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pandas as pd
import psutil

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))   # src/
from common import CODE, NIFTI, OUTPUTS, T_SEG

# ưu tiên .venv-tss riêng; không có thì dùng totalspineseg cùng venv với Python đang chạy
_TSS_BIN = CODE / ".venv-tss" / ("Scripts" if sys.platform == "win32" else "bin")
TSS_EXE = shutil.which("totalspineseg", path=f"{_TSS_BIN}{os.pathsep}{Path(sys.executable).parent}")
TSS_DATA = CODE / ".tss_data"
PILOT = OUTPUTS / "tss_pilot"


def run_monitored(cmd):
    """Chạy lệnh, trả về (mã thoát, giây, RAM đỉnh GB của cả cây tiến trình)."""
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
    if TSS_EXE is None:
        sys.exit(f"Không thấy totalspineseg trong {_TSS_BIN} hoặc {Path(sys.executable).parent}")
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
    print(f"\nMã thoát {code} | {secs:.0f} giây ({secs / len(files):.0f} giây/file) | "
          f"RAM đỉnh {peak:.2f} GB / {psutil.virtual_memory().total / 2**30:.1f} GB")

    log = T_SEG / "tss_pilot_log.csv"
    row = pd.DataFrame([{"run": name, "kind": kind, "n_files": len(files),
                         "exit_code": code, "seconds": round(secs, 1),
                         "sec_per_file": round(secs / len(files), 1),
                         "peak_ram_gb": round(peak, 2),
                         "time": time.strftime("%Y-%m-%d %H:%M")}])
    row.to_csv(log, mode="a", header=not log.exists(), index=False)


if __name__ == "__main__":
    main()
