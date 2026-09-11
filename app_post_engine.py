from pathlib import Path
import hashlib
import json

import pandas as pd
import streamlit as st

from ai_post_generator import generate_post

st.set_page_config(page_title="Instagram Rebuild — Motor", layout="wide")

CSV = Path("data/media_geo.csv")
if not CSV.exists():
    st.error("No existe data/media_geo.csv. Ejecuta primero enrich_locations.py.")
    st.stop()

df = pd.read_csv(CSV)
df["captured_at"] = pd.to_datetime(df["captured_at"], errors="coerce")
df["quality_score"] = pd.to_numeric(df["quality_score"], errors="coerce").fillna(0)

if "selected_paths" not in st.session_state:
    st.session_state.selected_paths = []
if "post_draft" not in st.session_state:
    st.session_state.post_draft = None

def key_for(path):
    return hashlib.md5(str(path).encode("utf-8")).hexdigest()

def set_selected(path, widget_key):
    current = set(st.session_state.selected_paths)
    if st.session_state.get(widget_key):
        current.add(path)
    else:
        current.discard(path)
    st.session_state.selected_paths = list(current)

st.title("🚀 Instagram Rebuild — Motor de publicaciones")
st.caption("Elegir experiencia → seleccionar material → IA propone carrusel/caption → revisión humana")

# ---------- SIDEBAR ----------
st.sidebar.header("🔎 Explorar")

countries = ["Todos"] + sorted(df.country.dropna().astype(str).unique().tolist())
country = st.sidebar.selectbox("🌎 País", countries)

work = df.copy()
if country != "Todos":
    work = work[work.country == country]

cities = ["Todas"] + sorted(work.city.dropna().astype(str).unique().tolist())
city = st.sidebar.selectbox("📍 Ciudad", cities)
if city != "Todas":
    work = work[work.city == city]

years = sorted([int(x) for x in work.year.dropna().unique()])
year = st.sidebar.selectbox("📅 Año", ["Todos"] + years)
if year != "Todos":
    work = work[work.year == year]

media_type = st.sidebar.selectbox("🎞️ Tipo", ["Todos", "image", "video"])
if media_type != "Todos":
    work = work[work.media_type == media_type]

loc_sources = st.sidebar.multiselect(
    "🧭 Fuente ubicación",
    ["gps", "time_inferred", "none"],
    default=["gps", "time_inferred"]
)
work = work[work.location_source.isin(loc_sources)]

date_sources = st.sidebar.multiselect(
    "🕒 Fuente fecha",
    ["original_or_video", "filesystem_fallback"],
    default=["original_or_video"]
)
work = work[work.date_source.isin(date_sources)]

st.sidebar.divider()
st.sidebar.metric("✅ Seleccionadas", len(st.session_state.selected_paths))

if st.sidebar.button("🗑️ Limpiar selección", use_container_width=True):
    st.session_state.selected_paths = []
    st.session_state.post_draft = None
    st.rerun()

# ---------- KPIs ----------
c1,c2,c3,c4 = st.columns(4)
c1.metric("Elementos", len(work))
c2.metric("📸 Fotos", int((work.media_type == "image").sum()))
c3.metric("🎬 Videos", int((work.media_type == "video").sum()))
c4.metric("✅ Seleccionadas", len(st.session_state.selected_paths))

# ---------- GALLERY ----------
st.subheader("🖼️ Material")

if len(work) == 0:
    st.info("No hay contenido con estos filtros.")
    st.stop()

gallery = work.sort_values(["quality_score", "captured_at"], ascending=[False, True]).head(100)

cols = st.columns(5)

