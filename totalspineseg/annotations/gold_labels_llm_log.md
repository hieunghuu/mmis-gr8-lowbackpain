# Nhật ký gán nhãn bộ đánh giá NLP (do LLM gán)

## File này là gì?

Để đo độ chính xác của bộ rule NLP (bước 3), cần một **bộ đáp án**: 80 ghi chú bác sĩ được
gán nhãn cẩn thận, độc lập với bộ rule. Bộ đáp án này do **Claude Opus 5.5** (mô hình ngôn ngữ
lớn) gán theo đúng hướng dẫn và quy ước của nhóm. Vì người gán không phải con người/chuyên gia
y khoa, bộ nhãn được gọi là **"silver standard"** (chuẩn bạc) thay vì "gold standard" – cần nêu rõ
điều này khi báo cáo kết quả, và nên để nhóm rà lại một mẫu (~20 ghi chú) để đối chiếu.

| Mục | Giá trị |
|---|---|
| Người gán | Claude Opus 5.5 (`claude-opus-5-5`), chạy như một người gán nhãn độc lập |
| Ngày | 15/10/2026 |
| Đầu vào | `gold_annotation.xlsx` – 80 ghi chú (sheet `Notes`) + hướng dẫn (sheet `HuongDan`, `ViDu`) |
| Đầu ra | `gold_labels_llm.xlsx` (sheet `Labels`) và `gold_labels_llm.csv` (cùng nội dung, UTF-8) |

## Cách làm – và cách giữ tính độc lập

1. **Chỉ đọc hướng dẫn gán nhãn:** sheet `HuongDan`, ví dụ mẫu `ViDu` (bệnh nhân 4), và README mục
   5.4 (danh mục nhãn) + 5.5 (quy ước Q1–Q11).
2. **Không xem bộ rule đang được đánh giá:** không mở thư mục `src/`, `outputs/`, không đọc các mục
   README mô tả cách cài đặt rule.
3. **Đọc và gán tay từng ghi chú:** không dùng regex hay từ khóa để gán tự động. Python chỉ dùng để
   in ghi chú ra và ghi kết quả vào file.
4. **Tự kiểm tra trước khi nộp:** đủ 80 bệnh nhân; mọi giá trị nằm trong danh sách cho phép; không
   có dòng trùng `(patient_id, level, finding, present)`; sắp xếp theo `patient_id`.

## Thống kê kết quả

| Chỉ số | Giá trị |
|---|---|
| Tổng số dòng | **423** – khẳng định (`TRUE`) 347, phủ định (`FALSE`) 76 (bản gốc 426 dòng; đã bỏ 3 dòng khi chốt – xem cuối file) |
| Số bệnh nhân | 80/80 đều có ít nhất 1 dòng |
| Dòng `none` (ghi chú không có phát hiện nào) | 0 – ghi chú nào cũng có ít nhất 1 phát hiện hoặc câu phủ định |
| Dòng `other` (phát hiện ngoài danh mục) | 9 |
| Cột `vertebra` / `root` có điền | 3 dòng / 5 dòng |

Số dòng theo tầng:

| L4-L5 | UNSPEC | L5-S1 | L3-L4 | L2-L3 | T12-L1 | L1-L2 |
|---|---|---|---|---|---|---|
| 133 | 129 | 108 | 46 | 5 | 2 | 0 |

## Các tình huống khó và cách đã xử lý

### A. Gán tầng

| # | Tình huống | Cách xử lý |
|---|---|---|
| A1 | Câu **không có tầng** đứng sau câu có tầng, nhưng là câu khuôn mẫu chung (vd câu phủ định chèn ép, "adequate spinal canal") | Gán `UNSPEC`, **không** kế thừa tầng (nay là quy ước **Q12**). Chỉ kế thừa khi câu rõ ràng nối tiếp câu trước (vd bắt đầu bằng "Compressing …", hoặc cùng mệnh đề "but not causing …") |
| A2 | "multilevel" nhưng không nêu tầng nào | 1 dòng `UNSPEC`. Có nêu tầng ("noticeably at …") thì chỉ ghi các tầng đó (quy ước Q8) |
| A3 | "Modic" cùng mệnh đề với trượt đốt "L3 over L4" | Kế thừa tầng L3-L4 của mệnh đề đó |
| A4 | Thoát vị ở **cột sống cổ** (C4-C5) nhắc trong ghi chú | Ghi `other`, tầng `UNSPEC` (không phải tầng thắt lưng) |

