import base64
import json
import mimetypes
import os
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

def to_data_url(path):
    path = Path(path)
    mime = mimetypes.guess_type(path.name)[0] or "image/jpeg"
    data = base64.b64encode(path.read_bytes()).decode()
    return f"data:{mime};base64,{data}"

def generate_draft(image_paths, metadata=None):
    if not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError("Falta OPENAI_API_KEY en .env")

    client = OpenAI()
    model = os.getenv("OPENAI_MODEL", "gpt-5.6-luna")

    content = [{
        "type": "input_text",
        "text": f"""
Analiza estas imágenes como candidatas para reconstruir un feed personal de Instagram.
Contexto de la experiencia: {json.dumps(metadata or {}, ensure_ascii=False)}

Devuelve SOLO JSON válido con:
{{
  "theme": "...",
  "post_type": "carousel|single|reel_candidate",
  "recommended_order": [1,2,3],
  "cover_index": 1,
  "caption_es": "...",
  "short_caption_es": "...",
  "location_label": "...",
  "hashtags": ["..."],
  "music_mood": "...",
  "why": "..."
}}

Tono: personal, sobrio, viajero, humano. No inventes hechos, relaciones ni lugares que no estén sustentados por las imágenes o metadatos.
No identifiques personas.
"""
    }]

    for p in image_paths[:10]:
        content.append({"type": "input_image", "image_url": to_data_url(p), "detail": "low"})

    r = client.responses.create(
        model=model,
        input=[{"role":"user","content":content}],
        store=False,
        max_output_tokens=1200
    )
    txt = r.output_text.strip()
    # tolerate markdown fences
    txt = txt.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    return json.loads(txt)
