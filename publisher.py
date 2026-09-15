import hashlib
import mimetypes
import os
import time
from datetime import datetime, timezone
from pathlib import Path
import boto3
import requests
from dotenv import load_dotenv

from s3_library import is_s3_uri, presigned_url

load_dotenv()
BASE = "https://graph.instagram.com"

def _is_dry_run():
    return os.getenv("DRY_RUN", "false").strip().lower() in {"1", "true", "yes", "y"}

DRY_RUN = _is_dry_run()

def config_status():
    return {
        "INSTAGRAM_ACCESS_TOKEN": bool(os.getenv("INSTAGRAM_ACCESS_TOKEN")),
        "INSTAGRAM_USER_ID": bool(os.getenv("INSTAGRAM_USER_ID")),
        "S3_BUCKET": bool(os.getenv("S3_BUCKET")),
    }

def _token():
    v=os.getenv("INSTAGRAM_ACCESS_TOKEN")
    if not v: raise RuntimeError("Falta INSTAGRAM_ACCESS_TOKEN")
    return v

def _ig_id():
    v=os.getenv("INSTAGRAM_USER_ID")
    if not v: raise RuntimeError("Falta INSTAGRAM_USER_ID")
    return v

def _bucket():
    v=os.getenv("S3_BUCKET")
    if not v: raise RuntimeError("Falta S3_BUCKET")
    return v

def upload_and_presign(path, expires=7200):
    if is_s3_uri(path):
        # Already migrated to S3 (Etapa Cloud D) — sign the existing
        # object instead of downloading it just to re-upload it.
        return presigned_url(path, expires=expires)
    path=Path(path)
    prefix=os.getenv("S3_PREFIX","instagram-rebuild").strip("/")
    key=f"{prefix}/{int(time.time())}_{path.name}"
    ctype=mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    s3=boto3.client("s3")
    s3.upload_file(str(path), _bucket(), key, ExtraArgs={"ContentType":ctype})
    return s3.generate_presigned_url("get_object", Params={"Bucket":_bucket(),"Key":key}, ExpiresIn=expires)

def _post(endpoint,data):
    r=requests.post(endpoint,data=data,timeout=90)
    if not r.ok:
        raise RuntimeError(f"Instagram API {r.status_code}: {r.text}")
    return r.json()

def fetch_permalink(media_id):
    """Best-effort lookup of the public URL for a just-published media_id.
    media_publish only returns the id, not the permalink — a separate call
    is needed, and it's not critical enough to fail the publish over."""
    if not media_id:
        return None
    try:
        r = requests.get(
            f"{BASE}/{media_id}",
            params={"fields": "permalink", "access_token": _token()},
            timeout=30,
        )
        return r.json().get("permalink") if r.ok else None
    except Exception:
        return None

def publish_single(local_path, caption):
    url=upload_and_presign(local_path)
    cid=_post(f"{BASE}/{_ig_id()}/media",{"image_url":url,"caption":caption,"access_token":_token()})["id"]
    time.sleep(2)
    result = _post(f"{BASE}/{_ig_id()}/media_publish",{"creation_id":cid,"access_token":_token()})
    result["permalink"] = fetch_permalink(result.get("id"))
    return result

def publish_carousel(local_paths, caption):
    if not 2 <= len(local_paths) <= 10:
        raise ValueError("Carrusel: entre 2 y 10 imágenes.")
    children=[]
    for p in local_paths:
        url=upload_and_presign(p)
        cid=_post(f"{BASE}/{_ig_id()}/media",{"image_url":url,"is_carousel_item":"true","access_token":_token()})["id"]
        children.append(cid)
    time.sleep(3)
    parent=_post(
        f"{BASE}/{_ig_id()}/media",
        {"media_type":"CAROUSEL","children":",".join(children),"caption":caption,"access_token":_token()}
    )["id"]
    time.sleep(3)
    result = _post(f"{BASE}/{_ig_id()}/media_publish",{"creation_id":parent,"access_token":_token()})
    result["permalink"] = fetch_permalink(result.get("id"))
    return result

def _simulate_publish(local_paths, caption):
    fingerprint = hashlib.md5((caption + "".join(local_paths)).encode("utf-8")).hexdigest()[:10]
    return {
        "dry_run": True,
        "id": f"DRYRUN-{fingerprint}",
        "media_type": "CAROUSEL" if len(local_paths) > 1 else "IMAGE",
        "children": len(local_paths),
        "note": "Simulado — DRY_RUN activo, no se llamó a la API de Instagram ni se subió nada a S3.",
        "simulated_at": datetime.now(timezone.utc).isoformat(),
    }

def publish_images(local_paths, caption):
    if _is_dry_run():
        return _simulate_publish(local_paths, caption)
    if len(local_paths)==1:
        return publish_single(local_paths[0],caption)
    return publish_carousel(local_paths,caption)
