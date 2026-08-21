import os
import json
from datetime import datetime
from sqlalchemy import create_engine, Column, String, Float, DateTime, Text
from sqlalchemy.orm import declarative_base, sessionmaker

DB_URL = "sqlite:///./forensic_case_data.db"
engine = create_engine(DB_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class DBForensicRecord(Base):
    __tablename__ = "forensic_records"

    record_id = Column(String, primary_key=True, index=True)
    case_id = Column(String, default="CHD-CYBER-2026-0881", index=True)
    source_domain = Column(String, index=True)
    raw_source_file = Column(String)
    file_sha256 = Column(String)
    timestamp = Column(DateTime, index=True)
    primary_entity_type = Column(String)
    primary_entity_value = Column(String, index=True)
    secondary_entity_type = Column(String, nullable=True)
    secondary_entity_value = Column(String, nullable=True, index=True)
    action = Column(String)
    amount = Column(Float, nullable=True)
    ip_address = Column(String, nullable=True, index=True)
    geo_lat = Column(Float, nullable=True)
    geo_lon = Column(Float, nullable=True)
    raw_metadata_json = Column(Text, default="{}")

Base.metadata.create_all(bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()