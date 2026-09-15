"""Auto-detect which library photos were already posted to the real
Instagram account, so old posts (made before this app existed, or from
outside it) don't need to be registered by hand one at a time.

Downloads the account's existing media via the Graph API, computes a
perceptual hash for each posted photo the same way scan_media.py does
for the library, and matches it against media_geo.csv's phash column
(the enriched index — country/city/year only live there, not in the
raw media_index.csv). Instagram recompresses/resizes on upload, so an
exact content_hash never matches an original file — the visual hash
still does, within a margin.
"""
import io
import os

import imagehash
import pandas as pd
import requests
from PIL import Image

from curation import _phash_distance
from publication_history import record_existing_publication
from config import MEDIA_GEO_CSV

BASE = "https://graph.instagram.com"
# Looser than curation.py's near-duplicate threshold (6): that one compares
# two local files with minimal transformation (burst shots), this compares
# a local file against Instagram's recompressed/resized/cropped copy of it.
PHASH_THRESHOLD = 10


def _token():
    v = os.getenv("INSTAGRAM_ACCESS_TOKEN")
    if not v:
        raise RuntimeError("Falta INSTAGRAM_ACCESS_TOKEN")
    return v


def _ig_id():
    v = os.getenv("INSTAGRAM_USER_ID")
    if not v:
        raise RuntimeError("Falta INSTAGRAM_USER_ID")
    return v


def _phash_of_url(url):
    r = requests.get(url, timeout=30)
    r.raise_for_status()
    im = Image.open(io.BytesIO(r.content)).convert("RGB")
    return str(imagehash.phash(im.resize((min(im.width, 1024), min(im.height, 1024)))))


def _fetch_media_items():
    """Every real photo posted to the account, flattening carousels into
    their individual images. Videos are skipped — nothing to phash-match
    a frame against."""
    items = []
    url = f"{BASE}/{_ig_id()}/media"
    params = {
        "fields": "id,media_type,permalink,children{media_type,media_url}",
        "access_token": _token(),
        "limit": 50,
    }
    while url:
        r = requests.get(url, params=params, timeout=30)
        r.raise_for_status()
        data = r.json()
        for item in data.get("data", []):
            permalink = item.get("permalink")
            if item.get("media_type") == "CAROUSEL_ALBUM":
                for child in item.get("children", {}).get("data", []):
                    if child.get("media_type") == "IMAGE" and child.get("media_url"):
                        items.append({"permalink": permalink, "media_url": child["media_url"]})
            elif item.get("media_type") == "IMAGE" and item.get("media_url"):
                items.append({"permalink": permalink, "media_url": item["media_url"]})
        params = {}  # paging["next"] already carries every query param
        url = data.get("paging", {}).get("next")
    return items


def import_existing_publications(progress=None):
    """Match each real Instagram photo against the local library by phash
    and record any match as an existing publication (skips ones already
    recorded — record_existing_publication is a no-op for known keys).
    Returns a stats dict, or {"error": "..."} if nothing could run."""
    if not MEDIA_GEO_CSV.exists():
        return {"error": f"Falta {MEDIA_GEO_CSV} — corre 'Recalcular ubicación' primero."}
    index = pd.read_csv(MEDIA_GEO_CSV)
    if index.empty or "phash" not in index.columns:
        return {"error": "El índice local está vacío o no tiene phash — escanea tus fuentes primero."}

    cols = [c for c in ("path", "content_hash", "phash", "filename", "country", "city", "year") if c in index.columns]
    local = index[index["phash"].notna()][cols].to_dict("records")
    if not local:
        return {"error": "No hay fotos con phash calculado en el índice local todavía."}

    items = _fetch_media_items()
    matched_posts, matched_count = set(), 0
    for i, item in enumerate(items, start=1):
        if progress:
            progress(i, len(items))
        try:
            remote_phash = _phash_of_url(item["media_url"])
        except Exception:
            continue
        best = None
        for row in local:
            dist = _phash_distance(remote_phash, row.get("phash"))
            if dist is not None and dist <= PHASH_THRESHOLD and (best is None or dist < best[0]):
                best = (dist, row)
        if best:
            record_existing_publication(
                [best[1]], item["permalink"],
                note="Publicación existente importada automáticamente",
            )
            matched_count += 1
            matched_posts.add(item["permalink"])

    return {"matched": matched_count, "checked": len(items), "posts": len(matched_posts)}
