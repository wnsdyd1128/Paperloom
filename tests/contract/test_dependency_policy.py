"""설치 계약: 잠금 파일과 소스에 유료 모델·임베딩 SDK나 API 키 경로가 없어야 한다 (PLAN A01, IMPL §3·§12).

문자열 검사는 비용 경계의 한 층일 뿐이다. 실행 중 egress 감사는 W11에서 별도로 한다.
"""

import json
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

PAID_PYTHON_PACKAGES = {
    "openai", "anthropic", "cohere", "mistralai", "google-generativeai", "google-genai",
    "google-cloud-aiplatform", "groq", "together", "replicate", "voyageai",
    "langchain-openai", "langchain-anthropic", "langchain-google-genai", "litellm",
}
PAID_NPM_PACKAGES = {
    "openai", "@anthropic-ai/sdk", "@google/generative-ai", "@google/genai", "@mistralai/mistralai",
    "cohere-ai", "groq-sdk", "together-ai", "replicate", "@ai-sdk/openai", "@ai-sdk/anthropic",
}
PAID_API_MARKERS = re.compile(r"OPENAI_API_KEY|ANTHROPIC_API_KEY|api\.openai\.com|api\.anthropic\.com")


def python_lock_packages(lock: Path) -> set[str]:
    names = re.findall(r"^([A-Za-z0-9][A-Za-z0-9._-]*)==", lock.read_text(encoding="utf-8"), re.MULTILINE)
    return {re.sub(r"[._]", "-", name.lower()) for name in names}


def npm_lock_packages(lock: Path) -> set[str]:
    packages = json.loads(lock.read_text(encoding="utf-8"))["packages"]
    return {path.rsplit("node_modules/", 1)[1] for path in packages if "node_modules/" in path}


def test_python_locks_have_no_paid_model_sdk():
    locks = sorted((REPO_ROOT / "backend").glob("requirements*.lock"))
    assert locks, "backend 잠금 파일이 없습니다"
    for lock in locks:
        installed = python_lock_packages(lock)
        assert "fastapi" in installed  # 파싱이 실제로 동작하는지 확인
        assert installed.isdisjoint(PAID_PYTHON_PACKAGES), lock.name


def test_web_lock_has_no_paid_model_sdk():
    installed = npm_lock_packages(REPO_ROOT / "apps" / "web" / "package-lock.json")
    assert "react" in installed
    assert installed.isdisjoint(PAID_NPM_PACKAGES)


def test_sources_do_not_reference_paid_model_api_keys_or_hosts():
    sources = [*(REPO_ROOT / "backend" / "src").rglob("*.py"), *(REPO_ROOT / "apps" / "web" / "src").rglob("*.ts*")]
    assert sources
    offenders = [str(path) for path in sources if PAID_API_MARKERS.search(path.read_text(encoding="utf-8"))]
    assert offenders == []
