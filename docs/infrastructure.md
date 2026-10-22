# Đặc tả hạ tầng – Spine Segmentation Service (on-premise)

Oct 22, 2026 · @Hieu

Tài liệu này mô tả hạ tầng để triển khai hệ thống ở [spec.md](spec.md) tại **một bệnh viện, dùng nội bộ, không có domain public, máy chủ không ra Internet**. Kiến trúc phần mềm giữ nguyên như spec: 1 process Python, 1 worker, 1 GPU, SQLite, file trên ổ local.

Các con số đánh dấu *(ước tính)* chưa được đo trên máy đích; mục 10 mô tả cách đo để chốt.

## 1. Giả định tải

Giả định: bệnh viện phục vụ khoảng **500 lượt bệnh nhân mỗi ngày**. Hệ thống chỉ xử lý ca **MRI cột sống thắt lưng (T2 sagittal)**, nên số ca thực tế bị giới hạn bởi số máy MRI, thấp hơn nhiều so với 500. Số ca MRI cột sống thắt lưng mỗi ngày cần bệnh viện xác nhận.

| Mức | Ca/ngày | Thời gian GPU cần (60 s/ca) | Ý nghĩa |
| --- | --- | --- | --- |
| Thường | 10 | 10 phút | 1 máy MRI, cột sống thắt lưng là một phần lịch chụp |
| **Thiết kế** | **100** | **1,7 giờ** | Gấp 10 lần mức thường, gồm cả nhập lại ca cũ |
| Cực đại | 500 | 8,3 giờ (12,5 giờ nếu 90 s/ca) | Mỗi bệnh nhân trong ngày đều có 1 ca, vẫn vừa 1 GPU trong 24 giờ |

- **Thời gian mỗi job** *(ước tính)* 30–90 s trên GPU, lấy 60 s để tính. Số đã đo: 18 s/ca trên Kaggle T4 (chạy theo lô, nạp model một lần); trong app mỗi job khởi động lại CLI và nạp lại model nên chậm hơn. Trên CPU khoảng 14 phút/ca, không dùng được.
- **Đỉnh tải:** người dùng có thể upload dồn khoảng 30–50 ca cuối ca trực. Đặt `MAX_PENDING_JOBS=50`; thời gian xả hết hàng chờ ≤ 50 phút.
- **Người dùng đồng thời:** khoảng 5–10 bác sĩ/KTV. FE gọi `GET /jobs/{id}` mỗi 3 giây khi đang chờ, tổng chỉ vài request mỗi giây.
- **Kết luận:** 1 server với 1 GPU đủ cho cả mức cực đại. Code hiện chỉ dùng 1 GPU và 1 job mỗi lúc, nên thêm GPU không tăng throughput nếu không sửa code.

## 2. Kiến trúc triển khai

```
Máy trạm (trình duyệt) ──HTTPS 443──> nginx ──127.0.0.1:8000──> uvicorn (FastAPI + FE + worker thread)
PACS ──xuất DICOM .zip thủ công──> máy trạm                         │
                                                                    ├─ SQLite  /srv/spine/app.db
                                                                    ├─ jobs/   /srv/spine/jobs
                                                                    └─ TotalSpineSeg (subprocess) ── GPU
/srv/spine ──hằng đêm──> NAS backup
```

- Chỉ nginx mở cổng ra mạng; uvicorn chỉ nghe `127.0.0.1`.
- Không kết nối PACS tự động (ngoài phạm vi MVP); người dùng xuất zip DICOM từ PACS hoặc máy trạm MRI rồi upload.
- **Không triển khai HA.** Hệ thống là công cụ hỗ trợ quyết định: khi hệ thống ngừng, bác sĩ vẫn đọc phim từ PACS như bình thường. Code cũng chỉ hỗ trợ 1 process. Phục hồi dựa vào backup (mục 6).

## 3. Phần cứng

**Máy chủ ứng dụng (1 máy)**

