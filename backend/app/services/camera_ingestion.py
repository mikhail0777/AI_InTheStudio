"""Isolated live-camera ingestion with protected secrets and bounded queues.

The capture implementation is deliberately adapter-driven so reconnect, stall and
overload behaviour can be verified without a physical camera.  OpenCV/FFmpeg is
the production adapter; no stream URL or credential is ever logged or returned.
"""
from __future__ import annotations

import base64
import ctypes
from ctypes import wintypes
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import queue
import random
import socket
import threading
import time
import uuid
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
import xml.etree.ElementTree as ET

from app.database import get_db_connection, DB_DIR


PUBLIC_STATUSES = {"online", "reconnecting", "offline", "authentication_failure", "unsupported_stream", "overloaded", "paused"}


def redact_stream_url(value: str | None) -> str | None:
    if not value:
        return None
    try:
        parsed = urlsplit(value)
        host = parsed.hostname or ""
        if parsed.port:
            host += f":{parsed.port}"
        return urlunsplit((parsed.scheme, host, parsed.path, parsed.query, ""))
    except Exception:
        return "configured"


class _Blob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_byte))]


class WindowsCredentialProtector:
    """DPAPI CurrentUser encryption; ciphertext is installation/user scoped."""
    @staticmethod
    def _blob(data: bytes):
        buffer = ctypes.create_string_buffer(data)
        return _Blob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_byte))), buffer

    def protect(self, values: dict) -> bytes:
        if os.name != "nt":
            raise RuntimeError("Camera credential storage requires Windows DPAPI.")
        raw = json.dumps(values, separators=(",", ":")).encode("utf-8")
        source, keepalive = self._blob(raw)
        output = _Blob()
        entropy, entropy_keepalive = self._blob(b"LotTrace camera credential v1")
        if not ctypes.windll.crypt32.CryptProtectData(ctypes.byref(source), "LotTrace", ctypes.byref(entropy), None, None, 0x1, ctypes.byref(output)):
            raise ctypes.WinError()
        try:
            return ctypes.string_at(output.pbData, output.cbData)
        finally:
            ctypes.windll.kernel32.LocalFree(output.pbData)

    def unprotect(self, encrypted: bytes) -> dict:
        if os.name != "nt":
            raise RuntimeError("Camera credential storage requires Windows DPAPI.")
        source, keepalive = self._blob(encrypted)
        output = _Blob()
        entropy, entropy_keepalive = self._blob(b"LotTrace camera credential v1")
        if not ctypes.windll.crypt32.CryptUnprotectData(ctypes.byref(source), None, ctypes.byref(entropy), None, None, 0x1, ctypes.byref(output)):
            raise ctypes.WinError()
        try:
            return json.loads(ctypes.string_at(output.pbData, output.cbData).decode("utf-8"))
        finally:
            ctypes.windll.kernel32.LocalFree(output.pbData)


def _credential_url(url: str, credentials: dict) -> str:
    parsed = urlsplit(url)
    public_query = list(parse_qsl(parsed.query, keep_blank_values=True))
    public_query.extend(credentials.get("sensitive_query", []))
    url = urlunsplit((parsed.scheme, parsed.netloc, parsed.path, urlencode(public_query), parsed.fragment))
    if not credentials.get("username"):
        return url
    from urllib.parse import quote
    parsed = urlsplit(url)
    auth = quote(credentials["username"], safe="")
    if credentials.get("password") is not None:
        auth += ":" + quote(credentials["password"], safe="")
    host = parsed.hostname or ""
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    if parsed.port:
        host += f":{parsed.port}"
    return urlunsplit((parsed.scheme, f"{auth}@{host}", parsed.path, parsed.query, parsed.fragment))


