from pathlib import Path
import hashlib, json
import pandas as pd
import streamlit as st
from ai_post_generator import generate_post
from publisher import config_status, publish_images
from publication_history import load_history, media_key, record_publication, record_existing_publication
from config import MEDIA_GEO_CSV, PROFILE_CONTEXT_JSON
import media_sources as ms

st.set_page_config(page_title="Instagram Rebuild", layout="wide")

if not MEDIA_GEO_CSV.exists():
    st.error(f"Falta {MEDIA_GEO_CSV}")
    st.stop()

def dedupe_by_content(df):
    """Collapse rows that are the same file (by content_hash) seen in more than
    one source folder, keeping the best copy (highest quality_score, then
    earliest captured_at). Rows without a content_hash (scanned before this
    feature existed) are left untouched — nothing to compare them against."""
    if "content_hash" not in df.columns:
        return df, 0
    ch = df["content_hash"].astype(str).str.strip().str.lower()
    has_hash = ~ch.isin(["", "nan", "none"])
    with_hash = df[has_hash].sort_values(["quality_score","captured_at"], ascending=[False, True])
    canonical = with_hash.drop_duplicates(subset="content_hash", keep="first")
    without_hash = df[~has_hash]
    return pd.concat([canonical, without_hash], ignore_index=False), len(with_hash) - len(canonical)

df = pd.read_csv(MEDIA_GEO_CSV)
df["captured_at"] = pd.to_datetime(df["captured_at"], errors="coerce")
df["quality_score"] = pd.to_numeric(df["quality_score"], errors="coerce").fillna(0)

if "source_id" in df.columns:
    disabled_ids = {s["id"] for s in ms.list_sources() if not s.get("enabled", True)}
    if disabled_ids:
        df = df[~df["source_id"].isin(disabled_ids)]

df, duplicate_count = dedupe_by_content(df)

DEFAULT_PROFILE = """Sebastián. Chileno-croata 🇨🇱🇭🇷.
Ingeniero Civil Industrial con vínculo a metalurgia y procesos industriales.
Interés profesional en Data Science, inteligencia artificial y tecnología.
Hobbies: viajes, fotografía, drone/FPV, tecnología y conocer nuevos lugares.
Emprendedor y fundador de un proyecto tecnológico.
El Instagram es personal: lo profesional es contexto, no tema obligatorio."""

profile_saved = DEFAULT_PROFILE
if PROFILE_CONTEXT_JSON.exists():
    try:
        profile_saved = json.loads(PROFILE_CONTEXT_JSON.read_text(encoding="utf-8")).get("profile_context", DEFAULT_PROFILE)
    except Exception:
        pass

st.session_state.setdefault("selected_paths", [])
st.session_state.setdefault("post_draft", None)

def key_for(path):
    return hashlib.md5(str(path).encode("utf-8")).hexdigest()

def clear_checkbox_states():
    for k in list(st.session_state.keys()):
        if str(k).startswith("cb_"):
            del st.session_state[k]

def clear_selection():
    st.session_state.selected_paths = []
    st.session_state.post_draft = None
    clear_checkbox_states()

def set_selected(path, widget_key):
    current = set(st.session_state.selected_paths)
    if st.session_state.get(widget_key):
        current.add(path)
    else:
        current.discard(path)
    st.session_state.selected_paths = list(current)
    st.session_state.post_draft = None

if st.session_state.get("flash_message"):
    st.success(st.session_state.pop("flash_message"))

history = load_history()
published_set = set(history["media_key"].dropna().astype(str))

st.title("🚀 Instagram Rebuild")
st.caption("Explorar → seleccionar → contextualizar → crear → revisar → publicar → registrar")

st.sidebar.caption("⚙️ Administra tus carpetas de fotos en 'Fuentes multimedia' (menú lateral arriba).")
st.sidebar.header("🔎 Explorar")

if st.sidebar.button("🔄 Reiniciar búsqueda", use_container_width=True):
    st.session_state.clear()
    st.rerun()

hide_published = st.sidebar.toggle("🙈 Ocultar ya publicadas", value=True)
allow_reuse = st.sidebar.toggle("♻️ Permitir reutilizar publicadas", value=False)

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

media_type = st.sidebar.selectbox("🎞️ Tipo", ["Todos","image","video"])
if media_type != "Todos":
    work = work[work.media_type == media_type]

loc_sources = st.sidebar.multiselect("🧭 Fuente ubicación", ["gps","time_inferred","none"], default=["gps","time_inferred"])
if loc_sources:
    work = work[work.location_source.isin(loc_sources)]

date_sources = st.sidebar.multiselect("🕒 Fuente fecha", ["original_or_video","filesystem_fallback"], default=["original_or_video"])
if date_sources:
    work = work[work.date_source.isin(date_sources)]

