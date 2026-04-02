"""
main.py - Credit Card Payment Reminder
Reads Gmail for bank statements, sends Telegram alert 1 day before due date.
"""

import os
import base64
import json
import re
import sys
from datetime import date, timedelta
from email import message_from_bytes
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
import requests

from parser import parse_email

# ──────────────────────────────────────────────
# Config (from environment variables / GitHub Secrets)
# ──────────────────────────────────────────────

MANUAL_DATES_FILE = Path("manual_dates.json")

TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

# Gmail OAuth scopes
SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]

# How many days ahead to check (1 = alert 1 day before due)
DAYS_BEFORE = 1

# File to track already-sent alerts (avoid duplicate notifications)
SENT_ALERTS_FILE = Path("sent_alerts.json")


# ──────────────────────────────────────────────
# Gmail helpers
# ──────────────────────────────────────────────

def get_gmail_service():
    """Authenticate and return Gmail API service."""
    creds = None

    # Load token if exists (for local dev)
    if Path("token.json").exists():
        creds = Credentials.from_authorized_user_file("token.json", SCOPES)

    # Load from env if available (for GitHub Actions)
    token_env = os.environ.get("GMAIL_TOKEN_JSON")
    if token_env:
        token_data = json.loads(token_env)
        creds = Credentials.from_authorized_user_info(token_data, SCOPES)

    # Refresh if expired
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
        # Save refreshed token back (for local)
        if not os.environ.get("GMAIL_TOKEN_JSON"):
            with open("token.json", "w") as f:
                f.write(creds.to_json())

    if not creds or not creds.valid:
        # Only for local first-time setup
        flow = InstalledAppFlow.from_client_secrets_file("credentials.json", SCOPES)
        creds = flow.run_local_server(port=0)
        with open("token.json", "w") as f:
            f.write(creds.to_json())

    return build("gmail", "v1", credentials=creds)


def get_email_body(msg_data: dict) -> str:
    """Extract plain text or HTML body from Gmail message."""
    payload = msg_data.get("payload", {})

    def extract_parts(parts):
        text = ""
        for part in parts:
            mime = part.get("mimeType", "")
            data = part.get("body", {}).get("data", "")
            if mime == "text/plain" and data:
                text += base64.urlsafe_b64decode(data).decode("utf-8", errors="ignore")
            elif mime == "text/html" and data and not text:
                html = base64.urlsafe_b64decode(data).decode("utf-8", errors="ignore")
                # Strip HTML tags
                text += re.sub(r"<[^>]+>", " ", html)
            elif "parts" in part:
                text += extract_parts(part["parts"])
        return text

    if "parts" in payload:
        return extract_parts(payload["parts"])
    elif payload.get("body", {}).get("data"):
        data = payload["body"]["data"]
        return base64.urlsafe_b64decode(data).decode("utf-8", errors="ignore")
    return ""


def fetch_bank_emails(service) -> list[dict]:
    """Search Gmail for bank statement emails from last 60 days."""
    query = (
        "subject:(sao kê OR statement OR credit card OR thẻ tín dụng) "
        "from:(bidv OR shb OR vib OR vpbank OR hsbc) "
        "newer_than:60d"
    )

    result = service.users().messages().list(userId="me", q=query, maxResults=50).execute()
    messages = result.get("messages", [])

    emails = []
    for msg in messages:
        msg_data = service.users().messages().get(
            userId="me", messageId=msg["id"], format="full"
        ).execute()

        headers = {h["name"]: h["value"] for h in msg_data["payload"].get("headers", [])}
        subject = headers.get("Subject", "")
        body = get_email_body(msg_data)

        emails.append({
            "id": msg["id"],
            "subject": subject,
            "body": body,
        })

    return emails


# ──────────────────────────────────────────────
# Telegram helpers
# ──────────────────────────────────────────────

def send_telegram(message: str):
    """Send message via Telegram Bot API."""
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "HTML",
    }
    resp = requests.post(url, json=payload, timeout=10)
    resp.raise_for_status()
    print(f"✅ Telegram sent: {message[:60]}...")


