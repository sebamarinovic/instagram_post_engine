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

# Fixed (not random) id: migrate_to_s3.py runs on a different machine than
# the deployed app and stamps this same id into every manifest row it
# writes to S3 — a random per-machine uuid (like add_source generates)
# would never match up across the two.
S3_LIBRARY_SOURCE_ID = "s3-library"

def ensure_s3_source(bucket, prefix="library/", name="☁️ Librería en S3"):
    """Find (or create) the source that represents the bulk-migrated S3
    library. Its 'path' is an s3://bucket/prefix marker, not a real
    filesystem path — the rest of the app detects it (str starting with
    "s3://") to use S3-appropriate actions instead of filesystem ones."""
    data = _load_raw()
    sources = data.setdefault("sources", [])
    for s in sources:
        if s["id"] == S3_LIBRARY_SOURCE_ID:
            return S3_LIBRARY_SOURCE_ID
    sources.append({
        "id": S3_LIBRARY_SOURCE_ID,
        "name": name,
        "path": f"s3://{bucket}/{prefix}",
        "enabled": True,
        "primary": len(sources) == 0,
        "last_scanned_at": None,
        "last_scan_items": 0,
    })
    _save_raw(data)
    return S3_LIBRARY_SOURCE_ID
