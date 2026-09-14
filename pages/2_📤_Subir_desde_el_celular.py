import hashlib
from pathlib import Path

import streamlit as st

import auth
import media_sources as ms
import enrich_locations
from scan_media import IMAGE_EXTS, VIDEO_EXTS, scan_source_incremental
from config import UPLOADS_DIR, MEDIA_INDEX_CSV, MEDIA_GEO_CSV

st.set_page_config(page_title="Subir desde el celular", layout="wide")
auth.require_login()
auth.sidebar_user_badge()

st.title("📤 Subir fotos y videos")
st.caption(
    "Desde el celular: elige fotos o videos de tu galería y súbelos directo a tu biblioteca. "
    "Quedan guardados en el servidor y entran al mismo catálogo que tus otras carpetas."
)

source_id = ms.ensure_uploads_source(UPLOADS_DIR)
source = ms.get_source(source_id)

allowed_exts = sorted(e.lstrip(".") for e in (IMAGE_EXTS | VIDEO_EXTS))
uploaded = st.file_uploader(
    "Selecciona fotos o videos",
    type=allowed_exts,
    accept_multiple_files=True,
)

if uploaded:
    st.write(f"{len(uploaded)} archivo(s) listo(s) para subir.")
    if st.button("⬆️ Subir y procesar", type="primary", use_container_width=True):
        progress = st.progress(0.0, text="Guardando archivos...")
        saved, skipped = 0, 0
        for i, f in enumerate(uploaded, start=1):
            data = f.getvalue()
            digest = hashlib.sha256(data).hexdigest()[:12]
            stem = Path(f.name).stem
            ext = Path(f.name).suffix.lower()
            # content-hash suffix: re-uploading the exact same file is a
            # no-op (same target path), and two different files that
            # happen to share a name never collide.
            target = UPLOADS_DIR / f"{stem}_{digest}{ext}"
            if target.exists():
                skipped += 1
            else:
                target.write_bytes(data)
                saved += 1
            progress.progress(i / len(uploaded), text=f"{i}/{len(uploaded)}")
        progress.empty()

        with st.spinner("Analizando archivos nuevos..."):
            stats = scan_source_incremental(source_id, source["name"], str(UPLOADS_DIR))
        ms.update_scan_stats(source_id, stats["new"] + stats["modified"] + stats["unchanged"])

        st.success(
            f"✅ {saved} archivo(s) subido(s)"
            + (f" ({skipped} ya existían, se omitieron)" if skipped else "")
            + f". 🆕 {stats['new']} nuevo(s) analizado(s) · ✏️ {stats['modified']} actualizado(s)."
        )

st.divider()
st.caption(f"Carpeta de subidas en el servidor: `{UPLOADS_DIR}` · fuente: **{source['name']}**")

if st.button(
    "🌍 Actualizar ubicación ahora",
    disabled=not MEDIA_INDEX_CSV.exists(),
    use_container_width=True,
    help="Recalcula país/ciudad/año para todo el índice combinado, no solo lo recién subido.",
):
    with st.spinner("Geolocalizando..."):
        enrich_locations.main(str(MEDIA_INDEX_CSV), str(MEDIA_GEO_CSV))
    st.success("Ubicación actualizada. Ya puedes verlas en '🚀 Instagram Rebuild'.")
