from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent
DATA_DIR = PROJECT_DIR / "data"
THUMB_DIR = DATA_DIR / "thumbs"
CONFIG_DIR = PROJECT_DIR / "config"
UPLOADS_DIR = DATA_DIR / "uploads"

for p in (DATA_DIR, THUMB_DIR, CONFIG_DIR, UPLOADS_DIR):
    p.mkdir(parents=True, exist_ok=True)

MEDIA_INDEX_CSV = DATA_DIR / "media_index.csv"
MEDIA_GEO_CSV = DATA_DIR / "media_geo.csv"
PUBLISHED_MEDIA_CSV = DATA_DIR / "published_media.csv"
PROFILE_CONTEXT_JSON = DATA_DIR / "profile_context.json"
MEDIA_SOURCES_JSON = CONFIG_DIR / "media_sources.json"

# SQLite is not used by the running app yet — see db.py and
# migrate_to_sqlite.py. This path is where a migration would write to;
# app.py, scan_media.py etc. still read/write the CSVs above exclusively.
SQLITE_DB = DATA_DIR / "instagram_rebuild.db"
