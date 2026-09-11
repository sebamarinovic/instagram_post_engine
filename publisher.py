import mimetypes
import os
import time
from pathlib import Path

import boto3
import requests
from dotenv import load_dotenv

load_dotenv()

BASE = "https://graph.instagram.com"

def ig_token():
    t = os.getenv("INSTAGRAM_ACCESS_TOKEN")
    if not t: raise RuntimeError("Falta INSTAGRAM_ACCESS_TOKEN")
    return t

def ig_id():
    x = os.getenv("INSTAGRAM_USER_ID")
    if not x: raise RuntimeError("Falta INSTAGRAM_USER_ID")
    return x

def s3_client():
    return boto3.client("s3")

def upload_and_presign(path, expires=7200):
    bucket = os.getenv("S3_BUCKET")
    if not bucket: raise RuntimeError("Falta S3_BUCKET")
    prefix = os.getenv("S3_PREFIX", "instagram-rebuild").strip("/")
    path = Path(path)
    key = f"{prefix}/{int(time.time())}_{path.name}"
    ctype = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    s3 = s3_client()
    s3.upload_file(str(path), bucket, key, ExtraArgs={"ContentType": ctype})
    return s3.generate_presigned_url(
        "get_object",
        Params={"Bucket": bucket, "Key": key},
        ExpiresIn=expires
    )

def create_image_container(image_url, caption=None, is_carousel_item=False):
    data = {
        "image_url": image_url,
        "access_token": ig_token(),
    }
    if caption is not None:
        data["caption"] = caption
    if is_carousel_item:
        data["is_carousel_item"] = "true"
    r = requests.post(f"{BASE}/{ig_id()}/media", data=data, timeout=60)
    r.raise_for_status()
    return r.json()["id"]

def publish_container(creation_id):
    r = requests.post(
        f"{BASE}/{ig_id()}/media_publish",
        data={"creation_id": creation_id, "access_token": ig_token()},
        timeout=60
    )
    r.raise_for_status()
    return r.json()

def publish_single(local_path, caption):
    url = upload_and_presign(local_path)
    cid = create_image_container(url, caption=caption)
    return publish_container(cid)

def publish_carousel(local_paths, caption):
    if not 2 <= len(local_paths) <= 10:
        raise ValueError("Carrusel: usa entre 2 y 10 imágenes.")
    child_ids = []
    for p in local_paths:
        url = upload_and_presign(p)
        child_ids.append(create_image_container(url, is_carousel_item=True))

    data = {
        "media_type": "CAROUSEL",
        "children": ",".join(child_ids),
        "caption": caption,
        "access_token": ig_token()
    }
    r = requests.post(f"{BASE}/{ig_id()}/media", data=data, timeout=60)
    r.raise_for_status()
    parent = r.json()["id"]
    return publish_container(parent)