class OpenCVCapture:
    def __init__(self, url: str):
        import cv2
        parameters = []
        if hasattr(cv2, "CAP_PROP_OPEN_TIMEOUT_MSEC"):
            parameters.extend((cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 5000))
        if hasattr(cv2, "CAP_PROP_READ_TIMEOUT_MSEC"):
            parameters.extend((cv2.CAP_PROP_READ_TIMEOUT_MSEC, 5000))
        self._capture = cv2.VideoCapture(url, cv2.CAP_FFMPEG, parameters)
        if not self._capture.isOpened():
            raise ConnectionError("Unable to open the configured camera stream.")
    def read(self):
        ok, frame = self._capture.read()
        return ok, frame, None
    def close(self):
        self._capture.release()


@dataclass
class CameraMetrics:
    captured_frames: int = 0
    processed_frames: int = 0
    corrupt_frames: int = 0
    dropped_processing_frames: int = 0
    evidence_queue_failures: int = 0
    reconnects: int = 0
    processing_queue_depth: int = 0
    evidence_queue_depth: int = 0
    last_source_timestamp: float | None = None
    last_receipt_at: str | None = None
    processing_latency_ms: float | None = None


@dataclass
class FrameEnvelope:
    frame: object
    receipt_monotonic: float
    receipt_at: str
    source_timestamp: float | None