| Hạng mục | Cấu hình | Lý do |
| --- | --- | --- |
| Dạng máy | Server rack 2U, bảo hành onsite next-business-day. Không có tủ rack thì dùng workstation tower. | |
| GPU | 1× **NVIDIA L4 24 GB** (server: 72 W, tản thụ động). Workstation tower thì dùng RTX 4000 Ada 20 GB hoặc RTX A4000 16 GB. **Tối thiểu 16 GB VRAM.** | Đã chạy thật trên T4 16 GB. VRAM đỉnh của TotalSpineSeg *(ước tính)* dưới 16 GB, cần đo (mục 10). |
| CPU | 12–16 core x86-64, có AVX2 | Tiền/hậu xử lý nnU-Net, `analyze()`, chuyển DICOM đều chạy CPU |
| RAM | 32 GB ECC | nnU-Net inference, resample volume, SimpleITK, page cache |
| Ổ OS | 2× 480 GB SSD, RAID 1 | CUDA, PyTorch, venv, wheelhouse khoảng vài chục GB |
| Ổ data | 2× 1,92 TB NVMe, RAID 1, mã hóa LUKS, mount `/srv/spine` | Chứa ảnh bệnh nhân; RAID 1 để hỏng 1 ổ không mất dữ liệu (mục 5) |
| Mạng | 2× 1 GbE: 1 cổng LAN lâm sàng, 1 cổng quản trị/backup | Zip DICOM khoảng 19–25 MB/ca, upload dưới 1 s |
| Nguồn | PSU kép, cắm UPS phòng server | |

**Lưu trữ backup:** NAS sẵn có của bệnh viện, hoặc NAS riêng có RAID, **≥ 2 TB dùng được**.

## 4. Phần mềm

| Thành phần | Phiên bản | Ghi chú |
| --- | --- | --- |
| OS | Ubuntu Server 22.04 LTS hoặc 24.04 LTS | |
| NVIDIA driver | ≥ 550 | Đủ cho CUDA 12.4. Không cần cài CUDA toolkit vì wheel PyTorch đã kèm runtime. |
| Python | 3.12, venv tại `/opt/spine/.venv` | |
| PyTorch | `torch<2.6`, bản `cu124` | Yêu cầu của TotalSpineSeg |
| TotalSpineSeg | `totalspineseg[nnunetv2]`, `kornia<0.8` | Cùng venv với BE |
| Thư viện BE/AI | `be/requirements.txt`, `pipeline/requirements.txt` | |
| nginx | bản của OS | TLS, giới hạn truy cập, đăng nhập |
| sqlite3 CLI | bản của OS | Để backup |
| Frontend | file tĩnh `fe/dist` | Build trên máy dev rồi copy sang; server không cần Node.js |

**Cài offline (server không có Internet):**

- **Weights của model (khoảng 4 GB):** lần chạy đầu TotalSpineSeg tự tải từ GitHub, trên server sẽ lỗi. Phải tải trên máy có Internet rồi copy vào `/srv/spine/models` (`TOTALSPINESEG_DATA`).
- **Gói Python:** dùng `pip download` thành wheelhouse trên một máy cùng OS và cùng phiên bản Python, rồi trên server chạy `pip install --no-index --find-links wheelhouse/ ...`. Nếu bệnh viện có mirror PyPI nội bộ thì dùng mirror.

## 5. Mạng và bảo mật

App **không có đăng nhập và phân quyền** (ngoài phạm vi MVP, spec mục 1), trong khi dữ liệu là ảnh MRI bệnh nhân. Các lớp bảo vệ dưới đây là bắt buộc:

| Lớp | Yêu cầu |
| --- | --- |
| DNS | Bản ghi nội bộ, ví dụ `spine.bv.local`, trỏ về IP server |
| TLS | Chứng chỉ do CA nội bộ của bệnh viện cấp; HTTP 80 chuyển sang 443 |
| Firewall | Cổng 443 chỉ mở cho VLAN lâm sàng; cổng 22 chỉ mở cho VLAN quản trị IT. **Chặn mọi kết nối ra ngoài** từ server. |
| Đăng nhập | nginx `auth_basic`, mỗi người dùng một tài khoản. Có thể thay bằng LDAP/AD nếu bệnh viện yêu cầu. |
| Giới hạn IP | nginx `allow` dải VLAN lâm sàng, `deny all` |
| Cổng app | uvicorn chỉ nghe `127.0.0.1:8000` |
| Dữ liệu lưu trữ | Ổ data mã hóa LUKS; NAS backup nằm trong mạng nội bộ |
| Audit | nginx access log ghi user và đường dẫn `/api/v1/jobs/{id}`, tức ai đã xem ca nào. Lưu theo quy định của bệnh viện. |

**Dữ liệu cá nhân:**

