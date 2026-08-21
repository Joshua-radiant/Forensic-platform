import json
import uuid
from typing import List
from ..models import ForensicRecord, Entity
from ..utils import clean_phone_number, clean_ip, parse_flexible_datetime

def parse_social_activity(file_bytes: bytes, filename: str, file_hash: str) -> List[ForensicRecord]:
    try:
        data = json.loads(file_bytes.decode("utf-8"))
    except Exception:
        return []

    records: List[ForensicRecord] = []
    entries = data if isinstance(data, list) else [data]

    for item in entries:
        raw_ts = (
            item.get("timestamp") 
            or item.get("timestamp_utc") 
            or item.get("created_at") 
            or item.get("date_time")
        )
        parsed_ts = parse_flexible_datetime(raw_ts)
        
        # Comprehensive handle identification
        handle_raw = (
            item.get("handle") 
            or item.get("account_handle") 
            or item.get("username") 
            or item.get("user_id") 
            or item.get("profile")
            or ""
        )
        handle = str(handle_raw).strip()
        if not handle:
            continue
            
        # Associated identifiers & IP
        assoc = item.get("associated_identifiers") or {}
        phone_raw = assoc.get("phone_number") if isinstance(assoc, dict) else None
        phone = clean_phone_number(phone_raw or item.get("phone") or item.get("mobile"))
        
        ip = clean_ip(
            item.get("ip_address") 
            or item.get("source_ip") 
            or item.get("ip") 
            or item.get("last_login_ip")
        )
        
        action = str(
            item.get("action") 
            or item.get("action_type") 
            or item.get("activity") 
            or item.get("platform") 
            or "POST"
        ).upper()

        # Handle flat or nested GPS coordinates
        loc = item.get("location") or {}
        lat_val = (
            item.get("geo_lat") 
            or item.get("lat") 
            or item.get("latitude") 
            or (loc.get("latitude") if isinstance(loc, dict) else None)
        )
        lon_val = (
            item.get("geo_lon") 
            or item.get("lon") 
            or item.get("longitude") 
            or (loc.get("longitude") if isinstance(loc, dict) else None)
        )

        geo_lat = None
        geo_lon = None
        try:
            if lat_val is not None and str(lat_val).strip() != "":
                geo_lat = float(lat_val)
            if lon_val is not None and str(lon_val).strip() != "":
                geo_lon = float(lon_val)
        except (ValueError, TypeError):
            pass

        rec_id = item.get("event_id") or f"SOC-{uuid.uuid4().hex[:8]}"

        records.append(ForensicRecord(
            record_id=str(rec_id),
            source_domain="SOCIAL",
            raw_source_file=filename,
            file_sha256=file_hash,
            timestamp=parsed_ts,
            primary_entity=Entity(entity_type="HANDLE", value=handle),
            secondary_entity=Entity(entity_type="PHONE", value=phone) if phone else None,
            action=action,
            ip_address=ip,
            geo_lat=geo_lat,
            geo_lon=geo_lon,
            raw_metadata=item
        ))
    return records