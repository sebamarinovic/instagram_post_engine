"""CLI to scan (or incrementally rescan) one media-source folder, saving
progress in small batches instead of one big all-or-nothing pass — safe
to interrupt (laptop sleep, closed terminal, crash) and resume, which
matters once a folder has tens of thousands of files and a full scan can
run for hours. Unlike the inline one-liner used for small folders, this
never loses more than one batch's worth of work.

Usage:
    python scan_source.py --path "C:\\Users\\me\\iCloudPhotos\\Photos" --name "iCloud completo"

Re-running the same command later only processes files it hasn't seen
yet for that source (new since last run, or already in progress when it
was interrupted) — everything already indexed is left untouched.
"""
import argparse

import media_sources as ms
from scan_media import find_media_files, build_index, merge_source_into_index, load_index

BATCH_SIZE = 200


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--path", required=True)
    ap.add_argument("--name", required=True)
    args = ap.parse_args()

    source_id = None
    for s in ms.list_sources():
        if s.get("path") == args.path:
            source_id = s["id"]
            break
    if source_id is None:
        source_id = ms.add_source(args.name, args.path)

    print("Buscando archivos en la carpeta...")
    on_disk = find_media_files(args.path)

    existing = load_index()
    known_paths = set()
    if not existing.empty and "source_id" in existing.columns:
        known_paths = set(existing[existing["source_id"] == source_id]["path"].astype(str))

    pending = [p for p in on_disk if str(p) not in known_paths]
    print(
        f"{len(on_disk):,} archivo(s) en la carpeta · {len(known_paths):,} ya indexado(s) "
        f"· {len(pending):,} por procesar ahora."
    )
    if not pending:
        print("Nada nuevo para procesar.")
        return

    processed = 0
    for i in range(0, len(pending), BATCH_SIZE):
        batch = pending[i:i + BATCH_SIZE]
        df = build_index(batch, source_id, args.name, args.path)
        merge_source_into_index(df, source_id, replace=False)
        processed += len(batch)
        ms.update_scan_stats(source_id, len(known_paths) + processed)
        print(f"{processed:,}/{len(pending):,} procesado(s) en esta corrida (guardado).")

    print("Listo.")


if __name__ == "__main__":
    main()
