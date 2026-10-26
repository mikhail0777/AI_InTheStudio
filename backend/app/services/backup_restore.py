"""Consistent local backup and restart-bound staged restore."""
from __future__ import annotations
import base64, hashlib, json, os, shutil, sqlite3, tempfile, uuid, zipfile
from datetime import datetime, timezone
from pathlib import Path

from app import database
from app.services.governance import audit
from app.services.camera_ingestion import WindowsCredentialProtector

APP_VERSION="0.1.0"

def _sha(path):
    digest=hashlib.sha256()
    with Path(path).open("rb") as stream:
        while chunk:=stream.read(1024*1024):digest.update(chunk)
    return digest.hexdigest()

def _safe_extract(archive, destination):
    destination=Path(destination).resolve()
    for item in archive.infolist():
        target=(destination/item.filename).resolve()
        if destination!=target and destination not in target.parents:raise ValueError("Backup contains an unsafe path.")
    archive.extractall(destination)

def create_backup(user, *, encrypt=True, protector=None):
    root=Path(database.DB_DIR);folder=root/"backups";folder.mkdir(parents=True,exist_ok=True)
    backup_id="backup_"+uuid.uuid4().hex;stamp=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    with tempfile.TemporaryDirectory(dir=folder) as temporary:
        stage=Path(temporary);db_copy=stage/"lottrace.sqlite"
        source=sqlite3.connect(database.DB_PATH,timeout=20);destination=sqlite3.connect(db_copy)
        try:source.backup(destination);integrity=destination.execute("PRAGMA integrity_check").fetchone()[0];schema=destination.execute("PRAGMA user_version").fetchone()[0]
        finally:destination.close();source.close()
        if integrity!="ok":raise RuntimeError("SQLite backup integrity validation failed.")
        evidence=[];evidence_root=root/"evidence"
        if evidence_root.exists():
            for path in sorted(p for p in evidence_root.rglob("*") if p.is_file()):
                evidence.append({"path":str(path.relative_to(root)).replace("\\","/"),"size":path.stat().st_size,"sha256":_sha(path)})
        evidence_path=stage/"evidence_manifest.json";evidence_path.write_text(json.dumps(evidence,indent=2),encoding="utf-8")
        manifest={"backup_id":backup_id,"backup_version":1,"schema_version":schema,"created_at":datetime.now(timezone.utc).isoformat(),"application_version":APP_VERSION,"dealership_id":user["dealership_id"],"contents":["lottrace.sqlite","evidence_manifest.json"],"checksums":{"lottrace.sqlite":_sha(db_copy),"evidence_manifest.json":_sha(evidence_path)}}
        manifest_path=stage/"manifest.json";manifest_path.write_text(json.dumps(manifest,indent=2),encoding="utf-8")
        plain=folder/f"lottrace-{stamp}-{backup_id}.zip"
        with zipfile.ZipFile(plain,"w",zipfile.ZIP_DEFLATED) as archive:
            for name in manifest["contents"]+["manifest.json"]:archive.write(stage/name,name)
        output=plain
        if encrypt:
            payload=base64.b64encode(plain.read_bytes()).decode("ascii")
            sealed=(protector or WindowsCredentialProtector()).protect({"kind":"lottrace-backup-v1","payload":payload})
            output=plain.with_suffix(".ltbackup");output.write_bytes(b"LOTTRACE-DPAPI-1\n"+base64.b64encode(sealed));plain.unlink()
        archive_hash=_sha(output)
    with database.get_db_connection() as conn:audit(conn,user,"backup.created","backup",backup_id,new={**manifest,"archive_sha256":archive_hash,"encrypted":encrypt})
    return {"backup_id":backup_id,"path":str(output),"sha256":archive_hash,"size_bytes":output.stat().st_size,"encrypted":encrypt,"manifest":manifest}

