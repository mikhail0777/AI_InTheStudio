"""Authentication, authorization, and immutable governance events."""
from __future__ import annotations
import base64, hashlib, hmac, json, secrets, uuid
from datetime import datetime, timedelta, timezone
from app.database import get_db_connection

ROLE_LEVEL={"viewer":1,"reviewer":2,"manager":3,"administrator":4,"auditor":1}

def _password_hash(password:str, salt:bytes|None=None)->str:
    if len(password)<12: raise ValueError("Password must contain at least 12 characters.")
    salt=salt or secrets.token_bytes(16)
    value=hashlib.scrypt(password.encode(),salt=salt,n=2**14,r=8,p=1)
    return base64.b64encode(salt).decode()+":"+base64.b64encode(value).decode()

def _verify(password:str, stored:str)->bool:
    try:
        salt,value=stored.split(":",1); expected=base64.b64decode(value)
        actual=hashlib.scrypt(password.encode(),salt=base64.b64decode(salt),n=2**14,r=8,p=1)
        return hmac.compare_digest(actual,expected)
    except Exception:return False

def configured()->bool:
    with get_db_connection() as conn:return bool(conn.execute("SELECT 1 FROM users LIMIT 1").fetchone())

def bootstrap(dealership_name,email,display_name,password):
    if not dealership_name.strip() or not display_name.strip() or "@" not in email: raise ValueError("Dealership name, display name, and a valid email are required.")
    with get_db_connection() as conn:
        conn.execute("BEGIN IMMEDIATE")
        if conn.execute("SELECT 1 FROM users LIMIT 1").fetchone():raise RuntimeError("LotTrace is already configured.")
        dealership_id,user_id="dealer_"+uuid.uuid4().hex,"user_"+uuid.uuid4().hex
        conn.execute("INSERT INTO dealerships(dealership_id,name) VALUES (?,?)",(dealership_id,dealership_name.strip()))
        conn.execute("INSERT INTO users(user_id,dealership_id,email,display_name,role,password_hash) VALUES (?,?,?,?,?,?)",
                     (user_id,dealership_id,email.strip().lower(),display_name.strip(),"administrator",_password_hash(password)))
        # A first-time setup adopts records created by the pre-account local build.
        conn.execute("UPDATE sessions SET dealership_id=? WHERE dealership_id IS NULL",(dealership_id,))
        conn.execute("UPDATE vehicle_sightings SET dealership_id=? WHERE dealership_id IS NULL",(dealership_id,))
        conn.execute("INSERT INTO retention_policies(dealership_id,updated_by) VALUES (?,?)",(dealership_id,user_id))
    return create_session(email,password)

def create_session(email,password):
    with get_db_connection() as conn:
        row=conn.execute("SELECT * FROM users WHERE email=? AND active=1",(email.strip().lower(),)).fetchone()
        if not row or not _verify(password,row["password_hash"]):raise ValueError("Invalid email or password.")
        token=secrets.token_urlsafe(32); digest=hashlib.sha256(token.encode()).hexdigest()
        expires=(datetime.now(timezone.utc)+timedelta(hours=12)).isoformat()
        conn.execute("INSERT INTO user_sessions(token_hash,user_id,expires_at) VALUES (?,?,?)",(digest,row["user_id"],expires))
        return token,public_user(dict(row))

def public_user(row):return {key:row[key] for key in ("user_id","dealership_id","email","display_name","role")}

def authenticate(token):
    if not token:return None
    digest=hashlib.sha256(token.encode()).hexdigest(); now=datetime.now(timezone.utc).isoformat()
    with get_db_connection() as conn:
        row=conn.execute("SELECT u.* FROM user_sessions s JOIN users u ON u.user_id=s.user_id WHERE s.token_hash=? AND s.expires_at>? AND u.active=1",(digest,now)).fetchone()
    return public_user(dict(row)) if row else None

def logout(token):
    if token:
        with get_db_connection() as conn:conn.execute("DELETE FROM user_sessions WHERE token_hash=?",(hashlib.sha256(token.encode()).hexdigest(),))

def list_users(user):
    with get_db_connection() as conn:
        rows=conn.execute("SELECT user_id,dealership_id,email,display_name,role,active,created_at FROM users WHERE dealership_id=? ORDER BY display_name",(user["dealership_id"],)).fetchall()
    return [dict(row) for row in rows]

def create_user(actor,email,display_name,role,password):
    if role not in ROLE_LEVEL: raise ValueError("Unknown role.")
    if not display_name.strip() or "@" not in email: raise ValueError("Display name and a valid email are required.")
    user_id="user_"+uuid.uuid4().hex
    with get_db_connection() as conn:
        conn.execute("INSERT INTO users(user_id,dealership_id,email,display_name,role,password_hash) VALUES (?,?,?,?,?,?)",(user_id,actor["dealership_id"],email.strip().lower(),display_name.strip(),role,_password_hash(password)))
        row=conn.execute("SELECT user_id,dealership_id,email,display_name,role,active,created_at FROM users WHERE user_id=?",(user_id,)).fetchone()
        audit(conn,actor,"user.created","user",user_id,new=dict(row))
    return dict(row)

def permitted(role,method,path):
    if method in ("GET","HEAD","OPTIONS"):return role in ROLE_LEVEL
    if path=="/api/vehicle-events/from-track":return role in ("manager","administrator")
    if method not in ("GET","HEAD","OPTIONS") and path.startswith("/api/system/"):return role=="administrator"
    if path.endswith("/review") or "/feedback" in path:return role in ("reviewer","manager","administrator")
    if path.startswith("/api/vehicles") or path.startswith("/api/cameras") or path.startswith("/api/retention"):return role in ("manager","administrator")
    if method=="DELETE":return role=="administrator"
    return role in ("reviewer","manager","administrator")

def audit(conn,user,action,entity_type,entity_id,previous=None,new=None,reason=None,sources=None):
    conn.execute("INSERT INTO audit_events(event_id,dealership_id,actor_user_id,action,entity_type,entity_id,previous_value,new_value,reason,source_identifiers) VALUES (?,?,?,?,?,?,?,?,?,?)",
        (uuid.uuid4().hex,user["dealership_id"],user["user_id"],action,entity_type,entity_id,json.dumps(previous) if previous is not None else None,json.dumps(new) if new is not None else None,reason,json.dumps(sources or {})))
