import hashlib
import re
import ipaddress
from datetime import datetime
from typing import Optional, Any

def calculate_sha256(file_bytes: bytes) -> str:
    """Computes SHA-256 for court-admissible evidence integrity."""
    hasher = hashlib.sha256()
    hasher.update(file_bytes)
    return hasher.hexdigest()

def clean_phone_number(raw_val: Any) -> str:
    """Sanitizes Indian phone numbers into standardized +91XXXXXXXXXX format."""
    if not raw_val:
        return ""
    digits = re.sub(r"\D", "", str(raw_val))
    if len(digits) == 10:
        return f"+91{digits}"
    elif len(digits) == 12 and digits.startswith("91"):
        return f"+{digits}"
    elif len(digits) == 11 and digits.startswith("0"):
        return f"+91{digits[1:]}"
    return digits

def clean_amount(raw_val: Any) -> Optional[float]:
    """Cleans currency strings like '₹ 1,50,000.00' or '150000.00 CR' into float."""
    if raw_val is None:
        return None
    cleaned = re.sub(r"[^\d.]", "", str(raw_val))
    try:
        return float(cleaned) if cleaned else None
    except ValueError:
        return None

def clean_ip(raw_val: Any) -> Optional[str]:
    """Validates IPv4 / IPv6 addresses and strips ports if present."""
    if not raw_val:
        return None
    cleaned = str(raw_val).strip().split(":")[0]
    try:
        ipaddress.ip_address(cleaned)
        return cleaned
    except ValueError:
        return None

def parse_flexible_datetime(raw_val: Any) -> datetime:
    """Parses heterogeneous date-time formats from different vendor exports."""
    if not raw_val:
        return datetime.utcnow()
    val_str = str(raw_val).strip()
    
    formats = [
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S",
        "%d-%m-%Y %H:%M:%S",
        "%d/%m/%Y %H:%M:%S",
        "%d/%m/%Y %H:%M",
        "%Y/%m/%d %H:%M:%S"
    ]
    for fmt in formats:
        try:
            return datetime.strptime(val_str, fmt)
        except ValueError:
            pass
    try:
        return datetime.fromisoformat(val_str.replace("Z", "+00:00"))
    except Exception:
        return datetime.utcnow()