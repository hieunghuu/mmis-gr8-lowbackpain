# Nhat ky gan nhan gold – nguoi gan nhan LLM

- **Mo hinh:** Claude Opus 5.5 (`claude-opus-5-5`), chay trong Claude Code (vai tro nguoi gan nhan doc lap).
- **Ngay:** 2026-10-15
- **Dau ra:** `gold_labels_llm.xlsx` (sheet `Labels`, giu nguyen cac sheet khac, validation va sheet an `Lists`), `gold_labels_llm.csv` (UTF-8).

## Quy trinh
1. Doc toan bo sheet `HuongDan`, vi du `ViDu` (BN 4) va README chi muc 5.4 (danh muc nhan) va 5.5 (quy uoc Q1–Q11).
   **Khong** mo thu muc `src/`, `outputs/`, va khong doc cac muc khac cua README.
2. Dung Python chi de in 80 ghi chu tu sheet `Notes`.
3. Doc tung ghi chu va tu go tay tung dong nhan (khong dung regex/tu khoa de gan tu dong).
4. Script chi dung de: kiem tra gia tri hop le theo `Lists`, kiem tra trung khoa (patient_id, level, finding, present),
   kiem tra du 80 BN, roi ghi vao xlsx/csv, sap xep theo patient_id.

## Thong ke
- Tong so dong: **426** (TRUE 350, FALSE 76); 80/80 BN co it nhat 1 dong; khong co dong `none` (moi ghi chu deu co it nhat 1 phat hien hoac cau phu dinh).
- Theo tang: L4-L5 134, UNSPEC 129, L5-S1 108, L3-L4 47, L2-L3 6, T12-L1 2.
- `other`: 9 dong. Cot `vertebra` dien 3 dong, cot `root` dien 5 dong.

## Quy uoc mo ho va cach giai quyet
1. **Severity/side cho dong FALSE:** de trong (huong dan noi chi dung cho phat hien co mat).
2. **Cau tong quat khong tang sau cau co tang** (cau mau phu dinh chen ep, "adequate spinal canal", "canal still adequate"): gan UNSPEC, khong ke thua tang. Chi ke thua khi cau ro rang noi tiep (vd dong bat dau bang dong tu "Compressing ...", hoac cung menh de "but not causing ...").
3. **"exit (neural) canals" so nhieu khong noi ben** -> foraminal_stenosis, side = bilateral (mo rong Q11 tu "nerve roots" sang "exit canals"). So it -> unspecified.
4. **Mot dong tu mang muc do chi phoi hai tan ngu** ("mild compressing the thecal sac and exit nerve roots"): muc do ap dung cho ca hai. Khac dong tu (vd vi du BN 4 "encroaching") -> khong ke thua.
5. **"central and left paracentral" / "central and to the left"**: side = left.
6. **Tu muc do ngoai bang tu vung:** "significantly" -> severe; "largely" -> severe (co ghi chu); "relatively", "partial" -> unspecified; "small" -> mild; Grade I/II cua truot dot -> unspecified (ghi grade vao comment).
7. **"extending to (Lt) lateral recess"**: gan spinal_canal_stenosis TRUE kem comment "uncertain" (README 5.4 liet ke lateral recess thuoc hep ong song).
8. **Cau mau bi mat tu "No"** (cau chen ep co "or" va "noted", khong kem tang, sau cau khong thoat vi): gan FALSE theo y nghia, ghi chu ro la ban chat chu nghia la duong tinh.
9. **Mau thuan trong cung ghi chu** (chen ep nhe tai L4-L5 roi cau "khong chen ep dang ke" khong tang): giu ca hai – L4-L5 TRUE, UNSPEC FALSE.
10. **"abutting the cord"** tai T12-L1: khong co nhan chen ep tuy -> `other` FALSE (Q1).
11. **Phat hien ngoai danh sach** -> `other`: limbus vertebra (vertebra L4), lipoma day tan cung, tien su phau thuat, mo xo/hat sau mo (2 BN), "degenerative spondylotic changes" (2 BN), thoat vi co C4-C5 (UNSPEC vi khong phai tang that lung).
12. **"bone marrow signal reconversion"** -> bone_marrow_lesion TRUE (ghi chu nghi ngo); "preserved vertebral height / marrow signal" -> vertebral_fracture FALSE va bone_marrow_lesion FALSE.
13. **Phat hien ngoai cot song** (MRI goi trong cung ghi chu): bo qua.
14. **"Modic" trong cung menh de voi truot dot "L3 over L4"**: ke thua tang L3-L4.
15. **"multilevel" khong neu tang nao**: ghi 1 dong UNSPEC; neu co tang duoc neu ("noticeably at ...") chi ghi tang do (Q8).
16. **Chen ep do mo xo sau mo** (khong phai dia dem): van ghi thecal_sac_compression / foraminal_stenosis TRUE.
17. **Re don le khong noi ben nhung ngu canh ngu y mot ben**: side = unspecified (chi dung tu gan voi chinh phat hien do).
