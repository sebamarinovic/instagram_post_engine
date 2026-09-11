from pathlib import Path

import streamlit as st

import media_sources as ms
import enrich_locations
from scan_media import find_media_files, merge_source_into_index, build_index, load_index
from config import MEDIA_GEO_CSV, MEDIA_INDEX_CSV

st.set_page_config(page_title="Fuentes multimedia", layout="wide")
st.title("⚙️ Fuentes multimedia")
st.caption("Agrega, activa/desactiva o reescanea carpetas de fotos y videos sin tocar código.")

index_df = load_index()

if not index_df.empty and "content_hash" in index_df.columns:
    ch = index_df["content_hash"].astype(str).str.strip().str.lower()
    has_hash = ~ch.isin(["", "nan", "none"])
    dup_hashes = ch[has_hash][ch[has_hash].duplicated(keep=False)]
    if len(dup_hashes):
        st.info(
            f"🔁 {dup_hashes.nunique()} archivo(s) están repetidos en más de una carpeta "
            f"({len(dup_hashes)} copias en total). El motor de publicación ya los combina "
            "y solo ofrece la mejor copia de cada uno."
        )

st.subheader("➕ Agregar carpeta")
with st.form("add_source_form", clear_on_submit=True):
    c1, c2 = st.columns([1, 2])
    name = c1.text_input("Nombre")
    path = c2.text_input("Ruta local", placeholder=r"D:\Fotos\Viajes")
    submitted = st.form_submit_button("Agregar fuente", use_container_width=True)
    if submitted:
        if not name.strip() or not path.strip():
            st.error("Completa nombre y ruta.")
        elif not Path(path).exists():
            st.error(f"La ruta no existe en este equipo: {path}")
        else:
            ms.add_source(name.strip(), path.strip())
            st.success(f"Fuente '{name}' agregada.")
            st.rerun()

st.divider()
st.subheader("📁 Fuentes configuradas")

sources = ms.list_sources()
if not sources:
    st.info("Todavía no hay fuentes multimedia configuradas. Agrega la primera arriba.")
    st.stop()

for source in sources:
    sid = source["id"]
    with st.container(border=True):
        top = st.columns([3, 2, 2, 1, 1])
        label = source["name"] + (" ⭐" if source.get("primary") else "")
        top[0].markdown(f"**{label}**\n\n`{source['path']}`")

        if not index_df.empty and "source_id" in index_df.columns:
            src_rows = index_df[index_df["source_id"] == sid]
            photos = int((src_rows.media_type == "image").sum())
            videos = int((src_rows.media_type == "video").sum())
        else:
            photos = videos = 0
        top[1].metric("📸 Fotos / 🎬 Videos", f"{photos} / {videos}")

        last_scan = source.get("last_scanned_at")
        top[2].caption("Último escaneo")
        top[2].write(last_scan[:19].replace("T", " ") if last_scan else "Nunca")

        enabled = top[3].toggle("Activa", value=source.get("enabled", True), key=f"en_{sid}")
        if enabled != source.get("enabled", True):
            ms.set_enabled(sid, enabled)
            st.rerun()

        if top[4].button("🗑️ Quitar", key=f"rm_{sid}", use_container_width=True):
            ms.remove_source(sid)
            st.rerun()

        path_exists = Path(source["path"]).exists()
        if not path_exists:
            st.warning("La carpeta no está accesible desde este equipo ahora mismo.")

        b1, b2, b3 = st.columns(3)

        if b1.button("🔄 Reescanear completo", key=f"full_{sid}", disabled=not path_exists, use_container_width=True):
            with st.spinner(f"Reescaneando '{source['name']}'..."):
                paths = find_media_files(source["path"])
                df_new = build_index(paths, sid, source["name"], source["path"])
                merge_source_into_index(df_new, sid, replace=True)
                ms.update_scan_stats(sid, len(df_new))
            st.success(f"{len(df_new)} archivo(s) indexados desde '{source['name']}'.")
            st.rerun()

        if b2.button("🆕 Actualizar solo nuevos", key=f"new_{sid}", disabled=not path_exists, use_container_width=True):
            with st.spinner(f"Buscando archivos nuevos en '{source['name']}'..."):
                paths = find_media_files(source["path"])
                known = set(index_df["path"].astype(str)) if not index_df.empty else set()
                new_paths = [p for p in paths if str(p) not in known]
                total = int((index_df["source_id"] == sid).sum()) if not index_df.empty and "source_id" in index_df.columns else 0
                if new_paths:
                    df_new = build_index(new_paths, sid, source["name"], source["path"])
                    merged = merge_source_into_index(df_new, sid, replace=False)
                    total = int((merged["source_id"] == sid).sum())
            ms.update_scan_stats(sid, total)
            st.success(f"{len(new_paths)} archivo(s) nuevo(s) agregados." if new_paths else "No hay archivos nuevos.")
            st.rerun()

        if b3.button("⭐ Marcar como principal", key=f"pri_{sid}", disabled=source.get("primary", False), use_container_width=True):
            ms.set_primary(sid)
            st.rerun()

st.divider()
st.subheader("🌍 Actualizar ubicación")
st.caption(
    "Recalcula país/ciudad/año para todo el índice combinado (todas las fuentes) "
    "y genera el `media_geo.csv` que usa el motor de publicación."
)
if st.button("🌍 Recalcular ubicación (enrich_locations)", disabled=not MEDIA_INDEX_CSV.exists(), use_container_width=True):
    with st.spinner("Geolocalizando..."):
        enrich_locations.main(str(MEDIA_INDEX_CSV), str(MEDIA_GEO_CSV))
    st.success(f"{MEDIA_GEO_CSV.name} actualizado. Ya puedes volver a '🚀 Instagram Rebuild'.")
