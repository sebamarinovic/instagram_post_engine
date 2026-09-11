from pathlib import Path
import pandas as pd
import streamlit as st

st.set_page_config(page_title="Instagram Rebuild Geo", layout="wide")
st.title("🌎 Instagram Rebuild — Explorar por país")
st.caption("Fuente histórica: álbumes de Instagram · GPS exacto e inferencias conservadoras")

CSV = Path("data/media_geo.csv")
if not CSV.exists():
    st.warning("Ejecuta primero: python enrich_locations.py")
    st.stop()

df = pd.read_csv(CSV)
df["captured_at"] = pd.to_datetime(df["captured_at"], errors="coerce")
df["quality_score"] = pd.to_numeric(df["quality_score"], errors="coerce").fillna(0)

st.sidebar.header("🔎 Filtros")

country_opts = ["Todos"] + sorted(df["country"].dropna().unique().tolist())
country = st.sidebar.selectbox("🌎 País", country_opts)
work = df.copy()
if country != "Todos":
    work = work[work.country == country]

city_opts = ["Todas"] + sorted(work["city"].dropna().unique().tolist())
city = st.sidebar.selectbox("📍 Ciudad", city_opts)
if city != "Todas":
    work = work[work.city == city]

years = sorted([int(x) for x in work["year"].dropna().unique()])
year = st.sidebar.selectbox("📅 Año", ["Todos"] + years)
if year != "Todos":
    work = work[work.year == year]

media_type = st.sidebar.selectbox("🎞️ Tipo", ["Todos","image","video"])
if media_type != "Todos":
    work = work[work.media_type == media_type]

loc_mode = st.sidebar.multiselect(
    "🧭 Fuente de ubicación",
    ["gps","time_inferred","none"],
    default=["gps","time_inferred"]
)
work = work[work.location_source.isin(loc_mode)]

date_mode = st.sidebar.multiselect(
    "🕒 Fuente de fecha",
    ["original_or_video","filesystem_fallback"],
    default=["original_or_video"]
)
work = work[work.date_source.isin(date_mode)]

c1,c2,c3,c4 = st.columns(4)
c1.metric("Elementos", len(work))
c2.metric("📸 Fotos", int((work.media_type=="image").sum()))
c3.metric("🎬 Videos", int((work.media_type=="video").sum()))
c4.metric("📍 GPS exacto", int((work.location_source=="gps").sum()))

if len(work) == 0:
    st.info("No hay elementos con estos filtros.")
    st.stop()

st.subheader("🗺️ Lugares")
summary = (
    work.groupby(["country","city"], dropna=False)
        .size()
        .reset_index(name="elementos")
        .sort_values("elementos", ascending=False)
)
st.dataframe(summary, use_container_width=True, hide_index=True)

st.subheader("🖼️ Mejores candidatos")
top = work.sort_values("quality_score", ascending=False).head(60)
cols = st.columns(5)

for i,(_,r) in enumerate(top.iterrows()):
    with cols[i % 5]:
        thumb = r.get("thumb_path")
        if isinstance(thumb,str) and Path(thumb).exists():
            st.image(thumb, use_container_width=True)
        else:
            st.write("🎬" if r.media_type=="video" else "📷")
        date_txt = "" if pd.isna(r.captured_at) else r.captured_at.strftime("%Y-%m-%d")
        city = "" if pd.isna(r.get("city")) else str(r.get("city"))
        country = "" if pd.isna(r.get("country")) else str(r.get("country"))
        loc = " · ".join([x for x in [city,country] if x])
        badge = "📍" if r.location_source=="gps" else ("🧭" if r.location_source=="time_inferred" else "❔")
        st.caption(f"{badge} {loc or 'sin ubicación'}\n\n📅 {date_txt}\n⭐ {r.quality_score:.0f}")
        st.checkbox("Seleccionar", key=f"sel_{r.name}")

st.divider()
st.info("Siguiente fase: selección → carrusel/reel → caption IA → Instagram API.")
