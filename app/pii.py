from __future__ import annotations

import hashlib
import re

PII_PATTERNS: dict[str, str] = {
    "email": r"[\w\.-]+@[\w\.-]+\.\w+",
    "phone_vn": r"(?:\+84|0)[ \.-]?\d{3}[ \.-]?\d{3}[ \.-]?\d{3,4}", # Matches 090 123 4567, 090.123.4567, etc.
    "cccd": r"\b\d{12}\b",
    "credit_card": r"\b\d{4}[ \-]?\d{4}[ \-]?\d{4}[ \-]?\d{4}\b",
    # TODO: Add more patterns (e.g., Passport, Vietnamese address keywords)
    "passport": r"\b[A-Z]\d{7,8}\b",
    
    # Mã số thuế (MST): 10 số (cá nhân/DN) hoặc 13 số (chi nhánh)
    "tax_id": r"\b\d{10}(?:-\d{3})?\b",
    
    # Từ khóa địa chỉ Việt Nam (Dùng để nhận diện vùng chứa địa chỉ)
    "address_vn": r"(?i)\b(?:số|đường|phố|ngõ|ngách|thôn|xóm|xã|phường|quận|huyện|tỉnh|thành phố)\b.*",
}


def scrub_text(text: str) -> str:
    safe = text
    for name, pattern in PII_PATTERNS.items():
        safe = re.sub(pattern, f"[REDACTED_{name.upper()}]", safe)
    return safe


def summarize_text(text: str, max_len: int = 80) -> str:
    safe = scrub_text(text).strip().replace("\n", " ")
    return safe[:max_len] + ("..." if len(safe) > max_len else "")


def hash_user_id(user_id: str) -> str:
    return hashlib.sha256(user_id.encode("utf-8")).hexdigest()[:12]
