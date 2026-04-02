"""
parser.py - Parse due date & minimum payment from bank statement emails
Supports: BIDV, SHB, VIB, VPBank, HSBC
"""

import re
from datetime import datetime, date


def parse_date(text: str) -> date | None:
    """Try common Vietnamese date formats."""
    patterns = [
        r"(\d{2})/(\d{2})/(\d{4})",   # DD/MM/YYYY
        r"(\d{2})-(\d{2})-(\d{4})",   # DD-MM-YYYY
        r"(\d{4})-(\d{2})-(\d{2})",   # YYYY-MM-DD
        r"(\d{2})/(\d{2})/(\d{2})",   # DD/MM/YY
    ]
    for pat in patterns:
        m = re.search(pat, text)
        if m:
            g = m.groups()
            try:
                if len(g[0]) == 4:  # YYYY-MM-DD
                    return date(int(g[0]), int(g[1]), int(g[2]))
                elif int(g[2]) < 100:  # DD/MM/YY
                    return date(2000 + int(g[2]), int(g[1]), int(g[0]))
                else:
                    return date(int(g[2]), int(g[1]), int(g[0]))
            except ValueError:
                continue
    return None


def parse_amount(text: str) -> str:
    """Extract currency amount from text."""
    # Match numbers like 1,234,567 or 1.234.567 or 1234567
    m = re.search(r"([\d][,.\d]*\d)\s*(?:VND|đ|VNĐ|USD)?", text, re.IGNORECASE)
    if m:
        return m.group(0).strip()
    return "N/A"


# ──────────────────────────────────────────────
# Bank-specific parsers
# ──────────────────────────────────────────────

def parse_bidv(subject: str, body: str, sender: str = "") -> dict | None:
    """BIDV credit card statement email — from saokethebidv@bidv.com.vn."""
    if sender and "saokethebidv@bidv.com.vn" not in sender.lower():
        return None
    if not sender and not re.search(r"BIDV|sao k[eê]", subject + body, re.IGNORECASE):
        return None

    due_keywords = [
        # "Ngày hết hạn thanh toán/Due Date 06-04-2026"
        r"Ng[àa]y h[eế]t h[aạ]n thanh to[áa]n/Due Date\s+([\d\-/]+)",
        r"Due Date\s+([\d\-/]+)",
        r"[Hh][aạ]n\s+thanh\s+to[áa]n[^:]*[:\s]+([\d\-/]+)",
    ]
    balance_keywords = [
        # "Dư nợ cuối kỳ/Closing Balance -43,978,880.00"
        r"D[ưu] n[ợo] cu[oố]i k[ỳy]/Closing Balance\s+-?([\d,]+\.?\d*)",
        r"Closing Balance\s+-?([\d,]+\.?\d*)",
    ]

    # Extract card number "476632******4486"
    card_m = re.search(r"Card Number\s+([\d*]+)", body)
    card_number = card_m.group(1) if card_m else ""

    due_date = _extract_date(body, due_keywords)
    balance = _extract_text(body, balance_keywords)

    if due_date:
        return {
            "bank": "BIDV",
            "card_number": card_number,
            "due_date": due_date,
            "balance": f"{balance} VND" if balance else "N/A",
        }
    return None


def parse_shb(subject: str, body: str, sender: str = "") -> dict | None:
    """SHB credit card statement email — subject contains 'Bang sao ke dien tu the tin dung SHB VISA'."""
    if not re.search(r"Bang sao ke dien tu the tin dung SHB", subject, re.IGNORECASE):
        return None

    due_keywords = [
        # "Ngày đến hạn thanh toán: 09/04/2026" — match cả trường hợp đã strip HTML
        r"[Nn]g.{1,5}y\s+.{1,10}n\s+h.{1,5}n\s+thanh\s+to.{1,5}n\s*:\s*([\d/\-]+)",
        r"[Hh].{1,5}n\s+thanh\s+to.{1,5}n\s*:\s*([\d/\-]+)",
        # fallback: tìm pattern ngày sau keyword
        r"[\u0111\u0110d][e\u1ebf\u1ec1\u1ec3\u1ec5]\u0301?\s*n\s+h.{1,5}n[^:]*:\s*([\d/\-]+)",
    ]
    balance_keywords = [
        # "Dư nợ cuối kỳ (VNĐ): 111,141,706"
        r"[Dd].{1,5}\s+n.{1,5}\s+cu.{1,5}i\s+k.{1,5}\s*\([^)]*\)\s*:\s*([\d,]+)",
        r"[Dd].{1,3}\s+n.{1,3}\s+cu.{1,3}i\s+k.{1,3}[^:]*:\s*([\d,]+)",
    ]

    due_date = _extract_date(body, due_keywords)
    balance = _extract_text(body, balance_keywords)

    if due_date:
        return {"bank": "SHB", "due_date": due_date, "balance": f"{balance} VNĐ" if balance else "N/A"}
    return None