### B. Phủ định

| # | Tình huống | Cách xử lý |
|---|---|---|
| B1 | Câu khuôn mẫu có vẻ **bị mất chữ "No"** (câu chèn ép dạng "… or … noted", không có tầng, đứng sau câu "không thoát vị") | Gán `FALSE` theo **nghĩa**, ghi chú rằng nếu đọc đúng từng chữ thì câu là khẳng định |
| B2 | Ghi chú **tự mâu thuẫn** (chèn ép nhẹ ở L4-L5, rồi câu "không chèn ép đáng kể" không có tầng) | Giữ cả hai: L4-L5 `TRUE`, `UNSPEC` `FALSE` |
| B3 | "abutting the cord" (chạm tủy) ở T12-L1 | Không có nhãn chèn ép tủy → `other`, `FALSE` (theo Q1: "chạm" không phải chèn ép) |
| B4 | "preserved vertebral height / marrow signal" | `vertebral_fracture` `FALSE` và `bone_marrow_lesion` `FALSE` |

### C. Mức độ (severity) và bên (side)

| # | Tình huống | Cách xử lý |
|---|---|---|
| C1 | Mức độ / bên của dòng `FALSE` | Để trống (hướng dẫn chỉ áp dụng cho phát hiện có mặt) |
| C2 | Một động từ có mức độ chi phối **hai đối tượng** ("mild compressing the thecal sac and exit nerve roots") | Mức độ áp dụng cho **cả hai**. Nếu đối tượng thứ hai có động từ riêng (vd "encroaching" ở ví dụ BN 4) thì không áp dụng |
| C3 | "exit (neural) **canals**" số nhiều, không nói bên | `foraminal_stenosis`, side = `bilateral` (nay đã đưa vào **Q11**). Số ít → `unspecified` |
| C4 | "central and left paracentral", "central and to the left" | side = `left` |
| C5 | Rễ thần kinh đơn lẻ không nói bên, dù ngữ cảnh gợi ý một bên | side = `unspecified` (chỉ dùng từ gắn trực tiếp với phát hiện đó) |
| C6 | Từ mức độ ngoài bảng từ vựng | "significantly", "largely" → `severe`; "small" → `mild`; "relatively", "partial" → `unspecified`; trượt đốt độ I/II → `unspecified`, ghi độ vào cột `comment` |

### D. Phát hiện ngoài danh mục và trường hợp đặc biệt

| # | Tình huống | Cách xử lý |
|---|---|---|
| D1 | Phát hiện cột sống không có trong danh mục | `other` + mô tả: limbus vertebra (đốt L4), u mỡ dây tận cùng, tiền sử phẫu thuật, mô xơ/mô hạt sau mổ (2 BN), "degenerative spondylotic changes" (2 BN) |
| D2 | Chèn ép do **mô xơ sau mổ** (không phải do đĩa đệm) | Vẫn ghi `thecal_sac_compression` / `foraminal_stenosis` `TRUE` |
| D3 | "bone marrow signal reconversion" | `bone_marrow_lesion` `TRUE`, ghi chú "nghi ngờ" |
| D4 | Phát hiện **ngoài cột sống** (vd kết quả MRI gối trong cùng ghi chú) | Bỏ qua |

## Đã chốt (16/10/2026)

Các điểm còn mở sau lần gán nhãn đầu đã được nhóm quyết định như sau:

| Mục | Quyết định | Đã làm |
|---|---|---|
| **"extending to the lateral recess"** (BN 174: L2-L3, L4-L5; BN 253: L3-L4) | Không tính là hẹp ống sống – "extending to" chỉ là **vị trí** (README 3.4.1) | **Bỏ 3 dòng** khỏi `gold_labels_llm.xlsx` và `.csv` (426 → 423 dòng) |
| C3 – "exit canals" số nhiều → `bilateral` | Chấp nhận | Mở rộng quy ước **Q11** (README 3.5, sheet `QuyUoc`); bộ rule cập nhật theo |
| A1 – câu phủ định khuôn mẫu không có tầng → `UNSPEC` | Chấp nhận | Thêm quy ước **Q12**; bộ rule không còn kế thừa tầng cho phát hiện phủ định; phần phủ định được chấm ở **mức bệnh nhân** |
| B1 – gán theo nghĩa thay vì theo chữ | Chấp nhận – đáp án phải theo nghĩa | Ghi vào giới hạn của rule (README 3.9) |
