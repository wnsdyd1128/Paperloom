"""아티팩트 링크 (paperloom.artifacts): 페이지 파일 쓰기, 같은 내용은 같은 링크, 격리 응답 머리, 한도, 쓰기 실패, 경로 표시."""

import hashlib
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from paperloom.artifacts import store
from paperloom.artifacts.routes import MAX_BYTES
from paperloom.bootstrap.app import create_app
from paperloom.bootstrap.config import AppSettings, ArtifactSettings, Settings

PAGE = '<!doctype html><meta charset="utf-8"><title>그림</title><p id="hello">안녕</p><script>document.title = "실행";</script>'


def _client(tmp_path: Path, shown_dir: str | None = None) -> TestClient:
    settings = Settings(app=AppSettings(mode="test", data_dir=tmp_path / "data"), artifacts=ArtifactSettings(shown_dir=shown_dir))
    return TestClient(create_app(settings))


@pytest.fixture
def client(tmp_path) -> TestClient:
    return _client(tmp_path)


def test_a_page_is_written_once_under_its_content_hash(client, tmp_path):
    created = client.post("/api/v1/artifacts", json={"html": PAGE})

    assert created.status_code == 201
    body = created.json()
    artifact_id = hashlib.sha256(PAGE.encode("utf-8")).hexdigest()[:32]
    assert body["artifact_id"] == artifact_id
    assert body["url"] == f"/artifacts/{artifact_id}"
    assert body["path"].endswith(f"data/artifacts/{artifact_id}.html")
    folder = tmp_path / "data" / "artifacts"
    assert (folder / f"{artifact_id}.html").read_bytes() == PAGE.encode("utf-8")

    again = client.post("/api/v1/artifacts", json={"html": PAGE})
    assert again.status_code == 200
    assert again.json() == body
    other = client.post("/api/v1/artifacts", json={"html": PAGE + "<p>더</p>"})
    assert other.status_code == 201 and other.json()["artifact_id"] != artifact_id
    assert sorted(path.name for path in folder.iterdir()) == sorted([f"{artifact_id}.html", f"{other.json()['artifact_id']}.html"])


def test_the_page_is_served_sandboxed_so_it_cannot_reach_paperloom(client):
    url = client.post("/api/v1/artifacts", json={"html": PAGE}).json()["url"]

    page = client.get(url)

    assert page.status_code == 200
    assert page.text == PAGE
    assert page.headers["content-type"] == "text/html; charset=utf-8"
    # 출처 없는 문서로 돈다(allow-same-origin 없음): 같은 주소의 API 응답·저장소를 읽지 못한다. 바깥에서 불러오는 것도 없다
    policy = [part.strip() for part in page.headers["content-security-policy"].split(";")]
    assert policy[0] == "sandbox allow-scripts"
    assert "default-src 'none'" in policy and "form-action 'none'" in policy and "base-uri 'none'" in policy
    assert not any("allow-same-origin" in part or "connect-src" in part for part in policy)
    assert page.headers["x-content-type-options"] == "nosniff"
    assert page.headers["referrer-policy"] == "no-referrer"


@pytest.mark.parametrize("artifact_id", ["0" * 32, "0" * 31, "A" * 32, "..%2Fpaperloom.sqlite3", ".tmp-" + "0" * 27])
def test_unknown_or_malformed_ids_are_not_found(client, artifact_id):
    client.post("/api/v1/artifacts", json={"html": PAGE})

    response = client.get(f"/artifacts/{artifact_id}")

    assert response.status_code == 404
    assert response.json()["code"] == "NOT_FOUND"


def test_a_page_over_the_limit_is_refused_and_nothing_is_written(client, tmp_path):
    response = client.post("/api/v1/artifacts", json={"html": "가" * (MAX_BYTES // 3 + 1)})  # 한 글자가 UTF-8 3바이트

    assert response.status_code == 413
    assert response.json()["code"] == "TOO_LARGE"
    assert not (tmp_path / "data" / "artifacts").exists()


@pytest.mark.parametrize("body", [{}, {"html": ""}, {"html": PAGE, "title": "그림"}])
def test_a_malformed_request_is_refused(client, body):
    response = client.post("/api/v1/artifacts", json=body)

    assert response.status_code == 422
    assert response.json()["code"] == "INVALID_REQUEST"


def test_a_folder_that_cannot_be_written_is_reported(client, tmp_path):
    (tmp_path / "data" / "artifacts").write_text("폴더 자리에 파일", encoding="utf-8")

    response = client.post("/api/v1/artifacts", json={"html": PAGE})

    assert response.status_code == 500
    body = response.json()
    assert (body["code"], body["retryable"]) == ("ARTIFACT_WRITE_FAILED", True)


def test_a_write_cut_short_leaves_no_file(client, tmp_path, monkeypatch):
    def fail(*_):
        raise OSError("디스크가 가득 참")

    monkeypatch.setattr(store.os, "replace", fail)

    response = client.post("/api/v1/artifacts", json={"html": PAGE})

    assert response.status_code == 500
    assert list((tmp_path / "data" / "artifacts").iterdir()) == []  # 임시 파일도 남지 않는다
    monkeypatch.undo()
    assert client.post("/api/v1/artifacts", json={"html": PAGE}).status_code == 201  # 고친 뒤 다시 하면 된다


def test_docker_shows_the_host_folder_instead_of_the_container_path(tmp_path):
    body = _client(tmp_path, shown_dir="var/artifacts").post("/api/v1/artifacts", json={"html": PAGE}).json()

    assert re.fullmatch(r"var/artifacts/[0-9a-f]{32}\.html", body["path"])
    assert (tmp_path / "data" / "artifacts" / f"{body['artifact_id']}.html").is_file()


def test_the_user_folder_is_shown_as_a_tilde(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))

    body = _client(tmp_path).post("/api/v1/artifacts", json={"html": PAGE}).json()

    assert body["path"] == f"~/data/artifacts/{body['artifact_id']}.html"
