# syntax=docker/dockerfile:1

ARG PYTHON_VERSION=3.13
FROM python:${PYTHON_VERSION}-bookworm AS builder

RUN apt-get update && apt-get install -y \
    build-essential \
    libgdal-dev \
    libproj-dev \
    libgeos-dev \
    libspatialindex-dev \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# COPY só requirements e gere wheels (wheelhouse)
COPY requirements.txt .
RUN pip install --upgrade pip wheel && \
    pip wheel --no-cache-dir --wheel-dir=/wheels -r requirements.txt

# Instala as wheels locais (sem baixar da internet)
RUN pip install --no-index --find-links=/wheels -r requirements.txt

# Copia o código
COPY . .

ENV DJANGO_SETTINGS_MODULE=config.settings \
    DJANGO_SECRET_KEY='temp-key-for-build' \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

RUN python manage.py collectstatic --noinput || echo "Collectstatic skipped"

# ================= Runtime =================
FROM python:${PYTHON_VERSION}-slim-bookworm AS runtime

RUN apt-get update && apt-get install -y \
    libgdal32 \
    libproj25 \
    libgeos-c1v5 \
    libspatialindex6 \
    libpq5 \
    libmagic1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY --from=builder /usr/local/lib/python3.13/site-packages /usr/local/lib/python3.13/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin
COPY --from=builder /app /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

EXPOSE 5000

CMD gunicorn --bind 0.0.0.0:$PORT --timeout 120 config.wsgi:application