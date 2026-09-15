"""Shared S3 helpers for the bulk-migrated photo/video library (Etapa Cloud D).

Media that lives in S3 is identified by an "s3://bucket/key" string used
wherever the rest of the app expects a local file path (the `path` and
`thumb_path` columns of the media index). Two things build on that:
  - `presigned_url` turns such a URI into a temporary HTTPS link a browser
    (or Instagram's fetcher) can load directly — used for thumbnails and,
    in publisher.py, for publishing without a redundant download+reupload.
  - `sync_manifest_source` pulls the manifest CSV that `migrate_to_s3.py`
    maintains in the bucket into the local media index, the same way a
    filesystem scan would for a local folder.
"""
import io
from urllib.parse import urlparse

import boto3
import pandas as pd
from botocore.exceptions import ClientError

from scan_media import merge_source_into_index

S3_SCHEME = "s3://"
MANIFEST_KEY = "manifest/s3_library.csv"


def is_s3_uri(value):
    return isinstance(value, str) and value.startswith(S3_SCHEME)


def parse_s3_uri(uri):
    parsed = urlparse(uri)
    return parsed.netloc, parsed.path.lstrip("/")


def make_s3_uri(bucket, key):
    return f"{S3_SCHEME}{bucket}/{key}"


def presigned_url(value, expires=3600):
    """s3://bucket/key -> temporary HTTPS URL. Anything else (a local path,
    None, NaN) is returned unchanged, so callers can pass either kind of
    value through the same code path without checking first."""
    if not is_s3_uri(value):
        return value
    bucket, key = parse_s3_uri(value)
    s3 = boto3.client("s3")
    return s3.generate_presigned_url("get_object", Params={"Bucket": bucket, "Key": key}, ExpiresIn=expires)


def upload_file(local_path, bucket, key):
    import mimetypes
    ctype = mimetypes.guess_type(str(local_path))[0] or "application/octet-stream"
    s3 = boto3.client("s3")
    s3.upload_file(str(local_path), bucket, key, ExtraArgs={"ContentType": ctype})


def download_manifest(bucket, manifest_key=MANIFEST_KEY):
    s3 = boto3.client("s3")
    try:
        obj = s3.get_object(Bucket=bucket, Key=manifest_key)
    except ClientError as e:
        if e.response.get("Error", {}).get("Code") in ("NoSuchKey", "404"):
            return pd.DataFrame()
        raise
    return pd.read_csv(io.BytesIO(obj["Body"].read()))


def upload_manifest(df, bucket, manifest_key=MANIFEST_KEY):
    s3 = boto3.client("s3")
    buf = io.StringIO()
    df.to_csv(buf, index=False)
    s3.put_object(Bucket=bucket, Key=manifest_key, Body=buf.getvalue().encode("utf-8"), ContentType="text/csv")


def sync_manifest_source(source_id, source_name, bucket, manifest_key=MANIFEST_KEY):
    """Pull the current S3 library manifest into the local media index.
    This is the deployed app's equivalent of a filesystem scan for an S3
    source: it never touches original files or thumbnails directly, just
    the small manifest — those are fetched on demand via presigned URLs."""
    df = download_manifest(bucket, manifest_key)
    if df.empty:
        return 0
    merge_source_into_index(df, source_id, replace=True)
    return len(df)
