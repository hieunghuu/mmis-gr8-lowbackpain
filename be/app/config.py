from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


def _bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    return default if value is None else value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    database_path: Path
    totalspineseg_data: Path
    max_upload_mb: int = 200
    job_timeout_sec: int = 900
    max_pending_jobs: int = 20
    cors_origins: tuple[str, ...] = ("http://localhost:5173", "http://127.0.0.1:5173")
    api_version: str = "1.0.0"
    mock_worker: bool = False
    worker_poll_sec: float = 1.0
    serve_frontend: bool = True
    frontend_dist: Path = REPO_ROOT / "fe" / "dist"

    @classmethod
    def from_env(cls) -> "Settings":
        data_dir = Path(os.getenv("DATA_DIR", str(REPO_ROOT / "be" / "data"))).resolve()
        origins = tuple(x.strip() for x in os.getenv(
            "CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
        ).split(",") if x.strip())
        return cls(
            data_dir=data_dir,
            database_path=Path(os.getenv("DATABASE_PATH", str(data_dir / "app.db"))).resolve(),
            totalspineseg_data=Path(os.getenv("TOTALSPINESEG_DATA", str(data_dir / "models"))).resolve(),
            max_upload_mb=int(os.getenv("MAX_UPLOAD_MB", "200")),
            job_timeout_sec=int(os.getenv("JOB_TIMEOUT_SEC", "900")),
            max_pending_jobs=int(os.getenv("MAX_PENDING_JOBS", "20")),
            cors_origins=origins,
            api_version=os.getenv("API_VERSION", "1.0.0"),
            mock_worker=_bool("MOCK_WORKER"),
            worker_poll_sec=float(os.getenv("WORKER_POLL_SEC", "1")),
            serve_frontend=_bool("SERVE_FRONTEND", True),
            frontend_dist=Path(os.getenv("FRONTEND_DIST", str(REPO_ROOT / "fe" / "dist"))).resolve(),
        )

    def prepare(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        (self.data_dir / "jobs").mkdir(parents=True, exist_ok=True)
        self.totalspineseg_data.mkdir(parents=True, exist_ok=True)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
