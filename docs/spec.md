# Đặc tả giao tiếp – Spine Segmentation Service

Oct 16, 2026 · @Hieu

## 1. Tổng quan và phạm vi

Hệ thống nhận một ảnh MRI cột sống định dạng NIfTI, hoặc file zip DICOM của một lần chụp (hệ thống tự chọn series T2 sagittal rồi chuyển sang NIfTI), chạy [TotalSpineSeg](https://github.com/neuropoly/totalspineseg) dưới dạng job nền, rồi trả về mask phân đoạn đốt sống, đĩa đệm, tủy sống và ống sống để xem chồng lên ảnh gốc trên web. Sau phân đoạn, hệ thống đo theo từng tầng đĩa đệm và gợi ý bệnh có thể có ở mỗi tầng (mục 5, phân tích sau segmentation). Tài liệu này là hợp đồng giữa các thành phần: dev FE và BE làm song song được, chỉ cần bám đúng endpoint, payload và trạng thái mô tả ở đây.

| Thành phần | Công nghệ đề xuất | Trách nhiệm |
| --- | --- | --- |
| Frontend | React (Vite) + NiiVue | Upload file (NIfTI hoặc zip DICOM), theo dõi trạng thái job, hiển thị ảnh và mask |
| Backend API | FastAPI, Python ≥ 3.10 | Nhận và kiểm tra file, quản lý job, trả file kết quả |
| Chuyển DICOM | Python (`ai/dicom_to_nifti.py`), chạy trong request upload | Đọc header mọi file trong zip, chọn series T2 sagittal, dựng NIfTI; xóa DICOM gốc |
| Worker | Thread nền trong cùng process BE, 1 job mỗi lúc | Lấy job `pending` cũ nhất từ SQLite, gọi CLI TotalSpineSeg, cập nhật trạng thái |
| TotalSpineSeg | CLI dựa trên nnU-Net, chạy GPU CUDA | Phân đoạn ảnh, ghi mask ra thư mục output |
| Phân tích | Python (`ai/analyze.py`), chạy CPU trong worker | Từ ảnh + mask: QC tầng, số đo theo tầng, gợi ý bệnh theo bảng ngưỡng |
| SQLite | Một file `app.db` | Lưu job và metadata; bảng `jobs` cũng chính là hàng chờ |
| Lưu trữ file | Thư mục local `data/` | Lưu ảnh input, output, log |

&#91;embedded content: kiến trúc · 6 thành phần, giao thức trên từng cạnh\]

Chỉ Backend API mở cổng HTTP. Worker và TotalSpineSeg không có API mạng: API và worker trao đổi qua SQLite (không có hàng chờ riêng trong RAM), worker và TotalSpineSeg trao đổi qua tham số dòng lệnh và thư mục file.

**Trong phạm vi MVP**

- Mỗi job xử lý đúng 1 file: `.nii` / `.nii.gz`, hoặc `.zip` chứa DICOM của một lần chụp (nhiều series cũng được; hệ thống tự chọn series T2 sagittal, mục 5).
- Xử lý tuần tự, mỗi lúc 1 job trên 1 GPU.
- Không có đăng nhập; hệ thống chỉ chạy trên localhost hoặc mạng nội bộ.
- FE xem ảnh gốc, mask và chú thích nhãn.
- Phân tích sau segmentation: số đo theo tầng (T12-L1 … L5-S1) và gợi ý bệnh kèm độ tin cậy, chỉ cho ảnh sagittal T2 cột sống thắt lưng. Đây là **gợi ý để bác sĩ xem lại, không phải chẩn đoán**.

**Ngoài phạm vi MVP**

- Upload DICOM dạng nhiều file lẻ hoặc thư mục không nén (chỉ nhận một file `.zip`); người dùng tự chọn series.
- Nhiều người dùng, phân quyền, nhiều GPU, kết nối PACS.
- Chỉnh sửa mask; đo đạc thủ công trên viewer.
- Gợi ý bệnh cho ảnh axial (mặt cắt ngang) hoặc ảnh không phải cột sống thắt lưng.

## 2. Quy ước chung

Mọi giao tiếp giữa FE và BE đều là HTTP/JSON qua prefix `/api/v1`; ngoại lệ duy nhất là upload (multipart) và tải file ảnh (binary).

| Hạng mục | Quy ước |
| --- | --- |
| Base URL | `http://<host>:8000/api/v1` |
| Request JSON | `Content-Type: application/json; charset=utf-8` |
| Upload | `multipart/form-data` |
| Tải file ảnh | `application/octet-stream` kèm header `Content-Disposition: attachment; filename="..."` |
| Tên trường | `snake_case` |
| ID job | UUID v4 dạng chuỗi, do BE sinh |
| Thời gian | ISO 8601, múi giờ UTC, ví dụ `2026-10-16T12:30:00Z` |
| Kích thước upload tối đa | 200 MB, chỉnh qua biến `MAX_UPLOAD_MB` |
| CORS (lúc dev) | Cho phép origin `http://localhost:5173` |
| Đường dẫn file | Không bao giờ trả đường dẫn trên ổ đĩa ra API, chỉ trả URL tương đối |

Mọi lỗi HTTP (4xx, 5xx) dùng chung một dạng body. FE hiển thị `message`, còn logic xử lý thì dựa vào `code` (danh sách ở mục 8).

```json
{
  "error": {
    "code": "INVALID_FILE_TYPE",
    "message": "Chỉ chấp nhận file .nii hoặc .nii.gz",
    "details": { "filename": "scan.dcm" }
  }
}
```

## 3. API giữa FE và BE

FE chỉ cần 8 endpoint. Luồng chính gồm 4 bước: tạo job, poll trạng thái, tải ảnh gốc, tải mask.

| Method | Path | Mục đích | Thành công |
| --- | --- | --- | --- |
| GET | `/health` | Kiểm tra BE và GPU | 200 |
| POST | `/jobs` | Upload ảnh, tạo job | 202 |
| GET | `/jobs/{job_id}` | Xem trạng thái một job | 200 |
| GET | `/jobs` | Liệt kê job | 200 |
| GET | `/jobs/{job_id}/input` | Tải ảnh gốc để làm nền cho viewer | 200 |
| GET | `/jobs/{job_id}/result` | Tải mask kết quả | 200 |
| DELETE | `/jobs/{job_id}` | Xóa job và các file của job | 204 |
| GET | `/labels` | Bảng nhãn để tô màu và hiện chú thích | 200 |

### 3.1 GET /health

```json
{
  "status": "ok",
  "gpu_available": true,
  "queue": { "pending": 2, "running": 1 },
  "api_version": "1.0.0"
}
```

### 3.2 POST /jobs

Request dạng `multipart/form-data`:

| Trường | Kiểu | Bắt buộc | Mặc định | Ý nghĩa |
| --- | --- | --- | --- | --- |
| `file` | file | Có |  | Ảnh `.nii` / `.nii.gz`, hoặc `.zip` chứa DICOM của một lần chụp |
| `iso` | `true` / `false` | Không | `false` | Trả mask ở độ phân giải 1 mm đẳng hướng thay vì không gian ảnh gốc |
| `step1_only` | `true` / `false` | Không | `false` | Chỉ chạy step 1, ra một nhãn chung cho mọi đốt sống |

Response `202 Accepted`. FE lưu `job_id` lại rồi bắt đầu poll.

```json
{
  "job_id": "7c9e6679-7425-40de-944b-e07fc1f90ae7",
  "status": "pending",
  "created_at": "2026-10-16T12:30:00Z",
  "links": { "self": "/api/v1/jobs/7c9e6679-7425-40de-944b-e07fc1f90ae7" }
}
```

BE kiểm tra theo thứ tự sau và dừng ở lỗi đầu tiên gặp phải: `iso` / `step1_only` hợp lệ, kích thước khai báo (`Content-Length`), hàng chờ chưa đầy, đuôi file, kích thước thực khi đọc file, rồi nội dung:

- `.nii` / `.nii.gz`: `nibabel` đọc được, ảnh 3D (hoặc 4D có chiều cuối bằng 1), spacing và affine hợp lệ.
- `.zip`: chuyển DICOM sang NIfTI **ngay trong request** bằng `ai.dicom_to_nifti.convert()` (thường dưới 2 giây; chạy trong threadpool, không chặn các request khác). Lỗi chuyển đổi trả `400` với mã ở mục 8. Hàng chờ được kiểm tra trước bước này để không chuyển đổi vô ích khi hàng chờ đầy.

Sau bước này mọi job đều có ảnh NIfTI `input/{job_id}.nii.gz`; worker, `/input` và viewer không phân biệt ảnh đến từ NIfTI hay DICOM.

### 3.3 GET /jobs/{job\_id}

Đây là payload FE dùng nhiều nhất. Trường `result` chỉ có giá trị khi `status = done`, trường `error` chỉ có giá trị khi `status = failed`.

`input.dicom` là `null` khi upload NIfTI. Khi upload `.zip` DICOM, trường này cho biết series đã được chọn, để người dùng kiểm tra hệ thống chọn đúng chưa:

```json
"input": {
  "filename": "study_0100.zip", "size_bytes": 19456210,
  "dicom": { "series_description": "t2_tse_sag_384", "series_number": 2, "n_series": 6, "n_slices": 15 }
}
```

`n_series` là số series tìm thấy trong zip; `n_slices` là số lát của series đã chọn.

Khi đang chờ hoặc đang chạy:

```json
{
  "job_id": "7c9e6679-7425-40de-944b-e07fc1f90ae7",
  "status": "pending",
  "queue_position": 2,
  "input": { "filename": "sub-01_T2w.nii.gz", "size_bytes": 18350212, "dicom": null },
  "options": { "iso": false, "step1_only": false },
  "created_at": "2026-10-16T12:30:00Z",
  "started_at": null,
  "finished_at": null,
  "duration_seconds": null,
  "result": null,
  "error": null
}
```

Khi hoàn thành:

```json
{
  "job_id": "7c9e6679-7425-40de-944b-e07fc1f90ae7",
  "status": "done",
  "queue_position": null,
  "input": { "filename": "sub-01_T2w.nii.gz", "size_bytes": 18350212, "dicom": null },
  "options": { "iso": false, "step1_only": false },
  "created_at": "2026-10-16T12:30:00Z",
  "started_at": "2026-10-16T12:31:05Z",
  "finished_at": "2026-10-16T12:33:40Z",
  "duration_seconds": 155,
  "result": {
    "input_url": "/api/v1/jobs/7c9e6679-7425-40de-944b-e07fc1f90ae7/input",
    "segmentation_url": "/api/v1/jobs/7c9e6679-7425-40de-944b-e07fc1f90ae7/result",
    "labels_url": "/api/v1/labels",
    "labels_present": [1, 2, 41, 42, 43, 44, 45, 50, 92, 93, 94, 95, 100],
    "analysis": { "...": "xem mục 3.3.1" }
  },
  "error": null
}
```

Khi lỗi:

```json
{
  "job_id": "7c9e6679-7425-40de-944b-e07fc1f90ae7",
  "status": "failed",
  "finished_at": "2026-10-16T12:32:10Z",
  "result": null,
  "error": {
    "code": "SEGMENTATION_FAILED",
    "message": "TotalSpineSeg thoát với mã 1",
    "log_tail": "RuntimeError: CUDA out of memory ..."
  }
}
```

`labels_present` là danh sách nhãn thực sự xuất hiện trong mask, do worker tính ra. FE dựa vào đó để chỉ hiện chú thích cho những cấu trúc mà ảnh có.

#### 3.3.1 `result.analysis`

Kết quả phân tích sau segmentation (mục 5). Là `null` khi job chạy với `iso=true` hoặc `step1_only=true`, vì khi đó mask không đo được. Ví dụ (rút gọn còn 1 tầng, 1 gợi ý; thực tế luôn có 6 tầng):

```json
{
  "qc": { "ok": true, "warnings": [] },
  "levels": [
    {
      "level": "L4-L5",
      "missing": null,
      "measures": {
        "disc_height_mm": 3.542, "dhi": 0.127, "disc_csf_ratio": 0.109, "disc_vb_ratio": 0.279,
        "disc_post_bulge_mm": 1.776, "canal_ap_mm": 8.108, "canal_csa_approx_mm2": 111.016,
        "listhesis_mm": -1.743
      },
      "suggestions": [
        {
          "label": "foraminal_stenosis",
          "label_vi": "Hẹp lỗ liên hợp",
          "measure": "disc_post_bulge_mm",
          "measure_vi": "nhô sau (mm)",
          "value": 1.776,
          "rule": ">=",
          "threshold": 1.119,
          "threshold_unit": "gốc",
          "percentile": 79,
          "confidence": "vừa",
          "sensitivity": 0.71,
          "specificity": 0.72,
          "ppv": 0.53,
          "literature": null,
          "literature_source": null
        }
      ]
    }
  ],
  "lordosis_deg": 43.9,
  "disclaimer": "Gợi ý từ số đo trên ảnh, không phải chẩn đoán; bác sĩ cần xem lại.",
  "error": null
}
```

| Trường | Ý nghĩa |
| --- | --- |
| `qc.ok` | `false` khi thiếu đốt / đĩa, có đốt chuyển tiếp (6 đốt thắt lưng) hoặc thứ tự tầng sai. Khi đó vẫn có `measures` nhưng mọi `suggestions` rỗng, vì không chắc đánh số tầng |
| `qc.warnings[]` | `{code, message}`, code ở mục 8 (cảnh báo phân tích) |
| `levels[]` | Luôn 6 tầng theo thứ tự `T12-L1`, `L1-L2`, `L2-L3`, `L3-L4`, `L4-L5`, `L5-S1` |
| `levels[].missing` | `null`, hoặc `"disc"` / `"mid_slices"` khi tầng đó không đo được (`measures` rỗng) |
| `levels[].measures` | Số đo của tầng; số đo nào không tính được thì không có key. Đơn vị nằm trong tên (`_mm`, `_mm2`); `dhi`, `disc_csf_ratio`, `disc_vb_ratio` là tỉ số |
| `suggestions[].label`, `label_vi` | Mã bệnh và tên tiếng Việt để hiển thị |
| `suggestions[].measure`, `value`, `rule`, `threshold` | Quy tắc đã khớp: `value rule threshold`. Khi `threshold_unit = "z"` thì ngưỡng là z-score trong tầng, `value` vẫn là giá trị gốc |
| `suggestions[].percentile` | Vị trí của `value` so với 513 bệnh nhân cùng tầng (5 = thấp nhất 5 %, 95 = cao nhất 5 %; giới hạn trong 5–95) |
| `suggestions[].confidence` | `"cao"` / `"vừa"`, theo cận dưới khoảng tin cậy 95 % của AUC (≥ 0,80 / ≥ 0,70) |
| `suggestions[].sensitivity`, `specificity`, `ppv` | Độ nhạy, độ đặc hiệu, PPV của quy tắc này khi kiểm chứng chéo trên bệnh nhân chưa dùng để học |
| `suggestions[].literature` | Chuỗi hiển thị nguyên văn bên cạnh gợi ý: `value` rơi vào mức nào theo ngưỡng y văn, ví dụ `"theo y văn: < 10 mm - hẹp tuyệt đối"` hoặc `"theo y văn: chưa tới ngưỡng < 12 mm"`. Có cho đường kính trước–sau ống sống (< 10 / < 12 mm), diện tích ống sống (Schönström < 75 / < 100 mm²) và độ trượt (≥ 3 mm); `null` với số đo khác. Chỉ để tham khảo: thang đo của hệ thống thấp hơn y văn khoảng 2 mm với đường kính ống sống và độ trượt (`pipeline/src/analysis/s12_literature_compare.py`). Trường không bắt buộc, FE cũ bỏ qua được |
| `suggestions[].literature_source` | `{ "citation": "...", "url": "https://..." }`: bài gắn với ngưỡng y văn đó, FE hiện thành link cạnh dòng `literature`; `null` khi `literature` là `null`. Nhãn `citation` ghi rõ mức chắc chắn (vd "mốc mm theo nguồn thứ cấp"). Danh sách: `pipeline/README.md` mục 7, phần Nguồn |
| `lordosis_deg` | Góc ưỡn thắt lưng (độ), giữa trục đĩa L1-L2 và L5-S1 |
| `disclaimer` | Câu FE bắt buộc hiển thị cạnh bảng gợi ý |
| `error` | `null`, hoặc `{code, message}` khi phân tích lỗi (mục 8). Khi đó `qc` là `null`, `levels` rỗng |

### 3.4 GET /jobs

Query: `status` (không bắt buộc), `limit` (mặc định 20, tối đa 100), `offset` (mặc định 0). Kết quả sắp xếp theo `created_at` mới nhất trước.

```json
{
  "items": [
    { "job_id": "7c9e6679-...", "status": "done", "filename": "sub-01_T2w.nii.gz", "created_at": "2026-10-16T12:30:00Z" }
  ],
  "total": 1,
  "limit": 20,
  "offset": 0
}
```

### 3.5 GET /jobs/{job\_id}/input và /result

Cả hai trả binary `.nii.gz`; với job upload DICOM, `/input` trả ảnh NIfTI đã chuyển đổi. Gọi `/result` khi job chưa `done` thì nhận `409 JOB_NOT_READY`. Tên file trả về là `{job_id}_input.nii.gz` và `{job_id}_seg.nii.gz`, không dùng tên file gốc.

### 3.6 DELETE /jobs/{job\_id}

Thành công trả `204 No Content`, không có body. Nếu job đang `running` thì trả `409 JOB_RUNNING`. Job `pending` bị xóa thì tự ra khỏi hàng chờ, vì hàng chờ chính là các dòng `pending` trong DB.

API xóa bằng `DELETE FROM jobs WHERE id = ? AND status <> 'running'`. Nếu không xóa được dòng nào mà job vẫn tồn tại, nghĩa là worker vừa lấy job đó, thì trả `409 JOB_RUNNING`. Câu lệnh này tránh tình huống xóa đúng lúc worker đổi job sang `running`.

### 3.7 GET /labels

BE đọc file `tss_map.json` có sẵn trong package TotalSpineSeg và trả về kèm màu gợi ý, để FE không phải tự hard-code bảng nhãn.

```json
{
  "labels": [
    { "value": 1, "name": "spinal_cord", "group": "cord", "color": "#FFD700" },
    { "value": 2, "name": "spinal_canal", "group": "canal", "color": "#00BFFF" },
    { "value": 41, "name": "vertebrae_L1", "group": "vertebra", "color": "#E6194B" },
    { "value": 95, "name": "disc_L4_L5", "group": "disc", "color": "#3CB44B" }
  ]
}
```

## 4. Vòng đời job

Một job có đúng 4 trạng thái: `pending`, `running`, `done`, `failed`. Chỉ worker được đổi trạng thái; API chỉ tạo job ở `pending` và đọc ra.

&#91;embedded content: vòng đời job · 4 trạng thái, 2 trạng thái cuối\]

Mọi lỗi trong lúc chạy đều dẫn về `failed`; job `pending` vẫn nằm trong DB nên vẫn ở trong hàng chờ khi BE khởi động lại.

**Hàng chờ bằng SQLite**

Không có hàng chờ riêng trong RAM: hàng chờ là các dòng `status = 'pending'` trong bảng `jobs`, xếp theo `created_at`. Nhờ vậy, xóa job, khôi phục sau restart và tính `queue_position` đều chỉ là truy vấn trên cùng một bảng.

- Worker lặp: `SELECT id FROM jobs WHERE status = 'pending' ORDER BY created_at LIMIT 1`. Nếu không có job thì ngủ 1 giây rồi hỏi lại.
- Nhận job bằng `UPDATE jobs SET status = 'running', started_at = ? WHERE id = ? AND status = 'pending'`. Nếu `rowcount = 0` (job vừa bị xóa) thì bỏ qua, quay lại vòng lặp.
- Độ trễ từ lúc tạo job đến lúc chạy tối đa khoảng 1 giây, không đáng kể so với thời gian phân đoạn.

**Quy tắc chuyển trạng thái**

1. `pending` sang `running`: worker lấy job `pending` cũ nhất trong DB, ghi `started_at`.
2. `running` sang `done`: CLI trả exit code 0 và tìm thấy file mask (mục 5), chạy xong bước phân tích, ghi `finished_at`, `labels_present` và `analysis`. Phân tích lỗi **không** làm job `failed`: job vẫn `done` (mask vẫn xem được), lỗi nằm trong `analysis.error`.
3. `running` sang `failed`: CLI trả exit code khác 0, hoặc không có file mask, hoặc chạy quá `JOB_TIMEOUT_SEC` (mặc định 900 giây).
4. `done` và `failed` là trạng thái cuối, không chuyển tiếp nữa. Muốn chạy lại thì tạo job mới.

**Khi BE khởi động lại**

- Trước khi bắt đầu vòng lặp, worker chuyển mọi job đang `running` thành `failed` với code `WORKER_INTERRUPTED`.
- Job đang `pending` không cần xử lý gì: chúng vẫn nằm trong DB và sẽ được chạy theo thứ tự `created_at`.

**Quy tắc polling ở FE**

- Gọi `GET /jobs/{job_id}` mỗi 3 giây khi trạng thái là `pending` hoặc `running`.
- Sau 2 phút chưa xong thì giãn ra 10 giây một lần.
- Dừng poll ngay khi nhận `done` hoặc `failed`.
- Nếu poll trả `404`, dừng và báo job không còn tồn tại.
- Lưu `job_id` vào URL (ví dụ `/jobs/7c9e...`) để người dùng tải lại trang mà vẫn tiếp tục theo dõi được.

## 5. Worker và TotalSpineSeg

Worker gọi TotalSpineSeg như một chương trình ngoài qua `subprocess`; giữa hai bên không có API mạng nào. Hợp đồng gồm: tham số dòng lệnh, biến môi trường, exit code và cấu trúc thư mục output.

**Lệnh gọi**

Cú pháp CLI là `totalspineseg INPUT OUTPUT_FOLDER [--step1] [--iso]`. INPUT có thể là một thư mục hoặc một file NIfTI (`.nii.gz` hoặc `.nii`) ([README](https://github.com/neuropoly/totalspineseg)).

- INPUT là file input của job, OUTPUT\_FOLDER là thư mục `output/` của job (mục 6).
- `iso=true` thì thêm cờ `--iso`; `step1_only=true` thì thêm cờ `--step1`.
- Thời gian chạy tối đa là `JOB_TIMEOUT_SEC`; quá hạn thì worker dừng process.

* Gọi CLI trực tiếp, không qua shell, để tránh chèn lệnh qua tên file.
* `TOTALSPINESEG_DATA` là thư mục chứa weights. Nếu không đặt biến này, weights mặc định nằm trong package dưới `totalspineseg/models`. Lần chạy đầu tool tự tải pre-trained model từ GitHub release, nên cần tải sẵn (warm-up) trước buổi demo.
* Toàn bộ stdout và stderr ghi vào `logs/totalspineseg.log`; 30 dòng cuối được đưa vào `error.log_tail` khi job lỗi.

**Cách xác định kết quả**

| Điều kiện | Trạng thái | Error code |
| --- | --- | --- |
| Exit code 0 và có đúng 1 file `.nii.gz` trong `step2_output/` (hoặc `step1_output/` nếu `step1_only`) | `done` |  |
| Exit code 0 nhưng không có file | `failed` | `OUTPUT_NOT_FOUND` |
| Exit code khác 0 | `failed` | `SEGMENTATION_FAILED` |
| Hết `JOB_TIMEOUT_SEC` | `failed` | `TIMEOUT` (worker kill process) |

Worker tìm file mask bằng glob trong thư mục output, không giả định trước tên file.

**Cấu trúc output của TotalSpineSeg**

Kết quả cuối cùng nằm ở `step2_output/`; các thư mục khác chỉ dùng để debug ([README](https://github.com/neuropoly/totalspineseg)).

```
output/
├── input/          # ảnh input đã tiền xử lý
├── preview/        # ảnh preview JPEG của các bước
├── step1_raw/
├── step1_output/
├── step1_cord/
├── step1_canal/
├── step1_levels/   # 1 voxel trên đường tâm ống sống tại mỗi tầng đĩa đệm
├── step2_raw/
└── step2_output/   # kết quả cuối cùng
```

Mặc định, mask được resample về không gian của ảnh input, nên FE overlay trực tiếp được. Cờ `--iso` cho mask ở độ phân giải gốc của model là 1 mm đẳng hướng. MVP giữ mặc định `iso=false`.

**Phân tích sau segmentation**

Sau khi tìm thấy mask, worker gọi trong cùng process (không qua subprocess):

```python
from ai.segment import segment
from ai.analyze import analyze, AnalysisError

seg = segment(input_path, output_dir, iso=iso, step1=step1_only, timeout=JOB_TIMEOUT_SEC)
if iso or step1_only:
    analysis = None
else:
    try:
        analysis = analyze(input_path, seg.mask_path)          # dict, mục 3.3.1
    except AnalysisError as e:
        analysis = {"qc": None, "levels": [], "lordosis_deg": None, "disclaimer": None,
                    "error": {"code": e.code, "message": e.message}}
```

- `analyze()` chạy CPU, vài giây mỗi ca; không cần GPU.
- Các bước: kiểm tra hình học (mask cùng lưới với ảnh, ảnh sagittal), QC nhãn, đo 8 số đo cho mỗi tầng (cùng code đo `pipeline/src/measurements/s09_level_features.py`), so với bảng ngưỡng.
- Bảng ngưỡng học từ 513 bệnh nhân của bộ dữ liệu (README `pipeline` mục 6), nằm trong `pipeline/outputs/tables/analysis/` (`threshold_rules.csv`, `threshold_cv_by_level.csv`, `measure_reference.csv`). BE chỉ đọc, không sửa.
- Mỗi (bệnh, tầng) dùng đúng 1 quy tắc: ngưỡng riêng của tầng nếu có, không thì ngưỡng z chung.
- Quy tắc có PPV < 0,05 khi kiểm chứng chéo (với ngưỡng z chung: PPV tại đúng tầng đó) bị bỏ qua, nên không bao giờ có gợi ý với `ppv` < 0,05.

**Nhận DICOM (trong `POST /jobs`, trước khi tạo job)**

BE gọi `ai.dicom_to_nifti.convert(zip, input/{job_id}.nii.gz)`. Worker không tham gia: khi job vào hàng chờ, ảnh đã là NIfTI.

```python
from ai.dicom_to_nifti import convert, ConvertError

info = convert(zip_path, input_path)   # dict | raise ConvertError(code, message) -> HTTP 400
```

- Giải nén vào thư mục tạm, giới hạn 2 GB và 20.000 file sau giải nén (chặn zip bomb). File được ghi với tên phẳng, không dùng đường dẫn trong zip, nên không có lỗi zip-slip. Thư mục tạm và file zip đều bị **xóa ngay** sau khi chuyển, vì header DICOM chứa thông tin bệnh nhân; NIfTI thì không.
- Đọc header mọi file, gom theo `SeriesInstanceUID`; file không phải ảnh DICOM bị bỏ qua. Không dựa vào tên thư mục hay tên file.
- Chọn series theo đúng quy tắc của `pipeline/src/dicom/s02_select_convert.py` (đã dùng cho 515 bệnh nhân học ngưỡng), nhưng đọc từ header để chạy được với máy của hãng khác:
  - T2: `EchoTime > 60 ms`; bỏ STIR / TIRM / FLAIR / TrueFISP / CISS;
  - bỏ localizer và ảnh dẫn xuất (`ImageType` có `DERIVED`, vd POSDISP);
  - mặt cắt tính từ `ImageOrientationPatient`, chỉ lấy sagittal;
  - ưu tiên: study L-SPINE > trường nhìn ≥ 250 mm > tâm cách vùng chụp axial ≤ 100 mm > nhiều lát nhất > chụp sau.
- Dựng ảnh bằng `build_volume()` của s02: xếp lát theo vị trí thật, bỏ lát lưu trùng, ghi đúng hình học.
- Đã kiểm tra: chọn đúng series cho 515/515 bệnh nhân (so với `series_selected.csv`); ảnh BN 100 tạo từ zip trùng từng voxel với ảnh của pipeline, nên `analysis` cũng trùng.

## 6. Lưu trữ

SQLite chỉ lưu metadata và đường dẫn tương đối; mọi ảnh nằm trên ổ đĩa trong `data/jobs/{job_id}/`. Xóa một job nghĩa là xóa dòng trong DB và xóa thư mục của job đó.

**Schema**

```sql
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS jobs (
  id                TEXT PRIMARY KEY,               -- UUID v4
  status            TEXT NOT NULL
                    CHECK (status IN ('pending','running','done','failed')),
  original_filename TEXT NOT NULL,
  size_bytes        INTEGER NOT NULL,
  input_path        TEXT NOT NULL,                  -- tương đối so với DATA_DIR
  dicom_info        TEXT,                           -- JSON input.dicom (mục 3.3), NULL nếu upload NIfTI
  output_path       TEXT,                           -- file mask cuối cùng
  opt_iso           INTEGER NOT NULL DEFAULT 0,     -- 0/1
  opt_step1         INTEGER NOT NULL DEFAULT 0,     -- 0/1
  labels_present    TEXT,                           -- JSON array, ví dụ "[1,2,41]"
  analysis          TEXT,                           -- JSON object mục 3.3.1, NULL nếu không phân tích
  error_code        TEXT,
  error_message     TEXT,
  log_tail          TEXT,
  created_at        TEXT NOT NULL,                  -- ISO 8601 UTC
  started_at        TEXT,
  finished_at       TEXT
);

CREATE INDEX IF NOT EXISTS idx_jobs_status_created
  ON jobs (status, created_at);
```

- Chỉ worker ghi khi đổi trạng thái; API chỉ `INSERT` lúc tạo job và `DELETE` khi xóa job.
- Mỗi request mở một connection riêng và đặt `timeout=10` để tránh lỗi `database is locked`.
- `queue_position` không lưu trong DB, mà tính bằng cách đếm số job `pending` có `created_at` nhỏ hơn.
- DB tạo trước khi có cột `dicom_info`: lúc khởi động BE tự thêm cột (`ALTER TABLE`), vì `CREATE TABLE IF NOT EXISTS` không thêm cột mới cho bảng đã có.

**Thư mục**

```
data/
├── app.db
├── models/                        # TOTALSPINESEG_DATA, chứa weights
└── jobs/
    └── {job_id}/
        ├── input/{job_id}.nii.gz      # BE đổi tên file khi lưu
        ├── output/                    # thư mục output của TotalSpineSeg
        └── logs/totalspineseg.log
```

BE đổi tên file upload thành `{job_id}.nii.gz` ngay khi lưu, vì tên file gốc có thể chứa tên bệnh nhân. File `.zip` DICOM không được lưu: chỉ giữ ảnh NIfTI đã chuyển đổi. `original_filename` chỉ để hiển thị trên FE; có thể bỏ trường này nếu dữ liệu chưa được ẩn danh.

## 7. FE hiển thị kết quả

Khi job `done`, FE nạp 2 volume vào NiiVue: ảnh gốc làm nền và mask làm overlay dạng nhãn. Màu và tên nhãn lấy từ `GET /labels`, không hard-code trong FE.

- URL của API không có đuôi file, nên khi nạp vào viewer phải khai báo rõ định dạng là `.nii.gz`.
- Phần chú thích bên cạnh viewer chỉ liệt kê các nhãn có trong `labels_present`.
- Thanh trượt opacity từ 0 đến 1 cho overlay; checkbox ẩn hoặc hiện từng nhóm (đốt sống, đĩa đệm, tủy, ống sống).

**Bảng nhãn của TotalSpineSeg**

Giá trị voxel trong mask được mã hóa theo vùng như bảng dưới. Bảng đầy đủ nằm trong file `totalspineseg/resources/labels_maps/tss_map.json` ([README](https://github.com/neuropoly/totalspineseg)).

| Giá trị | Cấu trúc |
| --- | --- |
| 1 | spinal\_cord |
| 2 | spinal\_canal |
| 11–17 | vertebrae\_C1 đến vertebrae\_C7 |
| 21–32 | vertebrae\_T1 đến vertebrae\_T12 |
| 41–45 | vertebrae\_L1 đến vertebrae\_L5 |
| 50 | sacrum |
| 63–67 | disc\_C2\_C3 đến disc\_C6\_C7 |
| 71–82 | disc\_C7\_T1 đến disc\_T11\_T12 |
| 91–95 | disc\_T12\_L1 đến disc\_L4\_L5 |
| 100 | disc\_L5\_S |

Với ảnh cột sống thắt lưng, các nhãn thường gặp là 41–45, 50 và 91–100.

**Màn hình tối thiểu**

1. Trang upload: chọn file (`.nii`, `.nii.gz` hoặc `.zip` DICOM), 2 checkbox tùy chọn (`iso`, `step1_only`), nút gửi.
2. Trang job: hiện trạng thái, vị trí trong hàng chờ, thời gian đã chạy; khi `failed` thì hiện `error.message`. Khi `input.dicom` khác `null`, hiện series đã chọn, ví dụ "DICOM: chọn series t2_tse_sag_384 (số 2, 15 lát) trong 6 series".
3. Viewer: mở khi `done`, gồm 3 mặt cắt kèm chú thích nhãn.
4. Bảng phân tích cạnh viewer (từ `result.analysis`, mục 3.3.1).
5. Danh sách job: lấy từ `GET /jobs`, có nút xóa.

**Bảng phân tích**

- Mỗi tầng một dòng (T12-L1 trên cùng). Cột: tầng, các gợi ý (`label_vi`, nhãn độ tin cậy `cao` / `vừa`), nút mở chi tiết.
- Chi tiết một gợi ý: `measure_vi` = `value` (`rule` `threshold`), "cao hơn / thấp hơn `percentile` % bệnh nhân cùng tầng", độ nhạy / độ đặc hiệu / PPV.
- Khi `literature` khác `null`: thêm dòng "↳ `literature`", kèm link `literature_source.citation` → `literature_source.url` (mở tab mới).
- Bấm vào tầng thì viewer nhảy tới đĩa đệm tầng đó (nhãn 91–95, 100).
- Luôn hiện `disclaimer` ngay trên bảng.
- `qc.ok = false`: hiện các `qc.warnings[].message` thay cho gợi ý, vẫn cho xem số đo.
- `analysis = null`: hiện "Không có phân tích (chỉ có khi `iso` và `step1_only` đều tắt)". `analysis.error` khác `null`: hiện `error.message`.

## 8. Bảng mã lỗi

Có hai loại lỗi. Lỗi request trả về ngay qua HTTP status kèm body `error`. Lỗi job nằm trong trường `error` của `GET /jobs/{job_id}` khi `status = failed`.

**Lỗi request**

| HTTP | Code | Khi nào |
| --- | --- | --- |
| 400 | `INVALID_FILE_TYPE` | Đuôi file không phải `.nii`, `.nii.gz` hoặc `.zip` |
| 400 | `INVALID_NIFTI` | `nibabel` không đọc được file, hoặc ảnh không phải 3D |
| 400 | `INVALID_ZIP` | File `.zip` rỗng, hỏng, hoặc quá lớn sau khi giải nén (> 2 GB hoặc > 20.000 file) |
| 400 | `NO_DICOM` | Zip không có file ảnh DICOM nào |
| 400 | `NO_SAGITTAL_T2` | Có DICOM nhưng không có series T2 sagittal phù hợp; `message` liệt kê các series tìm thấy |
| 400 | `CONVERSION_FAILED` | Chọn được series nhưng không dựng được ảnh 3D |
| 400 | `INVALID_OPTION` | `iso` hoặc `step1_only` không phải `true` / `false` |
| 404 | `JOB_NOT_FOUND` | Không có `job_id` này |
| 409 | `JOB_NOT_READY` | Gọi `/result` khi job chưa `done` |
| 409 | `JOB_RUNNING` | Xóa job đang chạy |
| 413 | `FILE_TOO_LARGE` | Vượt quá `MAX_UPLOAD_MB` |
| 503 | `QUEUE_FULL` | Số job `pending` đã chạm `MAX_PENDING_JOBS` |
| 500 | `INTERNAL_ERROR` | Lỗi không lường trước; chi tiết chỉ ghi vào log của BE |

**Lỗi job**

| Code | Khi nào | FE hiển thị gợi ý |
| --- | --- | --- |
| `SEGMENTATION_FAILED` | CLI thoát với exit code khác 0 | Thử lại; nếu lặp lại thì gửi `log_tail` cho người phụ trách |
| `OUTPUT_NOT_FOUND` | CLI chạy xong nhưng không có file mask | Báo lỗi hệ thống |
| `TIMEOUT` | Chạy quá `JOB_TIMEOUT_SEC` | Kiểm tra GPU hoặc kích thước ảnh |
| `WORKER_INTERRUPTED` | BE bị restart khi job đang chạy | Tạo lại job |

**Lỗi phân tích** (trong `analysis.error`, job vẫn `done`)

| Code | Khi nào | FE hiển thị gợi ý |
| --- | --- | --- |
| `GEOMETRY_MISMATCH` | Mask không cùng lưới với ảnh | Chạy lại với `iso=false` |
| `NOT_SAGITTAL` | Ảnh không phải mặt cắt sagittal | Chỉ phân tích ảnh sagittal T2 thắt lưng |
| `ANALYSIS_FAILED` | Lỗi khác khi đo | Báo lỗi hệ thống; mask vẫn xem được |

**Cảnh báo phân tích** (trong `analysis.qc.warnings`, không có gợi ý)

| Code | Khi nào |
| --- | --- |
| `MISSING_STRUCTURE` | Thiếu đốt L1–L5, xương cùng, hoặc đĩa L1-L2 … L5-S1 |
| `TRANSITIONAL_VERTEBRA` | Có đốt L6 (6 đốt thắt lưng): không chắc đánh số tầng |
| `LEVEL_ORDER` | Thứ tự đốt / đĩa từ đầu xuống chân không hợp lệ |

## 9. Môi trường chạy và triển khai

Toàn bộ hệ thống chạy trên một máy có GPU, trong một process Python. Docker không bắt buộc cho MVP.

**Cài đặt**

- Python ≥ 3.10 ([README](https://github.com/neuropoly/totalspineseg)).
- Gói totalspineseg cài kèm extra `nnunetv2`, để giữ đúng phiên bản nnU-Net đã được kiểm thử.
- Muốn dùng GPU CUDA thì cần PyTorch bản nhỏ hơn 2.6.
- BE cần một thư viện đọc được NIfTI để kiểm tra file upload, và `pydicom` để đọc DICOM (`be/requirements.txt`).
- Phân tích cần thêm `numpy`, `pandas`, `SimpleITK`, `scipy`, `matplotlib` (xem `pipeline/requirements.txt`). BE chạy từ gốc repo để `ai/analyze.py` tìm được `pipeline/src/` và các bảng ngưỡng.

**Biến môi trường**

| Biến | Mặc định | Ý nghĩa |
| --- | --- | --- |
| `DATA_DIR` | `./data` | Thư mục gốc chứa DB và các job |
| `TOTALSPINESEG_DATA` | `./data/models` | Nơi lưu weights của model |
| `MAX_UPLOAD_MB` | `200` | Kích thước file upload tối đa |
| `JOB_TIMEOUT_SEC` | `900` | Thời gian chạy tối đa của một job |
| `MAX_PENDING_JOBS` | `20` | Số job tối đa được chờ trong hàng |
| `CORS_ORIGINS` | `http://localhost:5173` | Origin FE được phép gọi khi dev |

**Chạy**

- Lúc dev: BE chạy ở cổng 8000, FE dev server chạy ở cổng 5173.
- Lúc demo: FE build thành file tĩnh và BE phục vụ luôn các file đó. Như vậy chỉ còn 1 cổng và không cần cấu hình CORS.
- Chỉ chạy 1 process BE (không dùng `--reload` hay nhiều worker của uvicorn khi demo): mỗi process sẽ có một worker thread, nên nhiều job chạy cùng lúc và tranh nhau GPU/CPU; `--reload` còn khởi động lại process làm job đang chạy thành `WORKER_INTERRUPTED`.

**Có cần Docker không**

Với phạm vi môn học thì không bắt buộc. Một `venv` cùng `requirements.txt` và README hướng dẫn chạy là đủ, nếu cả nhóm dùng chung một máy GPU. Chỉ nên làm thêm 1 `Dockerfile` (không cần compose hay Kubernetes) khi có ít nhất một trong các tình huống sau:

- Nhiều người cần chạy lại trên các máy khác nhau, hoặc giảng viên cần chấm bằng cách tự chạy.
- Cần cố định đúng cặp CUDA, PyTorch và nnU-Net để tránh lỗi môi trường.
- Rubric của môn có chấm phần triển khai.

Nếu làm Docker: dùng base image CUDA runtime, tải weights sẵn lúc build (hoặc mount `data/models`), mount `data/` thành volume, rồi chạy container có quyền truy cập GPU và mở cổng 8000.

## 10. Phân công và checklist

FE và BE làm song song được ngay từ ngày đầu: BE dựng mock trả đúng payload ở mục 3 trước, sau đó mới nối worker thật vào.

**Backend API**

- [x] Khởi tạo FastAPI, prefix `/api/v1`, bật CORS, có `/health`
- [x] Tạo schema SQLite khi khởi động, bật WAL
- [x] `POST /jobs`: kiểm tra file, đổi tên, lưu file, insert job, trả 202
- [x] `POST /jobs` nhận `.zip`: `convert()` trong threadpool, xóa zip, lưu `dicom_info`, đổi `ConvertError` thành lỗi 400 (mục 5)
- [x] `GET /jobs/{job_id}`, `GET /jobs`, `DELETE /jobs/{job_id}` theo đúng payload mục 3
- [x] `GET /jobs/{job_id}/input`, `/result`, `GET /labels`
- [x] Dùng chung format lỗi ở mục 2 và mã lỗi ở mục 8
- [x] Mock mode (`MOCK_WORKER=1`): job tự `done` sau 5 giây, trả lại chính ảnh input làm mask và `analysis` mẫu ở mục 3.3.1, để FE test trước khi có GPU

**Worker**

- [x] 1 worker thread lấy job `pending` cũ nhất từ SQLite (mục 4, hàng chờ bằng SQLite)
- [x] Gọi CLI theo mục 5, ghi log, xử lý timeout
- [x] Tìm file mask, tính `labels_present`, cập nhật trạng thái
- [x] Gọi `analyze()` sau segmentation (mục 5), lưu JSON vào cột `analysis`; lỗi phân tích không làm job `failed`
- [x] Khôi phục trạng thái khi BE khởi động lại (mục 4)
- [x] Script warm-up tải sẵn weights vào `TOTALSPINESEG_DATA`

**Frontend**

- [x] Trang upload, có báo lỗi validate; nhận `.nii`, `.nii.gz`, `.zip`
- [x] Trang job hiện series DICOM đã chọn (`input.dicom`); bảng phân tích hiện dòng y văn kèm link nguồn
- [x] Trang job: poll theo quy tắc ở mục 4, giữ `job_id` trên URL
- [x] Viewer NiiVue: ảnh nền, mask, LUT từ `/labels`, thanh opacity, chú thích nhãn
- [x] Bảng phân tích theo tầng (mục 7): gợi ý, độ tin cậy, chi tiết, cảnh báo QC, disclaimer
- [x] Danh sách job có nút xóa

**Tiêu chí hoàn thành MVP**

- [x] Upload 1 ảnh MRI sagittal cột sống thắt lưng, sau đó thấy mask L1–L5, sacrum và các đĩa đệm chồng đúng lên ảnh gốc
- [x] Cùng ảnh đó có bảng phân tích 6 tầng; ảnh có 6 đốt thắt lưng (vd BN 113 của bộ dữ liệu) chỉ hiện cảnh báo, không có gợi ý
- [x] Upload zip DICOM của BN 100 (cả lần chụp, 6 series): chọn đúng `t2_tse_sag_384`, và `analysis` trùng với khi upload NIfTI của cùng bệnh nhân
- [x] Đo và ghi lại thời gian chạy thực tế của một job trên GPU dùng để demo
- [x] Restart BE giữa chừng thì không mất job `pending`, job `running` chuyển thành `failed`
- [ ] Cả 13 lỗi request ở mục 8 đều tái hiện được bằng `curl`

## Nguồn

- [neuropoly/totalspineseg (README: cài đặt, CLI, cấu trúc output, bảng nhãn)](https://github.com/neuropoly/totalspineseg)
- [totalspineseg trên PyPI](https://pypi.org/project/totalspineseg/)
