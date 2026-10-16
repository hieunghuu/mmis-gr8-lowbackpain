# Chạy TotalSpineSeg trên Kaggle GPU

**Vì sao:** trên CPU máy nhà, TotalSpineSeg mất **~15 phút/ca** (đo ở `s03_tss_pilot.py`,
RAM đỉnh 3,9 GB) → 515 ca ≈ 5,3 ngày. Kaggle Notebook có GPU miễn phí (30 giờ/tuần,
mỗi phiên tối đa 12 giờ).

## 1. Chuẩn bị file (trên máy)

```bash
cd totalspineseg
python src/segmentation/s04_pack_for_kaggle.py     # -> outputs/kaggle/lumbar_sag_nifti.zip (1,2 GB, 515 file)
```

## 2. Tài khoản Kaggle

- Đăng nhập kaggle.com → *Settings* → **Phone Verification** (bắt buộc để bật GPU và Internet).

## 3. Tạo Dataset (riêng tư)

1. kaggle.com → *Datasets* → **New Dataset**.
2. Kéo thả `outputs/kaggle/lumbar_sag_nifti.zip` (Kaggle tự giải nén).
3. Tên ví dụ `lumbar-sag-nifti`, **Visibility: Private** → *Create*.

Dữ liệu là bộ MRI công khai, đã ẩn danh (Mendeley Data, CC BY 4.0); vẫn để **Private**.

## 4. Tạo Notebook

1. *Code* → **New Notebook** → *File* → **Import Notebook** → chọn `kaggle/tss_kaggle.ipynb`.
2. Panel phải *Settings*:
   - **Accelerator: GPU T4 x2** (không chọn P100).
   - **Internet: On**.
3. *Add Input* → chọn dataset `lumbar-sag-nifti` vừa tạo.

## 5. Chạy thử (tương tác)

Chạy lần lượt **cell 1 → 4**:

| Cell | Làm gì | Mong đợi |
|---|---|---|
| 1 | Tìm thư mục ảnh | `Anh dau vao: … - 515 file` |
| 2 | Cài TotalSpineSeg | `CUDA: True | Tesla T4` |
| 3 | Định nghĩa hàm chạy theo lô | `Da xong tu truoc: 0` |
| 4 | Chạy 3 ca đầu (lần đầu tải trọng số ~4 GB) | `… 3 ca, … s (… s/ca), OK` |

**Gửi lại cho Claude dòng kết quả của cell 4** (số giây/ca) để ước tính thời gian.
Lưu ý: lần đầu có thời gian tải trọng số, nên số giây/ca ở cell 4 sẽ cao hơn thực tế.

## 6. Chạy toàn bộ (chạy ngầm)

Nếu cell 4 ổn: góc phải trên **Save Version** → **Save & Run All (Commit)** → *Save*.
Notebook chạy ngầm từ đầu đến cuối (tối đa 12 giờ), không cần mở trình duyệt.
Theo dõi ở trang notebook → *Versions*.

## 7. Tải kết quả

Version chạy xong → tab **Output** → tải `tss_sag_results.zip`, đặt vào
`totalspineseg/outputs/kaggle/`. Bên trong:

```
tss_sag/
├── step2_output/0001.nii.gz …   mask cuối: L1–L5 (41–45), sacrum (50), đĩa (91–100), ống sống (2), tủy (1)
├── step1_levels/0001.nii.gz …   1 voxel ở mép sau mỗi đĩa
├── preview/*.jpg                 ảnh xem nhanh để QC
└── batch_log.csv                 thời gian từng lô
```

## Nếu bị ngắt giữa chừng

Cell 5 tự dừng nhận lô mới sau 11 giờ. Khi đó: tạo version mới, *Add Input* thêm
**Output của version trước** → chạy lại. Những ca đã có `step2_output` sẽ được bỏ qua,
và kết quả cũ được chép sang để file zip cuối gom đủ.
