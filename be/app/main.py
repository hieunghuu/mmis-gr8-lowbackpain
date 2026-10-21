from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

from .api import router
from .config import Settings
from .db import Database
from .errors import ApiError, api_error_handler, body, validation_error_handler
from .storage import Storage
from .worker import JobWorker

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger(__name__)


def create_app(settings: Settings | None = None, *, start_worker: bool = True) -> FastAPI:
    cfg = settings or Settings.from_env()
    cfg.prepare()
    db = Database(cfg.database_path)
    db.initialize()
    storage = Storage(cfg.data_dir, cfg.max_upload_mb)
    worker = JobWorker(cfg, db, storage)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        if start_worker:
            worker.start()
        yield
        if start_worker:
            worker.stop()

    app = FastAPI(title="Spine Segmentation Service", version=cfg.api_version, lifespan=lifespan)
    app.state.settings, app.state.db, app.state.storage, app.state.worker = cfg, db, storage, worker
    app.add_middleware(CORSMiddleware, allow_origins=list(cfg.cors_origins), allow_credentials=False,
                       allow_methods=["GET", "POST", "DELETE", "OPTIONS"], allow_headers=["Content-Type"],
                       expose_headers=["Content-Disposition", "Content-Length", "ETag", "Last-Modified"])
    app.add_exception_handler(ApiError, api_error_handler)
    app.add_exception_handler(RequestValidationError, validation_error_handler)

    @app.exception_handler(Exception)
    async def unexpected(_: Request, exc: Exception):
        log.exception("Unhandled request error", exc_info=exc)
        return JSONResponse(body("INTERNAL_ERROR", "Lỗi hệ thống không lường trước"), status_code=500)

    app.include_router(router)

    if cfg.serve_frontend and (cfg.frontend_dist / "index.html").is_file():
        from fastapi.staticfiles import StaticFiles
        assets = cfg.frontend_dist / "assets"
        if assets.is_dir():
            app.mount("/assets", StaticFiles(directory=assets), name="assets")

        @app.get("/{path:path}", include_in_schema=False)
        def frontend(path: str):
            candidate = (cfg.frontend_dist / path).resolve()
            if cfg.frontend_dist in candidate.parents and candidate.is_file():
                return FileResponse(candidate)
            return FileResponse(cfg.frontend_dist / "index.html")
    return app


app = create_app()
