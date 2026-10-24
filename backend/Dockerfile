# syntax=docker/dockerfile:1

# ---------- Stage 1: build dependencies + pre-fetch the embedding model ----------
FROM python:3.11-slim AS builder

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# Pre-download the fastembed ONNX model at BUILD time into a cache dir baked into the
# image, so container startup (and Render's spin-up) never pays a model-download cost.
ENV FASTEMBED_CACHE_PATH=/opt/fastembed_cache
RUN PYTHONPATH=/install/lib/python3.11/site-packages python -c "\
from fastembed import TextEmbedding; \
TextEmbedding(model_name='BAAI/bge-small-en-v1.5', cache_dir='/opt/fastembed_cache')"

# ---------- Stage 2: runtime ----------
FROM python:3.11-slim AS runtime

RUN groupadd --system app && useradd --system --gid app --home /app app

WORKDIR /app

COPY --from=builder /install /usr/local
COPY --from=builder /opt/fastembed_cache /opt/fastembed_cache

ENV FASTEMBED_CACHE_PATH=/opt/fastembed_cache \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

COPY app ./app
COPY alembic ./alembic
COPY alembic.ini ./alembic.ini
COPY docker-entrypoint.sh ./docker-entrypoint.sh

RUN chmod +x ./docker-entrypoint.sh && chown -R app:app /app /opt/fastembed_cache

USER app

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD python -c "import os,urllib.request; urllib.request.urlopen('http://127.0.0.1:' + os.environ.get('PORT', '8000') + '/health', timeout=3)" || exit 1

ENTRYPOINT ["./docker-entrypoint.sh"]
