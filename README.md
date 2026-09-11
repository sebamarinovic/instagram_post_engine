# Instagram Rebuild MVP

Objetivo: convertir una fototeca grande de iCloud en candidatos publicables sin revisar archivo por archivo.

## 0. Antes de comenzar
Asegúrate de que las fotos/videos estén descargados localmente ("Mantener siempre en este dispositivo").
No trabajes con placeholders de iCloud.

Instala Python 3.11+ y, para videos, FFmpeg:
- https://www.ffmpeg.org/

## 1. Crear entorno
En PowerShell:

```powershell
cd C:\ruta\instagram_rebuild_mvp
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
```

## 2. Escanear la biblioteca
Ejemplo:

```powershell
python scan_media.py --root "C:\Users\sebam\Pictures\iCloud Photos"
```

Con 100k+ archivos puede tardar bastante. Es normal.
Se genera `data/media_index.csv`.

## 3. Enriquecer con ubicación
```powershell
python enrich_locations.py
```

Genera `data/media_geo.csv`: país/ciudad por GPS exacto o por inferencia temporal
(±12 h) cuando no hay GPS, más `date_source`/`location_source` para filtrar por
confiabilidad del dato.

## 4. Abrir el motor de publicación
```powershell
streamlit run app.py
```

Ahí filtras por país/ciudad/año/tipo, seleccionas material, generas 3 propuestas
de caption con IA, revisas y publicas — con historial para no repetir contenido.

## 5. IA opcional
Crea una API key en tu proveedor y colócala en `.env`:

```text
OPENAI_API_KEY=...
OPENAI_MODEL=gpt-5.6-luna
```

El dashboard envía únicamente miniaturas seleccionadas, no toda la fototeca.
La API de Responses admite imágenes de entrada y devuelve el borrador de caption/orden.

## 6. Instagram
Nunca pongas tokens en el código ni en GitHub.

```text
INSTAGRAM_ACCESS_TOKEN=...
INSTAGRAM_USER_ID=...
```

## 7. AWS S3
Para publicar, Instagram necesita poder descargar el archivo por HTTPS.
El módulo `publisher.py` sube el archivo a S3 y genera una URL firmada temporal.

Completa:
```text
AWS_ACCESS_KEY_ID=
AWS_SECRET_ACCESS_KEY=
AWS_DEFAULT_REGION=
S3_BUCKET=
```

## Estrategia recomendada
1. PC filtra 100k+ archivos.
2. Filtras por país/ciudad/año hasta llegar a un puñado de candidatos.
3. Tú marcas 5-10.
4. IA genera orden, caption y concepto.
5. Tú apruebas.
6. Publicador sube temporalmente a S3.
7. Instagram API publica.

No automatices `IA -> publicar` sin aprobación durante las primeras semanas.
