# syntax=docker/dockerfile:1
# 빌드 컨텍스트는 저장소 루트다 (ops/compose/compose.yaml).

FROM node:22-alpine AS web
WORKDIR /web
COPY apps/web/package.json apps/web/package-lock.json ./
RUN npm ci --no-fund --no-audit
COPY apps/web/ ./
RUN npm run build

FROM python:3.13-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PAPERLOOM_CONFIG=/app/config/paperloom.yaml
WORKDIR /app
COPY backend/requirements.lock ./
RUN pip install --no-cache-dir --require-hashes --no-deps -r requirements.lock
COPY backend/ ./backend/
RUN pip install --no-cache-dir --no-deps ./backend && rm -rf ./backend
COPY ops/config/docker.yaml /app/config/paperloom.yaml
COPY --from=web /web/dist /app/web
# named volume이 처음 만들어질 때 /data의 소유자를 이어받도록 이미지에서 먼저 만든다.
RUN useradd --system --uid 10001 paperloom && mkdir /data && chown paperloom /data
USER paperloom
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health', timeout=3)"]
CMD ["python", "-m", "paperloom"]
