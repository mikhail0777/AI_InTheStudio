"""Human-led condition inspections, incidents, holds, and evidence exports."""
from __future__ import annotations
import hashlib, json, os, uuid, zipfile
from datetime import datetime, timezone, timedelta
from pathlib import Path
from app.database import get_db_connection
from app.services.governance import audit
from app.services.vehicle_records import get_vehicle

VIEWPOINTS=("front","rear","left","right","front_left","front_right","rear_left","rear_right","wheel_front_left","wheel_front_right","wheel_rear_left","wheel_rear_right","windscreen","roof","close_up")
ASSESSMENTS=("pre_existing","possible_change","unchanged","repaired","inconclusive")

def _one(conn,sql,args,message):
    row=conn.execute(sql,args).fetchone()
    if not row: raise LookupError(message)
    return row

def create_inspection(user,values):
    get_vehicle(user,values["vehicle_id"])
    if values["inspection_type"] not in ("arrival","departure"): raise ValueError("Inspection type must be arrival or departure.")
    inspection_id="inspection_"+uuid.uuid4().hex
    captured=values.get("captured_at") or datetime.now(timezone.utc).isoformat()
    with get_db_connection() as conn:
        conn.execute("""INSERT INTO inspections(inspection_id,dealership_id,vehicle_id,inspection_type,camera_id,device_label,operator_user_id,notes,captured_at) VALUES (?,?,?,?,?,?,?,?,?)""",(inspection_id,user["dealership_id"],values["vehicle_id"],values["inspection_type"],values.get("camera_id"),values.get("device_label"),user["user_id"],values.get("notes"),captured))
        row=conn.execute("SELECT * FROM inspections WHERE inspection_id=?",(inspection_id,)).fetchone();audit(conn,user,"inspection.created","inspection",inspection_id,new=dict(row))
    return dict(row)

def list_inspections(user,vehicle_id=None):
    sql="SELECT i.*,COUNT(m.media_id) media_count FROM inspections i LEFT JOIN inspection_media m ON m.inspection_id=i.inspection_id WHERE i.dealership_id=?";args=[user["dealership_id"]]
    if vehicle_id: sql+=" AND i.vehicle_id=?";args.append(vehicle_id)
    sql+=" GROUP BY i.inspection_id ORDER BY i.captured_at DESC"
    with get_db_connection() as conn:rows=conn.execute(sql,args).fetchall()
    return [dict(row) for row in rows]

def get_inspection(user,inspection_id):
    with get_db_connection() as conn:
        row=_one(conn,"SELECT * FROM inspections WHERE inspection_id=? AND dealership_id=?",(inspection_id,user["dealership_id"]),"Inspection not found.")
        media=conn.execute("SELECT * FROM inspection_media WHERE inspection_id=? ORDER BY viewpoint",(inspection_id,)).fetchall()
        annotations=conn.execute("SELECT a.* FROM condition_annotations a JOIN inspection_media m ON m.media_id=a.media_id WHERE m.inspection_id=? ORDER BY a.created_at",(inspection_id,)).fetchall()
    return {**dict(row),"media":[dict(x) for x in media],"annotations":[dict(x) for x in annotations],"required_viewpoints":list(VIEWPOINTS)}

def register_media(user,inspection_id,values):
    if values["viewpoint"] not in VIEWPOINTS: raise ValueError("Unknown standardized viewpoint.")
    with get_db_connection() as conn:
        inspection=_one(conn,"SELECT * FROM inspections WHERE inspection_id=? AND dealership_id=?",(inspection_id,user["dealership_id"]),"Inspection not found.")
        if inspection["status"]=="completed": raise ValueError("Reopen the inspection before adding media.")
        media_id="media_"+uuid.uuid4().hex
        conn.execute("""INSERT INTO inspection_media(media_id,inspection_id,viewpoint,source_filename,storage_path,mime_type,sha256,width,height,captured_at) VALUES (?,?,?,?,?,?,?,?,?,?)""",(media_id,inspection_id,values["viewpoint"],values["source_filename"],values["storage_path"],values["mime_type"],values["sha256"],values["width"],values["height"],values.get("captured_at") or datetime.now(timezone.utc).isoformat()))
        row=conn.execute("SELECT * FROM inspection_media WHERE media_id=?",(media_id,)).fetchone();audit(conn,user,"inspection.media_added","inspection",inspection_id,new=dict(row),sources={"sha256":values["sha256"]})
    return dict(row)

