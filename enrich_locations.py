import argparse
import pandas as pd
import reverse_geocoder as rg

COUNTRY_NAMES = {
    "CL":"Chile","HR":"Croacia","JP":"Japón","EG":"Egipto","TR":"Turquía","BR":"Brasil",
    "BO":"Bolivia","AR":"Argentina","PE":"Perú","US":"Estados Unidos","MX":"México",
    "ES":"España","FR":"Francia","IT":"Italia","DE":"Alemania","NL":"Países Bajos",
    "GB":"Reino Unido","PT":"Portugal","GR":"Grecia","CZ":"Chequia","AT":"Austria",
    "HU":"Hungría","TH":"Tailandia","ID":"Indonesia","AU":"Australia","NZ":"Nueva Zelanda",
    "FJ":"Fiyi","TO":"Tonga","PF":"Polinesia Francesa","AE":"Emiratos Árabes Unidos"
}

def main(csv_path, out_path, infer_hours=12):
    df = pd.read_csv(csv_path)
    df["captured_at"] = pd.to_datetime(df["captured_at"], errors="coerce")
    df["filesystem_mtime"] = pd.to_datetime(df.get("filesystem_mtime"), errors="coerce")

    delta = (df["captured_at"] - df["filesystem_mtime"]).abs().dt.total_seconds()
    df["date_source"] = "original_or_video"
    df.loc[delta.fillna(999999) <= 2, "date_source"] = "filesystem_fallback"
    df["year"] = df["captured_at"].dt.year

    df["lat_r"] = pd.to_numeric(df["lat"], errors="coerce").round(4)
    df["lon_r"] = pd.to_numeric(df["lon"], errors="coerce").round(4)
    gps_mask = df[["lat_r","lon_r"]].notna().all(axis=1)

    df["country_code"] = None
    df["country"] = None
    df["city"] = None
    df["admin1"] = None
    df["location_source"] = "none"

    coords = df.loc[gps_mask, ["lat_r","lon_r"]].drop_duplicates()
    if len(coords):
        pts = list(zip(coords["lat_r"].astype(float), coords["lon_r"].astype(float)))
        results = rg.search(pts, mode=1)
        mapping = {}
        for (lat,lon), r in zip(pts, results):
            cc = r.get("cc")
            mapping[(lat,lon)] = {
                "country_code": cc,
                "country": COUNTRY_NAMES.get(cc, cc),
                "city": r.get("name"),
                "admin1": r.get("admin1"),
            }
        for idx,row in df.loc[gps_mask].iterrows():
            rec = mapping[(float(row.lat_r), float(row.lon_r))]
            for k,v in rec.items():
                df.at[idx,k] = v
            df.at[idx,"location_source"] = "gps"

    exact = df[(df["location_source"]=="gps") & df["captured_at"].notna()].sort_values("captured_at")
    missing = df[(df["location_source"]=="none") & df["captured_at"].notna()].index

    for idx in missing:
        t = df.at[idx,"captured_at"]
        window = exact[
            (exact["captured_at"] >= t - pd.Timedelta(hours=infer_hours)) &
            (exact["captured_at"] <= t + pd.Timedelta(hours=infer_hours))
        ]
        if len(window) < 2:
            continue
        countries = window["country_code"].dropna().unique()
        if len(countries) != 1:
            continue
        nearest_idx = (window["captured_at"] - t).abs().idxmin()
        nearest = window.loc[nearest_idx]
        for k in ["country_code","country","city","admin1"]:
            df.at[idx,k] = nearest[k]
        df.at[idx,"location_source"] = "time_inferred"

    df.drop(columns=["lat_r","lon_r"], inplace=True)
    df.to_csv(out_path, index=False)

    print(f"TOTAL: {len(df)}")
    print(f"GPS exacto: {(df.location_source=='gps').sum()}")
    print(f"Ubicacion inferida: {(df.location_source=='time_inferred').sum()}")
    print(f"Sin ubicacion: {(df.location_source=='none').sum()}")
    print(f"Fecha original/video probable: {(df.date_source=='original_or_video').sum()}")
    print(f"Fecha fallback Windows: {(df.date_source=='filesystem_fallback').sum()}")
    print("\nPaises detectados:")
    print(df[df.country.notna()].groupby(["country_code","country"]).size().sort_values(ascending=False).to_string())

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default="data/media_index.csv")
    ap.add_argument("--output", default="data/media_geo.csv")
    ap.add_argument("--infer-hours", type=int, default=12)
    args = ap.parse_args()
    main(args.input, args.output, args.infer_hours)
