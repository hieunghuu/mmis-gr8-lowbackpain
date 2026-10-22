from __future__ import annotations

import json
import logging
import os
import shutil
import threading
from datetime import datetime, timezone
from pathlib import Path

from .config import REPO_ROOT, Settings
from .db import Database
from .storage import Storage

log = logging.getLogger(__name__)


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


class JobWorker:
    def __init__(self, settings: Settings, db: Database, storage: Storage):
        self.settings = settings
        self.db = db
        self.storage = storage
        self.stop_event = threading.Event()
        self.thread: threading.Thread | None = None

    def start(self) -> None:
        recovered = self.db.recover_running(utcnow())
        if recovered:
            log.warning("Marked %d interrupted job(s) as failed", recovered)
        self.thread = threading.Thread(target=self._loop, name="spine-job-worker", daemon=True)
        self.thread.start()

    def stop(self) -> None:
        self.stop_event.set()
        if self.thread:
            self.thread.join(timeout=15)

    def _loop(self) -> None:
        while not self.stop_event.is_set():
            row = self.db.claim_next(utcnow())
            if row:
                self._process(row)
            else:
                self.stop_event.wait(self.settings.worker_poll_sec)

    def _process(self, row: dict) -> None:
        try:
            if self.settings.mock_worker:
                mask, labels, analysis = self._mock(row)
            else:
                mask, labels, analysis = self._real(row)
            relative = mask.resolve().relative_to(self.settings.data_dir).as_posix()
            self.db.complete(row["id"], output_path=relative, labels=labels,
                             analysis=analysis, finished_at=utcnow())
        except Exception as exc:
            code = getattr(exc, "code", "SEGMENTATION_FAILED")
            message = getattr(exc, "message", f"Lỗi xử lý: {exc}")
            tail = getattr(exc, "log_tail", None)
            log.exception("Job %s failed: %s", row["id"], message)
            self.db.fail(row["id"], code=code, message=message, log_tail=tail, finished_at=utcnow())

    def _real(self, row: dict) -> tuple[Path, list[int], dict | None]:
        os.environ.setdefault("TOTALSPINESEG_DATA", str(self.settings.totalspineseg_data))
        from ai.segment import segment

        input_path = self.storage.resolve(row["input_path"])
        root = self.storage.job_dir(row["id"])
        seg = segment(input_path, root / "output", iso=bool(row["opt_iso"]),
                      step1=bool(row["opt_step1"]), timeout=self.settings.job_timeout_sec,
                      log_path=root / "logs" / "totalspineseg.log", cancel_event=self.stop_event)
        analysis = None
        if not row["opt_iso"] and not row["opt_step1"]:
            try:
                from ai.analyze import AnalysisError, analyze
                analysis = analyze(input_path, seg.mask_path)
            except Exception as exc:
                code = getattr(exc, "code", "ANALYSIS_FAILED")
                message = getattr(exc, "message", "Không thể phân tích số đo sau segmentation")
                log.exception("Analysis failed for job %s", row["id"])
                analysis = {"qc": None, "levels": [], "lordosis_deg": None, "disclaimer": None,
                            "error": {"code": code, "message": message}}
        return seg.mask_path, seg.labels_present, analysis

    def _mock(self, row: dict) -> tuple[Path, list[int], dict | None]:
        root = self.storage.job_dir(row["id"])
        out = root / "output" / ("step1_output" if row["opt_step1"] else "step2_output")
        out.mkdir(parents=True, exist_ok=True)
        mask = out / f"{row['id']}.nii.gz"
        # Mock giữ nguyên geometry bằng cách dùng chính input làm mask, đúng hợp đồng MVP.
        # Dữ liệu chỉ để kiểm thử luồng API/viewer, không mang ý nghĩa phân đoạn.
        shutil.copy2(self.storage.resolve(row["input_path"]), mask)
        labels = [1, 2, 32, 41, 42, 43, 44, 45, 50, 91, 92, 93, 94, 95, 100]
        analysis = None
        demo_analysis = REPO_ROOT / "ai" / "demo" / "analysis_0100.json"
        if not row["opt_iso"] and not row["opt_step1"] and demo_analysis.exists():
            analysis = json.loads(demo_analysis.read_text(encoding="utf-8"))
        return mask, labels, analysis
