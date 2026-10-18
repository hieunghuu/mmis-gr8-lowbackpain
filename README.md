# CO5111 – MMIS – Nhóm 8: *More Precise Diagnosis for Low Back Pain*

Assignment môn **Modern Management Information Systems (CO5111)**. Đề tài: dùng ảnh MRI cột sống
thắt lưng và ghi chú của bác sĩ X-quang để tạo **thông tin có cấu trúc** hỗ trợ chẩn đoán đau lưng
dưới chính xác hơn.

## Ý tưởng

Ảnh và văn bản được đưa về **cùng một khóa `(patient_id, level)`** – bệnh nhân × tầng đĩa đệm – rồi
mới ghép lại để phân tích:

```
MRI (DICOM) ─► chọn series, NIfTI ─► phân đoạn TotalSpineSeg ─► số đo / tầng ──┐
                                                                               ├─► ghép (patient_id, level) ─► phân tích
Ghi chú bác sĩ (xlsx) ─► NLP bằng rule: tầng + bệnh + phủ định ─► nhãn / tầng ─┘
```

Hệ thống **không thay bác sĩ chẩn đoán**: nó chuẩn hóa dữ liệu, đo lường, và gợi ý chỗ cần xem lại
(ví dụ số đo bất thường nhưng báo cáo không nhắc).

## Kết quả chính

| | |
|---|---|
| Dữ liệu | 515 bệnh nhân có cả ảnh MRI và ghi chú bác sĩ |
| Phân đoạn ảnh | TotalSpineSeg: 514/515 ca đạt QC, 513 ca dùng được theo tầng |
| NLP ghi chú | F1 **0,959** (mức tầng) trên 79 ghi chú gold |
| Ảnh × văn bản | Số đo khớp mạnh với nhận xét bác sĩ: hẹp khoang đĩa AUC 0,97, hẹp ống sống 0,88, lồi đĩa 0,87 |
| Ca lệch | Mất nước đĩa bị ghi thiếu nhiều nhất: 12 % đĩa L5-S1 không được nhắc nhưng tín hiệu tối như ca được ghi |

Chi tiết từng bước, số liệu và hình: [`pipeline/README.md`](pipeline/README.md).

## Cấu trúc repo

```
mmis-gr8-lowbackpain/
├── data/                  # dữ liệu gốc – chỉ README + hình minh họa nằm trong Git
│   ├── MRI_Data/          #   ảnh DICOM 515 bệnh nhân (tự tải, 12,5 GB)
│   └── Radiologists Report.xlsx
├── pipeline/              # code, nhãn gold, bảng kết quả, hình
│   ├── src/               #   dicom/ segmentation/ nlp/ measurements/ analysis/
│   ├── annotations/       #   nhãn chuẩn vàng cho NLP
│   ├── kaggle/            #   notebook chạy TotalSpineSeg trên GPU
│   └── outputs/           #   tables/ figures/ (trong Git); nifti/, tss/… (không)
└── fe/                    # giao diện (chưa bắt đầu)
```

| Tài liệu | Đọc khi |
|---|---|
| [`data/README.md`](data/README.md) | Cần hiểu bộ dữ liệu, giải phẫu cột sống, thuật ngữ y khoa Anh – Việt (viết cho người không học y) |
| [`pipeline/README.md`](pipeline/README.md) | Cần chạy lại pipeline, xem thiết kế, kết quả, kiến trúc hệ thống |
| [`pipeline/kaggle/README.md`](pipeline/kaggle/README.md) | Cần chạy lại TotalSpineSeg trên Kaggle GPU |

## Bắt đầu nhanh

1. **Tải dữ liệu** (không có trong Git) từ Mendeley và đặt vào `data/` theo cấu trúc trên – link và
   trích dẫn: [`pipeline/README.md`, mục "Nguồn dữ liệu và trích dẫn"](pipeline/README.md#nguồn-dữ-liệu-và-trích-dẫn).
2. **Cài môi trường** (Python 3.13):
   ```bash
   cd pipeline
   pip install -r requirements.txt
   ```
3. **Lấy mask TotalSpineSeg** của nhóm thay vì chạy lại (~2,7 giờ GPU):
   ```bash
   python src/s00_shared_data.py --fetch
   ```
4. **Chạy các bước** theo thứ tự số `s01` → `s10` (bỏ qua `s03`, `s04` nếu đã tải mask) – lệnh và
   thời gian từng bước ở [`pipeline/README.md`](pipeline/README.md).

Bảng kết quả và hình đã có sẵn trong `pipeline/outputs/` – chỉ cần chạy lại khi sửa code.

## Quy ước làm việc

- Mỗi thay đổi làm trên một nhánh riêng (`feat/…`, `refactor/…`, `docs/…`), mở PR vào `main`, xóa
  nhánh sau khi merge.
- **Không commit dữ liệu y tế** (ảnh DICOM, NIfTI, mask) – đã chặn trong `.gitignore`. Mask dùng
  chung qua GitHub Release `v0.1-tss-masks`.
