#!/bin/sh
# Inicialização em produção (Render): aplica migrations e sobe o Gunicorn na porta do serviço.
set -e
python manage.py migrate --noinput
# Opcional: base de demonstração em banco vazio (LABTECH_CARREGAR_DEMO=true).
if [ "${LABTECH_CARREGAR_DEMO:-false}" = "true" ]; then
  python manage.py carregar_demo
fi
exec gunicorn config.wsgi:application --bind "0.0.0.0:${PORT:-8000}" --workers "${WEB_CONCURRENCY:-2}" --timeout 60
