"""
setup_gmail.py - Chạy 1 lần để tạo token.json từ credentials.json
Chạy: python setup_gmail.py
"""

from google_auth_oauthlib.flow import InstalledAppFlow
import json

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]

flow = InstalledAppFlow.from_client_secrets_file("credentials.json", SCOPES)
creds = flow.run_local_server(port=0)

with open("token.json", "w") as f:
    f.write(creds.to_json())

print("✅ token.json đã được tạo!")
print()
print("📋 Copy nội dung dưới đây vào GitHub Secret GMAIL_TOKEN_JSON:")
print()
print(creds.to_json())
