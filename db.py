"""SQLite schema and connection helper for the (not yet wired in) database
backend. Nothing in app.py, scan_media.py, publication_history.py or
media_sources.py reads or writes this database — they still use the CSV
and JSON files under data/ and config/ exclusively. This module and
migrate_to_sqlite.py exist so that migration can be built, run and
validated against real data safely, before any decision is made to switch
the running app over to it.
"""
import sqlite3
from contextlib import contextmanager

from config import SQLITE_DB

SCHEMA = """
CREATE TABLE IF NOT EXISTS sources (
    id TEXT PRIMARY KEY,
    name TEXT,
    path TEXT,
    enabled INTEGER NOT NULL DEFAULT 1,
    is_primary INTEGER NOT NULL DEFAULT 0,
    last_scanned_at TEXT,
    last_scan_items INTEGER
);

CREATE TABLE IF NOT EXISTS media (
    path TEXT PRIMARY KEY,
    filename TEXT,
    ext TEXT,
    media_type TEXT,
    size_mb REAL,
    filesystem_mtime TEXT,
    content_hash TEXT,
    source_id TEXT REFERENCES sources(id),
    source_name TEXT,
    source_path TEXT,
    width INTEGER,
    height INTEGER,
    captured_at TEXT,
    lat REAL,
    lon REAL,
    sharpness REAL,
    brightness REAL,
    phash TEXT,
    quality_score REAL,
    thumb_path TEXT,
    available_local INTEGER,
    duration_s REAL,
    error TEXT,
    date_source TEXT,
    year INTEGER,
    country_code TEXT,
    country TEXT,
    city TEXT,
    admin1 TEXT,
    location_source TEXT
);

CREATE TABLE IF NOT EXISTS publications (
    publication_id TEXT PRIMARY KEY,
    published_at TEXT,
    instagram_media_id TEXT,
    caption TEXT,
    country TEXT,
    city TEXT,
    year INTEGER,
    permalink TEXT,
    source TEXT
);

CREATE TABLE IF NOT EXISTS publication_media (
    publication_id TEXT NOT NULL REFERENCES publications(publication_id),
    media_key TEXT NOT NULL,
    path TEXT,
    filename TEXT,
    PRIMARY KEY (publication_id, media_key)
);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT
);

CREATE INDEX IF NOT EXISTS idx_media_content_hash ON media(content_hash);
CREATE INDEX IF NOT EXISTS idx_media_source_id ON media(source_id);
CREATE INDEX IF NOT EXISTS idx_media_country_city ON media(country, city);
CREATE INDEX IF NOT EXISTS idx_publication_media_media_key ON publication_media(media_key);
"""

@contextmanager
def connect():
    conn = sqlite3.connect(SQLITE_DB)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()

def init_db():
    SQLITE_DB.parent.mkdir(parents=True, exist_ok=True)
    with connect() as conn:
        conn.executescript(SCHEMA)

def table_count(conn, table):
    return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