# ──────────────────────────────────────────────
# Dedup helpers
# ──────────────────────────────────────────────

def load_manual_dates() -> list[dict]:
    """Load manually entered due dates for HSBC, VIB, VPBank."""
    if not MANUAL_DATES_FILE.exists():
        return []
    data = json.loads(MANUAL_DATES_FILE.read_text(encoding="utf-8"))
    results = []
    for entry in data:
        due_str = entry.get("due_date", "").strip()
        if not due_str:
            continue
        try:
            # Accept DD/MM/YYYY or YYYY-MM-DD
            if "/" in due_str:
                d, m, y = due_str.split("/")
                due_date = date(int(y), int(m), int(d))
            else:
                due_date = date.fromisoformat(due_str)
            results.append({
                "bank": entry.get("bank", "Manual"),
                "due_date": due_date,
                "min_payment": entry.get("min_payment", "N/A") or "N/A",
            })
        except (ValueError, AttributeError):
            print(f"⚠️ Ngày không hợp lệ cho {entry.get('bank')}: {due_str}")
    return results


def load_sent_alerts() -> set:
    if SENT_ALERTS_FILE.exists():
        data = json.loads(SENT_ALERTS_FILE.read_text())
        return set(data)
    return set()


def save_sent_alerts(alerts: set):
    SENT_ALERTS_FILE.write_text(json.dumps(list(alerts)))


# ──────────────────────────────────────────────
# Main logic
# ──────────────────────────────────────────────

def main():
    today = date.today()
    target_date = today + timedelta(days=DAYS_BEFORE)

    print(f"📅 Today: {today} | Checking due dates on: {target_date}")

    service = get_gmail_service()
    emails = fetch_bank_emails(service)
    print(f"📧 Found {len(emails)} bank emails to check")

    # Collect all due dates: auto (Gmail) + manual
    all_results = []

    for email in emails:
        result = parse_email(email["subject"], email["body"])
        if result:
            all_results.append(result)

    manual = load_manual_dates()
    print(f"📝 Manual entries: {len(manual)}")
    all_results.extend(manual)

    sent_alerts = load_sent_alerts()
    new_alerts = set()
    notified = 0

    for result in all_results:
        bank = result["bank"]
        due_date = result["due_date"]
        min_payment = result["min_payment"]

        alert_key = f"{bank}:{due_date}"
        print(f"  🏦 {bank}: due={due_date}, min={min_payment}")

        if due_date == target_date and alert_key not in sent_alerts:
            message = (
                f"⚠️ <b>Nhắc thanh toán thẻ tín dụng</b>\n\n"
                f"🏦 Ngân hàng: <b>{bank}</b>\n"
                f"📅 Ngày đến hạn: <b>{due_date.strftime('%d/%m/%Y')}</b>\n"
                f"💳 Số tiền tối thiểu: <b>{min_payment}</b>\n\n"
                f"⏰ Hãy thanh toán trước ngày mai để tránh phí phạt!"
            )
            send_telegram(message)
            new_alerts.add(alert_key)
            notified += 1

    if notified == 0:
        print("✅ Không có thẻ nào đến hạn ngày mai")
    else:
        print(f"🔔 Đã gửi {notified} cảnh báo")

    sent_alerts.update(new_alerts)
    save_sent_alerts(sent_alerts)


