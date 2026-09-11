import argparse
from math import radians, sin, cos, asin, sqrt
from pathlib import Path

import pandas as pd
import reverse_geocoder as rg

from config import MEDIA_CSV, EXPERIENCES_CSV

def haversine(lat1, lon1, lat2, lon2):
    try:
        lon1, lat1, lon2, lat2 = map(radians, [float(lon1), float(lat1), float(lon2), float(lat2)])
    except Exception:
        return None
    dlon = lon2-lon1; dlat = lat2-lat1
    a = sin(dlat/2)**2 + cos(lat1)*cos(lat2)*sin(dlon/2)**2
    return 6371 * 2 * asin(sqrt(a))

def city_country(lat, lon):
    if pd.isna(lat) or pd.isna(lon):
        return None, None
    try:
        x = rg.search([(float(lat), float(lon))], mode=1)[0]
        return x.get("name"), x.get("cc")
    except Exception:
        return None, None

def cluster(max_gap_hours=72, jump_km=600):
    df = pd.read_csv(MEDIA_CSV)
    df["captured_at"] = pd.to_datetime(df["captured_at"], errors="coerce", utc=True)
    df = df[df["captured_at"].notna()].sort_values("captured_at").reset_index(drop=True)

    exp = 1
    ids = [exp]
    for i in range(1, len(df)):
        prev, cur = df.iloc[i-1], df.iloc[i]
        gap_h = (cur["captured_at"] - prev["captured_at"]).total_seconds()/3600
        dist = None
        if pd.notna(prev.get("lat")) and pd.notna(cur.get("lat")):
            dist = haversine(prev["lat"], prev["lon"], cur["lat"], cur["lon"])

        new_exp = gap_h > max_gap_hours
        if dist is not None and dist > jump_km and gap_h > 1:
            new_exp = True

        if new_exp:
            exp += 1
        ids.append(exp)

    df["experience_id"] = ids

    # candidates: quality + diversity. Keep top 30 per experience.
    summaries = []
    for eid,g in df.groupby("experience_id"):
        start, end = g["captured_at"].min(), g["captured_at"].max()
        lat = g["lat"].dropna().median() if "lat" in g else None
        lon = g["lon"].dropna().median() if "lon" in g else None
        city, cc = city_country(lat, lon) if pd.notna(lat) and pd.notna(lon) else (None,None)

        gg = g.copy()
        gg["quality_score"] = pd.to_numeric(gg["quality_score"], errors="coerce").fillna(0)
        top = gg.sort_values(["quality_score","size_mb"], ascending=False).head(30)

        summaries.append({
            "experience_id": int(eid),
            "start": start,
            "end": end,
            "days": max(1, (end-start).days+1),
            "items": len(g),
            "images": int((g["media_type"]=="image").sum()),
            "videos": int((g["media_type"]=="video").sum()),
            "lat": lat, "lon": lon,
            "city": city, "country_code": cc,
            "candidate_paths": "|||".join(top["path"].astype(str)),
            "candidate_thumbs": "|||".join(top["thumb_path"].dropna().astype(str)),
        })

    out = pd.DataFrame(summaries)
    out.to_csv(EXPERIENCES_CSV, index=False)
    df.to_csv(MEDIA_CSV, index=False)
    print(f"Experiencias: {len(out):,}")
    print(f"Guardado en {EXPERIENCES_CSV}")

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-gap-hours", type=int, default=72)
    ap.add_argument("--jump-km", type=int, default=600)
    args = ap.parse_args()
    cluster(args.max_gap_hours, args.jump_km)
