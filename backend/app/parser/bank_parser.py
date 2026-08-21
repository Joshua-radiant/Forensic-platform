import io
import uuid
import polars as pl
import pdfplumber
from typing import List
from ..models import ForensicRecord, Entity
from ..utils import clean_phone_number, clean_ip, clean_amount, parse_flexible_datetime

def parse_bank_records(file_bytes: bytes, filename: str, file_hash: str) -> List[ForensicRecord]:
    records: List[ForensicRecord] = []
    
    if filename.lower().endswith(".csv"):
        df = pl.read_csv(io.BytesIO(file_bytes), infer_schema_length=5000, ignore_errors=True)
        col_map = {col: col.lower().strip().replace(" ", "_") for col in df.columns}
        df = df.rename(col_map)
        
        for row in df.iter_rows(named=True):
            raw_ts = (
                row.get("timestamp") 
                or row.get("txn_date") 
                or row.get("date")
                or row.get("transaction_timestamp")
            )
            parsed_ts = parse_flexible_datetime(raw_ts)
            
            # Comprehensive source and destination account matching
            sender_raw = (
                row.get("source_account")
                or row.get("sender_acc") 
                or row.get("account_number") 
                or row.get("from_acc") 
                or row.get("from_account")
                or row.get("remitter_account")
                or ""
            )
            receiver_raw = (
                row.get("destination_account")
                or row.get("receiver_acc") 
                or row.get("beneficiary_acc") 
                or row.get("to_acc") 
                or row.get("to_account")
                or row.get("beneficiary_account")
                or ""
            )
            
            sender = str(sender_raw).strip()
            receiver = str(receiver_raw).strip()
            
            if not sender and not receiver:
                continue

            amount = clean_amount(
                row.get("amount") 
                or row.get("debit") 
                or row.get("withdrawal")
                or row.get("txn_amount")
            )
            
            ip = clean_ip(
                row.get("ip_address") 
                or row.get("ip") 
                or row.get("client_ip") 
                or row.get("source_ip")
            )
            
            action_type = str(
                row.get("channel") 
                or row.get("txn_type") 
                or row.get("transaction_type") 
                or "FUNDS_TRANSFER"
            ).upper()

            rec_id = row.get("txn_id") or f"BNK-{uuid.uuid4().hex[:8]}"

            metadata = dict(row)
            if "linked_mobile" in row and row["linked_mobile"]:
                metadata["linked_phone"] = clean_phone_number(row["linked_mobile"])

            records.append(ForensicRecord(
                record_id=str(rec_id),
                source_domain="BANKING",
                raw_source_file=filename,
                file_sha256=file_hash,
                timestamp=parsed_ts,
                primary_entity=Entity(entity_type="BANK_ACCOUNT", value=sender if sender else "UNKNOWN"),
                secondary_entity=Entity(entity_type="BANK_ACCOUNT", value=receiver) if receiver else None,
                action=action_type,
                amount=amount,
                ip_address=ip,
                raw_metadata=metadata
            ))

    elif filename.lower().endswith(".pdf"):
        with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
            for page in pdf.pages:
                tables = page.extract_tables()
                for table in tables:
                    if not table or len(table) < 2:
                        continue
                    headers = [str(h).lower().strip().replace(" ", "_") if h else f"col_{i}" for i, h in enumerate(table[0])]
                    for row_data in table[1:]:
                        row = dict(zip(headers, row_data))
                        sender_val = str(row.get("account_number") or row.get("source_account") or "ACC_UNKNOWN").strip()
                        receiver_val = str(row.get("destination_account") or row.get("beneficiary_acc") or "").strip()
                        
                        records.append(ForensicRecord(
                            record_id=f"BNK-{uuid.uuid4().hex[:8]}",
                            source_domain="BANKING",
                            raw_source_file=filename,
                            file_sha256=file_hash,
                            timestamp=parse_flexible_datetime(row.get("date") or row.get("txn_date") or row.get("timestamp")),
                            primary_entity=Entity(entity_type="BANK_ACCOUNT", value=sender_val),
                            secondary_entity=Entity(entity_type="BANK_ACCOUNT", value=receiver_val) if receiver_val else None,
                            action=str(row.get("channel") or row.get("txn_type") or "PDF_STATEMENT_TXN").upper(),
                            amount=clean_amount(row.get("debit") or row.get("amount") or row.get("withdrawal")),
                            ip_address=clean_ip(row.get("ip_address") or row.get("ip")),
                            raw_metadata=row
                        ))
    return records