def parse_vib(subject: str, body: str, sender: str = "") -> dict | None:
    """VIB credit card statement email — must have VIB in subject or sender."""
    # Yêu cầu VIB rõ ràng trong subject hoặc sender, tránh match nhầm ngân hàng khác
    if not re.search(r"\bVIB\b", subject + sender, re.IGNORECASE):
        return None

    due_keywords = [
        r"[Nn]g[àa]y\s+[đd][eé]n\s+h[aạ]n[^:]*[:\s]+([\d/\-]+)",
        r"[Pp]ayment\s+[Dd]ue[^:]*[:\s]+([\d/\-]+)",
        r"[Hh][aạ]n\s+thanh\s+to[áa]n[^:]*[:\s]+([\d/\-]+)",
    ]
    min_keywords = [
        r"[Ss][oố]\s+ti[eề]n\s+t[oố]i\s+thi[eể]u[^:]*[:\s]+([\d,. ]+(?:VND|đ|VNĐ)?)",
        r"[Mm]inimum\s+[Aa]mount\s+[Dd]ue[^:]*[:\s]+([\d,. ]+(?:VND|USD|đ)?)",
    ]

    due_date = _extract_date(body, due_keywords)
    min_payment = _extract_text(body, min_keywords)

    if due_date:
        return {"bank": "VIB", "due_date": due_date, "min_payment": min_payment or "N/A"}
    return None


def parse_vpbank(subject: str, body: str, sender: str = "") -> dict | None:
    """VPBank credit card statement email."""
    if not re.search(r"VPBank|VP\s*Bank|sao k[eê]|th[eẻ] t[ií]n d[uụ]ng", subject + body, re.IGNORECASE):
        return None

    due_keywords = [
        r"[Nn]g[àa]y\s+[đd][eé]n\s+h[aạ]n[^:]*[:\s]+([\d/\-]+)",
        r"[Hh][aạ]n\s+thanh\s+to[áa]n[^:]*[:\s]+([\d/\-]+)",
        r"[Pp]ayment\s+[Dd]ue\s+[Dd]ate[^:]*[:\s]+([\d/\-]+)",
    ]
    min_keywords = [
        r"[Ss][oố]\s+ti[eề]n\s+t[oố]i\s+thi[eể]u[^:]*[:\s]+([\d,. ]+(?:VND|đ|VNĐ)?)",
        r"[Tt][oố]i\s+thi[eể]u[^:]*[:\s]+([\d,. ]+(?:VND|đ|VNĐ)?)",
    ]

    due_date = _extract_date(body, due_keywords)
    min_payment = _extract_text(body, min_keywords)

    if due_date:
        return {"bank": "VPBank", "due_date": due_date, "min_payment": min_payment or "N/A"}
    return None


def parse_hsbc(subject: str, body: str, sender: str = "") -> dict | None:
    """HSBC credit card statement email."""
    if not re.search(r"HSBC|credit\s+card\s+statement|sao k[eê]", subject + body, re.IGNORECASE):
        return None

    due_keywords = [
        r"[Pp]ayment\s+[Dd]ue\s+[Dd]ate[^:]*[:\s]+([\d/\-]+)",
        r"[Dd]ue\s+[Dd]ate[^:]*[:\s]+([\d/\-]+)",
        r"[Nn]g[àa]y\s+[đd][eé]n\s+h[aạ]n[^:]*[:\s]+([\d/\-]+)",
    ]
    min_keywords = [
        r"[Mm]inimum\s+[Pp]ayment\s+[Dd]ue[^:]*[:\s]+([\d,. ]+(?:VND|USD|đ)?)",
        r"[Mm]inimum\s+[Aa]mount\s+[Dd]ue[^:]*[:\s]+([\d,. ]+(?:VND|USD|đ)?)",
        r"[Ss][oố]\s+ti[eề]n\s+t[oố]i\s+thi[eể]u[^:]*[:\s]+([\d,. ]+(?:VND|USD|đ)?)",
    ]

    due_date = _extract_date(body, due_keywords)
    min_payment = _extract_text(body, min_keywords)

    if due_date:
        return {"bank": "HSBC", "due_date": due_date, "min_payment": min_payment or "N/A"}
    return None


# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────

def _extract_date(text: str, patterns: list[str]) -> date | None:
    for pat in patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            d = parse_date(m.group(1))
            if d:
                return d
    return None


def _extract_text(text: str, patterns: list[str]) -> str | None:
    for pat in patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            return m.group(1).strip()
    return None


ALL_PARSERS = [parse_bidv, parse_shb, parse_vib, parse_vpbank, parse_hsbc]


def parse_email(subject: str, body: str, sender: str = "") -> dict | None:
    """Try all parsers, return first match."""
    for parser in ALL_PARSERS:
        result = parser(subject, body, sender)
        if result:
            return result
    return None
