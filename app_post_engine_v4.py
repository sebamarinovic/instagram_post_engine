from pathlib import Path
import hashlib, json
import pandas as pd
import streamlit as st
from ai_post_generator_v4 import generate_post
from publisher_v4 import config_status, publish_images

st.set_page_config(page_title="Instagram Rebuild V4", layout="wide")

CSV=Path("data/media_geo.csv")
PROFILE_FILE=Path("data/profile_context.json")
if not CSV.exists():
    st.error("Falta data/media_geo.csv")
    st.stop()

df=pd.read_csv(CSV)
df["captured_at"]=pd.to_datetime(df["captured_at"],errors="coerce")
df["quality_score"]=pd.to_numeric(df["quality_score"],errors="coerce").fillna(0)

DEFAULT_PROFILE = '''Sebastián. Chileno-croata 🇨🇱🇭🇷.
Ingeniero Civil Industrial con vínculo a metalurgia y procesos industriales.
Interés profesional en Data Science, inteligencia artificial y tecnología.
Hobbies: viajes, fotografía, drone/FPV, tecnología y conocer nuevos lugares.
Emprendedor y fundador de un proyecto tecnológico.
El Instagram es personal: lo profesional es contexto, no tema obligatorio.'''

profile_saved=DEFAULT_PROFILE
if PROFILE_FILE.exists():
    try:
        profile_saved=json.loads(PROFILE_FILE.read_text(encoding="utf-8")).get("profile_context",DEFAULT_PROFILE)
    except Exception:
        pass

if "selected_paths" not in st.session_state: st.session_state.selected_paths=[]
if "post_draft" not in st.session_state: st.session_state.post_draft=None

def key_for(path): return hashlib.md5(str(path).encode()).hexdigest()

def set_selected(path,key):
    s=set(st.session_state.selected_paths)
    if st.session_state.get(key): s.add(path)
    else: s.discard(path)
    st.session_state.selected_paths=list(s)

st.title("🚀 Instagram Rebuild — Motor V4")
st.caption("Explorar → seleccionar → dar contexto → obtener opciones → editar → publicar")

st.sidebar.header("🔎 Explorar")
if st.sidebar.button("🔄 Reiniciar búsqueda",use_container_width=True):
    st.session_state.clear(); st.rerun()

countries=["Todos"]+sorted(df.country.dropna().astype(str).unique())
country=st.sidebar.selectbox("🌎 País",countries)
work=df.copy()
if country!="Todos": work=work[work.country==country]

cities=["Todas"]+sorted(work.city.dropna().astype(str).unique())
city=st.sidebar.selectbox("📍 Ciudad",cities)
if city!="Todas": work=work[work.city==city]

years=sorted([int(x) for x in work.year.dropna().unique()])
year=st.sidebar.selectbox("📅 Año",["Todos"]+years)
if year!="Todos": work=work[work.year==year]

media_type=st.sidebar.selectbox("🎞️ Tipo",["Todos","image","video"])
if media_type!="Todos": work=work[work.media_type==media_type]

loc_sources=st.sidebar.multiselect("🧭 Fuente ubicación",["gps","time_inferred","none"],default=["gps","time_inferred"])
if loc_sources: work=work[work.location_source.isin(loc_sources)]

date_sources=st.sidebar.multiselect("🕒 Fuente fecha",["original_or_video","filesystem_fallback"],default=["original_or_video"])
if date_sources: work=work[work.date_source.isin(date_sources)]

if st.sidebar.button("🗑️ Limpiar selección",use_container_width=True):
    st.session_state.selected_paths=[]; st.session_state.post_draft=None; st.rerun()

c1,c2,c3,c4=st.columns(4)
c1.metric("Elementos",len(work)); c2.metric("📸 Fotos",int((work.media_type=="image").sum()))
c3.metric("🎬 Videos",int((work.media_type=="video").sum())); c4.metric("✅ Seleccionadas",len(st.session_state.selected_paths))

st.subheader("🖼️ Material")
gallery=work.sort_values(["quality_score","captured_at"],ascending=[False,True]).head(100)
cols=st.columns(5)
for pos,(_,row) in enumerate(gallery.iterrows()):
    path=str(row.path); k="cb_"+key_for(path)
    with cols[pos%5]:
        t=row.get("thumb_path")
        if isinstance(t,str) and Path(t).exists(): st.image(t,use_container_width=True)
        city_txt="" if pd.isna(row.get("city")) else str(row.get("city"))
        country_txt="" if pd.isna(row.get("country")) else str(row.get("country"))
        date="" if pd.isna(row.captured_at) else row.captured_at.strftime("%Y-%m-%d")
        st.caption(f"📍 {' · '.join([x for x in [city_txt,country_txt] if x]) or 'sin ubicación'}\n\n📅 {date}\n⭐ {row.quality_score:.0f}")
        st.checkbox("Seleccionar",key=k,value=(path in st.session_state.selected_paths),on_change=set_selected,args=(path,k))

