FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY pyproject.toml ./
COPY config ./config
COPY apps ./apps
COPY manage.py ./
RUN python -m pip install --no-cache-dir .
RUN useradd --system --uid 10001 --no-create-home app
USER app
EXPOSE 8000
# Uso em desenvolvimento; deploy de produção exigirá servidor ASGI/WSGI.
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000", "--noreload"]
