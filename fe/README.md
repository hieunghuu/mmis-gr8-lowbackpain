# Frontend – Spine MRI Viewer

React + TypeScript (Vite) + NiiVue. Làm theo hợp đồng ở [`../docs/spec.md`](../docs/spec.md) (mục 3 API, mục 7 FE, mục 8 mã lỗi).

## Chạy

Cần Node ≥ 20.19.

```bash
cd fe
npm install
npm run mock     # terminal 1: mock BE ở :8000 (chưa cần GPU)
npm run dev      # terminal 2: FE ở http://localhost:5173
```

Mock dùng `ai/demo/0100_seg.nii.gz` làm cả ảnh nền lẫn mask (giống `MOCK_WORKER=1` của spec) và `ai/demo/analysis_0100.json` làm `result.analysis`. Vì ảnh nền ở đây cũng là mask nên viewer chưa nhìn giống ảnh MRI thật; khi nối BE thật thì ảnh nền là ảnh người dùng tải lên.

Các lệnh khác: `npm run build` (kiểm tra kiểu rồi build ra `dist/`), `npm run preview`.

## Nối BE thật

FE chỉ gọi `/api/v1/...`. Lúc dev Vite chuyển tiếp `/api` sang BE, nên đổi từ mock sang BE thật chỉ cần trỏ proxy:

```bash
VITE_PROXY_TARGET=http://localhost:8000 npm run dev   # BE thật chạy ở cổng 8000
```

- Lúc demo: `npm run build`, để BE phục vụ thư mục `dist/` (một cổng, không cần CORS). Route phía FE là `/`, `/jobs`, `/jobs/:jobId`, nên BE cần trả `index.html` cho các đường dẫn không phải `/api`.
- BE khác origin: đặt `VITE_API_BASE_URL=http://<host>:8000/api/v1` (xem `.env.example`) và bật CORS cho origin của FE.

## Cấu trúc

```
src/
├── types.ts            kiểu dữ liệu đúng như spec mục 3 và 8
├── api/                chỗ duy nhất gọi HTTP (client.ts: lỗi + URL, index.ts: 7 endpoint)
├── hooks/useJob.ts     polling theo spec mục 4 (3 giây, sau 2 phút thì 10 giây, dừng khi done/failed/404)
├── hooks/useHealth.ts  GET /health cho thanh trạng thái
├── components/         Layout, Viewer (NiiVue), AnalysisPanel, StatusTag, ErrorBox
├── pages/              UploadPage, JobPage (/jobs/:jobId), JobListPage
└── styles.css          không bo góc, chỉ giao diện sáng
mock/server.mjs         mock BE theo spec, không phụ thuộc thư viện
```

## Chưa làm / cần lưu ý

- Viewer: chưa kiểm tra với ảnh MRI sagittal T2 thật (mock dùng mask làm ảnh nền).
- Ẩn/hiện theo nhóm đang tách theo 4 nhóm của `/labels` (đốt sống, đĩa đệm, tủy, ống sống).
- Gợi ý bệnh luôn đi kèm `disclaimer` của BE; nếu BE không trả thì không hiện, nên BE cần trả đủ trường này.
- Chưa có test tự động.
