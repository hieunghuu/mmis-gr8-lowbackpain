from pathlib import Path

from be.app.db import Database


def row(job_id: str, created: str, status: str = "pending"):
    return {"id": job_id, "status": status, "original_filename": "x.nii.gz", "size_bytes": 1,
            "input_path": f"jobs/{job_id}/input/x.nii.gz", "created_at": created}


def test_queue_claim_and_delete(tmp_path: Path):
    db = Database(tmp_path / "app.db")
    db.initialize()
    db.insert(row("00000000-0000-4000-8000-000000000001", "2026-01-01T00:00:00Z"))
    db.insert(row("00000000-0000-4000-8000-000000000002", "2026-01-01T00:00:01Z"))
    second = db.get("00000000-0000-4000-8000-000000000002")
    assert db.queue_position(second) == 2
    claimed = db.claim_next("2026-01-01T00:00:02Z")
    assert claimed["id"].endswith("1") and claimed["status"] == "running"
    assert db.delete_if_not_running(claimed["id"]) == "running"
    assert db.delete_if_not_running(second["id"]) == "deleted"


def test_recover_running(tmp_path: Path):
    db = Database(tmp_path / "app.db")
    db.initialize()
    values = row("00000000-0000-4000-8000-000000000003", "2026-01-01T00:00:00Z", "running")
    db.insert(values)
    assert db.recover_running("2026-01-01T00:01:00Z") == 1
    recovered = db.get(values["id"])
    assert recovered["status"] == "failed"
    assert recovered["error_code"] == "WORKER_INTERRUPTED"