def complete_inspection(user,inspection_id):
    with get_db_connection() as conn:
        previous=_one(conn,"SELECT * FROM inspections WHERE inspection_id=? AND dealership_id=?",(inspection_id,user["dealership_id"]),"Inspection not found.")
        if not conn.execute("SELECT 1 FROM inspection_media WHERE inspection_id=?",(inspection_id,)).fetchone(): raise ValueError("At least one original image is required.")
        conn.execute("UPDATE inspections SET status='completed',completed_at=CURRENT_TIMESTAMP WHERE inspection_id=?",(inspection_id,));row=conn.execute("SELECT * FROM inspections WHERE inspection_id=?",(inspection_id,)).fetchone();audit(conn,user,"inspection.completed","inspection",inspection_id,dict(previous),dict(row))
    return get_inspection(user,inspection_id)

def annotate(user,media_id,values):
    if values["assessment"] not in ASSESSMENTS: raise ValueError("Unknown condition assessment.")
    for key in ("x","y","width","height"):
        if not 0 <= float(values[key]) <= 1: raise ValueError("Annotation coordinates must be normalized from 0 to 1.")
    if float(values["width"])<=0 or float(values["height"])<=0: raise ValueError("Annotation region must have positive dimensions.")
    annotation_id="annotation_"+uuid.uuid4().hex
    with get_db_connection() as conn:
        media=_one(conn,"SELECT m.* FROM inspection_media m JOIN inspections i ON i.inspection_id=m.inspection_id WHERE m.media_id=? AND i.dealership_id=?",(media_id,user["dealership_id"]),"Inspection media not found.")
        conn.execute("""INSERT INTO condition_annotations(annotation_id,media_id,x,y,width,height,damage_type,severity,assessment,notes,actor_user_id) VALUES (?,?,?,?,?,?,?,?,?,?,?)""",(annotation_id,media_id,values["x"],values["y"],values["width"],values["height"],values["damage_type"],values["severity"],values["assessment"],values.get("notes"),user["user_id"]))
        row=conn.execute("SELECT * FROM condition_annotations WHERE annotation_id=?",(annotation_id,)).fetchone();audit(conn,user,"condition.annotation_created","inspection",media["inspection_id"],new=dict(row),sources={"media_sha256":media["sha256"]})
    return dict(row)

def create_incident(user,values):
    if values.get("vehicle_id"): get_vehicle(user,values["vehicle_id"])
    incident_id="incident_"+uuid.uuid4().hex
    with get_db_connection() as conn:
        conn.execute("INSERT INTO incidents(incident_id,dealership_id,vehicle_id,title,summary,priority,created_by) VALUES (?,?,?,?,?,?,?)",(incident_id,user["dealership_id"],values.get("vehicle_id"),values["title"].strip(),values.get("summary"),values.get("priority","normal"),user["user_id"]))
        row=conn.execute("SELECT * FROM incidents WHERE incident_id=?",(incident_id,)).fetchone();audit(conn,user,"incident.created","incident",incident_id,new=dict(row))
    return dict(row)

def list_incidents(user):
    with get_db_connection() as conn:rows=conn.execute("SELECT * FROM incidents WHERE dealership_id=? ORDER BY updated_at DESC",(user["dealership_id"],)).fetchall()
    return [dict(row) for row in rows]

def get_incident(user,incident_id):
    with get_db_connection() as conn:
        row=_one(conn,"SELECT * FROM incidents WHERE incident_id=? AND dealership_id=?",(incident_id,user["dealership_id"]),"Incident not found.")
        evidence=conn.execute("SELECT * FROM incident_evidence WHERE incident_id=? ORDER BY created_at",(incident_id,)).fetchall();notes=conn.execute("SELECT * FROM incident_notes WHERE incident_id=? ORDER BY created_at",(incident_id,)).fetchall();approvals=conn.execute("SELECT * FROM incident_approvals WHERE incident_id=? ORDER BY created_at",(incident_id,)).fetchall();holds=conn.execute("SELECT * FROM evidence_holds WHERE incident_id=? ORDER BY placed_at",(incident_id,)).fetchall();attachments=conn.execute("SELECT attachment_id,incident_id,source_filename,mime_type,sha256,size_bytes,added_by,created_at FROM incident_attachments WHERE incident_id=? ORDER BY created_at",(incident_id,)).fetchall()
    return {**dict(row),"evidence":[dict(x) for x in evidence],"notes":[dict(x) for x in notes],"approvals":[dict(x) for x in approvals],"holds":[dict(x) for x in holds],"attachments":[dict(x) for x in attachments]}