class CameraWorker:
    def __init__(self, record: dict, credentials: dict, capture_factory=OpenCVCapture,
                 processor=None, evidence_writer=None, clock=time.monotonic,
                 random_source=random.random, processing_capacity=8, evidence_capacity=90,
                 stall_seconds=10.0, base_backoff=.25, max_backoff=30.0):
        self.record, self.credentials = record, credentials
        self.capture_factory, self.processor = capture_factory, processor
        self.evidence_writer = evidence_writer
        self.clock, self.random_source = clock, random_source
        self.processing_queue = queue.Queue(maxsize=processing_capacity)
        self.evidence_queue = queue.Queue(maxsize=evidence_capacity)
        self.stall_seconds, self.base_backoff, self.max_backoff = stall_seconds, base_backoff, max_backoff
        self.metrics = CameraMetrics()
        self.status, self.status_detail = "offline", None
        self._stop, self._pause = threading.Event(), threading.Event()
        self._threads: list[threading.Thread] = []
        self._capture = None

    def snapshot(self):
        self.metrics.processing_queue_depth = self.processing_queue.qsize()
        self.metrics.evidence_queue_depth = self.evidence_queue.qsize()
        return {"camera_id": self.record["camera_id"], "status": self.status,
                "status_detail": self.status_detail, "metrics": asdict(self.metrics)}

    def start(self):
        if any(t.is_alive() for t in self._threads): return
        self._stop.clear(); self._pause.clear()
        self._threads = [threading.Thread(target=self._capture_loop, daemon=True, name=f"camera-{self.record['camera_id']}-capture"),
                         threading.Thread(target=self._process_loop, daemon=True, name=f"camera-{self.record['camera_id']}-process"),
                         threading.Thread(target=self._evidence_loop, daemon=True, name=f"camera-{self.record['camera_id']}-evidence")]
        for thread in self._threads: thread.start()

    def pause(self):
        self._pause.set(); self.status = "paused"
    def resume(self):
        self._pause.clear(); self.status = "reconnecting"
    def stop(self, timeout=5):
        self._stop.set()
        if self._capture:
            try: self._capture.close()
            except Exception: pass
        for thread in self._threads: thread.join(timeout)
        self.status = "offline"

    def _set_failure(self, error):
        message = str(error).lower()
        if "401" in message or "403" in message or "auth" in message or "credential" in message:
            self.status, self.status_detail = "authentication_failure", "Camera authentication failed."
        elif "unsupported" in message:
            self.status, self.status_detail = "unsupported_stream", "The camera stream format is unsupported."
        else:
            self.status, self.status_detail = "reconnecting", "Camera connection interrupted."

    def _capture_loop(self):
        failures = 0
        while not self._stop.is_set():
            if self._pause.is_set(): self._stop.wait(.05); continue
            try:
                url = _credential_url(self.record["stream_url"], self.credentials)
                self._capture = self.capture_factory(url)
                self.status, self.status_detail, failures = "online", None, 0
                last_frame = self.clock()
                last_enqueued = -1e12
                capture_interval = 1 / max(float(self.record.get("capture_fps") or 15), .01)
                while not self._stop.is_set() and not self._pause.is_set():
                    ok, frame, source_timestamp = self._capture.read()
                    now = self.clock()
                    if not ok or frame is None:
                        self.metrics.corrupt_frames += 1
                        if now - last_frame >= self.stall_seconds:
                            raise TimeoutError("Camera stream stalled.")
                        continue
                    last_frame = now
                    if now - last_enqueued < capture_interval:
                        continue
                    last_enqueued = now
                    envelope = FrameEnvelope(frame, now, datetime.now(timezone.utc).isoformat(), source_timestamp)
                    self.metrics.captured_frames += 1
                    self.metrics.last_source_timestamp = source_timestamp
                    self.metrics.last_receipt_at = envelope.receipt_at
                    try: self.processing_queue.put_nowait(envelope)
                    except queue.Full:
                        try: self.processing_queue.get_nowait(); self.processing_queue.task_done()
                        except queue.Empty: pass
                        self.processing_queue.put_nowait(envelope)
                        self.metrics.dropped_processing_frames += 1
                        self.status = "overloaded"
                    if self.record.get("evidence_enabled", 1):
                        try: self.evidence_queue.put(envelope, timeout=.05)
                        except queue.Full:
                            self.metrics.evidence_queue_failures += 1
                            self.status, self.status_detail = "overloaded", "Evidence queue capacity exceeded; recording is incomplete."
                self._capture.close(); self._capture = None
            except Exception as error:
                self._set_failure(error)
                failures += 1; self.metrics.reconnects += 1
                delay = min(self.max_backoff, self.base_backoff * (2 ** min(failures - 1, 8)))
                delay *= .75 + self.random_source() * .5
                self._stop.wait(delay)
        if self._capture:
            try: self._capture.close()
            except Exception: pass

    def _process_loop(self):
        min_interval = 1 / max(float(self.record.get("inference_fps") or 3), .01)
        last_processed = -min_interval
        while not self._stop.is_set() or not self.processing_queue.empty():
            try: envelope = self.processing_queue.get(timeout=.1)
            except queue.Empty: continue
            try:
                if envelope.receipt_monotonic - last_processed >= min_interval:
                    if self.processor: self.processor(self.record["camera_id"], envelope)
                    last_processed = envelope.receipt_monotonic
                    self.metrics.processed_frames += 1
                    self.metrics.processing_latency_ms = max(0, (self.clock() - envelope.receipt_monotonic) * 1000)
            finally: self.processing_queue.task_done()

    def _evidence_loop(self):
        while not self._stop.is_set() or not self.evidence_queue.empty():
            try: envelope = self.evidence_queue.get(timeout=.1)
            except queue.Empty: continue
            try:
                if self.evidence_writer: self.evidence_writer(self.record, envelope)
            except Exception:
                self.metrics.evidence_queue_failures += 1
                self.status, self.status_detail = "overloaded", "Evidence writer failed; recording is incomplete."
            finally: self.evidence_queue.task_done()