work = work.copy()
work["_path_key"] = work["path"].astype(str).map(media_key)
if "content_hash" in work.columns:
    ch = work["content_hash"].astype(str).str.strip().str.lower()
    work["_content_key"] = ch.where(~ch.isin(["", "nan", "none"]))
else:
    work["_content_key"] = None
work["_published"] = work["_path_key"].isin(published_set) | work["_content_key"].isin(published_set)
if hide_published:
    work = work[~work["_published"]]

st.sidebar.divider()
st.sidebar.metric("✅ Seleccionadas", len(st.session_state.selected_paths))
st.sidebar.metric("📤 Publicadas registradas", len(published_set))
if duplicate_count:
    st.sidebar.metric("🔁 Duplicados omitidos", duplicate_count)

if st.sidebar.button("🗑️ Limpiar selección", use_container_width=True):
    clear_selection()
    st.rerun()

c1,c2,c3,c4,c5 = st.columns(5)
c1.metric("Elementos", len(work))
c2.metric("📸 Fotos", int((work.media_type=="image").sum()))
c3.metric("🎬 Videos", int((work.media_type=="video").sum()))
c4.metric("✅ Seleccionadas", len(st.session_state.selected_paths))
c5.metric("📤 Publicadas", len(published_set))

st.subheader("🖼️ Material")
gallery = work.sort_values(["quality_score","captured_at"], ascending=[False,True]).head(100)
cols = st.columns(5)

for pos,(_,row) in enumerate(gallery.iterrows()):
    path = str(row.path)
    widget_key = "cb_" + key_for(path)
    already = bool(row["_published"])
    with cols[pos % 5]:
        thumb = row.get("thumb_path")
        if isinstance(thumb,str) and Path(thumb).exists():
            st.image(thumb, use_container_width=True)
        else:
            st.write("🎬 VIDEO" if row.media_type=="video" else "📷")
        if already:
            st.caption("✅ YA PUBLICADA")
        date = "" if pd.isna(row.captured_at) else row.captured_at.strftime("%Y-%m-%d")
        city_txt = "" if pd.isna(row.get("city")) else str(row.get("city"))
        country_txt = "" if pd.isna(row.get("country")) else str(row.get("country"))
        loc = " · ".join([x for x in [city_txt,country_txt] if x])
        st.caption(f"📍 {loc or 'sin ubicación'}\n\n📅 {date}\n⭐ {row.quality_score:.0f}")
        st.checkbox(
            "Seleccionar",
            key=widget_key,
            value=(path in st.session_state.selected_paths),
            disabled=(already and not allow_reuse),
            on_change=set_selected,
            args=(path, widget_key)
        )

selected_df = df[df.path.astype(str).isin(st.session_state.selected_paths)].copy()
selected_keys = set(selected_df["path"].astype(str).map(media_key))
if "content_hash" in selected_df.columns:
    ch = selected_df["content_hash"].astype(str).str.strip().str.lower()
    selected_keys |= set(ch[~ch.isin(["", "nan", "none"])])
selected_already = selected_keys.intersection(published_set)

st.divider()
st.subheader(f"🎞️ Selección — {len(selected_df)} elementos")
with st.expander("🕘 Registrar selección como publicación antigua"):
    st.caption(
        "Úsalo para contenido que ya estaba publicado antes de instalar el historial. "
        "No publica nada."
    )

    historical_link = st.text_input(
        "🔗 Link de la publicación existente",
        placeholder="https://www.instagram.com/p/..."
    )

    historical_confirm = st.checkbox(
        "Confirmo que las fotos seleccionadas corresponden a esa publicación antigua",
        key="historical_confirm"
    )

    if st.button(
        "📌 MARCAR SELECCIÓN COMO YA PUBLICADA",
        disabled=not (
            len(selected_df) >= 1
            and historical_link.strip()
            and historical_confirm
        ),
        use_container_width=True
    ):
        added = record_existing_publication(
            selected_df.to_dict("records"),
            historical_link.strip()
        )

        clear_selection()

        st.session_state.flash_message = (
            f"✅ {added} archivo(s) registrados como publicación antigua. "
            "Ya no se ofrecerán nuevamente."
        )

        st.rerun()

if selected_already and not allow_reuse:
    st.warning("Hay material ya publicado en la selección. Limpia selección o activa 'Permitir reutilizar publicadas'.")

st.divider()
st.header("🧠 Contexto antes de crear")

profile_context = st.text_area("👤 Contexto permanente del perfil", value=profile_saved, height=150)
if st.button("💾 Guardar contexto del perfil"):
    PROFILE_CONTEXT_JSON.parent.mkdir(parents=True, exist_ok=True)
    PROFILE_CONTEXT_JSON.write_text(json.dumps({"profile_context":profile_context}, ensure_ascii=False, indent=2), encoding="utf-8")
    st.success("Contexto guardado.")

