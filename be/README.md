# Backend – Spine Segmentation Service

FastAPI backend cho frontend trong `fe/`. Hợp đồng HTTP bám theo `docs/spec.md`.

## Chức năng

- Upload và kiểm tra `.nii` / `.nii.gz` (tối đa 200 MB mặc định).
- SQLite là nơi lưu metadata và hàng chờ bền vững.
- Một worker nền xử lý tuần tự để không tranh GPU.
- Gọi `ai.segment.segment()` và `ai.analyze.analyze()` ở chế độ thật.
- Có `MOCK_WORKER=1` để chạy toàn bộ FE/API mà không cần TotalSpineSeg hoặc GPU.
- Khôi phục sau restart: job `pending` được giữ, job `running` thành `WORKER_INTERRUPTED`.
- Có thể phục vụ bản build của FE từ cùng cổng 8000.

## Cài đặt nhanh (mock)

Từ thư mục gốc repo:

```powershell
python -m venv .venv-be
.venv-be\Scripts\python -m pip install -r be/requirements-dev.txt
$env:MOCK_WORKER="1"
.venv-be\Scripts\python -m uvicorn be.app.main:app --host 127.0.0.1 --port 8000
```

Chạy FE ở terminal khác:

```powershell
cd fe
npm ci
npm run dev
```

Mở `http://localhost:5173`. Vite chuyển tiếp `/api` sang BE ở cổng 8000.

## Chạy AI thật

Khuyến nghị dùng Python 3.12 cho môi trường AI vì TotalSpineSeg/PyTorch có thể chưa hỗ trợ các bản
Python mới nhất. Cài các dependency trong `requirements.txt`, sau đó cài PyTorch CUDA và
TotalSpineSeg theo phiên bản phù hợp với GPU:

```powershell
python -m pip install "torch<2.6" --index-url https://download.pytorch.org/whl/cu124
python -m pip install "totalspineseg[nnunetv2]" "kornia<0.8"
$env:MOCK_WORKER="0"
$env:TOTALSPINESEG_DATA="D:\path\to\models"
python -m uvicorn be.app.main:app --host 0.0.0.0 --port 8000
```

Lần chạy đầu TotalSpineSeg có thể tải nhiều GB weights. Nên warm-up trước khi demo.

## Biến môi trường

Xem [`.env.example`](.env.example). Backend không tự đọc file `.env`; đặt biến trong shell hoặc dùng
trình quản lý process. Mặc định dữ liệu runtime nằm trong `be/data/`.

Quan trọng: chỉ chạy **một** Uvicorn worker. Nhiều process sẽ tạo nhiều worker AI và tranh GPU:

```powershell
python -m uvicorn be.app.main:app --workers 1
```

Không dùng `--reload` khi đang xử lý dữ liệu thật.

## API

- `GET /api/v1/health`
- `POST /api/v1/jobs`
- `GET /api/v1/jobs/{job_id}`
- `GET /api/v1/jobs?status=&limit=&offset=`
- `GET /api/v1/jobs/{job_id}/input`
- `GET /api/v1/jobs/{job_id}/result`
- `DELETE /api/v1/jobs/{job_id}`
- `GET /api/v1/labels`
- Swagger: `GET /docs`

## Kiểm thử

```powershell
python -m pytest be/tests -q
```

Kiểm tra hợp đồng từ phía FE khi BE đang chạy:

```powershell
cd fe
npm run check:api -- http://localhost:8000/api/v1
```

## Build và phục vụ FE cùng BE

```powershell
cd fe
npm run build
cd ..
$env:SERVE_FRONTEND="1"
python -m uvicorn be.app.main:app --host 0.0.0.0 --port 8000
```

Sau đó mở `http://localhost:8000`. Các route React như `/jobs/{id}` fallback về `index.html`, còn
`/api/*` luôn do FastAPI xử lý.

## Lưu trữ

```text
be/data/
├─ app.db
├─ models/
└─ jobs/{job_id}/
   ├─ input/{job_id}.nii.gz
   ├─ output/
   └─ logs/totalspineseg.log
```

Không commit `be/data/`, model weights, ảnh upload hoặc mask sinh ra.
