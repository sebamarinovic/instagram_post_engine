import argparse
import math
import os
import subprocess
from datetime import datetime
from pathlib import Path

import cv2
import imagehash
import numpy as np
import pandas as pd
from PIL import Image, ExifTags, ImageOps
from pillow_heif import register_heif_opener

from config import MEDIA_INDEX_CSV, THUMB_DIR

register_heif_opener()

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".heic", ".heif", ".webp", ".tif", ".tiff"}
VIDEO_EXTS = {".mp4", ".mov", ".m4v", ".avi", ".mkv", ".3gp"}

GPS_TAG = next((k for k,v in ExifTags.TAGS.items() if v == "GPSInfo"), 34853)
DT_TAGS = [
    next((k for k,v in ExifTags.TAGS.items() if v == "DateTimeOriginal"), 36867),
    next((k for k,v in ExifTags.TAGS.items() if v == "DateTimeDigitized"), 36868),
    next((k for k,v in ExifTags.TAGS.items() if v == "DateTime"), 306),
]

def ratio_to_float(x):
    try:
        return float(x)
    except Exception:
        try:
            return x[0] / x[1]
        except Exception:
            return None

def dms_to_decimal(values, ref):
    try:
        d = ratio_to_float(values[0]); m = ratio_to_float(values[1]); s = ratio_to_float(values[2])
        if None in (d,m,s): return None
        out = d + m/60 + s/3600
        if ref in ("S","W"): out *= -1
        return out
    except Exception:
        return None

def parse_exif_datetime(exif):
    for tag in DT_TAGS:
        val = exif.get(tag)
        if val:
            try:
                return datetime.strptime(str(val), "%Y:%m:%d %H:%M:%S")
            except Exception:
                pass
    return None

def extract_gps(exif):
    try:
        gps = exif.get_ifd(GPS_TAG)
        lat = dms_to_decimal(gps.get(2), gps.get(1))
        lon = dms_to_decimal(gps.get(4), gps.get(3))
        return lat, lon
    except Exception:
        return None, None

def image_metrics(path):
    row = {}
    try:
        with Image.open(path) as im:
            im = ImageOps.exif_transpose(im)
            row["width"], row["height"] = im.size
            exif = im.getexif()
            dt = parse_exif_datetime(exif)
            lat, lon = extract_gps(exif)
            row["captured_at"] = dt.isoformat(sep=" ") if dt else None
            row["lat"], row["lon"] = lat, lon

            rgb = im.convert("RGB")
            thumb = rgb.copy()
            thumb.thumbnail((1600, 1600))

            arr = np.array(thumb)
            gray = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)
            row["sharpness"] = float(cv2.Laplacian(gray, cv2.CV_64F).var())
            row["brightness"] = float(gray.mean())
            row["phash"] = str(imagehash.phash(rgb.resize((min(rgb.width, 1024), min(rgb.height, 1024)))))

            # simple quality score: resolution + sharpness + sane exposure
            mp = (rgb.width * rgb.height) / 1_000_000
            exposure_penalty = abs(row["brightness"] - 127) / 127
            row["quality_score"] = (
                min(mp / 12, 1.0) * 40
                + min(math.log1p(row["sharpness"]) / 8, 1.0) * 45
                + max(0, 1 - exposure_penalty) * 15
            )

            out = THUMB_DIR / (path.stem + "_" + str(abs(hash(str(path))))[-8:] + ".jpg")
            if not out.exists():
                t = rgb.copy()
                t.thumbnail((640, 640))
                t.save(out, "JPEG", quality=84)
            row["thumb_path"] = str(out)
            row["available_local"] = True
            return row
    except Exception as e:
        row.update({
            "width": None, "height": None, "captured_at": None,
            "lat": None, "lon": None, "sharpness": None,
            "brightness": None, "phash": None, "quality_score": 0,
            "thumb_path": None, "available_local": False,
            "error": str(e)[:300],
        })
        return row

