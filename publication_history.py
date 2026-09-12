from pathlib import Path
from datetime import datetime, timezone
import hashlib, os
import pandas as pd

from config import PUBLISHED_MEDIA_CSV

HISTORY_FILE = PUBLISHED_MEDIA_CSV
COLUMNS = [
    "media_key","path","filename","published_at","instagram_media_id",
    "publication_id","caption","country","city","year","permalink","source"
]

def normalize_path(path):
    return os.path.normcase(os.path.abspath(str(path)))

def _path_key(path):
    return hashlib.sha256(normalize_path(path).encode("utf-8")).hexdigest()

def _content_key(content_hash):
    return str(content_hash).strip().lower()

def media_key(path, content_hash=None):
    """Identifier to store for a file: content hash when known (stable across
    moves/renames/duplicate folders), otherwise a hash of its path (legacy
    behavior, kept for files scanned before content hashing existed)."""
    if content_hash and str(content_hash).strip() and str(content_hash).lower() != "nan":
        return _content_key(content_hash)
    return _path_key(path)

def media_keys(path, content_hash=None):
    """Every identifier that could refer to this file, for matching against
    history recorded under either scheme (path-based entries predate content
    hashing; a file rescanned since then also has a content-based key)."""
    keys = {_path_key(path)}
    if content_hash and str(content_hash).strip() and str(content_hash).lower() != "nan":
        keys.add(_content_key(content_hash))
    return keys

def load_history():
    if not HISTORY_FILE.exists():
        return pd.DataFrame(columns=COLUMNS)
    try:
        df = pd.read_csv(HISTORY_FILE)
    except Exception:
        return pd.DataFrame(columns=COLUMNS)

    for c in COLUMNS:
        if c not in df.columns:
            df[c] = None
    return df[COLUMNS]

def _append_rows(rows):
    HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    current = load_history()
    if rows:
        out = pd.concat([current, pd.DataFrame(rows)], ignore_index=True)
        out.to_csv(HISTORY_FILE, index=False, encoding="utf-8-sig")
    return len(rows)

def record_publication(records, caption, api_result):
    current = load_history()
    existing = set(current["media_key"].dropna().astype(str))

    is_dry_run = bool(isinstance(api_result, dict) and api_result.get("dry_run"))
    ig_id = str(api_result.get("id","")) if isinstance(api_result, dict) else ""
    permalink = api_result.get("permalink") if isinstance(api_result, dict) else None
    pub_id = ig_id or datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    now = datetime.now(timezone.utc).isoformat()

    rows = []
    for r in records:
        content_hash = r.get("content_hash")
        if media_keys(r["path"], content_hash) & existing:
            continue
        k = media_key(r["path"], content_hash)

        rows.append({
            "media_key": k,
            "path": normalize_path(r["path"]),
            "filename": r.get("filename") or Path(str(r["path"])).name,
            "published_at": now,
            "instagram_media_id": ig_id,
            "publication_id": pub_id,
            "caption": caption,
            "country": r.get("country"),
            "city": r.get("city"),
            "year": r.get("year"),
            "permalink": permalink,
            "source": "dry_run" if is_dry_run else "motor_v5_1"
        })

    return _append_rows(rows)

def record_existing_publication(records, permalink, note="Publicación histórica importada manualmente"):
    current = load_history()
    existing = set(current["media_key"].dropna().astype(str))
    pub_id = "historical_" + hashlib.md5(permalink.encode("utf-8")).hexdigest()[:12]
    now = datetime.now(timezone.utc).isoformat()

    rows = []
    for r in records:
        content_hash = r.get("content_hash")
        if media_keys(r["path"], content_hash) & existing:
            continue
        k = media_key(r["path"], content_hash)

        rows.append({
            "media_key": k,
            "path": normalize_path(r["path"]),
            "filename": r.get("filename") or Path(str(r["path"])).name,
            "published_at": now,
            "instagram_media_id": "",
            "publication_id": pub_id,
            "caption": note,
            "country": r.get("country"),
            "city": r.get("city"),
            "year": r.get("year"),
            "permalink": permalink,
            "source": "historical_manual"
        })

    return _append_rows(rows)

SUMMARY_COLUMNS = [
    "publication_id","published_at","photos","country","city","year",
    "caption","instagram_media_id","permalink","source","cover_filename","cover_path"
]

def summarize_publications(hist_df):
    """Collapse the per-photo history into one row per publication_id — the
    unit the historial view (and the user) actually thinks in terms of."""
    if hist_df.empty:
        return pd.DataFrame(columns=SUMMARY_COLUMNS)

    rows = []
    for pub_id, group in hist_df.groupby("publication_id", dropna=False):
        first = group.iloc[0]
        rows.append({
            "publication_id": pub_id,
            "published_at": group["published_at"].min(),
            "photos": len(group),
            "country": first.get("country"),
            "city": first.get("city"),
            "year": first.get("year"),
            "caption": first.get("caption"),
            "instagram_media_id": first.get("instagram_media_id"),
            "permalink": first.get("permalink"),
            "source": first.get("source"),
            "cover_filename": first.get("filename"),
            "cover_path": first.get("path"),
        })
    return pd.DataFrame(rows, columns=SUMMARY_COLUMNS).sort_values(
        "published_at", ascending=False, ignore_index=True
    )
