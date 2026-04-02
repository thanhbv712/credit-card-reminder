# 💳 Credit Card Payment Reminder

Tự động đọc email sao kê thẻ tín dụng từ Gmail và gửi cảnh báo qua Telegram trước 1 ngày đến hạn.

**Hỗ trợ:** BIDV, SHB, VIB, VPBank, HSBC

---

## 🚀 Setup (làm 1 lần)

### Bước 1: Tạo GitHub repo

1. Tạo repo mới trên GitHub (ví dụ: `credit-card-reminder`)
2. Push toàn bộ code này lên repo

### Bước 2: Bật Gmail API

1. Vào [Google Cloud Console](https://console.cloud.google.com/)
2. Tạo project mới (hoặc dùng project có sẵn)
3. Vào **APIs & Services → Enable APIs** → tìm **Gmail API** → Enable
4. Vào **APIs & Services → Credentials** → **Create Credentials → OAuth client ID**
   - Application type: **Desktop app**
   - Download file JSON → đổi tên thành `credentials.json`
   - Đặt vào thư mục project
5. Vào **OAuth consent screen** → thêm email của bạn vào **Test users**

### Bước 3: Tạo Gmail token

```bash
pip install -r requirements.txt
python setup_gmail.py
```

Trình duyệt sẽ mở, đăng nhập Gmail → cho phép quyền đọc email.

Script sẽ in ra nội dung JSON → copy để dùng ở bước sau.

### Bước 4: Thêm GitHub Secrets

Vào repo GitHub → **Settings → Secrets and variables → Actions → New repository secret**

| Secret name | Giá trị |
|-------------|---------|
| `TELEGRAM_TOKEN` | Token bot Telegram của bạn |
| `TELEGRAM_CHAT_ID` | Chat ID Telegram của bạn |
| `GMAIL_TOKEN_JSON` | Nội dung JSON từ bước 3 |

### Bước 5: Test thử

Vào GitHub repo → **Actions** → **Credit Card Payment Reminder** → **Run workflow**

---

## 📅 Lịch chạy

Script chạy tự động lúc **8:00 AM mỗi ngày** (GMT+7).

Nếu có thẻ đến hạn ngày mai, bạn sẽ nhận Telegram như này:

```
⚠️ Nhắc thanh toán thẻ tín dụng

🏦 Ngân hàng: VPBank
📅 Ngày đến hạn: 15/04/2026
💳 Số tiền tối thiểu: 1,200,000 VND

⏰ Hãy thanh toán trước ngày mai để tránh phí phạt!
```

---

## 🔧 Tùy chỉnh

Chỉnh trong `main.py`:
- `DAYS_BEFORE = 1` → cảnh báo trước bao nhiêu ngày
- Cron schedule trong `.github/workflows/reminder.yml` → đổi giờ chạy

---

## 📁 Cấu trúc project

```
credit-card-reminder/
├── main.py              # Script chính
├── parser.py            # Parse email từng ngân hàng
├── setup_gmail.py       # Chạy 1 lần để tạo Gmail token
├── requirements.txt     # Python dependencies
└── .github/
    └── workflows/
        └── reminder.yml # GitHub Actions workflow
```
