FROM python:3.12-slim

# Uygulama root olarak calismaz. UID 1000 = host'taki gelistirici kullanicisi: bind mount edilen
# backend/uploads klasorune yazilan dosyalar host'ta da ayni kullaniciya ait olur.
ARG APP_UID=1000
ARG APP_GID=1000
RUN groupadd -g ${APP_GID} app && useradd -m -u ${APP_UID} -g app app

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Yuklenen belgeler (compose'da bind mount) ve log klasoru (logging_config: /logs) uygulama kullanicisina ait
RUN mkdir -p /app/uploads /logs && chown -R app:app /app /logs

USER app

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
