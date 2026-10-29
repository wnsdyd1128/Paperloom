"""설치 계약: Windows 압축본(ops/bundle/build.py)이 잠금 파일·Docker 이미지·실행기와 맞아야 한다 (2026-10-29).

압축본은 잠금 파일(requirements.lock)의 wheel을 그대로 넣으므로 그 잠금을 만든 Python과 같은 판(3.13)이어야 한다.
Paperloom.cmd는 cmd가 바르게 읽도록 ASCII·CRLF로 쓰고, 압축본의 설정으로 실행기를 부른다.
"""

import importlib.util
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def build_script():
    spec = importlib.util.spec_from_file_location("bundle_build", REPO_ROOT / "ops" / "bundle" / "build.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_bundle_python_is_the_python_of_the_locks_and_the_image():
    build = build_script()
    for lock in ("requirements.lock", "requirements-dev.lock"):
        text = (REPO_ROOT / "backend" / lock).read_text(encoding="utf-8")
        assert re.search(r"pip-compile with Python (\d+\.\d+)", text).group(1) == build.PYTHON_MINOR, lock
    dockerfile = (REPO_ROOT / "ops" / "compose" / "Dockerfile").read_text(encoding="utf-8")
    assert re.search(r"^FROM python:(\d+\.\d+)-slim", dockerfile, re.MULTILINE).group(1) == build.PYTHON_MINOR
    assert build.PYTHON_URL.startswith("https://api.nuget.org/") and re.fullmatch(r"[0-9a-f]{64}", build.PYTHON_SHA256)


def test_the_launcher_script_is_ascii_crlf_and_starts_the_launcher_with_the_bundle_config():
    launcher = build_script().LAUNCHER
    launcher.encode("ascii")
    assert "\n" not in launcher.replace("\r\n", "")
    assert '-m paperloom.launcher --config "%~dp0config\\paperloom.yaml"' in launcher
    assert importlib.util.find_spec("paperloom.launcher") is not None