class RollingEvidenceWriter:
    def __init__(self, root: str | Path | None = None):
        self.root = Path(root or DB_DIR) / "evidence" / "live"
        self._writers, self._segments = {}, {}
        self._lock = threading.Lock()
    def __call__(self, record, envelope):
        import cv2
        camera_id = record["camera_id"]
        with self._lock:
            started = self._segments.get(camera_id, 0)
            if camera_id not in self._writers or envelope.receipt_monotonic - started >= int(record.get("evidence_segment_seconds") or 60):
                old = self._writers.pop(camera_id, None)
                if old: old.release()
                folder = self.root / camera_id; folder.mkdir(parents=True, exist_ok=True)
                stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
                path = folder / f"{stamp}.mp4"
                height, width = envelope.frame.shape[:2]
                writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), float(record.get("capture_fps") or 15), (width, height))
                if not writer.isOpened(): raise IOError("Unable to create evidence segment.")
                self._writers[camera_id], self._segments[camera_id] = writer, envelope.receipt_monotonic
                self._enforce_retention(folder, int(record.get("evidence_retention_hours") or 168))
            self._writers[camera_id].write(envelope.frame)
    @staticmethod
    def _enforce_retention(folder, hours):
        cutoff = time.time() - hours * 3600
        for path in folder.glob("*.mp4"):
            if path.stat().st_mtime < cutoff: path.unlink(missing_ok=True)
    def close(self):
        with self._lock:
            for writer in self._writers.values(): writer.release()
            self._writers.clear()


class CameraManager:
    def __init__(self, protector=None, capture_factory=OpenCVCapture, processor=None, evidence_writer=None):
        self.protector = protector or WindowsCredentialProtector()
        self.capture_factory, self.processor = capture_factory, processor
        self.evidence_writer = evidence_writer or RollingEvidenceWriter()
        self.workers: dict[str, CameraWorker] = {}
        self._lock = threading.Lock()
    def start_camera(self, camera_id, dealership_id):
        with get_db_connection() as conn:
            row = conn.execute("SELECT * FROM cameras WHERE camera_id=? AND dealership_id=?", (camera_id, dealership_id)).fetchone()
        if not row: raise LookupError("Camera not found.")
        record = dict(row)
        if not record.get("stream_url"): raise ValueError("Camera has no RTSP stream configured.")
        credentials = self.protector.unprotect(record["credential_blob"]) if record.get("credential_blob") else {}
        with self._lock:
            if camera_id in self.workers: self.workers[camera_id].stop()
            worker = CameraWorker(record, credentials, self.capture_factory, self.processor, self.evidence_writer)
            self.workers[camera_id] = worker; worker.start()
        return self.status(camera_id, dealership_id)
    def control(self, camera_id, dealership_id, action):
        worker = self.workers.get(camera_id)
        if not worker: raise LookupError("Camera is not running.")
        if action == "pause": worker.pause()
        elif action == "resume": worker.resume()
        elif action == "stop": worker.stop()
        else: raise ValueError("Unsupported camera action.")
        return worker.snapshot()
    def status(self, camera_id, dealership_id):
        worker = self.workers.get(camera_id)
        return worker.snapshot() if worker else {"camera_id": camera_id, "status": "offline", "status_detail": None, "metrics": asdict(CameraMetrics())}
    def stop_all(self):
        for worker in list(self.workers.values()): worker.stop()
        self.workers.clear()
        close = getattr(self.evidence_writer, "close", None)
        if close: close()
    def start_configured(self):
        """Resume active configured cameras after a backend/process restart."""
        with get_db_connection() as conn:
            rows = conn.execute("SELECT camera_id,dealership_id FROM cameras WHERE active=1 AND stream_url IS NOT NULL").fetchall()
        results = []
        for row in rows:
            try: results.append(self.start_camera(row["camera_id"], row["dealership_id"]))
            except Exception: # Status remains offline; secrets and connection details are intentionally not logged.
                results.append({"camera_id": row["camera_id"], "status": "offline"})
        return results


