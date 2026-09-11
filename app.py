import json
from pathlib import Path

import pandas as pd
import streamlit as st

from config import EXPERIENCES_CSV, MEDIA_CSV
from ai_draft import generate_draft

st.set_page_config(page_title="Instagram Rebuild", layout="wide")
st.title("Instagram Rebuild — Experiencias")

if not EXPERIENCES_CSV.exists() or not MEDIA_CSV.exists():
    st.warning("Primero ejecuta scan_media.py y cluster_experiences.py.")
    st.stop()

exp = pd.read_csv(EXPERIENCES_CSV)
media = pd.read_csv(MEDIA_CSV)

# most recent first
exp = exp.sort_values("start", ascending=False)

labels = []
for _,r in exp.iterrows():
    place = " · ".join([x for x in [str(r.get("city") or ""), str(r.get("country_code") or "")] if x and x != "nan"])
    labels.append(f"#{int(r.experience_id)} | {r.start[:10]} → {r.end[:10]} | {place or 'sin GPS'} | {int(r['items'])} archivos")

choice = st.selectbox("Experiencia", labels)
eid = int(choice.split("|")[0].replace("#","").strip())
er = exp[exp.experience_id == eid].iloc[0]
g = media[media.experience_id == eid].copy()
g["quality_score"] = pd.to_numeric(g["quality_score"], errors="coerce").fillna(0)
g = g.sort_values("quality_score", ascending=False)

st.caption(f"{len(g)} archivos · {int(er.images)} fotos · {int(er.videos)} videos")

# show top 30 candidates
cands = g[g.thumb_path.notna()].head(30).copy()
selected = []

cols = st.columns(5)
for idx,(_,r) in enumerate(cands.iterrows()):
    with cols[idx % 5]:
        try:
            st.image(r.thumb_path, use_container_width=True)
        except Exception:
            st.write("Sin miniatura")
        flag = st.checkbox(f"Elegir {idx+1}", key=f"{eid}_{idx}")
        st.caption(f"{Path(r.path).name[:28]} · score {r.quality_score:.1f}")
        if flag:
            selected.append(r.path)

st.divider()
st.write(f"Seleccionadas: **{len(selected)}**")

meta = {
    "experience_id": eid,
    "start": str(er.start),
    "end": str(er.end),
    "city": None if pd.isna(er.city) else er.city,
    "country_code": None if pd.isna(er.country_code) else er.country_code,
}

if st.button("Generar borrador con IA", disabled=(len(selected)==0)):
    with st.spinner("Analizando selección..."):
        # send thumbnails instead of originals to reduce cost and bandwidth
        thumbs = []
        for p in selected[:10]:
            row = g[g.path == p]
            if len(row) and pd.notna(row.iloc[0].thumb_path):
                thumbs.append(row.iloc[0].thumb_path)
        draft = generate_draft(thumbs, meta)
        st.session_state["draft"] = draft

draft = st.session_state.get("draft")
if draft:
    st.subheader("Borrador")
    st.json(draft)
    caption = st.text_area("Caption editable", draft.get("caption_es",""), height=220)
    st.info("Publicación automática se activa en el siguiente paso, después de revisar S3 y el token.")
