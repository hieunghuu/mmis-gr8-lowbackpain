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

Kiểm tra BE có đúng spec không:

```bash
npm run check:api                                   # mặc định http://localhost:8000/api/v1
npm run check:api -- http://<host>:<cổng>/api/v1
```

Script gọi lần lượt các endpoint, thử vài lỗi (404, sai đuôi file, sai tùy chọn), tải ảnh mẫu lên, chờ job xong rồi xóa. Mục nào sai spec sẽ in ra trường bị sai. Muốn dùng ảnh khác thì đặt `SAMPLE=đường/dẫn/ảnh.nii.gz`.

Nếu BE trả thiếu vài trường không bắt buộc, FE tự dùng giá trị mặc định. Nếu sai trường bắt buộc (ví dụ `status` lạ, job `done` mà không có `result`), FE hiện lỗi `CONTRACT_MISMATCH` kèm tên trường.

## Build

```bash
npm run build
```

Kết quả nằm trong `dist/`. Khi demo, cho BE phục vụ thư mục này và trả `index.html` cho mọi đường dẫn không bắt đầu bằng `/api`.

## Thư mục

- `src/api`: nơi duy nhất gọi API, `validate.ts` kiểm tra dữ liệu BE trả về
- `src/pages`: trang tải lên, trang job, danh sách job
- `src/components`: viewer NiiVue, bảng phân tích, các phần dùng chung
- `src/hooks`: polling trạng thái job và `/health`
- `src/types.ts`: kiểu dữ liệu theo spec
- `mock/server.mjs`: BE giả
- `scripts/check-api.ts`: kiểm tra BE theo spec

## Chưa có

- Chưa thử với ảnh MRI sagittal T2 thật.
- Chưa có test tự động.