def add_evidence(user,incident_id,values):
    with get_db_connection() as conn:
        _one(conn,"SELECT 1 FROM incidents WHERE incident_id=? AND dealership_id=?",(incident_id,user["dealership_id"]),"Incident not found.")
        kind=values["evidence_type"]
        if kind=="sighting": found=conn.execute("SELECT 1 FROM vehicle_sightings WHERE sighting_id=? AND dealership_id=?",(values["entity_id"],user["dealership_id"])).fetchone()
        elif kind=="inspection": found=conn.execute("SELECT 1 FROM inspections WHERE inspection_id=? AND dealership_id=?",(values["entity_id"],user["dealership_id"])).fetchone()
        elif kind=="annotation": found=conn.execute("SELECT 1 FROM condition_annotations a JOIN inspection_media m ON m.media_id=a.media_id JOIN inspections i ON i.inspection_id=m.inspection_id WHERE a.annotation_id=? AND i.dealership_id=?",(values["entity_id"],user["dealership_id"])).fetchone()
        else: raise ValueError("Evidence type must be sighting, inspection, or annotation.")
        if not found: raise LookupError("Evidence record not found.")
        evidence_id="evidence_"+uuid.uuid4().hex
        conn.execute("INSERT INTO incident_evidence(evidence_id,incident_id,evidence_type,entity_id,note,added_by) VALUES (?,?,?,?,?,?)",(evidence_id,incident_id,kind,values["entity_id"],values.get("note"),user["user_id"]))
        row=conn.execute("SELECT * FROM incident_evidence WHERE evidence_id=?",(evidence_id,)).fetchone();audit(conn,user,"incident.evidence_added","incident",incident_id,new=dict(row))
    return dict(row)

def add_note(user,incident_id,note):
    if not note.strip(): raise ValueError("A note is required.")
    with get_db_connection() as conn:
        _one(conn,"SELECT 1 FROM incidents WHERE incident_id=? AND dealership_id=?",(incident_id,user["dealership_id"]),"Incident not found.");note_id="note_"+uuid.uuid4().hex
        conn.execute("INSERT INTO incident_notes(note_id,incident_id,note,actor_user_id) VALUES (?,?,?,?)",(note_id,incident_id,note.strip(),user["user_id"]));row=conn.execute("SELECT * FROM incident_notes WHERE note_id=?",(note_id,)).fetchone();audit(conn,user,"incident.note_added","incident",incident_id,new=dict(row))
    return dict(row)

def decision(user,incident_id,action,reason):
    if user["role"] not in ("manager","administrator"): raise PermissionError("Manager role required.")
    if action not in ("approve","reopen"): raise ValueError("Action must be approve or reopen.")
    if not reason.strip(): raise ValueError("A decision reason is required.")
    status="approved" if action=="approve" else "requires_review"
    with get_db_connection() as conn:
        previous=_one(conn,"SELECT * FROM incidents WHERE incident_id=? AND dealership_id=?",(incident_id,user["dealership_id"]),"Incident not found.");approval_id="approval_"+uuid.uuid4().hex
        conn.execute("UPDATE incidents SET status=?,updated_at=CURRENT_TIMESTAMP WHERE incident_id=?",(status,incident_id));conn.execute("INSERT INTO incident_approvals(approval_id,incident_id,action,reason,actor_user_id) VALUES (?,?,?,?,?)",(approval_id,incident_id,action,reason.strip(),user["user_id"]));row=conn.execute("SELECT * FROM incidents WHERE incident_id=?",(incident_id,)).fetchone();audit(conn,user,"incident."+action,"incident",incident_id,dict(previous),dict(row),reason)
    return get_incident(user,incident_id)

def place_hold(user,incident_id,reason):
    if user["role"] not in ("manager","administrator"): raise PermissionError("Manager role required.")
    if not reason.strip(): raise ValueError("A hold reason is required.")
    with get_db_connection() as conn:
        _one(conn,"SELECT 1 FROM incidents WHERE incident_id=? AND dealership_id=?",(incident_id,user["dealership_id"]),"Incident not found.");hold_id="hold_"+uuid.uuid4().hex
        conn.execute("INSERT INTO evidence_holds(hold_id,incident_id,reason,placed_by) VALUES (?,?,?,?)",(hold_id,incident_id,reason.strip(),user["user_id"]));row=conn.execute("SELECT * FROM evidence_holds WHERE hold_id=?",(hold_id,)).fetchone();audit(conn,user,"evidence_hold.placed","incident",incident_id,new=dict(row),reason=reason)
    return dict(row)

def register_attachment(user,incident_id,values):
    with get_db_connection() as conn:
        _one(conn,"SELECT 1 FROM incidents WHERE incident_id=? AND dealership_id=?",(incident_id,user["dealership_id"]),"Incident not found.");attachment_id="attachment_"+uuid.uuid4().hex
        conn.execute("INSERT INTO incident_attachments(attachment_id,incident_id,source_filename,storage_path,mime_type,sha256,size_bytes,added_by) VALUES (?,?,?,?,?,?,?,?)",(attachment_id,incident_id,values["source_filename"],values["storage_path"],values["mime_type"],values["sha256"],values["size_bytes"],user["user_id"]))
        row=conn.execute("SELECT * FROM incident_attachments WHERE attachment_id=?",(attachment_id,)).fetchone();audit(conn,user,"incident.attachment_added","incident",incident_id,new={key:row[key] for key in row.keys() if key!="storage_path"},sources={"sha256":values["sha256"]})
    return {key:row[key] for key in row.keys() if key!="storage_path"}

