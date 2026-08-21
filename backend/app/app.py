import json
from typing import List, Dict, Any
from pydantic import BaseModel
from fastapi import FastAPI, UploadFile, File, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from .models import ForensicRecord, Entity
from .utils import calculate_sha256
from .parser import parse_telecom_cdr, parse_bank_records, parse_social_activity
from .correlation_engine import CorrelationEngine
from .anomaly_rules import AnomalyDetector
from .report_generator import generate_section_65b_pdf
from .copilot import ForensicCopilot
from .gnn_engine import GNNEngine
from .database import engine, DBForensicRecord, Base, get_db

Base.metadata.create_all(bind=engine)

class QueryRequest(BaseModel):
    query: str

app = FastAPI(
    title="Chandigarh Police Digital Footprint Analytics Engine",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def _db_to_forensic_record(row: DBForensicRecord) -> ForensicRecord:
    """Converts an SQLite DBForensicRecord row into a domain ForensicRecord object."""
    meta = json.loads(row.raw_metadata_json) if row.raw_metadata_json else {}
    return ForensicRecord(
        record_id=row.record_id,
        source_domain=row.source_domain,
        raw_source_file=row.raw_source_file,
        file_sha256=row.file_sha256,
        timestamp=row.timestamp,
        primary_entity=Entity(entity_type=row.primary_entity_type, value=row.primary_entity_value),
        secondary_entity=Entity(entity_type=row.secondary_entity_type, value=row.secondary_entity_value) if row.secondary_entity_value else None,
        action=row.action,
        amount=row.amount,
        ip_address=row.ip_address,
        geo_lat=row.geo_lat,
        geo_lon=row.geo_lon,
        raw_metadata=meta
    )

def _get_all_records_from_db(db: Session, case_id: str = "CHD-CYBER-2026-0881") -> List[ForensicRecord]:
    """Fetches all records for the case directly from SQLite."""
    rows = db.query(DBForensicRecord).filter(DBForensicRecord.case_id == case_id).all()
    return [_db_to_forensic_record(r) for r in rows]

def _insert_records_to_db(new_records: List[ForensicRecord], db: Session, case_id: str = "CHD-CYBER-2026-0881") -> int:
    """Persists newly parsed records into SQLite, skipping duplicates."""
    added_count = 0
    for rec in new_records:
        existing = db.query(DBForensicRecord).filter(DBForensicRecord.record_id == rec.record_id).first()
        if not existing:
            db_rec = DBForensicRecord(
                record_id=rec.record_id,
                case_id=case_id,
                source_domain=rec.source_domain,
                raw_source_file=rec.raw_source_file,
                file_sha256=rec.file_sha256,
                timestamp=rec.timestamp,
                primary_entity_type=rec.primary_entity.entity_type if rec.primary_entity else "UNKNOWN",
                primary_entity_value=rec.primary_entity.value if rec.primary_entity else "UNKNOWN",
                secondary_entity_type=rec.secondary_entity.entity_type if rec.secondary_entity else None,
                secondary_entity_value=rec.secondary_entity.value if rec.secondary_entity else None,
                action=rec.action,
                amount=rec.amount,
                ip_address=rec.ip_address,
                geo_lat=rec.geo_lat,
                geo_lon=rec.geo_lon,
                raw_metadata_json=json.dumps(rec.raw_metadata or {})
            )
            db.add(db_rec)
            added_count += 1
    db.commit()
    return added_count

# --- Ingestion Endpoints (Direct DB Write) ---

@app.post("/api/v1/upload/cdr")
async def upload_cdr(file: UploadFile = File(...), db: Session = Depends(get_db)):
    await file.seek(0)
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded CDR file is empty.")
    
    file_hash = calculate_sha256(content)
    records = parse_telecom_cdr(content, file.filename, file_hash)
    added = _insert_records_to_db(records, db)
    total = db.query(DBForensicRecord).count()
    return {
        "status": "success",
        "file": file.filename,
        "sha256": file_hash,
        "records_ingested": added,
        "total_records": total
    }

@app.post("/api/v1/upload/bank")
async def upload_bank(file: UploadFile = File(...), db: Session = Depends(get_db)):
    await file.seek(0)
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded Bank Statement is empty.")
    
    file_hash = calculate_sha256(content)
    records = parse_bank_records(content, file.filename, file_hash)
    added = _insert_records_to_db(records, db)
    total = db.query(DBForensicRecord).count()
    return {
        "status": "success",
        "file": file.filename,
        "sha256": file_hash,
        "records_ingested": added,
        "total_records": total
    }

@app.post("/api/v1/upload/social")
async def upload_social(file: UploadFile = File(...), db: Session = Depends(get_db)):
    await file.seek(0)
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded Social Dump is empty.")
    
    file_hash = calculate_sha256(content)
    records = parse_social_activity(content, file.filename, file_hash)
    added = _insert_records_to_db(records, db)
    total = db.query(DBForensicRecord).count()
    return {
        "status": "success",
        "file": file.filename,
        "sha256": file_hash,
        "records_ingested": added,
        "total_records": total
    }

# --- Core Query Endpoints (Direct DB Read) ---

@app.get("/api/v1/records/all", response_model=List[ForensicRecord])
def get_all_records(db: Session = Depends(get_db)):
    return _get_all_records_from_db(db)

@app.get("/api/v1/analytics/graph")
def get_entity_graph(db: Session = Depends(get_db)):
    records = _get_all_records_from_db(db)
    engine = CorrelationEngine(records)
    return engine.build_network_graph()

@app.get("/api/v1/analytics/timeline")
def get_event_timeline(db: Session = Depends(get_db)):
    records = _get_all_records_from_db(db)
    engine = CorrelationEngine(records)
    return engine.generate_chronological_timeline()

@app.get("/api/v1/analytics/anomalies")
def get_detected_anomalies(db: Session = Depends(get_db)):
    records = _get_all_records_from_db(db)
    detector = AnomalyDetector(records)
    all_alerts = detector.detect_all_anomalies()
    return {
        "total_anomalies": len(all_alerts),
        "anomalies": all_alerts
    }

@app.get("/api/v1/gnn/scores")
def get_gnn_risk_scores(db: Session = Depends(get_db)):
    records = _get_all_records_from_db(db)
    engine = GNNEngine(records)
    scores = engine.compute_risk_scores()
    return {"total_evaluated": len(scores), "scores": scores}

@app.post("/api/v1/copilot/query")
def copilot_query_endpoint(req: QueryRequest, db: Session = Depends(get_db)):
    records = _get_all_records_from_db(db)
    copilot = ForensicCopilot(records)
    return copilot.answer_query(req.query)

@app.get("/api/v1/export/pdf")
def export_case_dossier(case_id: str = "CHD-CYBER-2026-0881", db: Session = Depends(get_db)):
    records = _get_all_records_from_db(db, case_id=case_id)
    detector = AnomalyDetector(records)
    all_alerts = detector.detect_all_anomalies()
    
    records_payload = [
        r.model_dump() if hasattr(r, "model_dump") else r.dict() 
        for r in records
    ]
    
    pdf_buffer = generate_section_65b_pdf(
        case_id=case_id,
        records=records_payload,
        anomalies=all_alerts
    )
    return StreamingResponse(
        pdf_buffer,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=Dossier_{case_id}.pdf"}
    )

@app.delete("/api/v1/records/clear")
def clear_records(db: Session = Depends(get_db)):
    deleted = db.query(DBForensicRecord).delete()
    db.commit()
    return {"status": "cleared", "total_records": 0, "rows_deleted": deleted}