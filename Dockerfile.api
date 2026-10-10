FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PUBLIC_DEMO=true PORT=8000
WORKDIR /srv/emblemlab
COPY services/api/requirements.lock.txt /tmp/requirements.lock.txt
RUN pip install --no-cache-dir -r /tmp/requirements.lock.txt
COPY services/api/app services/api/app
COPY data/catalogs data/catalogs
# Non-root runtime; the public profile blocks database/import routes.
RUN useradd --uid 10001 --create-home preview && chown -R preview:preview /srv/emblemlab
USER preview
WORKDIR /srv/emblemlab/services/api
EXPOSE 8000
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1"]
