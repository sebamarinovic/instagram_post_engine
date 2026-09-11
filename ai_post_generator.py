import base64
import json
import mimetypes
import os
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

def _data_url(path):
    path = Path(path)
    mime = mimetypes.guess_type(path.name)[0] or "image/jpeg"
    data = base64.b64encode(path.read_bytes()).decode("utf-8")
    return f"data:{mime};base64,{data}"

def generate_post(selected_rows):
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "Falta OPENAI_API_KEY. Agrégala en el archivo .env del proyecto."
        )

    model = os.getenv("OPENAI_MODEL", "gpt-5.6-luna")
    client = OpenAI(api_key=api_key)

    rows = selected_rows[:10]
    metadata = []
    content = [{
        "type": "input_text",
        "text": """
Eres editor creativo de un feed personal de Instagram.

Analiza las imágenes seleccionadas y crea UNA propuesta de publicación coherente.

El perfil pertenece a una persona chileno-croata, ingeniero y profesional de Data Science/IA,
con foco personal en viajes, experiencias, tecnología, fotografía/drone y emprendimiento.
El tono debe ser humano, elegante, viajero y natural; nunca corporativo ni artificial.

Reglas:
- No inventes eventos, personas, relaciones ni lugares.
- Usa solo lugares/fechas presentes en los metadatos entregados.
- Si varias fotos no cuentan una historia coherente, indícalo.
- El carrusel debe tener máximo 10 imágenes.
- Prioriza narrativa sobre score técnico.
- No uses hashtags genéricos masivos.
- No identifiques personas de las fotografías.
- Caption en español, natural, breve-medio.
- Puede usar 2-5 emojis bien elegidos.
- Evita frases cliché tipo "coleccionando momentos" salvo que realmente aporte.

Devuelve SOLO JSON válido con esta estructura:

{
  "decision": "publish|revise_selection",
  "concept": "...",
  "title_internal": "...",
  "recommended_order": [1,2,3],
  "cover_index": 1,
  "caption": "...",
  "short_caption": "...",
  "location": "...",
  "year": "...",
  "country": "...",
  "city": "...",
  "hashtags": ["..."],
  "music_search": "...",
  "story_hook": "...",
  "why_this_order": "...",
  "selection_feedback": "..."
}
"""
    }]

    for i, row in enumerate(rows, start=1):
        meta = {
            "index": i,
            "filename": row.get("filename"),
            "captured_at": str(row.get("captured_at")),
            "country": row.get("country"),
            "city": row.get("city"),
            "location_source": row.get("location_source"),
            "quality_score": row.get("quality_score"),
            "media_type": row.get("media_type"),
        }
        metadata.append(meta)

        content.append({
            "type": "input_text",
            "text": f"IMAGEN {i} METADATOS: {json.dumps(meta, ensure_ascii=False)}"
        })

        img_path = row.get("thumb_path")
        if img_path and Path(str(img_path)).exists():
            content.append({
                "type": "input_image",
                "image_url": _data_url(img_path),
                "detail": "low"
            })

    response = client.responses.create(
        model=model,
        input=[{"role": "user", "content": content}],
        store=False,
        max_output_tokens=1800,
    )

    text = response.output_text.strip()
    if text.startswith("```json"):
        text = text[7:]
    elif text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]

    return json.loads(text.strip())