experience_context = st.text_area("🌎 ¿Qué estaba pasando en esta experiencia?", height=100)
intention = st.text_input("💭 ¿Qué quieres transmitir?")

b1,b2,b3,b4 = st.columns(4)
with b1: tone = st.selectbox("🎭 Tono", ["Natural","Emotivo","Minimalista","Reflexivo","Humor sutil","Elegante"])
with b2: length = st.selectbox("📏 Extensión", ["Corta","Media","Larga"], index=1)
with b3: emoji_level = st.selectbox("🙂 Emojis", ["Bajo","Medio","Alto"], index=1)
with b4: language = st.selectbox("🌐 Idioma", ["Español","Inglés","Español + frase en inglés"])

avoid = st.text_input("🚫 Evitar")
extra = st.text_area("➕ Instrucción extra", height=80)

can_generate = 1 <= len(selected_df) <= 10 and (allow_reuse or not selected_already)

if st.button("🤖 Crear 3 propuestas", type="primary", disabled=not can_generate, use_container_width=True):
    ctx = dict(profile_context=profile_context, experience_context=experience_context, intention=intention,
               tone=tone, length=length, emoji_level=emoji_level, language=language, avoid=avoid, extra=extra)
    with st.spinner("Creando propuestas..."):
        st.session_state.post_draft = generate_post(selected_df.to_dict("records"), ctx)

draft = st.session_state.post_draft
if draft:
    st.divider()
    st.header("✨ Propuesta creativa")
    st.write("**Concepto:**", draft.get("concept"))
    st.write("**Portada sugerida:**", draft.get("cover_index"))
    st.write("**Orden sugerido:**", draft.get("recommended_order"))

    options = draft.get("caption_options", [])
    labels = [f"{i+1}. {o.get('label','Opción')}" for i,o in enumerate(options)]
    choice = st.radio("✍️ Elige una redacción", labels, horizontal=True) if labels else None
    idx = labels.index(choice) if choice else 0
    chosen = options[idx] if options else {"caption":""}
    caption_final = st.text_area("✏️ Editar caption final", value=chosen.get("caption",""), height=230, key=f"caption_{idx}")

    st.write("**🎵 Música:**", draft.get("music_search") or "—")
    st.write("**📍 Ubicación:**", draft.get("location") or "—")
    st.write("**#️⃣ Hashtags:**", " ".join(draft.get("hashtags",[])))
    st.write("**💡 Feedback:**", draft.get("selection_feedback") or "—")

    selected_records = selected_df.to_dict("records")
    order = draft.get("recommended_order") or list(range(1,len(selected_records)+1))
    ordered = []
    for i in order:
        try:
            ordered.append(selected_records[int(i)-1])
        except Exception:
            pass
    if len(ordered) != len(selected_records):
        ordered = selected_records

    st.subheader("🚀 Publicación real")
    cfg = config_status()
    missing = [k for k,v in cfg.items() if not v]
    all_images = all(str(r.get("media_type"))=="image" for r in ordered)

    if missing:
        st.warning("Falta configurar: " + ", ".join(missing))
    if selected_already and not allow_reuse:
        st.error("Publicación bloqueada: contiene material ya publicado.")

    confirm = st.checkbox("✅ Confirmo que revisé fotos, orden y texto y quiero publicarlo")
    ready = not missing and all_images and 1 <= len(ordered) <= 10 and confirm and (allow_reuse or not selected_already)

    if st.button("🚀 PUBLICAR AHORA EN INSTAGRAM", type="primary", disabled=not ready, use_container_width=True):
        with st.spinner("Publicando..."):
            try:
                result = publish_images([r["path"] for r in ordered], caption_final)
                added = record_publication(ordered, caption_final, result)
                clear_selection()
                st.session_state.flash_message = f"✅ Publicación realizada. {added} archivo(s) registrados para no repetir."
                st.rerun()
            except Exception as e:
                st.error(f"❌ Error al publicar: {e}")

st.divider()
with st.expander("📚 Historial de publicaciones"):
    hist = load_history()
    if hist.empty:
        st.info("Todavía no hay publicaciones registradas.")
    else:
        show = [c for c in ["published_at","filename","country","city","year","instagram_media_id"] if c in hist.columns]
        st.dataframe(hist[show].sort_values("published_at", ascending=False), use_container_width=True, hide_index=True)
        st.download_button(
            "⬇️ Descargar historial CSV",
            hist.to_csv(index=False).encode("utf-8-sig"),
            "instagram_published_media.csv",
            "text/csv"
        )
