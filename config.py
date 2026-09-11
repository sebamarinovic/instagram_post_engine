from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent
DATA_DIR = PROJECT_DIR / "data"
THUMB_DIR = DATA_DIR / "thumbs"
DRAFT_DIR = DATA_DIR / "drafts"

for p in (DATA_DIR, THUMB_DIR, DRAFT_DIR):
    p.mkdir(parents=True, exist_ok=True)

MEDIA_CSV = DATA_DIR / "media_index.csv"
EXPERIENCES_CSV = DATA_DIR / "experiences.csv"
