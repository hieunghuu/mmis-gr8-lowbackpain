import sys
import time
from pathlib import Path

from fastapi.testclient import TestClient

import ai.segment
from be.app.config import REPO_ROOT, Settings
from be.app.main import create_app

DEMO_MASK = REPO_ROOT / "ai" / "demo" / "0100_seg.nii.gz"

# CLI giả cùng cú pháp `totalspineseg INPUT OUTPUT ...`: chép mask demo BN 100 vào step2_output/
FAKE_TSS = f"""
import shutil, sys
from pathlib import Path
out = Path(sys.argv[2]) / "step2_output"
out.mkdir(parents=True, exist_ok=True)
shutil.copy({str(DEMO_MASK)!r}, out / Path(sys.argv[1]).name)
"""


def test_real_worker_calls_segment_and_analyze(tmp_path: Path, monkeypatch):
    """MOCK_WORKER=0: BE -> ai.segment (subprocess) -> ai.analyze, chỉ thay mô hình bằng CLI giả.
    Bắt lỗi thiếu thư viện trong môi trường BE (vd scikit-learn) - mock mode không import ai.analyze."""
    fake = tmp_path / "fake_tss.py"
    fake.write_text(FAKE_TSS)
    monkeypatch.setattr(ai.segment, "TSS_CMD", [sys.executable, str(fake)])
    cfg = Settings(data_dir=tmp_path, database_path=tmp_path / "app.db", totalspineseg_data=tmp_path / "models",
                   mock_worker=False, worker_poll_sec=0.01, serve_frontend=False)

    with TestClient(create_app(cfg)) as client:
        # mask demo cùng lưới với ảnh BN 100 -> dùng làm ảnh input (ảnh thật không có trong Git)
        with DEMO_MASK.open("rb") as f:
            job_id = client.post("/api/v1/jobs", files={"file": ("0100.nii.gz", f)}).json()["job_id"]
        deadline = time.time() + 60
        while (job := client.get(f"/api/v1/jobs/{job_id}").json())["status"] not in ("done", "failed"):
            assert time.time() < deadline, "job không xong trong 60 s"
            time.sleep(0.05)

    assert job["status"] == "done", job["error"]
    result = job["result"]
    assert 41 in result["labels_present"] and 100 in result["labels_present"]
    analysis = result["analysis"]
    assert analysis["error"] is None, analysis["error"]
    assert [lv["level"] for lv in analysis["levels"]] == ["T12-L1", "L1-L2", "L2-L3", "L3-L4", "L4-L5", "L5-S1"]
    suggestions = [s for lv in analysis["levels"] for s in lv["suggestions"]]
    assert suggestions and all("literature" in s for s in suggestions)
    # hẹp ống sống L3-L4 (đường kính 6,38 mm) phải có mốc y văn
    assert any(s["literature"] and s["literature"].startswith("theo y văn: <") for s in suggestions)
    # mỗi dòng y văn kèm nguồn có link https
    assert all(s["literature_source"]["url"].startswith("https://") for s in suggestions if s["literature"])
