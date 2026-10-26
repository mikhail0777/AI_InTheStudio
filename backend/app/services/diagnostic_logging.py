"""Structured rotating diagnostics with secret redaction."""
import json,logging,logging.handlers,re
from datetime import datetime,timezone
from pathlib import Path
from app import database
_handler=None

SECRET=re.compile(r"(?i)(password|passwd|token|authorization|secret)([\"'=:\s]+)([^\s,}\"]+)")
RTSP_AUTH=re.compile(r"(?i)(rtsp://)[^/@\s]+@")

def redact(value):
    text=str(value);text=RTSP_AUTH.sub(r"\1[REDACTED]@",text);return SECRET.sub(r"\1\2[REDACTED]",text)

class JsonFormatter(logging.Formatter):
    def format(self,record):
        return json.dumps({"timestamp":datetime.now(timezone.utc).isoformat(),"level":record.levelname,"logger":record.name,"message":redact(record.getMessage())},separators=(",",":"))

def configure_logging():
    global _handler
    if _handler:
        logging.getLogger().removeHandler(_handler);_handler.close();_handler=None
    folder=Path(database.DB_DIR)/"logs";folder.mkdir(parents=True,exist_ok=True)
    handler=logging.handlers.RotatingFileHandler(folder/"lottrace.jsonl",maxBytes=5*1024*1024,backupCount=5,encoding="utf-8");handler.setFormatter(JsonFormatter())
    root=logging.getLogger();
    root.addHandler(handler);_handler=handler
    root.setLevel(logging.INFO);return str(folder/"lottrace.jsonl")

def shutdown_logging():
    global _handler
    if _handler:
        logging.getLogger().removeHandler(_handler);_handler.close();_handler=None
