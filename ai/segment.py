# -*- coding: utf-8 -*-
""" AI của Spine Segmentation Service (docs/spec.md mục 5): gọi CLI TotalSpineSeg cho 1 ảnh NIfTI.

Worker của BE gọi:
  segment(input, out_dir, iso=, step1=, timeout=, log_path=) -> SegResult | raise SegmentationError

TotalSpineSeg cài cùng venv với BE; weights lấy từ biến môi trường TOTALSPINESEG_DATA (CLI tự đọc).
Thử trên máy demo:  python ai/segment.py <ảnh.nii.gz> <thư_mục_output> [timeout_giây]
"""
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import nibabel as nib
import numpy as np
import psutil

# Windows: Scripts/totalspineseg.exe, macOS/Linux: bin/totalspineseg - cùng thư mục với python đang chạy
TSS_CMD = [shutil.which("totalspineseg", path=str(Path(sys.executable).parent)) or "totalspineseg"]
LOG_TAIL_LINES = 30


@dataclass
class SegResult:
    mask_path: Path
    labels_present: list[int]
    duration_seconds: float


class SegmentationError(Exception):
    """code: SEGMENTATION_FAILED | OUTPUT_NOT_FOUND | TIMEOUT (spec mục 8)."""

    def __init__(self, code, message, log_tail=None):
        super().__init__(message)
        self.code, self.message, self.log_tail = code, message, log_tail


def _kill_tree(proc):
    # nnU-Net sinh tiến trình con; chỉ kill tiến trình cha thì con vẫn giữ RAM / GPU
    try:
        parent = psutil.Process(proc.pid)
        procs = parent.children(recursive=True) + [parent]
    except psutil.NoSuchProcess:
        return
    for p in procs:
        try:
            p.kill()
        except psutil.NoSuchProcess:
            pass
    psutil.wait_procs(procs, timeout=10)


def _tail(log_path):
    lines = Path(log_path).read_text(encoding="utf-8", errors="replace").splitlines()
    return "\n".join(lines[-LOG_TAIL_LINES:]) or None


def segment(input_path, out_dir, *, iso=False, step1=False, timeout=900, log_path=None):
    out_dir = Path(out_dir)
    log_path = Path(log_path) if log_path else out_dir.parent / "logs" / "totalspineseg.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [*TSS_CMD, str(input_path), str(out_dir), "--quiet"]
    if iso:
        cmd.append("--iso")
    if step1:
        cmd.append("--step1")

    t0 = time.monotonic()
    with open(log_path, "w", encoding="utf-8") as log:
        try:
            proc = subprocess.Popen(cmd, stdout=log, stderr=subprocess.STDOUT)   # list args, không qua shell
        except OSError as e:
            raise SegmentationError("SEGMENTATION_FAILED", f"Không chạy được TotalSpineSeg: {e}") from None
        try:
            code = proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            code = None
            _kill_tree(proc)
        except BaseException:                    # BE tắt giữa chừng -> không để lại tiến trình mồ côi
            _kill_tree(proc)
            raise

    if code is None:
        raise SegmentationError("TIMEOUT", f"Chạy quá {timeout} giây", _tail(log_path))
    if code != 0:
        raise SegmentationError("SEGMENTATION_FAILED", f"TotalSpineSeg thoát với mã {code}", _tail(log_path))
    masks = sorted((out_dir / ("step1_output" if step1 else "step2_output")).glob("*.nii.gz"))
    if len(masks) != 1:
        raise SegmentationError("OUTPUT_NOT_FOUND", f"Cần đúng 1 file mask, tìm thấy {len(masks)}",
                                _tail(log_path))

    values = np.unique(np.asanyarray(nib.load(masks[0]).dataobj))
    return SegResult(masks[0], [int(v) for v in values if v != 0], round(time.monotonic() - t0, 1))


if __name__ == "__main__":
    r = segment(sys.argv[1], sys.argv[2], timeout=int(sys.argv[3]) if len(sys.argv) > 3 else 900)
    print(f"{r.mask_path} | {r.duration_seconds} s | nhãn: {r.labels_present}")
