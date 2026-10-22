from __future__ import annotations

import json
import logging
import shutil
import subprocess
import uuid
from datetime import datetime
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, File, Form, Query, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response

from .config import Settings
from .db import Database
from .errors import ApiError
from .labels import LABELS
from .storage import Storage
from .worker import utcnow

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1")


def deps(request: Request) -> tuple[Settings, Database, Storage]:
    state = request.app.state
    return state.settings, state.db, state.storage


def valid_id(job_id: str) -> None:
    try:
        if str(uuid.UUID(job_id, version=4)) != job_id.lower():
            raise ValueError
    except ValueError:
        raise ApiError(404, "JOB_NOT_FOUND", "Không có job này", {"job_id": job_id}) from None


def parse_bool(value: str, name: str) -> bool:
    if value not in {"true", "false"}:
        raise ApiError(400, "INVALID_OPTION", f"{name} chỉ nhận true hoặc false", {"field": name})
    return value == "true"


def duration(row: dict) -> int | None:
    if not row.get("started_at") or not row.get("finished_at"):
        return None
    try:
        a = datetime.fromisoformat(row["started_at"].replace("Z", "+00:00"))
        b = datetime.fromisoformat(row["finished_at"].replace("Z", "+00:00"))
        return max(0, round((b - a).total_seconds()))
    except ValueError:
        return None


def job_view(row: dict, db: Database) -> dict:
    status = row["status"]
    result = None
    error = None
    if status == "done":
        analysis = json.loads(row["analysis"]) if row["analysis"] else None
        result = {
            "input_url": f"/api/v1/jobs/{row['id']}/input",
            "segmentation_url": f"/api/v1/jobs/{row['id']}/result",
            "labels_url": "/api/v1/labels",
            "labels_present": json.loads(row["labels_present"] or "[]"),
            "analysis": analysis,
        }
    elif status == "failed":
        error = {"code": row["error_code"] or "UNKNOWN", "message": row["error_message"] or "Job thất bại."}
        if row["log_tail"]:
            error["log_tail"] = row["log_tail"]
    return {
        "job_id": row["id"], "status": status,
        "queue_position": db.queue_position(row),
        "input": {"filename": row["original_filename"], "size_bytes": row["size_bytes"],
                  "dicom": json.loads(row["dicom_info"]) if row.get("dicom_info") else None},
        "options": {"iso": bool(row["opt_iso"]), "step1_only": bool(row["opt_step1"])},
        "created_at": row["created_at"], "started_at": row["started_at"],
        "finished_at": row["finished_at"], "duration_seconds": duration(row),
        "result": result, "error": error,
    }


def gpu_available() -> bool:
    try:
        import torch
        return bool(torch.cuda.is_available())
    except Exception:
        try:
            return subprocess.run(["nvidia-smi", "-L"], capture_output=True, timeout=2).returncode == 0
        except (OSError, subprocess.SubprocessError):
            return False


@router.get("/health")
def health(request: Request):
    settings, db, _ = deps(request)
    return {"status": "ok", "gpu_available": gpu_available(), "queue": db.counts(),
            "api_version": settings.api_version + ("-mock" if settings.mock_worker else "")}


@router.get("/labels")
def labels():
    return {"labels": LABELS}


@router.post("/jobs", status_code=202)
async def create_job(request: Request, file: UploadFile = File(...), iso: str = Form("false"),
                     step1_only: str = Form("false")):
    settings, db, storage = deps(request)
    opt_iso, opt_step1 = parse_bool(iso, "iso"), parse_bool(step1_only, "step1_only")
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > settings.max_upload_mb * 1024 * 1024 + 1024 * 1024:
        raise ApiError(413, "FILE_TOO_LARGE", f"File vượt quá {settings.max_upload_mb} MB",
                       {"max_mb": settings.max_upload_mb})
    if db.counts()["pending"] >= settings.max_pending_jobs:
        raise ApiError(503, "QUEUE_FULL", "Hàng chờ đã đầy, thử lại sau")

    job_id, created = str(uuid.uuid4()), utcnow()
    input_path, size, dicom = await storage.save_upload(file, job_id)
    try:
        db.insert({
            "id": job_id, "status": "pending", "original_filename": Path(file.filename or "scan.nii.gz").name,
            "size_bytes": size, "input_path": input_path,
            "dicom_info": json.dumps(dicom, ensure_ascii=False) if dicom else None, "opt_iso": int(opt_iso),
            "opt_step1": int(opt_step1), "created_at": created,
        })
    except Exception:
        storage.delete_job(job_id)
        raise
    return {"job_id": job_id, "status": "pending", "created_at": created,
            "links": {"self": f"/api/v1/jobs/{job_id}"}}


@router.get("/jobs")
def list_jobs(request: Request, status: Literal["pending", "running", "done", "failed"] | None = None,
              limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0)):
    _, db, _ = deps(request)
    rows, total = db.list(status, limit, offset)
    return {"items": [{"job_id": r["id"], "status": r["status"], "filename": r["original_filename"],
                       "created_at": r["created_at"]} for r in rows],
            "total": total, "limit": limit, "offset": offset}


@router.get("/jobs/{job_id}")
def get_job(job_id: str, request: Request):
    valid_id(job_id)
    _, db, _ = deps(request)
    row = db.get(job_id)
    if not row:
        raise ApiError(404, "JOB_NOT_FOUND", "Không có job này", {"job_id": job_id})
    return job_view(row, db)


def attachment(path: Path, filename: str) -> FileResponse:
    if not path.is_file():
        raise ApiError(500, "INTERNAL_ERROR", "File của job không còn trên máy chủ")
    return FileResponse(path, media_type="application/octet-stream", filename=filename)


@router.get("/jobs/{job_id}/input")
def get_input(job_id: str, request: Request):
    valid_id(job_id)
    _, db, storage = deps(request)
    row = db.get(job_id)
    if not row:
        raise ApiError(404, "JOB_NOT_FOUND", "Không có job này", {"job_id": job_id})
    return attachment(storage.resolve(row["input_path"]), f"{job_id}_input.nii.gz")


@router.get("/jobs/{job_id}/result")
def get_result(job_id: str, request: Request):
    valid_id(job_id)
    _, db, storage = deps(request)
    row = db.get(job_id)
    if not row:
        raise ApiError(404, "JOB_NOT_FOUND", "Không có job này", {"job_id": job_id})
    if row["status"] != "done" or not row["output_path"]:
        raise ApiError(409, "JOB_NOT_READY", "Job chưa hoàn thành")
    return attachment(storage.resolve(row["output_path"]), f"{job_id}_seg.nii.gz")


@router.delete("/jobs/{job_id}", status_code=204, response_class=Response)
def delete_job(job_id: str, request: Request):
    valid_id(job_id)
    _, db, storage = deps(request)
    outcome = db.delete_if_not_running(job_id)
    if outcome == "missing":
        raise ApiError(404, "JOB_NOT_FOUND", "Không có job này", {"job_id": job_id})
    if outcome == "running":
        raise ApiError(409, "JOB_RUNNING", "Job đang chạy, không xóa được")
    storage.delete_job(job_id)
    return Response(status_code=204)
