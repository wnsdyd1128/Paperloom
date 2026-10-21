# syntax=docker/dockerfile:1
# 빌드 컨텍스트는 저장소 루트다 (ops/compose/compose.yaml).

FROM node:22-alpine AS web
WORKDIR /web
COPY apps/web/package.json apps/web/package-lock.json ./
RUN npm ci --no-fund --no-audit
COPY apps/web/ ./
RUN npm run build

FROM python:3.13-slim AS runtime
# cpu 또는 gpu. gpu는 onnxruntime 대신 onnxruntime-gpu와 CUDA 13·cuDNN 라이브러리를 깐다(requirements-gpu.lock,
# ops/compose/compose.gpu.yaml). GPU 이미지를 GPU 없이 띄워도 레이아웃 모델은 CPU로 돈다.
ARG RUNTIME=cpu
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PAPERLOOM_CONFIG=/app/config/paperloom.yaml
WORKDIR /app
# 문서 레이아웃 모델(130MB, Apache-2.0). 주소와 sha256은 documents.layout_model의 MODEL_URL·MODEL_SHA256과 같다(tests/contract가 확인)
ADD --checksum=sha256:77afb2caa74dd13240d087d2eced91d7fcd2caebd16006a0a66162fc8707ff0e --chmod=644 \
    https://huggingface.co/PaddlePaddle/PP-DocLayout_plus-L_onnx/resolve/feb74619326f634e0e883218598096a3733ad9f7/inference.onnx \
    /app/models/pp-doclayout-plus-l/inference.onnx
# 글줄 인식(OCR) 모델(21MB)과 글자 사전(Apache-2.0). documents.ocr_model의 MODEL_URL·DICTIONARY_URL과 sha256이 같다(tests/contract)
ADD --checksum=sha256:5435fd747c9e0efe15a96d0b378d5bd157e9492ed8fd80edf08f30d02fa24634 --chmod=644 \
    https://huggingface.co/PaddlePaddle/PP-OCRv6_small_rec_onnx/resolve/b8f84f0b80c529de40b4fbb3544b84fa7233a513/inference.onnx \
    /app/models/pp-ocrv6-small-rec/inference.onnx
ADD --checksum=sha256:ab078671bb49f06228eadccd34f1bb501e157f7a047095ffb943ba81512c77d1 --chmod=644 \
    https://huggingface.co/PaddlePaddle/PP-OCRv6_small_rec_onnx/resolve/b8f84f0b80c529de40b4fbb3544b84fa7233a513/inference.yml \
    /app/models/pp-ocrv6-small-rec/inference.yml
COPY backend/requirements.lock backend/requirements-gpu.lock ./
RUN pip install --no-cache-dir --require-hashes --no-deps -r "$([ "$RUNTIME" = gpu ] && echo requirements-gpu.lock || echo requirements.lock)" \
    && rm requirements*.lock
COPY backend/ ./backend/
RUN pip install --no-cache-dir --no-deps ./backend && rm -rf ./backend
COPY ops/config/docker.yaml /app/config/paperloom.yaml
COPY --from=web /web/dist /app/web
# named volume이 처음 만들어질 때 /data의 소유자를 이어받도록 이미지에서 먼저 만든다.
# 모델 ADD의 --chmod=644가 만든 폴더에도 붙어 서버(paperloom)가 모델에 닿지 못하므로 폴더를 755로 되돌린다(2026-10-19 시험 이미지)
RUN useradd --system --uid 10001 paperloom && mkdir /data && chown paperloom /data \
    && chmod 755 /app/models /app/models/pp-doclayout-plus-l /app/models/pp-ocrv6-small-rec
USER paperloom
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health', timeout=3)"]
CMD ["python", "-m", "paperloom"]