for pos, (_, row) in enumerate(gallery.iterrows()):
    path = str(row.path)
    widget_key = "cb_" + key_for(path)

    with cols[pos % 5]:
        thumb = row.get("thumb_path")
        if isinstance(thumb, str) and Path(thumb).exists():
            st.image(thumb, use_container_width=True)
        else:
            st.write("🎬 VIDEO" if row.media_type == "video" else "📷")

        date = ""
        if not pd.isna(row.captured_at):
            date = row.captured_at.strftime("%Y-%m-%d")

        city_txt = "" if pd.isna(row.get("city")) else str(row.get("city"))
        country_txt = "" if pd.isna(row.get("country")) else str(row.get("country"))
        loc = " · ".join([x for x in [city_txt, country_txt] if x])

        st.caption(
            f"📍 {loc or 'sin ubicación'}\n\n"
            f"📅 {date}\n"
            f"⭐ {row.quality_score:.0f}"
        )

        st.checkbox(
            "Seleccionar",
            key=widget_key,
            value=(path in st.session_state.selected_paths),
            on_change=set_selected,
            args=(path, widget_key)
        )

# ---------- SELECTED TRAY ----------
st.divider()
st.subheader(f"🎞️ Bandeja de publicación — {len(st.session_state.selected_paths)} seleccionadas")

selected_df = df[df.path.astype(str).isin(st.session_state.selected_paths)].copy()

if len(selected_df):
    tray_cols = st.columns(min(5, len(selected_df)))
    for i, (_, row) in enumerate(selected_df.iterrows()):
        with tray_cols[i % len(tray_cols)]:
            thumb = row.get("thumb_path")
            if isinstance(thumb, str) and Path(thumb).exists():
                st.image(thumb, use_container_width=True)
            st.caption(Path(str(row.path)).name[:30])

    if len(selected_df) > 10:
        st.warning("Instagram admite máximo 10 elementos por carrusel. Deja 10 o menos para esta publicación.")

    generate_disabled = not (1 <= len(selected_df) <= 10)

    if st.button(
        "🤖 Generar propuesta de publicación",
        type="primary",
        disabled=generate_disabled,
        use_container_width=True
    ):
        rows = selected_df.to_dict("records")
        with st.spinner("La IA está revisando narrativa, portada, orden y caption..."):
            try:
                st.session_state.post_draft = generate_post(rows)
            except Exception as e:
                st.error(f"No se pudo generar la propuesta: {e}")

else:
    st.info("Selecciona entre 1 y 10 fotos para crear una publicación.")

# ---------- DRAFT ----------
draft = st.session_state.post_draft

if draft:
    st.divider()
    st.header("✨ Propuesta IA")

    if draft.get("decision") == "revise_selection":
        st.warning("La IA recomienda revisar la selección antes de publicar.")

    a,b,c = st.columns(3)
    a.metric("🌎 País", draft.get("country") or "—")
    b.metric("📍 Lugar", draft.get("city") or draft.get("location") or "—")
    c.metric("📅 Año", draft.get("year") or "—")

    st.subheader(draft.get("concept", "Publicación"))

    st.write("**Portada sugerida:**", draft.get("cover_index"))
    st.write("**Orden sugerido:**", draft.get("recommended_order"))
    st.write("**Por qué ese orden:**", draft.get("why_this_order"))

    caption = st.text_area(
        "✍️ Caption",
        value=draft.get("caption", ""),
        height=220
    )

    st.write("**🎵 Buscar música:**", draft.get("music_search") or "—")
    st.write("**📍 Ubicación sugerida:**", draft.get("location") or "—")
    st.write("**#️⃣ Hashtags:**", " ".join(draft.get("hashtags", [])))
    st.write("**💡 Feedback de selección:**", draft.get("selection_feedback") or "—")

    col1,col2 = st.columns(2)

    with col1:
        if st.button("💾 Guardar borrador", use_container_width=True):
            out_dir = Path("data/drafts")
            out_dir.mkdir(parents=True, exist_ok=True)
            payload = dict(draft)
            payload["caption_final"] = caption
            payload["selected_paths"] = st.session_state.selected_paths
            out = out_dir / f"draft_{pd.Timestamp.now().strftime('%Y%m%d_%H%M%S')}.json"
            out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            st.success(f"Borrador guardado: {out}")

    with col2:
        st.button(
            "🚀 Aprobar para publicar",
            disabled=True,
            help="Lo habilitaremos cuando conectemos esta pantalla con publisher.py + S3 + Instagram API.",
            use_container_width=True
        )
