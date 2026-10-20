#!/bin/sh
# Paperloom을 Docker로 띄운다(Linux·macOS·Git Bash). NVIDIA GPU가 있으면 GPU 이미지로(문서 레이아웃 모델을 CUDA로), 없거나
# GPU로 띄우지 못하면 CPU 이미지로 띄운다. 데이터 volume은 같다. 실행: sh ops/start.sh
set -u
compose="$(dirname "$0")/compose"
if command -v nvidia-smi >/dev/null 2>&1 && nvidia-smi -L >/dev/null 2>&1; then
    echo "NVIDIA GPU를 찾았습니다. GPU 이미지로 띄웁니다."
    docker compose -f "$compose/compose.yaml" -f "$compose/compose.gpu.yaml" up -d --build && exit 0
    echo "GPU로 띄우지 못해 CPU 이미지로 띄웁니다." >&2
fi
exec docker compose -f "$compose/compose.yaml" up -d --build
