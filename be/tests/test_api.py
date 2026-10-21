import time
from pathlib import Path

from fastapi.testclient import TestClient

from be.app.config import REPO_ROOT, Settings
from be.app.main import create_app


def settings(tmp_path: Path) -> Settings:
    return Settings(data_dir=tmp_path, database_path=tmp_path / "app.db",
                    totalspineseg_data=tmp_path / "models", mock_worker=True,
                    worker_poll_sec=0.01, serve_frontend=False)


def test_contract_and_mock_lifecycle(tmp_path: Path):
    app = create_app(settings(tmp_path))
    sample = REPO_ROOT / "ai" / "demo" / "0100_seg.nii.gz"
    with TestClient(app) as client:
        h = client.get("/api/v1/health")
        assert h.status_code == 200 and h.json()["api_version"].endswith("-mock")
        assert client.get("/api/v1/labels").json()["labels"]

        bad = client.post("/api/v1/jobs", files={"file": ("x.txt", b"bad")})
        assert bad.status_code == 400 and bad.json()["error"]["code"] == "INVALID_FILE_TYPE"

        with sample.open("rb") as f:
            created = client.post("/api/v1/jobs", files={"file": ("sample.nii.gz", f, "application/octet-stream")},
                                  data={"iso": "false", "step1_only": "false"})
        assert created.status_code == 202
        job_id = created.json()["job_id"]
        deadline = time.time() + 3
        job = None
        while time.time() < deadline:
            job = client.get(f"/api/v1/jobs/{job_id}").json()
            if job["status"] == "done":
                break
            time.sleep(0.02)
        assert job["status"] == "done"
        assert job["result"]["analysis"]["levels"]
        assert client.get(f"/api/v1/jobs/{job_id}/input").content[:2] == b"\x1f\x8b"
        assert client.get(f"/api/v1/jobs/{job_id}/result").content[:2] == b"\x1f\x8b"
        assert client.delete(f"/api/v1/jobs/{job_id}").status_code == 204
        assert client.get(f"/api/v1/jobs/{job_id}").status_code == 404


def test_invalid_options_and_unknown_job(tmp_path: Path):
    app = create_app(settings(tmp_path), start_worker=False)
    sample = REPO_ROOT / "ai" / "demo" / "0100_seg.nii.gz"
    with TestClient(app) as client, sample.open("rb") as f:
        response = client.post("/api/v1/jobs", files={"file": ("x.nii.gz", f)}, data={"iso": "maybe"})
        assert response.status_code == 400
        assert response.json()["error"]["code"] == "INVALID_OPTION"
        missing = client.get("/api/v1/jobs/00000000-0000-4000-8000-000000000000")
        assert missing.status_code == 404
