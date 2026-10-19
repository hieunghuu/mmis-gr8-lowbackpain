# Frontend

Giao diện web cho hệ thống phân đoạn MRI cột sống. Viết bằng React, TypeScript và Vite, xem ảnh bằng NiiVue. API làm theo `docs/spec.md`.

## Chạy thử

Cần Node 20.19 trở lên. Mở hai terminal:

```bash
cd fe
npm install
npm run mock    # BE giả, cổng 8000
npm run dev     # FE, mở http://localhost:5173
```

Mock có sẵn vài job mẫu và dùng dữ liệu BN 0100 trong `ai/demo`. Ảnh nền của mock chính là file mask nên viewer chưa giống ảnh MRI thật.

## Dùng BE thật

Không chạy `npm run mock`, bật BE ở cổng 8000 rồi chạy `npm run dev`. Nếu BE ở chỗ khác:

```bash
VITE_PROXY_TARGET=http://<host>:<cổng> npm run dev
```

## Build

```bash
npm run build
```

Kết quả nằm trong `dist/`. Khi demo, cho BE phục vụ thư mục này và trả `index.html` cho mọi đường dẫn không bắt đầu bằng `/api`.

## Thư mục

- `src/api`: nơi duy nhất gọi API
- `src/pages`: trang tải lên, trang job, danh sách job
- `src/components`: viewer NiiVue, bảng phân tích, các phần dùng chung
- `src/hooks`: polling trạng thái job và `/health`
- `src/types.ts`: kiểu dữ liệu theo spec
- `mock/server.mjs`: BE giả

## Chưa có

- Chưa thử với ảnh MRI sagittal T2 thật.
- Chưa có test tự động.
