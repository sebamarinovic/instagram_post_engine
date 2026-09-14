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

**Opción A — desde la app (recomendado):**
```powershell
streamlit run app.py
```
Abre la página **⚙️ Fuentes multimedia** (menú lateral). Ahí agregas cada carpeta
de fotos/videos por nombre y ruta, y por cada una puedes: activarla/desactivarla,
o actualizarla con alguno de estos dos botones:

- **🔄 Actualizar biblioteca** — incremental: detecta archivos nuevos, modificados
  (mtime cambió) y eliminados desde el último escaneo, y solo reprocesa esos. Si
  una carpeta ya tenía 3.000 fotos indexadas y agregaste 20, no vuelve a analizar
  las 3.000.
- **♻️ Reconstruir índice completo** — reanaliza todo desde cero; úsala solo si
  sospechas que el índice quedó inconsistente.

No hace falta tocar código ni terminal para cambiar de carpeta o agregar una nueva
(ej. un backup de Instagram, tu librería de iCloud, un álbum de viajes en otro disco).
Los datos de fuentes viven en `config/media_sources.json` (no se sube a git: es
específico de tu equipo — usa `config/media_sources.example.json` como referencia
del formato).

Cada archivo se identifica además por el SHA-256 de su contenido (`content_hash`),
no solo por su ruta. Si la misma foto existe en dos carpetas (ej. tu backup de
Instagram y tu librería de iCloud), el motor de publicación la detecta como una
sola y solo ofrece la mejor copia — y una foto ya publicada se sigue reconociendo
como publicada aunque después la muevas o la renombres.

**Opción B — por terminal (una sola carpeta, sin registrar fuente):**
```powershell
python scan_media.py --root "C:\Users\sebam\Pictures\iCloud Photos"
```

Con 100k+ archivos puede tardar bastante. Es normal.
Cualquiera de las dos opciones genera/actualiza `data/media_index.csv`.

## 3. Enriquecer con ubicación
Desde la misma página **⚙️ Fuentes multimedia**, botón "🌍 Recalcular ubicación",
o por terminal:
```powershell
python enrich_locations.py
```

Genera `data/media_geo.csv`: país/ciudad por GPS exacto o por inferencia temporal
(±12 h) cuando no hay GPS, más `date_source`/`location_source` para filtrar por
confiabilidad del dato. Corre esto cada vez que agregues fotos nuevas.

## 4. Publicar
```powershell
streamlit run app.py
```

En la página principal filtras por país/ciudad/año/tipo, seleccionas material,
generas 3 propuestas de caption con IA, revisas y publicas — con historial para
no repetir contenido. Las fuentes desactivadas en "⚙️ Fuentes multimedia" no
aparecen aquí.

Si seleccionas más de 10 elementos, aparece un botón **✨ Seleccionar
automáticamente las mejores 10**: agrupa fotos casi idénticas (por similitud
perceptual) y se queda con la de mejor calidad de cada grupo, y reparte el
resto entre fecha/lugar en vez de tomar simplemente las 10 primeras. Después
muestra qué quedó fuera y por qué.

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

## 8. Modo prueba (DRY_RUN)
```text
DRY_RUN=true
```
Con `DRY_RUN=true` (el valor por defecto en `.env.example`), el botón de
publicar se convierte en "🧪 SIMULAR PUBLICACIÓN": no se llama a la API de
Instagram ni se sube nada a S3, no hace falta tener credenciales configuradas,
y el resultado simulado igual se registra en el historial (marcado con
`source=dry_run`) para que puedas probar todo el flujo — selección, límite de
10, generación de caption, "ya publicada" — sin publicar nada de verdad.
Pon `DRY_RUN=false` solo cuando quieras publicar en serio.

## 9. Historial de publicaciones
En la app, el expander **📚 Historial de publicaciones** agrupa las fotos por
publicación (una fila por post, no por foto): fecha, cantidad de fotos,
país/ciudad, caption, ID de Instagram y un link para abrir el post real
(cuando existe). Se puede buscar por texto y filtrar por país, exportar a
CSV, y hay un detalle por foto individual si lo necesitas.

## 10. Base de datos (opcional, todavía no activa)
Hoy todo vive en CSV/JSON bajo `data/` y `config/` — la app sigue leyendo y
escribiendo esos archivos exclusivamente. Hay un esquema SQLite listo
(`db.py`: tablas `media`, `sources`, `publications`, `publication_media`,
`settings`) y un script de migración que puedes correr cuando quieras
probarlo, sin ningún riesgo:

```powershell
python migrate_to_sqlite.py
```

Esto: hace backup de tus CSV/JSON actuales en
`data/backup_pre_sqlite_<fecha>/`, crea/actualiza `data/instagram_rebuild.db`,
y valida la migración (conteos + spot-check de filas al azar) imprimiendo un
reporte. **No borra ni modifica los archivos originales**, y la app no lee de
esta base de datos todavía — es un paso separado y deliberado, para cuando
decidas que vale la pena el cambio (por ejemplo si tu fototeca crece lo
suficiente como para que leer el CSV completo en cada interacción de
Streamlit empiece a notarse). Puedes correrlo las veces que quieras: es
idempotente, no duplica filas.

## 11. Login con Google (Etapa Cloud A)
La app ahora exige iniciar sesión con Google antes de mostrar nada — pensado
para cuando esté accesible por internet, no solo en tu PC. Solo las cuentas
que pongas en `ALLOWED_GOOGLE_EMAILS` (en `.env`) pueden entrar, aunque el
login con Google sea exitoso.