selected_df=df[df.path.astype(str).isin(st.session_state.selected_paths)].copy()

st.divider()
st.header("🧠 Contexto antes de crear")
profile_context=st.text_area("👤 Contexto permanente del perfil",value=profile_saved,height=150)
if st.button("💾 Guardar contexto del perfil"):
    PROFILE_FILE.parent.mkdir(parents=True,exist_ok=True)
    PROFILE_FILE.write_text(json.dumps({"profile_context":profile_context},ensure_ascii=False,indent=2),encoding="utf-8")
    st.success("Guardado")

experience_context=st.text_area("🌎 ¿Qué estaba pasando en esta experiencia?",placeholder="Ej.: Primer viaje a Japón, abril de 2017...",height=100)
intention=st.text_input("💭 ¿Qué quieres transmitir?",placeholder="Ej.: nostalgia, descubrimiento, humor, volver a guardar este recuerdo...")

b1,b2,b3,b4=st.columns(4)
with b1: tone=st.selectbox("🎭 Tono",["Natural","Emotivo","Minimalista","Reflexivo","Humor sutil","Elegante"])
with b2: length=st.selectbox("📏 Extensión",["Corta","Media","Larga"],index=1)
with b3: emoji_level=st.selectbox("🙂 Emojis",["Bajo","Medio","Alto"],index=1)
with b4: language=st.selectbox("🌐 Idioma",["Español","Inglés","Español + frase en inglés"])

avoid=st.text_input("🚫 Evitar",placeholder="Ej.: sonar cursi, hablar de trabajo, hashtags genéricos...")
extra=st.text_area("➕ Instrucción extra",placeholder="Ej.: menciona que fue mi primera vez en Japón.",height=80)

if st.button("🤖 Crear 3 propuestas",type="primary",disabled=not(1<=len(selected_df)<=10),use_container_width=True):
    ctx={"profile_context":profile_context,"experience_context":experience_context,"intention":intention,"tone":tone,
         "length":length,"emoji_level":emoji_level,"language":language,"avoid":avoid,"extra":extra}
    with st.spinner("Creando propuestas..."):
        st.session_state.post_draft=generate_post(selected_df.to_dict("records"),ctx)

draft=st.session_state.post_draft
if draft:
    st.divider(); st.header("✨ Propuesta creativa")
    if draft.get("decision")=="revise_selection": st.warning("Conviene revisar la selección.")
    st.write("**Concepto:**",draft.get("concept"))
    st.write("**Portada sugerida:**",draft.get("cover_index"))
    st.write("**Orden sugerido:**",draft.get("recommended_order"))
    st.write("**Por qué:**",draft.get("why_this_order"))

    options=draft.get("caption_options",[])
    labels=[f"{i+1}. {o.get('label','Opción')}" for i,o in enumerate(options)]
    choice=st.radio("✍️ Elige una redacción",labels,horizontal=True) if labels else None
    idx=labels.index(choice) if choice else 0
    chosen=options[idx] if options else {"caption":""}
    caption_final=st.text_area("✏️ Editar caption final",value=chosen.get("caption",""),height=230,key=f"caption_{idx}")

    st.write("**🎵 Música:**",draft.get("music_search") or "—")
    st.write("**📍 Ubicación:**",draft.get("location") or "—")
    st.write("**#️⃣ Hashtags:**"," ".join(draft.get("hashtags",[])))
    st.write("**💡 Feedback:**",draft.get("selection_feedback") or "—")

    selected_records=selected_df.to_dict("records")
    order=draft.get("recommended_order") or list(range(1,len(selected_records)+1))
    ordered=[]
    for i in order:
        try: ordered.append(selected_records[int(i)-1])
        except Exception: pass
    if len(ordered)!=len(selected_records): ordered=selected_records

    st.subheader("🚀 Publicación real")
    cfg=config_status(); missing=[k for k,v in cfg.items() if not v]
    all_images=all(str(r.get("media_type"))=="image" for r in ordered)

    if missing: st.warning("Falta configurar: "+", ".join(missing))
    if not all_images: st.info("V4 publica imágenes/carruseles. Videos/Reels vendrán en el módulo siguiente.")

    confirm=st.checkbox("✅ Confirmo que revisé fotos, orden y texto y quiero publicarlo")
    ready=(not missing and all_images and 1<=len(ordered)<=10 and confirm)

    if st.button("🚀 PUBLICAR AHORA EN INSTAGRAM",type="primary",disabled=not ready,use_container_width=True):
        with st.spinner("Publicando..."):
            try:
                result=publish_images([r["path"] for r in ordered],caption_final)
                st.success("✅ Publicación realizada correctamente")
                st.json(result)
                st.session_state.selected_paths=[]
                st.session_state.post_draft=None
            except Exception as e:
                st.error(f"❌ Error al publicar: {e}")
