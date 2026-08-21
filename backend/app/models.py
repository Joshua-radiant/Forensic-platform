from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime

class Entity(BaseModel):
    entity_type: str  # "PHONE", "BANK_ACCOUNT", "IP", "HANDLE", "IMEI", "IMSI"
    value: str

class ForensicRecord(BaseModel):
    record_id: str
    source_domain: str        # "TELECOM", "BANKING", "SOCIAL"
    raw_source_file: str
    file_sha256: str          # Digital chain-of-custody hash
    timestamp: datetime
    primary_entity: Entity    # Calling No / Sender Account / Social Handle
    secondary_entity: Optional[Entity] = None  # Called No / Receiver Account / Tagged Handle
    action: str               # "VOICE_CALL", "UPI_TRANSFER", "POST_PUBLISHED", etc.
    amount: Optional[float] = None
    ip_address: Optional[str] = None
    device_id: Optional[str] = None  # IMEI, User-Agent, Client-ID
    geo_lat: Optional[float] = None
    geo_lon: Optional[float] = None
    raw_metadata: Dict[str, Any] = Field(default_factory=dict)