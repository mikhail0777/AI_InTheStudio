"""Database-backed vehicle registry, timeline, and governance resources."""
from __future__ import annotations
import json, re, uuid
from datetime import datetime, timezone
from app.database import get_db_connection
from app.services.governance import audit

def normalize_plate(value):
    return re.sub(r"[^A-Z0-9]", "", (value or "").upper()) or None

def _row(row):
    return dict(row) if row else None

def list_vehicles(user):
    with get_db_connection() as conn:
        rows=conn.execute("SELECT * FROM vehicles WHERE dealership_id=? ORDER BY updated_at DESC",(user["dealership_id"],)).fetchall()
    return [_row(row) for row in rows]

def get_vehicle(user, vehicle_id):
    with get_db_connection() as conn:
        row=conn.execute("SELECT * FROM vehicles WHERE vehicle_id=? AND dealership_id=?",(vehicle_id,user["dealership_id"])).fetchone()
    if not row: raise LookupError("Vehicle record not found.")
    return _row(row)

def save_vehicle(user, values, vehicle_id=None):
    allowed=("vin","stock_number","make","model","year","color","body_type","status","notes")
    if values.get("year") is not None and not 1900 <= int(values["year"]) <= 2100: raise ValueError("Year must be between 1900 and 2100.")
    plate=normalize_plate(values.get("plate") if "plate" in values else values.get("normalized_plate"))
    with get_db_connection() as conn:
        conn.execute("BEGIN IMMEDIATE")
        if vehicle_id:
            previous=conn.execute("SELECT * FROM vehicles WHERE vehicle_id=? AND dealership_id=?",(vehicle_id,user["dealership_id"])).fetchone()
            if not previous: raise LookupError("Vehicle record not found.")
            merged=dict(previous)
            if "plate" in values or "normalized_plate" in values: merged["normalized_plate"]=plate
            for key in allowed:
                if key in values: merged[key]=values[key]
            conn.execute("""UPDATE vehicles SET normalized_plate=?,vin=?,stock_number=?,make=?,model=?,year=?,color=?,body_type=?,status=?,notes=?,updated_at=CURRENT_TIMESTAMP WHERE vehicle_id=?""",
                tuple(merged[key] for key in ("normalized_plate","vin","stock_number","make","model","year","color","body_type","status","notes"))+(vehicle_id,))
            result=conn.execute("SELECT * FROM vehicles WHERE vehicle_id=?",(vehicle_id,)).fetchone()
            audit(conn,user,"vehicle.updated","vehicle",vehicle_id,dict(previous),dict(result),values.get("reason"))
        else:
            vehicle_id="vehicle_"+uuid.uuid4().hex
            payload={key:values.get(key) for key in allowed}; payload["status"]=payload["status"] or "active"
            conn.execute("""INSERT INTO vehicles(vehicle_id,dealership_id,normalized_plate,vin,stock_number,make,model,year,color,body_type,status,notes) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                (vehicle_id,user["dealership_id"],plate)+tuple(payload[key] for key in allowed))
            result=conn.execute("SELECT * FROM vehicles WHERE vehicle_id=?",(vehicle_id,)).fetchone()
            audit(conn,user,"vehicle.created","vehicle",vehicle_id,new=dict(result),reason=values.get("reason"))
    return dict(result)

def add_alias(user, vehicle_id, values):
    vehicle=get_vehicle(user,vehicle_id); plate=normalize_plate(values.get("plate"))
    if not plate: raise ValueError("Plate alias is required.")
    alias_id="alias_"+uuid.uuid4().hex
    with get_db_connection() as conn:
        conn.execute("INSERT INTO plate_aliases(alias_id,vehicle_id,normalized_plate,valid_from,valid_to,reason) VALUES (?,?,?,?,?,?)",
          (alias_id,vehicle_id,plate,values.get("valid_from"),values.get("valid_to"),values.get("reason")))
        row=conn.execute("SELECT * FROM plate_aliases WHERE alias_id=?",(alias_id,)).fetchone()
        audit(conn,user,"plate_alias.created","vehicle",vehicle_id,new=dict(row),reason=values.get("reason"))
    return dict(row)

def link_sighting(user,sighting_id,vehicle_id,reason):
    if not (reason or "").strip(): raise ValueError("A link reason is required.")
    get_vehicle(user,vehicle_id)
    with get_db_connection() as conn:
        sighting=conn.execute("SELECT * FROM vehicle_sightings WHERE sighting_id=? AND (dealership_id=? OR dealership_id IS NULL)",(sighting_id,user["dealership_id"])).fetchone()
        if not sighting: raise LookupError("Sighting not found.")
        previous=conn.execute("SELECT * FROM sighting_vehicle_links WHERE sighting_id=?",(sighting_id,)).fetchone()
        conn.execute("INSERT OR REPLACE INTO sighting_vehicle_links(sighting_id,vehicle_id,linked_by,reason,created_at) VALUES (?,?,?,?,CURRENT_TIMESTAMP)",(sighting_id,vehicle_id,user["user_id"],reason.strip()))
        row=conn.execute("SELECT * FROM sighting_vehicle_links WHERE sighting_id=?",(sighting_id,)).fetchone()
        audit(conn,user,"sighting.linked","sighting",sighting_id,dict(previous) if previous else None,dict(row),reason,{"vehicle_id":vehicle_id})
    return dict(row)

def unlink_sighting(user,sighting_id,reason):
    if not (reason or "").strip(): raise ValueError("An unlink reason is required.")
    with get_db_connection() as conn:
        row=conn.execute("SELECT l.* FROM sighting_vehicle_links l JOIN vehicles v ON v.vehicle_id=l.vehicle_id WHERE l.sighting_id=? AND v.dealership_id=?",(sighting_id,user["dealership_id"])).fetchone()
        if not row: raise LookupError("Linked sighting not found.")
        conn.execute("DELETE FROM sighting_vehicle_links WHERE sighting_id=?",(sighting_id,))
        audit(conn,user,"sighting.unlinked","sighting",sighting_id,dict(row),None,reason)

def timeline(user,vehicle_id):
    get_vehicle(user,vehicle_id)
    with get_db_connection() as conn:
        sightings=conn.execute("""SELECT s.*,l.created_at linked_at,l.reason link_reason FROM sighting_vehicle_links l JOIN vehicle_sightings s ON s.sighting_id=l.sighting_id WHERE l.vehicle_id=? ORDER BY COALESCE(s.captured_at,s.created_at) DESC""",(vehicle_id,)).fetchall()
        aliases=conn.execute("SELECT * FROM plate_aliases WHERE vehicle_id=? ORDER BY created_at DESC",(vehicle_id,)).fetchall()
        events=conn.execute("SELECT * FROM audit_events WHERE dealership_id=? AND ((entity_type='vehicle' AND entity_id=?) OR json_extract(source_identifiers,'$.vehicle_id')=?) ORDER BY created_at DESC",(user["dealership_id"],vehicle_id,vehicle_id)).fetchall()
        inspections=conn.execute("SELECT * FROM inspections WHERE vehicle_id=? ORDER BY captured_at DESC",(vehicle_id,)).fetchall()
        incidents=conn.execute("SELECT * FROM incidents WHERE vehicle_id=? ORDER BY created_at DESC",(vehicle_id,)).fetchall()
        vehicle_events=conn.execute("SELECT * FROM vehicle_events WHERE matched_vehicle_id=? ORDER BY occurred_at DESC",(vehicle_id,)).fetchall()
        transitions=conn.execute("SELECT * FROM vehicle_status_transitions WHERE vehicle_id=? ORDER BY occurred_at DESC",(vehicle_id,)).fetchall()
    items=[{"type":"sighting","at":row["captured_at"] or row["created_at"],"data":dict(row)} for row in sightings]
    items += [{"type":"plate_alias","at":row["created_at"],"data":dict(row)} for row in aliases]
    items += [{"type":"audit","at":row["created_at"],"data":dict(row)} for row in events]
    items += [{"type":"inspection","at":row["captured_at"],"data":dict(row)} for row in inspections]
    items += [{"type":"incident","at":row["created_at"],"data":dict(row)} for row in incidents]
    items += [{"type":"vehicle_event","at":row["occurred_at"],"data":dict(row)} for row in vehicle_events]
    items += [{"type":"status_transition","at":row["occurred_at"],"data":dict(row)} for row in transitions]
    return sorted(items,key=lambda item:item["at"] or "",reverse=True)

def list_cameras(user):
    with get_db_connection() as conn: rows=conn.execute("SELECT * FROM cameras WHERE dealership_id=? ORDER BY name",(user["dealership_id"],)).fetchall()
    result=[]
    for row in rows:
        item=dict(row); secret=item.pop("credential_blob",None)
        item["credentials_configured"]=bool(secret)
        result.append(item)
    return result

def create_camera(user,values):
    camera_id="camera_"+uuid.uuid4().hex
    with get_db_connection() as conn:
        conn.execute("INSERT INTO cameras(camera_id,dealership_id,name,role,location,timezone) VALUES (?,?,?,?,?,?)",(camera_id,user["dealership_id"],values["name"].strip(),values.get("role","unknown"),values.get("location"),values.get("timezone","UTC")))
        row=conn.execute("SELECT * FROM cameras WHERE camera_id=?",(camera_id,)).fetchone(); audit(conn,user,"camera.created","camera",camera_id,new={k:v for k,v in dict(row).items() if k!="credential_blob"})
    item=dict(row); item.pop("credential_blob",None); item["credentials_configured"]=False
    return item

def get_retention(user):
    with get_db_connection() as conn: row=conn.execute("SELECT * FROM retention_policies WHERE dealership_id=?",(user["dealership_id"],)).fetchone()
    return dict(row)

def update_retention(user,values):
    fields=("source_video_days","derived_media_days","sightings_days","audit_days","inspections_days","incidents_days")
    previous=get_retention(user); merged={key:values.get(key,previous[key]) for key in fields}
    if any(int(merged[key]) < 1 for key in fields): raise ValueError("Retention periods must be at least one day.")
    with get_db_connection() as conn:
        conn.execute("UPDATE retention_policies SET source_video_days=?,derived_media_days=?,sightings_days=?,audit_days=?,inspections_days=?,incidents_days=?,updated_by=?,updated_at=CURRENT_TIMESTAMP WHERE dealership_id=?",tuple(int(merged[key]) for key in fields)+(user["user_id"],user["dealership_id"]))
        row=conn.execute("SELECT * FROM retention_policies WHERE dealership_id=?",(user["dealership_id"],)).fetchone(); audit(conn,user,"retention.updated","retention_policy",user["dealership_id"],previous,dict(row))
    return dict(row)

def list_audit(user,limit=200):
    with get_db_connection() as conn: rows=conn.execute("SELECT * FROM audit_events WHERE dealership_id=? ORDER BY created_at DESC LIMIT ?",(user["dealership_id"],min(max(limit,1),1000))).fetchall()
    return [dict(row) for row in rows]
