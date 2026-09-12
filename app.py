from pathlib import Path
import hashlib, json
import pandas as pd
import streamlit as st
from ai_post_generator import generate_post
from publisher import config_status, publish_images, DRY_RUN
from publication_history import load_history, media_key, record_publication, record_existing_publication, summarize_publications
from config import MEDIA_GEO_CSV, PROFILE_CONTEXT_JSON
from curation import pick_best
import media_sources as ms

MAX_CAROUSEL = 10

st.set_page_config(page_title="Instagram Rebuild", layout="wide")

if DRY_RUN:
    st.info("🧪 **DRY_RUN activo** — las publicaciones se simulan. No se llama a la API de Instagram ni se sube nada a S3.")

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
st.session_state.setdefault("last_auto_curation", None)

def key_for(path):
    return hashlib.md5(str(path).encode("utf-8")).hexdigest()

TRANSIENT_KEY_PREFIXES = ("cb_", "caption_")
TRANSIENT_KEYS = {"historical_confirm", "confirm_publish"}

def clear_widget_states():
    """Drop every widget's leftover state from a previous selection/draft —
    checkboxes, the historical-publication confirm, the edited caption text
    area and the final publish confirm — so nothing reappears pre-checked
    or pre-filled after 'Limpiar selección'."""
    for k in list(st.session_state.keys()):
        sk = str(k)
        if sk.startswith(TRANSIENT_KEY_PREFIXES) or sk in TRANSIENT_KEYS:
            del st.session_state[k]

def clear_selection():
    st.session_state.selected_paths = []
    st.session_state.post_draft = None
    st.session_state.last_auto_curation = None
    clear_widget_states()

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

if len(selected_df) > MAX_CAROUSEL:
    st.warning(f"⚠️ Seleccionaste {len(selected_df)} elementos. Instagram admite hasta {MAX_CAROUSEL} en este flujo.")
    if st.button("✨ Seleccionar automáticamente las mejores 10", use_container_width=True):
        kept, discarded = pick_best(selected_df.to_dict("records"), limit=MAX_CAROUSEL)
        st.session_state.selected_paths = [str(r["path"]) for r in kept]
        st.session_state.post_draft = None
        st.session_state.last_auto_curation = discarded
        st.rerun()

if st.session_state.get("last_auto_curation"):
    discarded = st.session_state.last_auto_curation
    with st.expander(f"📋 Se descartaron {len(discarded)} foto(s) para priorizar calidad y diversidad", expanded=True):
        for d in discarded:
            st.write(f"- {d.get('filename')} — {d.get('_reason')}")
        if st.button("Ocultar este resumen"):
            st.session_state.last_auto_curation = None
            st.rerun()

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

can_generate = 1 <= len(selected_df) <= MAX_CAROUSEL and (allow_reuse or not selected_already)

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

    st.subheader("🧪 Simulación (DRY_RUN)" if DRY_RUN else "🚀 Publicación real")
    cfg = config_status()
    missing = [] if DRY_RUN else [k for k,v in cfg.items() if not v]
    all_images = all(str(r.get("media_type"))=="image" for r in ordered)

    if missing:
        st.warning("Falta configurar: " + ", ".join(missing))
    if selected_already and not allow_reuse:
        st.error("Publicación bloqueada: contiene material ya publicado.")

    confirm = st.checkbox("✅ Confirmo que revisé fotos, orden y texto y quiero publicarlo", key="confirm_publish")
    ready = not missing and all_images and 1 <= len(ordered) <= MAX_CAROUSEL and confirm and (allow_reuse or not selected_already)

    button_label = "🧪 SIMULAR PUBLICACIÓN (DRY_RUN)" if DRY_RUN else "🚀 PUBLICAR AHORA EN INSTAGRAM"
    if st.button(button_label, type="primary", disabled=not ready, use_container_width=True):
        with st.spinner("Simulando..." if DRY_RUN else "Publicando..."):
            try:
                result = publish_images([r["path"] for r in ordered], caption_final)
                added = record_publication(ordered, caption_final, result)
                clear_selection()
                msg = "🧪 Simulación completada" if DRY_RUN else "✅ Publicación realizada"
                st.session_state.flash_message = f"{msg}. {added} archivo(s) registrados para no repetir."
                st.rerun()
            except Exception as e:
                st.error(f"❌ Error al publicar: {e}")

st.divider()
with st.expander("📚 Historial de publicaciones"):
    hist = load_history()
    if hist.empty:
        st.info("Todavía no hay publicaciones registradas.")
    else:
        summary = summarize_publications(hist)

        f1, f2 = st.columns([2, 1])
        search = f1.text_input("🔎 Buscar (caption, país, ciudad, archivo)", key="hist_search")
        country_opts = ["Todos"] + sorted(summary["country"].dropna().astype(str).unique().tolist())
        hist_country = f2.selectbox("🌎 País", country_opts, key="hist_country_filter")

        filtered = summary
        if hist_country != "Todos":
            filtered = filtered[filtered["country"].astype(str) == hist_country]
        if search.strip():
            q = search.strip().lower()
            text_cols = ["caption", "country", "city", "cover_filename"]
            mask = filtered[text_cols].astype(str).apply(lambda col: col.str.lower().str.contains(q, na=False))
            filtered = filtered[mask.any(axis=1)]

        st.caption(f"{len(filtered)} publicación(es) de {len(summary)} en total")

        display = filtered.drop(columns=["cover_path"], errors="ignore").rename(columns={
            "published_at": "Fecha", "photos": "Fotos", "country": "País", "city": "Ciudad",
            "year": "Año", "caption": "Caption", "instagram_media_id": "Instagram ID",
            "permalink": "Abrir", "source": "Origen", "cover_filename": "Portada",
            "publication_id": "ID publicación",
        })
        st.dataframe(
            display,
            use_container_width=True,
            hide_index=True,
            column_config={"Abrir": st.column_config.LinkColumn("Abrir", display_text="🔗 Ver")},
        )

        st.download_button(
            "⬇️ Descargar historial por publicación (CSV)",
            filtered.to_csv(index=False).encode("utf-8-sig"),
            "instagram_publications_summary.csv",
            "text/csv",
        )

        if st.checkbox("Ver detalle por foto", key="hist_show_detail"):
            show = [c for c in ["published_at","filename","country","city","year","instagram_media_id","source"] if c in hist.columns]
            st.dataframe(hist[show].sort_values("published_at", ascending=False), use_container_width=True, hide_index=True)
            st.download_button(
                "⬇️ Descargar historial detallado (CSV)",
                hist.to_csv(index=False).encode("utf-8-sig"),
                "instagram_published_media.csv",
                "text/csv",
            )
