from __future__ import annotations

import re


E164_RE = re.compile(r"^\+[1-9]\d{7,14}$")


def normalize_e164(phone: str) -> str:
    normalized = phone.strip().replace(" ", "")
    if not E164_RE.match(normalized):
        raise ValueError("Phone number must be valid E.164 format")
    return normalized

