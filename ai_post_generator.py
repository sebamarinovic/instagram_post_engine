import base64
import json
import mimetypes
import os
from pathlib import Path
import boto3
from dotenv import load_dotenv
from openai import OpenAI

from s3_library import is_s3_uri, parse_s3_uri

load_dotenv()

def _data_url(path):
    path_str = str(path)
    mime = mimetypes.guess_type(path_str)[0] or "image/jpeg"
    if is_s3_uri(path_str):
        bucket, key = parse_s3_uri(path_str)
        raw = boto3.client("s3").get_object(Bucket=bucket, Key=key)["Body"].read()
    else:
        raw = Path(path_str).read_bytes()
    data = base64.b64encode(raw).decode("utf-8")
    return f"data:{mime};base64,{data}"

def _thumb_available(thumb):
    return isinstance(thumb, str) and (is_s3_uri(thumb) or Path(thumb).exists())

def _clean_json(text):
    text = text.strip()
    if text.startswith("```json"):
        text = text[7:]
    elif text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    return text.strip()

def generate_post(selected_rows, creative_context):
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("Falta OPENAI_API_KEY en .env")

    model = os.getenv("OPENAI_MODEL", "gpt-5.6-luna")
    client = OpenAI(api_key=api_key)

    profile_context = creative_context.get("profile_context", "")
    experience_context = creative_context.get("experience_context", "")
    intention = creative_context.get("intention", "")
    tone = creative_context.get("tone", "Natural")
    length = creative_context.get("length", "Media")
    emoji_level = creative_context.get("emoji_level", "Medio")
    language = creative_context.get("language", "Español")
    avoid = creative_context.get("avoid", "")
    extra = creative_context.get("extra", "")

    prompt = f'''
Eres editor creativo de un feed personal de Instagram.
No describas literalmente cada foto. Encuentra la historia común.

PERFIL DEL AUTOR
{profile_context}

CONTEXTO DE ESTA EXPERIENCIA
{experience_context}

QUÉ QUIERE TRANSMITIR
{intention}

PREFERENCIAS
- Idioma: {language}
- Tono principal: {tone}
- Extensión: {length}
- Nivel de emojis: {emoji_level}
- Evitar: {avoid}
- Instrucción adicional: {extra}

REGLAS
- Mira las imágenes: usa lo que se ve (playa, montaña, comida, atardecer,
  actividad, ambiente) para describir la situación con naturalidad.
- No inventes hechos, relaciones, emociones, fechas ni lugares que no
  respalden ni la imagen ni los metadatos.
- Usa lugares y fechas solo si los metadatos los respaldan.
- Si el GPS es inferido, no presentes el lugar como exacto.
- No identifiques personas.
- No conviertas el texto en CV ni publicidad.
- Profesión, raíces, hobbies y emprendimiento son contexto de voz, no contenido obligatorio.
- Evita clichés y lenguaje demasiado inspiracional.
- Prioriza naturalidad y memoria personal.
- Máximo 10 elementos.
- Si la selección no es coherente, dilo.
- Usa pocos hashtags.
- Devuelve SOLO JSON válido.

{{
  "decision": "publish|revise_selection",
  "concept": "...",
  "title_internal": "...",
  "recommended_order": [1,2,3],
  "cover_index": 1,
  "location": "...",
  "country": "...",
  "city": "...",
  "year": "...",
  "music_search": "...",
  "story_hook": "...",
  "hashtags": ["..."],
  "why_this_order": "...",
  "selection_feedback": "...",
  "caption_options": [
    {{"label":"Natural","caption":"...","why":"..."}},
    {{"label":"Emotiva","caption":"...","why":"..."}},
    {{"label":"Minimalista","caption":"...","why":"..."}}
  ]
}}
'''

    content = [{"type": "input_text", "text": prompt}]
    for i, row in enumerate(selected_rows[:10], start=1):
        meta = {
            "index": i,
            "filename": row.get("filename"),
            "captured_at": str(row.get("captured_at")),
            "country": row.get("country"),
            "city": row.get("city"),
            "location_source": row.get("location_source"),
            "date_source": row.get("date_source"),
            "quality_score": row.get("quality_score"),
            "media_type": row.get("media_type"),
        }
        content.append({"type":"input_text","text":f"ELEMENTO {i} METADATOS: {json.dumps(meta, ensure_ascii=False)}"})
        thumb = row.get("thumb_path")
        if _thumb_available(thumb) and row.get("media_type") == "image":
            content.append({"type":"input_image","image_url":_data_url(thumb),"detail":"low"})

    response = client.responses.create(
        model=model,
        input=[{"role":"user","content":content}],
        store=False,
        max_output_tokens=2600
    )
    return json.loads(_clean_json(response.output_text))
