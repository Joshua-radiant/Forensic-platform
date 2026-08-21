import io
import uuid
import polars as pl
from typing import List
from ..models import ForensicRecord, Entity
from ..utils import clean_phone_number, clean_ip, parse_flexible_datetime

def parse_telecom_cdr(file_bytes: bytes, filename: str, file_hash: str) -> List[ForensicRecord]:
    df = pl.read_csv(io.BytesIO(file_bytes), infer_schema_length=5000, ignore_errors=True)
    col_map = {col: col.lower().strip().replace(" ", "_") for col in df.columns}
    df = df.rename(col_map)
    
    records: List[ForensicRecord] = []
    for row in df.iter_rows(named=True):
        # 1. Flexible timestamp extraction
        raw_ts = (
            row.get("timestamp") 
            or row.get("call_date_time") 
            or row.get("session_start") 
            or row.get("date")
            or row.get("start_time")
        )
        parsed_ts = parse_flexible_datetime(raw_ts)
        
        # 2. Comprehensive caller & receiver column resolution
        calling_raw = (
            row.get("caller") 
            or row.get("calling_no") 
            or row.get("a_party") 
            or row.get("source_number") 
            or row.get("calling_party")
            or row.get("originating_number")
        )
        called_raw = (
            row.get("receiver") 
            or row.get("called_no") 
            or row.get("b_party") 
            or row.get("dest_number") 
            or row.get("destination_number")
            or row.get("receiving_party")
        )
        
        calling = clean_phone_number(calling_raw)
        called = clean_phone_number(called_raw)
        
        # If neither party can be resolved, skip row
        if not calling and not called:
            continue
            
        ip = clean_ip(row.get("source_ip") or row.get("ip_address") or row.get("nat_ip") or row.get("ip"))
        imei = str(row.get("imei") or row.get("device_id") or row.get("cell_tower_id") or "").strip() or None
        
        # 3. Flexible geo coordinate resolution
        geo_lat = None
        geo_lon = None
        lat_val = row.get("geo_lat") or row.get("lat") or row.get("latitude")
        lon_val = row.get("geo_lon") or row.get("lon") or row.get("longitude") or row.get("lng")
        
        try:
            if lat_val is not None and str(lat_val).strip() != "":
                geo_lat = float(lat_val)
            if lon_val is not None and str(lon_val).strip() != "":
                geo_lon = float(lon_val)
        except (ValueError, TypeError):
            pass

        rec_id = row.get("call_id") or f"CDR-{uuid.uuid4().hex[:8]}"

        records.append(ForensicRecord(
            record_id=str(rec_id),
            source_domain="TELECOM",
            raw_source_file=filename,
            file_sha256=file_hash,
            timestamp=parsed_ts,
            primary_entity=Entity(entity_type="PHONE", value=calling if calling else "UNKNOWN"),
            secondary_entity=Entity(entity_type="PHONE", value=called) if called else None,
            action=str(row.get("call_type") or row.get("usage_type") or "VOICE_CALL").upper(),
            ip_address=ip,
            device_id=imei,
            geo_lat=geo_lat,
            geo_lon=geo_lon,
            raw_metadata=row
        ))
    return records