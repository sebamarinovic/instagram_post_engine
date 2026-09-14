import json
import uuid
from datetime import datetime, timezone

from config import MEDIA_SOURCES_JSON

def _load_raw():
    if not MEDIA_SOURCES_JSON.exists():
        return {"sources": []}
    try:
        return json.loads(MEDIA_SOURCES_JSON.read_text(encoding="utf-8"))
    except Exception:
        return {"sources": []}

def _save_raw(data):
    MEDIA_SOURCES_JSON.parent.mkdir(parents=True, exist_ok=True)
    MEDIA_SOURCES_JSON.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

def list_sources():
    return _load_raw().get("sources", [])

def get_source(source_id):
    for s in list_sources():
        if s["id"] == source_id:
            return s
    return None

def enabled_source_ids():
    return {s["id"] for s in list_sources() if s.get("enabled", True)}

def add_source(name, path):
    data = _load_raw()
    sources = data.setdefault("sources", [])
    new_id = uuid.uuid4().hex[:12]
    sources.append({
        "id": new_id,
        "name": name,
        "path": str(path),
        "enabled": True,
        "primary": len(sources) == 0,
        "last_scanned_at": None,
        "last_scan_items": 0,
    })
    _save_raw(data)
    return new_id

def remove_source(source_id):
    data = _load_raw()
    data["sources"] = [s for s in data.get("sources", []) if s["id"] != source_id]
    _save_raw(data)

def set_enabled(source_id, enabled):
    data = _load_raw()
    for s in data.get("sources", []):
        if s["id"] == source_id:
            s["enabled"] = enabled
    _save_raw(data)

def set_primary(source_id):
    data = _load_raw()
    for s in data.get("sources", []):
        s["primary"] = (s["id"] == source_id)
    _save_raw(data)

def update_scan_stats(source_id, item_count):
    data = _load_raw()
    for s in data.get("sources", []):
        if s["id"] == source_id:
            s["last_scanned_at"] = datetime.now(timezone.utc).isoformat()
            s["last_scan_items"] = item_count
    _save_raw(data)

def ensure_uploads_source(path, name="📱 Subidas desde el celular"):
    """Find (or create, on first use) the local source that backs
    mobile-uploaded files. Uploads are saved to `path` as plain files on
    disk, so this is just a regular source — nothing S3/cloud-specific."""
    path = str(path)
    for s in list_sources():
        if s.get("path") == path:
            return s["id"]
    return add_source(name, path)