def ask_manual_input():
    """
    Gửi tin nhắn hỏi Thành nhập ngày đến hạn.
    Tự detect ngân hàng theo ngày hiện tại, hoặc đọc env ASK_BANK.
    Lịch chốt sao kê: HSBC=5, VIB=25, VPBank=27 → hỏi sau 2 ngày.
    """
    # Map: ngày hỏi → ngân hàng
    SCHEDULE = {
        7:  ["HSBC"],
        27: ["VIB"],
        29: ["VPBank"],
    }

    ask_bank_env = os.environ.get("ASK_BANK", "auto").strip().lower()
    today_day = date.today().day

    if ask_bank_env == "all":
        banks = ["HSBC", "VIB", "VPBank"]
    elif ask_bank_env not in ("auto", ""):
        # Manual trigger với tên ngân hàng cụ thể
        banks = [ask_bank_env.upper()]
        if banks[0] == "VPBANK":
            banks = ["VPBank"]
    else:
        # Tự detect theo ngày
        banks = SCHEDULE.get(today_day, [])

    if not banks:
        print(f"⏭️ Hôm nay (ngày {today_day}) không có ngân hàng nào cần hỏi")
        return

    examples = {
        "HSBC":   "HSBC 15/04/2026 500000",
        "VIB":    "VIB 20/04/2026 300000",
        "VPBank": "VPBank 22/04/2026 1200000",
    }
    example_lines = "\n".join(f"<code>{examples[b]}</code>" for b in banks if b in examples)

    message = (
        f"📋 <b>Nhập thông tin sao kê thẻ tháng này</b>\n\n"
        f"Ngân hàng cần nhập: " + ", ".join(f"<b>{b}</b>" for b in banks) + "\n\n"
        f"Reply theo format:\n"
        f"<code>TÊN_NGÂN_HÀNG DD/MM/YYYY số_tiền</code>\n\n"
        f"Ví dụ:\n{example_lines}"
    )
    send_telegram(message)
    print(f"✅ Đã gửi yêu cầu nhập thông tin cho: {', '.join(banks)}")


def collect_manual_replies():
    """
    Đọc các tin nhắn reply từ Telegram, parse và lưu vào manual_dates.json.
    Chạy sau ask_manual_input() vài tiếng (cron riêng).
    """
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates"
    # Lấy offset từ file để không đọc lại tin cũ
    offset_file = Path("telegram_offset.txt")
    offset = int(offset_file.read_text()) if offset_file.exists() else 0

    resp = requests.get(url, params={"offset": offset, "limit": 50, "timeout": 5}, timeout=15)
    resp.raise_for_status()
    updates = resp.json().get("result", [])

    if not updates:
        print("📭 Không có reply mới")
        return

    # Load existing manual dates
    existing = []
    if MANUAL_DATES_FILE.exists():
        existing = json.loads(MANUAL_DATES_FILE.read_text(encoding="utf-8"))
    existing_map = {e["bank"]: e for e in existing}

    pattern = re.compile(
        r"^(HSBC|VIB|VPBank)\s+(\d{1,2}/\d{1,2}/\d{4})\s+([\d,. ]+(?:VND|đ)?)",
        re.IGNORECASE
    )

    parsed_count = 0
    last_update_id = offset

    for update in updates:
        last_update_id = update["update_id"] + 1
        msg = update.get("message", {})
        chat_id = str(msg.get("chat", {}).get("id", ""))
        text = msg.get("text", "").strip()

        # Chỉ xử lý tin từ chat của Thành
        if chat_id != TELEGRAM_CHAT_ID:
            continue

        for line in text.splitlines():
            m = pattern.match(line.strip())
            if m:
                bank = m.group(1).upper()
                # Normalize bank name
                if bank == "VPBANK":
                    bank = "VPBank"
                due_str = m.group(2)
                amount = m.group(3).strip()
                existing_map[bank] = {
                    "bank": bank,
                    "due_date": due_str,
                    "min_payment": amount,
                }
                print(f"  ✅ Parsed: {bank} → {due_str} | {amount}")
                parsed_count += 1

    # Save updated offset
    offset_file.write_text(str(last_update_id))

    if parsed_count > 0:
        updated = list(existing_map.values())
        MANUAL_DATES_FILE.write_text(
            json.dumps(updated, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )
        send_telegram(f"✅ Đã lưu thông tin <b>{parsed_count}</b> thẻ. Mình sẽ nhắc bạn trước 1 ngày đến hạn!")
        print(f"✅ Saved {parsed_count} manual entries")
    else:
        print("⚠️ Không tìm thấy dữ liệu hợp lệ trong các reply")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        if sys.argv[1] == "ask":
            ask_manual_input()
        elif sys.argv[1] == "collect":
            collect_manual_replies()
        else:
            print(f"Unknown command: {sys.argv[1]}")
    else:
        main()
