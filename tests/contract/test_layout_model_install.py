"""설치 계약: 문서 레이아웃 모델(documents.layout_model)의 이미지·잠금 파일이 코드와 맞아야 한다 (2026-10-19). 글줄 인식 모델
(documents.ocr_model)과 그 글자 사전도 이미지에 넣는다 (2026-10-21).

Docker 이미지는 빌드할 때 모델을 받아 sha256을 확인한다. 주소·해시가 코드와 다르면 다른 모델을 쓰거나 빌드가 깨진다.
CPU·GPU 잠금 파일은 둘 중 하나의 onnxruntime만 깔고(같은 모듈을 준다), GPU 잠금의 CUDA 판은 코드가 찾는 판이다.
"""

import re
import subprocess
import sys
from pathlib import Path, PurePosixPath

import yaml

from paperloom.documents import ocr_model
from paperloom.documents.layout_model import MODEL_SHA256, MODEL_URL
from paperloom.infrastructure.onnx_models import CUDA_MAJOR

REPO_ROOT = Path(__file__).resolve().parents[2]


def pins(lock: str) -> dict[str, str]:
    text = (REPO_ROOT / "backend" / lock).read_text(encoding="utf-8")
    return {name.lower(): version for name, version in re.findall(r"^([A-Za-z0-9][A-Za-z0-9._-]*)==(\S+)", text, re.MULTILINE)}


def test_the_image_downloads_the_models_the_code_expects_where_the_config_points():
    dockerfile = (REPO_ROOT / "ops" / "compose" / "Dockerfile").read_text(encoding="utf-8")
    added = re.findall(r"^ADD --checksum=sha256:(\w+) [^\n]*\\\n\s+(\S+) \\\n\s+(\S+)$", dockerfile, re.MULTILINE)
    expected = {MODEL_URL: MODEL_SHA256, ocr_model.MODEL_URL: ocr_model.MODEL_SHA256, ocr_model.DICTIONARY_URL: ocr_model.DICTIONARY_SHA256}
    assert {url: checksum for checksum, url, _ in added} == expected
    destination = {url: PurePosixPath(path) for _, url, path in added}
    config = yaml.safe_load((REPO_ROOT / "ops" / "config" / "docker.yaml").read_text(encoding="utf-8"))
    assert PurePosixPath(config["layout"]["model_path"]) == destination[MODEL_URL]
    assert PurePosixPath(config["ocr"]["model_path"]) == destination[ocr_model.MODEL_URL]
    assert destination[ocr_model.DICTIONARY_URL] == destination[ocr_model.MODEL_URL].with_name("inference.yml")  # 글자 사전은 모델 옆


def test_onnxruntime_is_imported_only_after_its_telemetry_is_turned_off():
    """onnxruntime(리눅스 1.31)은 Microsoft 수집 서버로 사용 통계를 보낸다. 불러오기 전에 ORT_DISABLE_TELEMETRY가 있어야 멈춘다
    (2026-10-19 컨테이너의 연결로 확인, disable_telemetry_events()로는 멈추지 않았다). 그래서 onnxruntime은 그 변수를 두는
    infrastructure.onnx_models만 불러온다(레이아웃·글줄 인식 모델이 함께 쓴다)."""
    importers = [
        path.name
        for path in (REPO_ROOT / "backend" / "src").rglob("*.py")
        if re.search(r"^\s*(?:import|from) onnxruntime", path.read_text(encoding="utf-8"), re.MULTILINE)
    ]
    assert importers == ["onnx_models.py"]
    probe = "import os, sys, paperloom.infrastructure.onnx_models; print(os.environ['ORT_DISABLE_TELEMETRY'], 'onnxruntime' in sys.modules)"
    result = subprocess.run([sys.executable, "-c", probe], capture_output=True, text=True, check=True)
    assert result.stdout.split() == ["1", "False"]  # 모듈을 불러오면 꺼지고, onnxruntime은 아직 불러오지 않았다


def test_cpu_and_gpu_locks_install_one_onnxruntime_of_the_same_version():
    cpu, dev, gpu = pins("requirements.lock"), pins("requirements-dev.lock"), pins("requirements-gpu.lock")
    assert "onnxruntime-gpu" not in cpu and "onnxruntime-gpu" not in dev and "onnxruntime" not in gpu
    assert cpu["onnxruntime"] == dev["onnxruntime"] == gpu["onnxruntime-gpu"]
    assert gpu["nvidia-cuda-runtime"].split(".")[0] == str(CUDA_MAJOR)
    shared = set(cpu) - {"onnxruntime"}
    assert {name: gpu.get(name) for name in shared} == {name: cpu[name] for name in shared}  # 나머지는 같은 판