def export_incident(user,incident_id,data_dir):
    incident=get_incident(user,incident_id);manifest={"format":"lottrace-evidence-manifest-v1","exported_at":datetime.now(timezone.utc).isoformat(),"incident":incident,"files":[]}
    with get_db_connection() as conn:
        media=conn.execute("""SELECT m.* FROM incident_evidence e JOIN inspection_media m ON e.evidence_type='inspection' AND m.inspection_id=e.entity_id WHERE e.incident_id=?""",(incident_id,)).fetchall()
        attachments=conn.execute("SELECT * FROM incident_attachments WHERE incident_id=?",(incident_id,)).fetchall()
    files=[]
    for row in media:
        path=Path(row["storage_path"])
        if path.exists():manifest["files"].append({"name":row["source_filename"],"sha256":row["sha256"],"viewpoint":row["viewpoint"]});files.append((path,row["source_filename"]))
    for row in attachments:
        path=Path(row["storage_path"])
        if path.exists():manifest["files"].append({"name":row["source_filename"],"sha256":row["sha256"],"kind":"incident_attachment"});files.append((path,row["source_filename"]))
    manifest_bytes=json.dumps(manifest,sort_keys=True,separators=(",",":")).encode();manifest_hash=hashlib.sha256(manifest_bytes).hexdigest();export_id="export_"+uuid.uuid4().hex;folder=Path(data_dir)/"evidence"/"exports";folder.mkdir(parents=True,exist_ok=True);archive=folder/f"{export_id}.zip"
    with zipfile.ZipFile(archive,"x",zipfile.ZIP_DEFLATED) as bundle:
        bundle.writestr("manifest.json",manifest_bytes)
        for index,(path,name) in enumerate(files):bundle.write(path,f"files/{index:03d}_{Path(name).name}")
    archive_hash=hashlib.sha256(archive.read_bytes()).hexdigest()
    with get_db_connection() as conn:
        conn.execute("INSERT INTO evidence_exports(export_id,incident_id,manifest_sha256,archive_sha256,storage_path,created_by) VALUES (?,?,?,?,?,?)",(export_id,incident_id,manifest_hash,archive_hash,str(archive),user["user_id"]));audit(conn,user,"incident.exported","incident",incident_id,new={"export_id":export_id,"manifest_sha256":manifest_hash,"archive_sha256":archive_hash})
    return {"export_id":export_id,"manifest_sha256":manifest_hash,"archive_sha256":archive_hash,"path":str(archive)}

def apply_retention(user,data_dir,now=None):
    if user["role"]!="administrator": raise PermissionError("Administrator role required.")
    now=now or datetime.now(timezone.utc)
    with get_db_connection() as conn:
        policy=_one(conn,"SELECT * FROM retention_policies WHERE dealership_id=?",(user["dealership_id"],),"Retention policy not found.")
        cutoff=(now-timedelta(days=policy["inspections_days"])).isoformat()
        rows=conn.execute("""SELECT i.inspection_id,m.media_id,m.storage_path FROM inspections i LEFT JOIN inspection_media m ON m.inspection_id=i.inspection_id
            WHERE i.dealership_id=? AND datetime(i.captured_at)<datetime(?) AND NOT EXISTS (
              SELECT 1 FROM incident_evidence e JOIN evidence_holds h ON h.incident_id=e.incident_id
              WHERE e.evidence_type='inspection' AND e.entity_id=i.inspection_id AND h.released_at IS NULL)""",(user["dealership_id"],cutoff)).fetchall()
        inspection_ids=sorted({row["inspection_id"] for row in rows});root=(Path(data_dir)/"evidence").resolve()
        for row in rows:
            if not row["storage_path"]:continue
            path=Path(row["storage_path"]).resolve()
            if root in path.parents and path.exists():path.unlink()
        for inspection_id in inspection_ids:
            conn.execute("DELETE FROM condition_annotations WHERE media_id IN (SELECT media_id FROM inspection_media WHERE inspection_id=?)",(inspection_id,));conn.execute("DELETE FROM inspection_media WHERE inspection_id=?",(inspection_id,));conn.execute("DELETE FROM inspections WHERE inspection_id=?",(inspection_id,));audit(conn,user,"retention.inspection_deleted","inspection",inspection_id,reason="Expired under configured retention policy")
    return {"deleted_inspections":len(inspection_ids),"held_inspections_skipped":True}
