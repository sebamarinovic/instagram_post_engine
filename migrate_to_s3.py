"""Bulk-upload the local photo/video library to S3 (Etapa Cloud D), once,
so the deployed app can serve and publish it without this PC needing to
be online.

Run this LOCALLY, on the machine that has your full library — not on the
server. It reads the already-scanned local index (scan your folders first
in "Fuentes multimedia" if you haven't), uploads whatever isn't in S3 yet
(matched by content_hash, so it's safe to interrupt and re-run), and
writes a small manifest CSV to S3 that the deployed app pulls in via
"Fuentes multimedia" -> the S3 source -> "Sincronizar desde S3".

Usage:
    python migrate_to_s3.py

Requires .env with S3_BUCKET and AWS credentials (same .env used by the
rest of the app).
"""
import os
import sys
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

import media_sources as ms
from config import MEDIA_INDEX_CSV
from scan_media import load_index
from s3_library import download_manifest, upload_manifest, upload_file, make_s3_uri, MANIFEST_KEY, S3_PREFIX

CHECKPOINT_EVERY = 50


def _checkpoint(manifest_df, new_rows, bucket):
    addition = pd.DataFrame(new_rows)
    merged = pd.concat([manifest_df, addition], ignore_index=True) if not manifest_df.empty else addition
    upload_manifest(merged, bucket)
    new_rows.clear()
    return merged


def main():
    load_dotenv()
    bucket = os.getenv("S3_BUCKET")
    if not bucket:
        sys.exit("Falta S3_BUCKET en .env")

    local_df = load_index()
    if local_df.empty:
        sys.exit(f"{MEDIA_INDEX_CSV} está vacío — escanea tus carpetas primero en 'Fuentes multimedia'.")
    if "content_hash" not in local_df.columns:
        sys.exit("El índice local no tiene content_hash (versión vieja) — reconstruye el índice primero.")

    local_df = local_df[~local_df["path"].astype(str).str.startswith("s3://")]
    local_df["content_hash"] = local_df["content_hash"].astype(str).str.strip().str.lower()
    local_df = local_df[~local_df["content_hash"].isin(["", "nan", "none"])]

    manifest_df = download_manifest(bucket)
    already = set()
    if not manifest_df.empty and "content_hash" in manifest_df.columns:
        already = set(manifest_df["content_hash"].astype(str).str.strip().str.lower())

    to_migrate = local_df[~local_df["content_hash"].isin(already)].drop_duplicates(subset="content_hash")

    print(
        f"{len(local_df):,} archivo(s) en el índice local · {len(already):,} ya migrado(s) · "
        f"{len(to_migrate):,} por migrar."
    )
    if to_migrate.empty:
        print("Nada nuevo para migrar.")
        return

    source_id = ms.ensure_s3_source(bucket)

    new_rows = []
    uploaded = 0
    missing_local = 0
    failed = 0
    try:
        for _, row in to_migrate.iterrows():
            local_path = Path(str(row["path"]))
            if not local_path.exists():
                missing_local += 1
                continue
            try:
                content_hash = row["content_hash"]
                ext = row.get("ext") or local_path.suffix.lower()
                key = f"{S3_PREFIX}/library/{content_hash}{ext}"
                upload_file(local_path, bucket, key)

                thumb_key = None
                thumb_local = row.get("thumb_path")
                if isinstance(thumb_local, str) and Path(thumb_local).exists():
                    thumb_key = f"{S3_PREFIX}/thumbnails/{content_hash}.jpg"
                    upload_file(thumb_local, bucket, thumb_key)

                new_row = row.to_dict()
                new_row["path"] = make_s3_uri(bucket, key)
                new_row["thumb_path"] = make_s3_uri(bucket, thumb_key) if thumb_key else None
                new_row["source_id"] = source_id
                new_row["source_name"] = "☁️ Librería en S3"
                new_row["source_path"] = make_s3_uri(bucket, f"{S3_PREFIX}/library/")
                new_row["available_local"] = True
                new_rows.append(new_row)
                uploaded += 1
            except Exception as e:
                failed += 1
                print(f"⚠️  Error subiendo {row.get('path')}: {e}")
                continue

            if uploaded and uploaded % CHECKPOINT_EVERY == 0:
                manifest_df = _checkpoint(manifest_df, new_rows, bucket)
                print(f"{uploaded:,}/{len(to_migrate):,} subido(s)...")
    finally:
        if new_rows:
            manifest_df = _checkpoint(manifest_df, new_rows, bucket)

    print(
        f"\nListo. {uploaded:,} archivo(s) nuevo(s) migrado(s) a s3://{bucket}/{S3_PREFIX}/library/ "
        f"· {missing_local:,} omitido(s) (no encontrado(s) en este equipo) "
        f"· {failed:,} con error "
        f"· manifiesto: s3://{bucket}/{MANIFEST_KEY} ({len(manifest_df):,} fila(s) en total)."
    )
    print("En el servidor: 'Fuentes multimedia' -> la fuente '☁️ Librería en S3' -> '🔄 Sincronizar desde S3'.")


if __name__ == "__main__":
    main()
