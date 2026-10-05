import mimetypes
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from paperloom.bootstrap.app import create_app
from paperloom.bootstrap.config import AppSettings, Settings

# 유료 모델 API 키가 환경에 있어도 앱 동작이 바뀌면 안 된다 (IMPL §12 비용 경계).
PAID_API_ENV_VARS = ["OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GOOGLE_API_KEY", "GEMINI_API_KEY", "COHERE_API_KEY"]


def make_settings(tmp_path: Path, web_dist_dir: Path | None = None) -> Settings:
    return Settings(app=AppSettings(mode="test", data_dir=tmp_path / "data", web_dist_dir=web_dist_dir))


def test_health_reports_local_state_and_creates_data_dir(tmp_path):
    client = TestClient(create_app(make_settings(tmp_path)))

    response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "version": "0.1.0",
        "mode": "test",
        "cost_policy": "plan_only",
        "data_dir_writable": True,
        "claude_code_url": "http://127.0.0.1:8001",  # Reader 대화 탭의 브리지 주소 (ADR 0003)
    }
    assert (tmp_path / "data").is_dir()


def test_paid_api_env_vars_do_not_change_behaviour(tmp_path, monkeypatch):
    baseline = TestClient(create_app(make_settings(tmp_path))).get("/api/v1/health").json()
    for name in PAID_API_ENV_VARS:
        monkeypatch.setenv(name, "sk-should-be-ignored")

    with_keys = TestClient(create_app(make_settings(tmp_path))).get("/api/v1/health").json()

    assert with_keys == baseline


def test_ai_host_sharing_api_is_gone(tmp_path):
    """MCP 어댑터와 AI 호스트 공유(W07)는 2026-10-05 사용자 요청으로 뺐다(Reader 대화는 Claude Code 브리지가 한다)."""
    client = TestClient(create_app(make_settings(tmp_path)))
    for path in ("/api/v1/host-connections", "/api/v1/share-grants", "/api/v1/host/packets"):
        assert client.get(path).status_code == 404, path


@pytest.fixture
def web_dist(tmp_path: Path) -> Path:
    dist = tmp_path / "web"
    dist.mkdir()
    (dist / "index.html").write_text("<!doctype html><title>Paperloom</title>", encoding="utf-8")
    return dist


def test_built_web_is_served_without_shadowing_api(tmp_path, web_dist):
    client = TestClient(create_app(make_settings(tmp_path, web_dist_dir=web_dist)))

    assert "<title>Paperloom</title>" in client.get("/").text
    assert client.get("/api/v1/health").json()["status"] == "ok"


def test_the_web_page_is_revalidated_every_time_but_hashed_assets_are_not(tmp_path, web_dist):
    """다시 빌드한 뒤 새로고침하면 새 웹앱을 받는다(2026-10-03 사용자 확인: 옛 화면이 새 번역 표시를 글자 그대로 보였다).
    index.html은 매번 서버에 묻게 하고, 이름에 해시가 든 assets는 그대로 둔다."""
    (web_dist / "assets").mkdir()
    (web_dist / "assets" / "index-abc123.js").write_text("console.log(1)", encoding="utf-8")
    client = TestClient(create_app(make_settings(tmp_path, web_dist_dir=web_dist)))
    for path in ("/", "/reader/some-paper?version=v", "/answers"):
        response = client.get(path)
        assert "<title>Paperloom</title>" in response.text
        assert response.headers["cache-control"] == "no-cache", path
    assert "cache-control" not in client.get("/assets/index-abc123.js").headers


@pytest.mark.parametrize("name", ["index-abc123.js", "pdf.worker.min-abc123.mjs"])
def test_scripts_are_served_as_javascript_even_if_the_registry_says_otherwise(tmp_path, web_dist, monkeypatch, name):
    """정적 파일 형식은 mimetypes가 정하고, Windows에서는 레지스트리 값이 기본값을 덮어쓴다. .mjs가 JS가 아니면 브라우저가
    PDF.js worker(module)를 거부해 PDF를 열지 못한다(2026-10-05 GitHub Actions Windows E2E의 실패와 같은 모습)."""
    if not mimetypes.inited:
        mimetypes.init()
    monkeypatch.setitem(mimetypes.types_map, ".js", "text/plain")
    monkeypatch.setitem(mimetypes.types_map, ".mjs", "text/plain")
    (web_dist / "assets").mkdir()
    (web_dist / "assets" / name).write_text("export {}", encoding="utf-8")
    client = TestClient(create_app(make_settings(tmp_path, web_dist_dir=web_dist)))

    assert client.get(f"/assets/{name}").headers["content-type"].startswith("text/javascript")
