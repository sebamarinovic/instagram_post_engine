"""Manual location corrections that survive re-running "Recalcular
ubicación". enrich_locations.py rebuilds country/city/location_source
from scratch (GPS, then time-inference) every time it runs — a one-off
edit to media_geo.csv would just get overwritten on the next run. This
stores corrections separately, keyed by content_hash (falling back to a
path hash for rows scanned before content hashing existed, same scheme
as publication_history.media_key), and enrich_locations applies them
last, so a manual correction always wins over the automated guess.
"""
import hashlib
import json
import os

from config import CONFIG_DIR

OVERRIDES_JSON = CONFIG_DIR / "location_overrides.json"


def _load():
    if not OVERRIDES_JSON.exists():
        return {}
    try:
        return json.loads(OVERRIDES_JSON.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save(data):
    OVERRIDES_JSON.parent.mkdir(parents=True, exist_ok=True)
    OVERRIDES_JSON.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def key_for(path, content_hash=None):
    ch = str(content_hash).strip().lower() if content_hash is not None else ""
    if ch and ch not in ("", "nan", "none"):
        return f"hash:{ch}"
    normalized = os.path.normcase(os.path.abspath(str(path)))
    return "path:" + hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def set_override(path, content_hash, country, city, country_code=None, admin1=None):
    data = _load()
    data[key_for(path, content_hash)] = {
        "country": country,
        "city": city,
        "country_code": country_code,
        "admin1": admin1,
    }
    _save(data)
    return len(data)


def remove_override(path, content_hash):
    data = _load()
    data.pop(key_for(path, content_hash), None)
    _save(data)


def apply_overrides(df):
    """Called by enrich_locations.py right before writing media_geo.csv."""
    data = _load()
    if not data or df.empty:
        return df
    for idx, row in df.iterrows():
        ov = data.get(key_for(row.get("path"), row.get("content_hash")))
        if not ov:
            continue
        df.at[idx, "country"] = ov.get("country")
        df.at[idx, "city"] = ov.get("city")
        df.at[idx, "country_code"] = ov.get("country_code")
        df.at[idx, "admin1"] = ov.get("admin1")
        df.at[idx, "location_source"] = "manual"
    return df
