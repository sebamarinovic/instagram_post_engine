"""One-shot, safe migration of the CSV/JSON data files into
data/instagram_rebuild.db (SQLite).

Does NOT touch app.py's behavior and does NOT delete or modify the
original files — it only reads them and backs them up. Run it, read the
validation report it prints, and decide from there whether switching the
app itself to read from the database is worth doing (a separate change,
not part of this script).

Usage:
    python migrate_to_sqlite.py
"""
import random
import shutil
from datetime import datetime, timezone

import pandas as pd

import db
import media_sources as ms
from config import DATA_DIR, MEDIA_GEO_CSV, PUBLISHED_MEDIA_CSV, MEDIA_SOURCES_JSON, PROFILE_CONTEXT_JSON
from publication_history import load_history, summarize_publications

MEDIA_COLUMNS = [
    "path","filename","ext","media_type","size_mb","filesystem_mtime",
    "content_hash","source_id","source_name","source_path","width","height",
    "captured_at","lat","lon","sharpness","brightness","phash","quality_score",
    "thumb_path","available_local","duration_s","error","date_source","year",
    "country_code","country","city","admin1","location_source",
]

def _clean_records(df, columns):
    """Return list of dict rows with every value present (as None where
    missing/NaN) so sqlite doesn't get pandas NaN floats in text columns."""
    df = df.reindex(columns=columns)
    df = df.astype(object).where(pd.notna(df), None)
    return df.to_dict("records")

def backup_originals():
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    backup_dir = DATA_DIR / f"backup_pre_sqlite_{stamp}"
    backup_dir.mkdir(parents=True, exist_ok=True)
    copied = []
    for src in (MEDIA_GEO_CSV, PUBLISHED_MEDIA_CSV, MEDIA_SOURCES_JSON, PROFILE_CONTEXT_JSON):
        if src.exists():
            shutil.copy2(src, backup_dir / src.name)
            copied.append(src.name)
    print(f"📦 Backup en {backup_dir} ({', '.join(copied) or 'nada que copiar'})")
    return backup_dir

def migrate_sources(conn):
    sources = ms.list_sources()
    for s in sources:
        conn.execute(
            """INSERT OR REPLACE INTO sources
               (id, name, path, enabled, is_primary, last_scanned_at, last_scan_items)
               VALUES (:id, :name, :path, :enabled, :primary, :last_scanned_at, :last_scan_items)""",
            {
                "id": s["id"], "name": s.get("name"), "path": s.get("path"),
                "enabled": int(bool(s.get("enabled", True))),
                "primary": int(bool(s.get("primary", False))),
                "last_scanned_at": s.get("last_scanned_at"),
                "last_scan_items": s.get("last_scan_items", 0),
            },
        )
    return len(sources)

def migrate_media(conn):
    if not MEDIA_GEO_CSV.exists():
        print(f"⏭️  {MEDIA_GEO_CSV} no existe todavía — nada que migrar en 'media'.")
        return 0, None
    media_df = pd.read_csv(MEDIA_GEO_CSV)
    records = _clean_records(media_df, MEDIA_COLUMNS)
    placeholders = ", ".join(f":{c}" for c in MEDIA_COLUMNS)
    conn.executemany(
        f"INSERT OR REPLACE INTO media ({', '.join(MEDIA_COLUMNS)}) VALUES ({placeholders})",
        records,
    )
    return len(records), media_df

def migrate_publications(conn):
    hist = load_history()
    if hist.empty:
        print(f"⏭️  {PUBLISHED_MEDIA_CSV} no existe o está vacío — nada que migrar en 'publications'.")
        return 0, 0, hist
    summary = summarize_publications(hist)
    for _, row in summary.iterrows():
        conn.execute(
            """INSERT OR REPLACE INTO publications
               (publication_id, published_at, instagram_media_id, caption,
                country, city, year, permalink, source)
               VALUES (:publication_id, :published_at, :instagram_media_id, :caption,
                       :country, :city, :year, :permalink, :source)""",
            {k: (None if pd.isna(v) else v) for k, v in row.to_dict().items()
             if k in {"publication_id","published_at","instagram_media_id","caption",
                       "country","city","year","permalink","source"}},
        )
    for _, row in hist.iterrows():
        conn.execute(
            """INSERT OR REPLACE INTO publication_media
               (publication_id, media_key, path, filename)
               VALUES (?, ?, ?, ?)""",
            (row.get("publication_id"), row.get("media_key"), row.get("path"), row.get("filename")),
        )
    return len(summary), len(hist), hist

def migrate_settings(conn):
    if not PROFILE_CONTEXT_JSON.exists():
        return 0
    import json
    data = json.loads(PROFILE_CONTEXT_JSON.read_text(encoding="utf-8"))
    profile_context = data.get("profile_context")
    if profile_context is not None:
        conn.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES ('profile_context', ?)",
            (profile_context,),
        )
        return 1
    return 0

def validate(conn, media_df, hist, sources_expected, publications_expected, photos_expected):
    print("\n--- Validación ---")
    ok = True

    media_actual = db.table_count(conn, "media")
    media_expected = 0 if media_df is None else len(media_df)
    print(f"media: esperado {media_expected}, en DB {media_actual}", "✅" if media_actual == media_expected else "❌")
    ok &= media_actual == media_expected

    sources_actual = db.table_count(conn, "sources")
    print(f"sources: esperado {sources_expected}, en DB {sources_actual}", "✅" if sources_actual == sources_expected else "❌")
    ok &= sources_actual == sources_expected

    pubs_actual = db.table_count(conn, "publications")
    print(f"publications: esperado {publications_expected}, en DB {pubs_actual}", "✅" if pubs_actual == publications_expected else "❌")
    ok &= pubs_actual == publications_expected

    pm_actual = db.table_count(conn, "publication_media")
    print(f"publication_media: esperado {photos_expected}, en DB {pm_actual}", "✅" if pm_actual == photos_expected else "❌")
    ok &= pm_actual == photos_expected

    if media_df is not None and len(media_df):
        sample_idx = random.sample(range(len(media_df)), min(5, len(media_df)))
        for i in sample_idx:
            row = media_df.iloc[i]
            db_row = conn.execute("SELECT filename, quality_score FROM media WHERE path = ?", (row["path"],)).fetchone()
            match = db_row is not None and db_row["filename"] == row["filename"]
            print(f"  spot-check {row['filename']}: {'✅' if match else '❌ no coincide'}")
            ok &= match

    print("✅ Migración validada correctamente." if ok else "❌ Hay diferencias — revisa arriba antes de confiar en la DB.")
    return ok

def main():
    print("=== Migración a SQLite (no destructiva) ===\n")
    backup_originals()
    db.init_db()

    with db.connect() as conn:
        sources_count = migrate_sources(conn)
        media_count, media_df = migrate_media(conn)
        publications_count, photos_count, hist = migrate_publications(conn)
        settings_count = migrate_settings(conn)

        print(f"\nImportado: {media_count} medios, {sources_count} fuentes, "
              f"{publications_count} publicaciones ({photos_count} fotos), {settings_count} ajuste(s).")

        validate(conn, media_df, hist, sources_count, publications_count, photos_count)

    print(f"\nBase de datos en: {db.SQLITE_DB}")
    print(
        "\nLos archivos CSV/JSON originales NO se modificaron ni se borraron. "
        "La app (app.py) sigue leyendo de ellos exactamente igual que antes — "
        "esta base de datos no está conectada a la app todavía."
    )

if __name__ == "__main__":
    main()
