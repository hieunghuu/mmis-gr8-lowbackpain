import gzip
import io
import zipfile
from pathlib import Path

import numpy as np
import pydicom
from fastapi.testclient import TestClient
from pydicom.dataset import Dataset, FileMetaDataset
from pydicom.uid import ExplicitVRLittleEndian, MRImageStorage, generate_uid

from be.app.config import Settings
from be.app.main import create_app

STUDY = generate_uid()


def series(desc: str, te: float, n: int = 5) -> list[bytes]:
    """n lát DICOM MR sagittal giả (32 x 32) của một series - đủ tag cho ai/dicom_to_nifti.py."""
    uid, out = generate_uid(), []
    for i in range(n):
        meta = FileMetaDataset()
        meta.MediaStorageSOPClassUID, meta.MediaStorageSOPInstanceUID = MRImageStorage, generate_uid()
        meta.TransferSyntaxUID = ExplicitVRLittleEndian
        ds = Dataset()
        ds.file_meta = meta
        ds.SOPClassUID, ds.SOPInstanceUID = MRImageStorage, meta.MediaStorageSOPInstanceUID
        ds.Modality, ds.StudyInstanceUID, ds.SeriesInstanceUID = "MR", STUDY, uid
        ds.SeriesDescription, ds.SeriesNumber, ds.InstanceNumber = desc, 2, i + 1
        ds.ImageType, ds.EchoTime = ["ORIGINAL", "PRIMARY"], te
        ds.ImageOrientationPatient = [0, 1, 0, 0, 0, -1]          # pháp tuyến theo trục x -> sagittal
        ds.ImagePositionPatient = [i * 4.0, -16.0, 16.0]
        ds.PixelSpacing, ds.SliceThickness = [1, 1], 4
        ds.Rows = ds.Columns = 32
        ds.SamplesPerPixel, ds.PhotometricInterpretation = 1, "MONOCHROME2"
        ds.BitsAllocated, ds.BitsStored, ds.HighBit, ds.PixelRepresentation = 16, 16, 15, 0
        ds.PixelData = np.full((32, 32), i * 10, np.uint16).tobytes()
        buf = io.BytesIO()
        pydicom.dcmwrite(buf, ds, enforce_file_format=True)
        out.append(buf.getvalue())
    return out


def zipped(files: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name, data in files.items():
            z.writestr(name, data)
    return buf.getvalue()


def client(tmp_path: Path) -> TestClient:
    cfg = Settings(data_dir=tmp_path, database_path=tmp_path / "app.db", totalspineseg_data=tmp_path / "models",
                   mock_worker=True, serve_frontend=False)
    return TestClient(create_app(cfg, start_worker=False))


def test_dicom_zip_upload_picks_t2_sagittal(tmp_path: Path):
    files = {f"study/T2/{i}.dcm": b for i, b in enumerate(series("t2_tse_sag", 90))}
    files |= {f"study/T1/{i}.dcm": b for i, b in enumerate(series("t1_tse_sag", 10))}
    files["study/README.txt"] = b"not dicom"
    with client(tmp_path) as c:
        r = c.post("/api/v1/jobs", files={"file": ("study.zip", zipped(files))})
        assert r.status_code == 202, r.json()
        job = c.get(f"/api/v1/jobs/{r.json()['job_id']}").json()
        assert job["input"]["dicom"] == {"series_description": "t2_tse_sag", "series_number": 2,
                                         "n_series": 2, "n_slices": 5}
        nifti = gzip.decompress(c.get(f"/api/v1/jobs/{job['job_id']}/input").content)
        assert int.from_bytes(nifti[:4], "little") == 348          # header NIfTI-1
    job_dir = tmp_path / "jobs" / job["job_id"] / "input"
    assert sorted(p.name for p in job_dir.iterdir()) == [f"{job['job_id']}.nii.gz"]   # zip DICOM đã bị xóa


def test_nifti_upload_has_no_dicom_info(tmp_path: Path):
    sample = Path(__file__).resolve().parents[2] / "ai" / "demo" / "0100_seg.nii.gz"
    with client(tmp_path) as c, sample.open("rb") as f:
        job_id = c.post("/api/v1/jobs", files={"file": ("x.nii.gz", f)}).json()["job_id"]
        assert c.get(f"/api/v1/jobs/{job_id}").json()["input"]["dicom"] is None


def test_dicom_zip_errors(tmp_path: Path):
    cases = {
        "INVALID_ZIP": b"not a zip",
        "NO_DICOM": zipped({"a.txt": b"hello"}),
        "NO_SAGITTAL_T2": zipped({f"{i}.dcm": b for i, b in enumerate(series("t1_tse_sag", 10))}),
    }
    with client(tmp_path) as c:
        for code, data in cases.items():
            r = c.post("/api/v1/jobs", files={"file": ("study.zip", data)})
            assert r.status_code == 400 and r.json()["error"]["code"] == code, (code, r.json())
        assert c.get("/api/v1/jobs").json()["total"] == 0
    assert not any((tmp_path / "jobs").iterdir())                     # không để lại thư mục job
