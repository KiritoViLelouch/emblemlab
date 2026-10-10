FROM node:24-slim AS web
WORKDIR /web
COPY apps/web/package.json apps/web/package-lock.json ./
RUN npm ci
COPY apps/web/ ./
RUN STATIC_EXPORT=true NEXT_PUBLIC_PUBLIC_DEMO=true NEXT_PUBLIC_API_URL=same-origin npm run build

FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PUBLIC_DEMO=true PORT=8000
WORKDIR /srv/emblemlab
COPY services/api/requirements.lock.txt /tmp/requirements.lock.txt
RUN pip install --no-cache-dir -r /tmp/requirements.lock.txt
COPY services/api/app services/api/app
COPY data/catalogs data/catalogs
COPY data/active data/active
COPY data/approved data/approved
COPY data/meta data/meta
COPY --from=web /web/.next-export /srv/emblemlab/public
ENV PUBLIC_WEB_DIR=/srv/emblemlab/public
# Non-root runtime; the public profile blocks database/import routes.
RUN useradd --uid 10001 --create-home preview && chown -R preview:preview /srv/emblemlab
USER preview
WORKDIR /srv/emblemlab/services/api
EXPOSE 8000
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1"]
