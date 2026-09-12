"""Heuristics for narrowing an oversized selection down to Instagram's
carousel limit, instead of just keeping the first N picked."""

def _phash_distance(a, b):
    if not a or not b:
        return None
    try:
        return bin(int(str(a), 16) ^ int(str(b), 16)).count("1")
    except Exception:
        return None

def _quality(row):
    try:
        return float(row.get("quality_score") or 0)
    except Exception:
        return 0.0

def _is_near_duplicate(phash, other_phash, threshold):
    dist = _phash_distance(phash, other_phash)
    return dist is not None and dist <= threshold

def _cluster_near_duplicates(rows, threshold):
    """Group rows whose phash differs by at most `threshold` bits — near
    duplicates such as burst shots or the same photo re-exported twice."""
    clusters = []
    for row in rows:
        phash = row.get("phash")
        match = next(
            (c for c in clusters if any(_is_near_duplicate(phash, o.get("phash"), threshold) for o in c)),
            None,
        )
        if match is not None:
            match.append(row)
        else:
            clusters.append([row])
    return clusters

def _bucket_key(row):
    country = row.get("country") or "?"
    city = row.get("city") or "?"
    day = str(row.get("captured_at") or "")[:10]
    return (country, city, day)

def pick_best(rows, limit=10, phash_threshold=6):
    """Narrow a list of media rows (dicts) down to at most `limit` items.

    1. Collapses visually near-duplicate shots (by phash), keeping only the
       highest quality_score copy of each.
    2. Spreads the remaining picks across (country, city, day) buckets in a
       round-robin, so a single burst or single day/place can't crowd out
       the rest of the story — instead of just taking the top-N by score.

    Returns (kept, discarded): `kept` may hold fewer than `limit` items if
    dedup already shrank the pool below it (that's fine — quality over
    hitting the number). Each discarded row carries a "_reason" string.
    """
    if len(rows) <= limit:
        return list(rows), []

    discarded = []
    clusters = _cluster_near_duplicates(rows, phash_threshold)
    representatives = []
    for cluster in clusters:
        cluster.sort(key=_quality, reverse=True)
        representatives.append(cluster[0])
        for extra in cluster[1:]:
            discarded.append({**extra, "_reason": f"Muy similar a {cluster[0].get('filename')}"})

    if len(representatives) <= limit:
        return representatives, discarded

    buckets = {}
    for row in representatives:
        buckets.setdefault(_bucket_key(row), []).append(row)
    for bucket in buckets.values():
        bucket.sort(key=_quality, reverse=True)

    bucket_keys = list(buckets.keys())
    kept = []
    i = 0
    while len(kept) < limit and any(buckets.values()):
        bucket = buckets[bucket_keys[i % len(bucket_keys)]]
        if bucket:
            kept.append(bucket.pop(0))
        i += 1

    for bucket in buckets.values():
        for row in bucket:
            discarded.append({**row, "_reason": "Se priorizó diversidad de fecha/lugar"})

    return kept, discarded