def video_probe(path):
    row = {
        "width": None, "height": None, "duration_s": None,
        "captured_at": None, "lat": None, "lon": None,
        "sharpness": None, "brightness": None, "phash": None,
        "quality_score": 35.0, "thumb_path": None,
        "available_local": True
    }
    try:
        cmd = [
            "ffprobe", "-v", "error",
            "-select_streams", "v:0",
            "-show_entries", "stream=width,height:format=duration:format_tags=creation_time",
            "-of", "default=noprint_wrappers=1",
            str(path)
        ]
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        vals = {}
        for line in p.stdout.splitlines():
            if "=" in line:
                k,v = line.split("=",1); vals[k.strip()] = v.strip()
        row["width"] = int(vals["width"]) if vals.get("width") else None
        row["height"] = int(vals["height"]) if vals.get("height") else None
        row["duration_s"] = float(vals["duration"]) if vals.get("duration") else None
        if vals.get("TAG:creation_time"):
            row["captured_at"] = vals["TAG:creation_time"].replace("T"," ").replace("Z","")
        # thumbnail
        out = THUMB_DIR / (path.stem + "_" + str(abs(hash(str(path))))[-8:] + "_v.jpg")
        if not out.exists():
            cmd2 = ["ffmpeg","-y","-ss","1","-i",str(path),"-frames:v","1","-vf","scale=640:-2",str(out)]
            subprocess.run(cmd2, capture_output=True, timeout=60)
        if out.exists():
            row["thumb_path"] = str(out)
        return row
    except Exception as e:
        row["available_local"] = False
        row["error"] = "ffprobe/ffmpeg no disponible o video no descargado: " + str(e)[:200]
        return row

def find_media_files(root):
    root = Path(root)
    return [p for p in root.rglob("*") if p.is_file() and p.suffix.lower() in (IMAGE_EXTS | VIDEO_EXTS)]

def build_index(paths, source_id=None, source_name=None, source_path=None):
    rows = []
    for i,p in enumerate(paths,1):
        ext = p.suffix.lower()
        base = {
            "path": str(p),
            "filename": p.name,
            "ext": ext,
            "media_type": "image" if ext in IMAGE_EXTS else "video",
            "size_mb": round(p.stat().st_size / 1024 / 1024, 3),
            "filesystem_mtime": datetime.fromtimestamp(p.stat().st_mtime).isoformat(sep=" "),
            "source_id": source_id,
            "source_name": source_name,
            "source_path": source_path,
        }
        meta = image_metrics(p) if ext in IMAGE_EXTS else video_probe(p)
        base.update(meta)
        if not base.get("captured_at"):
            base["captured_at"] = base["filesystem_mtime"]
        rows.append(base)
        if i % 250 == 0:
            print(f"{i:,}/{len(paths):,}")
    return pd.DataFrame(rows)

def load_index():
    if MEDIA_INDEX_CSV.exists():
        return pd.read_csv(MEDIA_INDEX_CSV)
    return pd.DataFrame()

def merge_source_into_index(df_new, source_id, replace):
    """Merge a freshly scanned source into the on-disk index.

    replace=True drops any previous rows for this source_id before adding
    df_new (a full rescan). replace=False only guards against re-adding a
    path that's already indexed (used for incremental "new files" scans,
    where df_new is expected to already exclude known paths).
    """
    existing = load_index()
    if existing.empty:
        merged = df_new
    else:
        if replace and "source_id" in existing.columns:
            existing = existing[existing["source_id"] != source_id]
        if not replace:
            known_paths = set(existing["path"].astype(str))
            df_new = df_new[~df_new["path"].astype(str).isin(known_paths)]
        merged = pd.concat([existing, df_new], ignore_index=True)
    merged.to_csv(MEDIA_INDEX_CSV, index=False)
    return merged

def scan(root):
    """CLI entry point: full scan of one folder, overwrites the whole index."""
    paths = find_media_files(root)
    print(f"Encontrados {len(paths):,} archivos multimedia.")
    df = build_index(paths, source_path=str(Path(root)))
    df.to_csv(MEDIA_INDEX_CSV, index=False)
    print(f"Índice guardado en {MEDIA_INDEX_CSV}")
    return df

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True, help="Carpeta raíz de Fotos en iCloud ya descargadas")
    args = ap.parse_args()
    scan(args.root)