def configure_camera(user, camera_id, values, protector=None):
    protector = protector or WindowsCredentialProtector()
    url = values.get("stream_url", "").strip()
    parsed = urlsplit(url)
    if parsed.scheme.lower() != "rtsp" or not parsed.hostname:
        raise ValueError("A valid RTSP URL is required.")
    # Strip inline credentials before persistence; store them only inside DPAPI ciphertext.
    credentials = {"username": values.get("username"), "password": values.get("password")}
    if parsed.username is not None:
        from urllib.parse import unquote
        credentials["username"], credentials["password"] = unquote(parsed.username), unquote(parsed.password or "")
    sensitive_names = ("password", "passwd", "pass", "token", "secret", "auth", "user", "username")
    public_query, sensitive_query = [], []
    for key, value in parse_qsl(parsed.query, keep_blank_values=True):
        (sensitive_query if any(name in key.lower() for name in sensitive_names) else public_query).append((key, value))
    credentials["sensitive_query"] = sensitive_query
    clean_url = urlunsplit((parsed.scheme, (parsed.hostname or "") + (f":{parsed.port}" if parsed.port else ""), parsed.path, urlencode(public_query), ""))
    encrypted = protector.protect(credentials) if credentials.get("username") or sensitive_query else None
    with get_db_connection() as conn:
        row = conn.execute("SELECT camera_id FROM cameras WHERE camera_id=? AND dealership_id=?", (camera_id, user["dealership_id"])).fetchone()
        if not row: raise LookupError("Camera not found.")
        conn.execute("""UPDATE cameras SET stream_url=?,credential_blob=?,onvif_device_url=?,onvif_profile_token=?,
            capture_fps=?,inference_fps=?,evidence_enabled=?,evidence_segment_seconds=?,evidence_retention_hours=?,updated_at=CURRENT_TIMESTAMP
            WHERE camera_id=?""", (clean_url, encrypted, values.get("onvif_device_url"), values.get("onvif_profile_token"),
            values.get("capture_fps", 15), values.get("inference_fps", 3), int(values.get("evidence_enabled", True)),
            values.get("evidence_segment_seconds", 60), values.get("evidence_retention_hours", 168), camera_id))
    return public_camera(camera_id, user["dealership_id"])


def public_camera(camera_id, dealership_id):
    with get_db_connection() as conn:
        row = conn.execute("SELECT * FROM cameras WHERE camera_id=? AND dealership_id=?", (camera_id, dealership_id)).fetchone()
    if not row: raise LookupError("Camera not found.")
    item = dict(row); item.pop("credential_blob", None)
    item["stream_url"] = redact_stream_url(item.get("stream_url")); item["credentials_configured"] = bool(row["credential_blob"])
    return item


def discover_onvif(timeout=1.5):
    """WS-Discovery probe. Results contain device service URLs only, never secrets."""
    message_id = "uuid:" + str(uuid.uuid4())
    payload = f'''<?xml version="1.0" encoding="UTF-8"?><e:Envelope xmlns:e="http://www.w3.org/2003/05/soap-envelope" xmlns:w="http://schemas.xmlsoap.org/ws/2004/08/addressing" xmlns:d="http://schemas.xmlsoap.org/ws/2005/04/discovery" xmlns:dn="http://www.onvif.org/ver10/network/wsdl"><e:Header><w:MessageID>{message_id}</w:MessageID><w:To e:mustUnderstand="true">urn:schemas-xmlsoap-org:ws:2005:04:discovery</w:To><w:Action e:mustUnderstand="true">http://schemas.xmlsoap.org/ws/2005/04/discovery/Probe</w:Action></e:Header><e:Body><d:Probe><d:Types>dn:NetworkVideoTransmitter</d:Types></d:Probe></e:Body></e:Envelope>'''.encode()
    found = {}
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    try:
        sock.settimeout(.2); sock.sendto(payload, ("239.255.255.250", 3702)); deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try: data, address = sock.recvfrom(65535)
            except socket.timeout: continue
            try:
                root = ET.fromstring(data)
                xaddrs = next((element.text for element in root.iter() if element.tag.endswith("XAddrs")), "") or ""
                for url in xaddrs.split(): found[url] = {"device_service_url": url, "address": address[0]}
            except ET.ParseError: continue
    finally: sock.close()
    return list(found.values())


manager = CameraManager()
