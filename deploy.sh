#!/usr/bin/env bash
# Run this on the Lightsail/EC2 instance, from the repo root, after
# copying .env.example -> .env, .streamlit/secrets.toml.example ->
# .streamlit/secrets.toml, and Caddyfile.example -> Caddyfile (and filling
# in real values in all three). See README, "Etapa Cloud C".
set -euo pipefail
cd "$(dirname "$0")"

if ! command -v docker &> /dev/null; then
    echo "Docker no está instalado. Instalando (requiere sudo)..."
    curl -fsSL https://get.docker.com | sh
    sudo usermod -aG docker "$USER"
    echo
    echo "Docker instalado. Cierra la sesión SSH, vuelve a entrar (para que el"
    echo "grupo 'docker' tome efecto) y vuelve a correr ./deploy.sh"
    exit 0
fi

missing=0
for f in .env .streamlit/secrets.toml Caddyfile; do
    if [ ! -f "$f" ]; then
        echo "❌ Falta $f — copia el .example correspondiente y complétalo antes de desplegar."
        missing=1
    fi
done
if [ "$missing" -eq 1 ]; then
    exit 1
fi

docker compose up -d --build

echo
echo "✅ Desplegado. Comandos útiles:"
echo "   docker compose ps              # estado de los contenedores"
echo "   docker compose logs -f app     # logs de la app en vivo"
echo "   docker compose logs -f caddy   # logs de Caddy (HTTPS/certificados)"
echo "   docker compose restart app     # reiniciar solo la app (ej. tras un cambio de código)"
echo "   docker compose down            # apagar todo"
