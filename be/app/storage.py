from __future__ import annotations

import os
import shutil
from pathlib import Path

from fastapi import UploadFile
from fastapi.concurrency import run_in_threadpool

from .errors import ApiError


CHUNK = 1024 * 1024


class Storage:
    def __init__(self, data_dir: Path, max_upload_mb: int):
        self.data_dir = Path(data_dir).resolve()
        self.jobs_dir = self.data_dir / "jobs"
        self.max_bytes = max_upload_mb * 1024 * 1024

    def job_dir(self, job_id: str) -> Path:
        path = (self.jobs_dir / job_id).resolve()
        if path.parent != self.jobs_dir.resolve():
            raise ValueError("invalid job id")
        return path

    def resolve(self, relative: str) -> Path:
        path = (self.data_dir / relative).resolve()
        if self.data_dir != path and self.data_dir not in path.parents:
            raise ValueError("path escapes data directory")
        return path

    async def save_upload(self, upload: UploadFile, job_id: str) -> tuple[str, int, dict | None]:
        """Lưu ảnh upload thành input/{job_id}.nii.gz; trả (đường dẫn tương đối, số byte, series DICOM đã chọn | None)."""
        name = Path(upload.filename or "").name
        lower = name.lower()
        is_zip = lower.endswith(".zip")
        if not (is_zip or lower.endswith(".nii") or lower.endswith(".nii.gz")):
            raise ApiError(400, "INVALID_FILE_TYPE",
                           "Chỉ chấp nhận file .nii, .nii.gz hoặc .zip (DICOM của một lần chụp)", {"filename": name})

        root = self.job_dir(job_id)
        input_dir = root / "input"
        input_dir.mkdir(parents=True, exist_ok=False)
        temp = input_dir / ("upload.zip" if is_zip else
                            "upload.nii.gz.part.nii.gz" if lower.endswith(".nii.gz") else "upload.part.nii")
        size = 0
        try:
            with temp.open("xb") as dst:
                while chunk := await upload.read(CHUNK):
                    size += len(chunk)
                    if size > self.max_bytes:
                        raise ApiError(413, "FILE_TOO_LARGE", f"File vượt quá {self.max_bytes // 2**20} MB",
                                       {"max_mb": self.max_bytes // 2**20})
                    dst.write(chunk)
            if size == 0:
                raise ApiError(400, "INVALID_ZIP" if is_zip else "INVALID_NIFTI", "File rỗng")
            target = input_dir / f"{job_id}.nii.gz"
            dicom = None
            if is_zip:   # đọc header + dựng ảnh mất ~0,2-2 s -> không chặn event loop
                dicom = await run_in_threadpool(self._convert_dicom, temp, target)
            else:
                self._validate_and_normalize(temp, target, lower.endswith(".gz"))
            relative = target.relative_to(self.data_dir).as_posix()
            return relative, size, dicom
        except Exception:
            shutil.rmtree(root, ignore_errors=True)
            raise
        finally:
            await upload.close()

    @staticmethod
    def _validate_and_normalize(temp: Path, target: Path, already_gz: bool) -> None:
        try:
            import nibabel as nib
            import numpy as np

            img = nib.load(str(temp))
            shape = img.shape
            if not (len(shape) == 3 or (len(shape) == 4 and shape[-1] == 1)):
                raise ValueError(f"cần ảnh 3D hoặc 4D có chiều cuối bằng 1, nhận {shape}")
            if any(int(x) <= 0 for x in shape[:3]) or not np.isfinite(img.affine).all():
                raise ValueError("shape hoặc affine không hợp lệ")
            zooms = img.header.get_zooms()[:3]
            if any(not np.isfinite(x) or x <= 0 for x in zooms):
                raise ValueError("voxel spacing không hợp lệ")
            if already_gz:
                # Force reading a small portion so truncated gzip/payloads fail before queuing.
                _ = np.asanyarray(img.dataobj[..., 0] if len(shape) == 4 else img.dataobj)[0, 0, 0]
                os.replace(temp, target)
            else:
                data = np.asanyarray(img.dataobj)
                if len(shape) == 4:
                    data = data[..., 0]
                nib.save(nib.Nifti1Image(data, img.affine, img.header), str(target))
                temp.unlink(missing_ok=True)
        except ApiError:
            raise
        except Exception as exc:
            raise ApiError(400, "INVALID_NIFTI", f"Không đọc được file NIfTI: {exc}") from None

    @staticmethod
    def _convert_dicom(zip_path: Path, target: Path) -> dict:
        from ai.dicom_to_nifti import ConvertError, convert

        try:
            info = convert(zip_path, target)
        except ConvertError as exc:
            raise ApiError(400, exc.code, exc.message) from None
        finally:
            zip_path.unlink(missing_ok=True)   # không giữ DICOM: header có thông tin bệnh nhân
        return {k: info[k] for k in ("series_description", "series_number", "n_series", "n_slices")}

    def delete_job(self, job_id: str) -> None:
        shutil.rmtree(self.job_dir(job_id), ignore_errors=True)
