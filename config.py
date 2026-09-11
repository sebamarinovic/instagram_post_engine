from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent
DATA_DIR = PROJECT_DIR / "data"
THUMB_DIR = DATA_DIR / "thumbs"
CONFIG_DIR = PROJECT_DIR / "config"

for p in (DATA_DIR, THUMB_DIR, CONFIG_DIR):
    p.mkdir(parents=True, exist_ok=True)

MEDIA_INDEX_CSV = DATA_DIR / "media_index.csv"
MEDIA_GEO_CSV = DATA_DIR / "media_geo.csv"
PUBLISHED_MEDIA_CSV = DATA_DIR / "published_media.csv"
PROFILE_CONTEXT_JSON = DATA_DIR / "profile_context.json"
MEDIA_SOURCES_JSON = CONFIG_DIR / "media_sources.json"
