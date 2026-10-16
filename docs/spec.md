# Đặc tả giao tiếp – Spine Segmentation Service

Oct 16, 2026 · @Hieu

## 1. Tổng quan và phạm vi

Hệ thống nhận một ảnh MRI cột sống định dạng NIfTI, chạy [TotalSpineSeg](https://github.com/neuropoly/totalspineseg) dưới dạng job nền, rồi trả về mask phân đoạn đốt sống, đĩa đệm, tủy sống và ống sống để xem chồng lên ảnh gốc trên web. Tài liệu này là hợp đồng giữa các thành phần: dev FE và BE làm song song được, chỉ cần bám đúng endpoint, payload và trạng thái mô tả ở đây.

| Thành phần | Công nghệ đề xuất | Trách nhiệm |
| --- | --- | --- |
| Frontend | React (Vite) + NiiVue | Upload file, theo dõi trạng thái job, hiển thị ảnh và mask |
| Backend API | FastAPI, Python ≥ 3.10 | Nhận và kiểm tra file, quản lý job, trả file kết quả |
| Worker | Thread nền trong cùng process BE, 1 job mỗi lúc | Lấy job từ hàng chờ, gọi CLI TotalSpineSeg, cập nhật trạng thái |
| TotalSpineSeg | CLI dựa trên nnU-Net, chạy GPU CUDA | Phân đoạn ảnh, ghi mask ra thư mục output |
| SQLite | Một file `app.db` | Lưu job và metadata |
| Lưu trữ file | Thư mục local `data/` | Lưu ảnh input, output, log |

&#91;embedded content: kiến trúc · 6 thành phần, giao thức trên từng cạnh\]

Chỉ Backend API mở cổng HTTP. Worker và TotalSpineSeg không có API mạng: chúng trao đổi với nhau qua hàng chờ trong RAM, SQLite và thư mục file.

**Trong phạm vi MVP**

- Mỗi job xử lý đúng 1 file `.nii` hoặc `.nii.gz`.
- Xử lý tuần tự, mỗi lúc 1 job trên 1 GPU.
- Không có đăng nhập; hệ thống chỉ chạy trên localhost hoặc mạng nội bộ.
- FE xem ảnh gốc, mask và chú thích nhãn.

**Ngoài phạm vi MVP**

- Upload DICOM (để ở giai đoạn 2, xem mục 5).
- Nhiều người dùng, phân quyền, nhiều GPU, kết nối PACS.
- Chỉnh sửa mask, đo đạc, mô hình chẩn đoán phía sau segmentation.

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
| `file` | file | Có |  | Ảnh `.nii` hoặc `.nii.gz` |
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

BE kiểm tra theo thứ tự sau và dừng ở lỗi đầu tiên gặp phải: đuôi file, kích thước, `nibabel` đọc được header, ảnh 3D (hoặc 4D có chiều cuối bằng 1), hàng chờ chưa đầy.

### 3.3 GET /jobs/{job\_id}

Đây là payload FE dùng nhiều nhất. Trường `result` chỉ có giá trị khi `status = done`, trường `error` chỉ có giá trị khi `status = failed`.

Khi đang chờ hoặc đang chạy:

```json
{
  "job_id": "7c9e6679-7425-40de-944b-e07fc1f90ae7",
  "status": "pending",
  "queue_position": 2,
  "input": { "filename": "sub-01_T2w.nii.gz", "size_bytes": 18350212 },
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
  "input": { "filename": "sub-01_T2w.nii.gz", "size_bytes": 18350212 },
  "options": { "iso": false, "step1_only": false },
  "created_at": "2026-10-16T12:30:00Z",
  "started_at": "2026-10-16T12:31:05Z",
  "finished_at": "2026-10-16T12:33:40Z",
  "duration_seconds": 155,
  "result": {
    "input_url": "/api/v1/jobs/7c9e6679-7425-40de-944b-e07fc1f90ae7/input",
    "segmentation_url": "/api/v1/jobs/7c9e6679-7425-40de-944b-e07fc1f90ae7/result",
    "labels_url": "/api/v1/labels",
    "labels_present": [1, 2, 41, 42, 43, 44, 45, 50, 92, 93, 94, 95, 100]
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

Cả hai trả binary `.nii.gz`. Gọi `/result` khi job chưa `done` thì nhận `409 JOB_NOT_READY`. Tên file trả về là `{job_id}_input.nii.gz` và `{job_id}_seg.nii.gz`, không dùng tên file gốc.

### 3.6 DELETE /jobs/{job\_id}

Thành công trả `204 No Content`, không có body. Nếu job đang `running` thì trả `409 JOB_RUNNING`. Job `pending` bị xóa sẽ được rút khỏi hàng chờ.

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

Mọi lỗi trong lúc chạy đều dẫn về `failed`; chỉ job `pending` mới được xếp lại hàng chờ khi BE khởi động lại.

**Quy tắc chuyển trạng thái**

1. `pending` sang `running`: worker lấy job cũ nhất trong hàng chờ, ghi `started_at`.
2. `running` sang `done`: CLI trả exit code 0 và tìm thấy file mask (mục 5), ghi `finished_at` và `labels_present`.
3. `running` sang `failed`: CLI trả exit code khác 0, hoặc không có file mask, hoặc chạy quá `JOB_TIMEOUT_SEC` (mặc định 900 giây).
4. `done` và `failed` là trạng thái cuối, không chuyển tiếp nữa. Muốn chạy lại thì tạo job mới.

**Khi BE khởi động lại**

- Job đang `running` chuyển thành `failed` với code `WORKER_INTERRUPTED`.
- Job đang `pending` được đưa lại vào hàng chờ theo thứ tự `created_at`.

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

**Giai đoạn 2: nhận DICOM**

Thêm một bước trước khi gọi CLI: nhận file `.zip` chứa 1 series, giải nén vào `input/dicom/`, rồi chuyển sang `.nii.gz` bằng dcm2niix. Nếu ra nhiều hơn 1 file NIfTI thì báo lỗi `MULTIPLE_SERIES`. Phần còn lại giữ nguyên.

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
  output_path       TEXT,                           -- file mask cuối cùng
  opt_iso           INTEGER NOT NULL DEFAULT 0,     -- 0/1
  opt_step1         INTEGER NOT NULL DEFAULT 0,     -- 0/1
  labels_present    TEXT,                           -- JSON array, ví dụ "[1,2,41]"
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

BE đổi tên file upload thành `{job_id}.nii.gz` ngay khi lưu, vì tên file gốc có thể chứa tên bệnh nhân. `original_filename` chỉ để hiển thị trên FE; có thể bỏ trường này nếu dữ liệu chưa được ẩn danh.

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

1. Trang upload: chọn file, 2 checkbox tùy chọn (`iso`, `step1_only`), nút gửi.
2. Trang job: hiện trạng thái, vị trí trong hàng chờ, thời gian đã chạy; khi `failed` thì hiện `error.message`.
3. Viewer: mở khi `done`, gồm 3 mặt cắt kèm chú thích nhãn.
4. Danh sách job: lấy từ `GET /jobs`, có nút xóa.

## 8. Bảng mã lỗi

Có hai loại lỗi. Lỗi request trả về ngay qua HTTP status kèm body `error`. Lỗi job nằm trong trường `error` của `GET /jobs/{job_id}` khi `status = failed`.

**Lỗi request**

| HTTP | Code | Khi nào |
| --- | --- | --- |
| 400 | `INVALID_FILE_TYPE` | Đuôi file không phải `.nii` hoặc `.nii.gz` |
| 400 | `INVALID_NIFTI` | `nibabel` không đọc được file, hoặc ảnh không phải 3D |
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
| `MULTIPLE_SERIES` | Giai đoạn 2: file zip DICOM ra nhiều hơn 1 series | Chỉ upload 1 series |

## 9. Môi trường chạy và triển khai

Toàn bộ hệ thống chạy trên một máy có GPU, trong một process Python. Docker không bắt buộc cho MVP.

**Cài đặt**

- Python ≥ 3.10 ([README](https://github.com/neuropoly/totalspineseg)).
- Gói totalspineseg cài kèm extra `nnunetv2`, để giữ đúng phiên bản nnU-Net đã được kiểm thử.
- Muốn dùng GPU CUDA thì cần PyTorch bản nhỏ hơn 2.6.
- BE cần một thư viện đọc được NIfTI để kiểm tra file upload.

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
- Chỉ chạy 1 process BE: nếu nhiều process thì mỗi process có hàng chờ riêng và sẽ tranh nhau GPU.

**Có cần Docker không**

Với phạm vi môn học thì không bắt buộc. Một `venv` cùng `requirements.txt` và README hướng dẫn chạy là đủ, nếu cả nhóm dùng chung một máy GPU. Chỉ nên làm thêm 1 `Dockerfile` (không cần compose hay Kubernetes) khi có ít nhất một trong các tình huống sau:

- Nhiều người cần chạy lại trên các máy khác nhau, hoặc giảng viên cần chấm bằng cách tự chạy.
- Cần cố định đúng cặp CUDA, PyTorch và nnU-Net để tránh lỗi môi trường.
- Rubric của môn có chấm phần triển khai.

Nếu làm Docker: dùng base image CUDA runtime, tải weights sẵn lúc build (hoặc mount `data/models`), mount `data/` thành volume, rồi chạy container có quyền truy cập GPU và mở cổng 8000.

## 10. Phân công và checklist

FE và BE làm song song được ngay từ ngày đầu: BE dựng mock trả đúng payload ở mục 3 trước, sau đó mới nối worker thật vào.

**Backend API**

- [ ] Khởi tạo FastAPI, prefix `/api/v1`, bật CORS, có `/health`
- [ ] Tạo schema SQLite khi khởi động, bật WAL
- [ ] `POST /jobs`: kiểm tra file, đổi tên, lưu file, insert job, trả 202
- [ ] `GET /jobs/{job_id}`, `GET /jobs`, `DELETE /jobs/{job_id}` theo đúng payload mục 3
- [ ] `GET /jobs/{job_id}/input`, `/result`, `GET /labels`
- [ ] Dùng chung format lỗi ở mục 2 và mã lỗi ở mục 8
- [ ] Mock mode (`MOCK_WORKER=1`): job tự `done` sau 5 giây, trả lại chính ảnh input làm mask, để FE test trước khi có GPU

**Worker**

- [ ] Hàng chờ 1 thread, lấy job `pending` cũ nhất
- [ ] Gọi CLI theo mục 5, ghi log, xử lý timeout
- [ ] Tìm file mask, tính `labels_present`, cập nhật trạng thái
- [ ] Khôi phục trạng thái khi BE khởi động lại (mục 4)
- [ ] Script warm-up tải sẵn weights vào `TOTALSPINESEG_DATA`

**Frontend**

- [ ] Trang upload, có báo lỗi validate
- [ ] Trang job: poll theo quy tắc ở mục 4, giữ `job_id` trên URL
- [ ] Viewer NiiVue: ảnh nền, mask, LUT từ `/labels`, thanh opacity, chú thích nhãn
- [ ] Danh sách job có nút xóa

**Tiêu chí hoàn thành MVP**

- [ ] Upload 1 ảnh MRI sagittal cột sống thắt lưng, sau đó thấy mask L1–L5, sacrum và các đĩa đệm chồng đúng lên ảnh gốc
- [ ] Đo và ghi lại thời gian chạy thực tế của một job trên GPU dùng để demo
- [ ] Restart BE giữa chừng thì không mất job `pending`, job `running` chuyển thành `failed`
- [ ] Cả 9 lỗi request ở mục 8 đều tái hiện được bằng `curl`

## Nguồn

- [neuropoly/totalspineseg (README: cài đặt, CLI, cấu trúc output, bảng nhãn)](https://github.com/neuropoly/totalspineseg)
- [totalspineseg trên PyPI](https://pypi.org/project/totalspineseg/)