- File DICOM (header có thông tin bệnh nhân) bị xóa ngay sau khi chuyển sang NIfTI.
- NIfTI và `dicom_info` chỉ giữ thông tin series, không có tên hay mã bệnh nhân.
- Tuy nhiên **tên file upload được lưu trong DB và hiện ở danh sách job**. Quy định đặt tên zip theo mã ca hoặc mã bệnh án, **không dùng tên bệnh nhân**.

## 6. Lưu trữ, retention và backup

**Dung lượng** *(ước tính khoảng 50 MB/job, gồm NIfTI input, toàn bộ output của TotalSpineSeg và log; cần đo)*

| Mục | Ở mức thiết kế (100 ca/ngày, 260 ngày làm việc/năm) |
| --- | --- |
| Jobs mỗi năm | 26.000 job, khoảng 1,3 TB nếu không xóa |
| Giữ 90 ngày | Khoảng 6.500 job, khoảng 330 GB |
| Giữ 180 ngày | Khoảng 13.000 job, khoảng 650 GB |
| SQLite | Khoảng 10 KB/job, khoảng 260 MB/năm |
| Weights | Khoảng 4 GB |

**Retention:** đề xuất giữ **90 ngày**. Kết quả của hệ thống là gợi ý, không phải hồ sơ bệnh án, và ảnh gốc vẫn lưu ở PACS. Nếu bệnh viện muốn lưu kết quả như một phần hồ sơ bệnh án thì phải theo quy định lưu trữ hồ sơ và tính lại dung lượng. Việc xóa dùng `DELETE /api/v1/jobs/{id}` cho các job có `created_at` quá hạn; script retention **chưa có**, cần viết (mục 11).

**Backup hằng đêm (cron 02:00):**

```bash
sqlite3 /srv/spine/app.db ".backup '/mnt/nas/spine/db/app-$(date +%F).db'"   # an toàn khi app đang chạy
rsync -a --delete /srv/spine/jobs/ /mnt/nas/spine/jobs/
find /mnt/nas/spine/db -name 'app-*.db' -mtime +30 -delete                  # giữ 30 bản DB
```

- `rsync --delete` là bản sao gương, không có lịch sử: một job bị xóa nhầm chỉ khôi phục được trước lần backup kế tiếp. Nếu NAS hỗ trợ snapshot thì bật snapshot hằng ngày.
- Không backup `models/`, vì có thể copy lại từ bộ cài offline.
- **RPO 24 giờ, RTO 1 ngày làm việc.** RTO phụ thuộc bảo hành phần cứng: cài lại theo mục 7, restore DB và `jobs/` từ NAS.

## 7. Vận hành

**Biến môi trường** (`/etc/spine.env`)

```
DATA_DIR=/srv/spine
TOTALSPINESEG_DATA=/srv/spine/models
MAX_UPLOAD_MB=200
JOB_TIMEOUT_SEC=900
MAX_PENDING_JOBS=50
SERVE_FRONTEND=1
FRONTEND_DIST=/opt/spine/fe/dist
```

**systemd** (`/etc/systemd/system/spine-api.service`). Chỉ 1 process: không dùng `--workers` hay `--reload`, vì mỗi process có một worker thread riêng và sẽ tranh GPU. `WorkingDirectory` phải là gốc repo để `ai/analyze.py` tìm được `pipeline/src/`.

```ini
[Unit]
Description=Spine segmentation API
After=network-online.target

[Service]
User=spine
WorkingDirectory=/opt/spine
EnvironmentFile=/etc/spine.env
ExecStart=/opt/spine/.venv/bin/python -m uvicorn be.app.main:app --host 127.0.0.1 --port 8000
Restart=on-failure
TimeoutStopSec=30

[Install]
WantedBy=multi-user.target
```

**nginx** (`/etc/nginx/sites-available/spine`)

```nginx
server {
    listen 80;
    server_name spine.bv.local;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl;
    server_name spine.bv.local;
    ssl_certificate     /etc/ssl/spine/spine.crt;   # CA nội bộ
    ssl_certificate_key /etc/ssl/spine/spine.key;

    allow 10.10.0.0/16;                              # VLAN lâm sàng, thay theo bệnh viện
    deny  all;
    auth_basic           "Spine";
    auth_basic_user_file /etc/nginx/spine.htpasswd;

    client_max_body_size 200m;                       # khớp MAX_UPLOAD_MB
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_read_timeout 120s;                     # upload zip có chuyển DICOM trong request
    }
}
```