**Crear el cliente OAuth (una sola vez), en [Google Cloud Console](https://console.cloud.google.com/):**
1. Crea un proyecto nuevo (o usa uno existente).
2. **APIs & Services → OAuth consent screen**: tipo "External", completa
   nombre de la app y tu correo. En "Test users" (mientras la app no esté
   verificada por Google) agrega tu propio correo — si no, Google no te
   deja iniciar sesión ni a ti mismo.
3. **APIs & Services → Credentials → Create Credentials → OAuth client ID**:
   tipo "Web application".
4. En **Authorized redirect URIs** agrega, por ahora:
   - `http://localhost:8501/oauth2callback` (para probar en tu PC)
   - más adelante, cuando esté desplegada: `https://tu-dominio.com/oauth2callback`
5. Guarda el **Client ID** y el **Client secret** que te muestra.

**Configurar la app localmente:**
```powershell
mkdir .streamlit
copy .streamlit\secrets.toml.example .streamlit\secrets.toml
```
Edita `.streamlit/secrets.toml` con el Client ID/secret del paso anterior, y
genera un `cookie_secret` random:
```powershell
python -c "import secrets; print(secrets.token_hex(32))"
```
En `.env`, agrega tu correo a `ALLOWED_GOOGLE_EMAILS` (el mismo que agregaste
como "test user" en el paso 2). `.streamlit/secrets.toml` **nunca se sube a
git** (ya está en `.gitignore`).

```powershell
streamlit run app.py
```
Debería pedirte iniciar sesión con Google antes de mostrar cualquier cosa. Si
entras con una cuenta que no está en `ALLOWED_GOOGLE_EMAILS`, la app te lo
dice y no te deja pasar.

## 12. Subir fotos desde el celular (Etapa Cloud B)
Página **📤 Subir desde el celular** (menú lateral): elige fotos/videos desde
la galería de tu teléfono y se suben directo al servidor donde corre la app —
no hace falta S3 ni ninguna configuración extra para esto. Quedan guardadas
en `data/uploads/` (una carpeta más, gestionada como cualquier otra fuente:
aparece también en **⚙️ Fuentes multimedia**) y se procesan igual que el
resto: EXIF, GPS, miniatura, `content_hash`. Si subes la misma foto dos
veces no se duplica ni se reprocesa.

Después de subir, toca **🌍 Actualizar ubicación** (ahí mismo, o en
Fuentes multimedia) para que aparezcan con país/ciudad en el motor
principal. El límite de subida por archivo es 1 GB (`.streamlit/config.toml`
— súbelo si necesitas videos más pesados).

Esto **no mueve tu fototeca existente a la nube** — tus carpetas locales
(iCloud, backups) siguen tal cual. Migrar todo lo demás a S3 es la etapa
siguiente (Etapa Cloud D), separada de esta.

## 13. Desplegar en un servidor (Etapa Cloud C)
Todo lo anterior corre en tu PC. Para que la app tenga una URL de verdad
(accesible desde el celular en cualquier red, no solo la de tu casa),
se empaqueta con Docker y se levanta en una instancia de AWS.

**Importante sobre el login de Google**: fuera de `localhost`, Google exige
que el `redirect_uri` sea HTTPS. Por eso el despliegue incluye
[Caddy](https://caddyserver.com/) como proxy — consigue el certificado HTTPS
automáticamente (Let's Encrypt) apenas tu dominio apunte al servidor. Sin
dominio + HTTPS, el login no va a funcionar en producción.

**1. Crear el servidor** (recomendado: [Lightsail](https://lightsail.aws.amazon.com/),
más simple que EC2 para este caso):
- Instancia Ubuntu 22.04+, el plan más chico alcanza (esto no es pesado en CPU).
- En el firewall de la instancia, abre los puertos **80**, **443** y **22**.
- Anota la IP pública fija que te asigna.

**2. Apuntar tu dominio**: crea un registro **A** apuntando tu dominio (o
subdominio, ej. `fotos.tudominio.com`) a esa IP pública. Espera a que
propague (unos minutos a un par de horas).

**3. Preparar el servidor** (por SSH):
```bash
sudo apt update && sudo apt install -y git
git clone https://github.com/sebamarinovic/instagram_post_engine.git
cd instagram_post_engine
git checkout claude/instagram-rebuild-refactor-yhaanw   # o main, una vez mergeado el PR

cp .env.example .env                                   # completa con tus credenciales reales
mkdir -p .streamlit
cp .streamlit/secrets.toml.example .streamlit/secrets.toml   # completa con tu OAuth client de la Etapa A
cp Caddyfile.example Caddyfile                          # cambia "tu-dominio.com" por el real

./deploy.sh
```
`deploy.sh` instala Docker si falta, valida que los 3 archivos anteriores
existan, y levanta todo (`docker compose up -d --build`). Con Docker ya
instalado, un despliegue nuevo es un solo comando: `./deploy.sh`.

**4. Verificar**: entra a `https://tu-dominio.com` desde el celular. Debería
pedirte login de Google (candado válido, sin advertencias del navegador).

**Actualizar la app** (tras un cambio de código): `git pull && ./deploy.sh`
(reconstruye solo lo que cambió). Tus fotos, índice y config **no se
pierden** entre despliegues — `data/` y `config/` están montados como
volúmenes del host, no viven dentro del contenedor.

**Costo aproximado**: instancia Lightsail chica desde US$5/mes. El resto
(dominio, Caddy) no tiene costo adicional — Let's Encrypt es gratis.

## Estrategia recomendada
1. PC filtra 100k+ archivos.
2. Filtras por país/ciudad/año hasta llegar a un puñado de candidatos.
3. Tú marcas 5-10.
4. IA genera orden, caption y concepto.
5. Tú apruebas.
6. Publicador sube temporalmente a S3.
7. Instagram API publica.

No automatices `IA -> publicar` sin aprobación durante las primeras semanas.
