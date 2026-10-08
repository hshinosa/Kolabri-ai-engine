# syntax=docker/dockerfile:1.6
FROM python:3.11-slim AS build

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /build

# Compile-time toolchain lives ONLY in this stage; the runtime image never
# carries build-essential (~640MB of gcc/g++/dev headers).
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        libgl1 \
        libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install --upgrade pip \
    && /opt/venv/bin/pip install --no-cache-dir -r requirements.txt

FROM python:3.11-slim AS production

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PATH="/opt/venv/bin:$PATH"

WORKDIR /app

# Runtime-only system deps: PDF/OCR processing + wget for the healthcheck.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        libgl1 \
        libglib2.0-0 \
        libgomp1 \
        poppler-utils \
        ghostscript \
        wget \
    && rm -rf /var/lib/apt/lists/*

# Unprivileged runtime user with a writable home (model/embedding caches).
RUN groupadd --system --gid 1000 app \
    && useradd --system --uid 1000 --gid app --create-home app

COPY --from=build /opt/venv /opt/venv
COPY . .

RUN mkdir -p data/chroma data/event_logs \
    && chown -R app:app /app

USER app

EXPOSE 8001

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8001"]