**Giám sát** (dùng hệ thống giám sát sẵn có của bệnh viện, ví dụ Zabbix):

| Kiểm tra | Tần suất | Cảnh báo khi |
| --- | --- | --- |
| `GET /api/v1/health` | 1 phút | Không trả 200, hoặc `gpu_available = false` |
| Dung lượng `/srv/spine` | 15 phút | Trên 80% |
| `GET /api/v1/jobs?status=failed` | Hằng ngày | `total` tăng bất thường |
| Nhiệt độ GPU (`nvidia-smi`) | 5 phút | Vượt ngưỡng của hãng |
| Job backup | Hằng ngày | Không có file `app-<ngày>.db` mới trên NAS |
| Log app | | `journalctl -u spine-api`; log từng job ở `jobs/<id>/logs/totalspineseg.log` |

**Cập nhật phiên bản**

1. Kiểm tra `GET /api/v1/jobs?status=running` trả `total = 0`. Nếu restart khi đang có job chạy, job đó thành `failed` với mã `WORKER_INTERRUPTED`.
2. `systemctl stop spine-api`, rồi backup DB bằng lệnh `.backup` ở mục 6.
3. Cập nhật code, venv (từ wheelhouse) và `fe/dist`.
4. `systemctl start spine-api`, kiểm tra `/health`, rồi chạy ca mẫu `0100` và so với `ai/demo/analysis_0100.json`.

## 8. Phân vai

| Việc | Bên phụ trách |
| --- | --- |
| Server, GPU, UPS, NAS, VLAN, firewall, DNS, chứng chỉ CA nội bộ | Phòng CNTT bệnh viện |
| Cài OS, driver, cài app offline, nginx, systemd, backup cron | Nhóm dự án cùng phòng CNTT |
| Tạo và thu hồi tài khoản người dùng (htpasswd hoặc AD) | Phòng CNTT |
| Theo dõi cảnh báo, kiểm tra restore định kỳ | Phòng CNTT |
| Cập nhật phiên bản, xử lý job lỗi | Nhóm dự án |

## 9. Ngoài phạm vi

- HA, nhiều GPU, nhiều server.
- Kết nối PACS tự động (DICOM C-STORE, DICOMweb).
- Đăng nhập, phân quyền trong app (tạm dùng nginx).
- Truy cập từ ngoài bệnh viện, VPN.

## 10. Nghiệm thu trên máy đích

Chạy trước khi đưa vào dùng. Kết quả đo ở các bước 1–2 dùng để thay các số *(ước tính)* trong tài liệu.

1. **Hiệu năng 1 ca:** upload ca `0100`. Trong lúc chạy, đo `nvidia-smi --query-gpu=memory.used --format=csv -lms 500` (VRAM đỉnh), `free -m` (RAM đỉnh), `duration_seconds` của job và `du -sh /srv/spine/jobs/<id>` (dung lượng mỗi job).
2. **Đỉnh tải:** gửi 50 job liên tiếp. Tất cả phải xong; job thứ 51 (khi 50 job còn `pending`) phải nhận `503 QUEUE_FULL`. Ghi lại thời gian xả hết hàng chờ.
3. **Restart giữa job:** job đang chạy chuyển `failed` với mã `WORKER_INTERRUPTED`; các job `pending` vẫn chạy tiếp sau khi khởi động lại.
4. **Offline:** khi đã chặn outbound, job đầu tiên sau khi cài vẫn chạy được, nghĩa là không cần tải weights.
5. **Khôi phục:** restore DB và `jobs/` từ NAS sang một máy khác; danh sách job và kết quả xem lại được.
6. **Bảo mật:**
   - Từ VLAN khác thì bị chặn.
   - Không có tài khoản thì nhận `401`.
   - Cổng 8000 không truy cập được từ mạng.
   - Sau khi upload zip, không còn file `.dcm` nào trên ổ.

## 11. Việc còn thiếu trong code

| Việc | Mức | Ghi chú |
| --- | --- | --- |
| Script retention xóa job quá hạn | Cần trước khi chạy thật | Cron gọi `GET /api/v1/jobs` rồi `DELETE` các job có `created_at` quá hạn |
| Đăng nhập trong app | Tạm thay bằng nginx | Nếu cần phân quyền theo khoa hoặc theo ca thì phải làm trong app |
| Kết nối PACS | Sau MVP | Hiện người dùng xuất zip thủ công |