def _open_backup(path,stage,protector):
    raw=Path(path).read_bytes()
    if raw.startswith(b"LOTTRACE-DPAPI-1\n"):
        value=(protector or WindowsCredentialProtector()).unprotect(base64.b64decode(raw.split(b"\n",1)[1]))
        if value.get("kind")!="lottrace-backup-v1":raise ValueError("Backup encryption envelope is invalid.")
        raw=base64.b64decode(value["payload"])
    archive_path=stage/"archive.zip";archive_path.write_bytes(raw)
    return zipfile.ZipFile(archive_path)

def stage_restore(user,path,*,protector=None):
    source=Path(path).resolve();root=Path(database.DB_DIR).resolve()
    if not source.is_file():raise FileNotFoundError("Backup archive not found.")
    restore_id="restore_"+uuid.uuid4().hex;stage=root/"restore-staging"/restore_id;stage.mkdir(parents=True)
    try:
        with _open_backup(source,stage,protector) as archive:_safe_extract(archive,stage)
        manifest=json.loads((stage/"manifest.json").read_text(encoding="utf-8"))
        if manifest.get("dealership_id")!=user["dealership_id"]:raise ValueError("Backup belongs to a different dealership.")
        for name,expected in manifest.get("checksums",{}).items():
            target=stage/name
            if not target.is_file() or _sha(target)!=expected:raise ValueError(f"Backup checksum failed for {name}.")
        conn=sqlite3.connect(stage/"lottrace.sqlite")
        try:integrity=conn.execute("PRAGMA integrity_check").fetchone()[0];schema=conn.execute("PRAGMA user_version").fetchone()[0]
        finally:conn.close()
        if integrity!="ok" or schema!=manifest.get("schema_version"):raise ValueError("Backup database validation failed.")
        pending={"restore_id":restore_id,"database":str((stage/"lottrace.sqlite").resolve()),"manifest":manifest,"requested_at":datetime.now(timezone.utc).isoformat(),"actor_user_id":user["user_id"],"dealership_id":user["dealership_id"]}
        marker=root/"pending_restore.json";marker.write_text(json.dumps(pending,indent=2),encoding="utf-8")
        with database.get_db_connection() as conn:audit(conn,user,"restore.staged","restore",restore_id,new={"manifest":manifest,"activation":"next_restart"})
        return {"restore_id":restore_id,"status":"staged","activation":"next_restart","manifest":manifest}
    except Exception:
        shutil.rmtree(stage,ignore_errors=True);raise

def apply_pending_restore():
    root=Path(database.DB_DIR);marker=root/"pending_restore.json"
    if not marker.is_file():return None
    pending=json.loads(marker.read_text(encoding="utf-8"));staged=Path(pending["database"]);current=Path(database.DB_PATH)
    rollback=root/"rollback";rollback.mkdir(parents=True,exist_ok=True);previous=rollback/f"pre-restore-{pending['restore_id']}.sqlite"
    if current.is_file():shutil.copy2(current,previous)
    temporary=current.with_suffix(".restore.tmp");shutil.copy2(staged,temporary)
    check=sqlite3.connect(temporary)
    try:
        if check.execute("PRAGMA integrity_check").fetchone()[0]!="ok":raise RuntimeError("Staged restore failed startup validation.")
    finally:check.close()
    os.replace(temporary,current);marker.unlink()
    conn=sqlite3.connect(current)
    try:
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("""INSERT INTO audit_events(event_id,dealership_id,actor_user_id,action,entity_type,entity_id,new_value,source_identifiers)
            VALUES (?,?,?,?,?,?,?,?)""",(uuid.uuid4().hex,pending["dealership_id"],pending["actor_user_id"],"restore.activated","restore",pending["restore_id"],json.dumps({"rollback_database":str(previous)}),"{}"))
        conn.commit()
    finally:conn.close()
    return {"restore_id":pending["restore_id"],"rollback_database":str(previous)}

def latest_backup_status():
    folder=Path(database.DB_DIR)/"backups"
    files=sorted((p for p in folder.glob("lottrace-*") if p.is_file()),key=lambda p:p.stat().st_mtime,reverse=True) if folder.exists() else []
    return {"ok":bool(files),"latest_path":str(files[0]) if files else None,"latest_at":datetime.fromtimestamp(files[0].stat().st_mtime,timezone.utc).isoformat() if files else None}
