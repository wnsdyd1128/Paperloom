"""Anchor·주석 REST (G2 R09–R11 서버 부분): 저장·재시작 뒤 조회, 서버 검증, revision 충돌, 버전 조회."""

import json
import sqlite3
from contextlib import closing
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from paperloom.bootstrap.app import create_app
from paperloom.bootstrap.config import AppSettings, Settings

QUAD = [0.1, 0.1, 0.5, 0.1, 0.5, 0.12, 0.1, 0.12]


def make_client(data_dir: Path, web_dist_dir: Path | None = None) -> TestClient:
    settings = Settings(app=AppSettings(mode="test", data_dir=data_dir, web_dist_dir=web_dist_dir))
    return TestClient(create_app(settings))


@pytest.fixture
def data_dir(tmp_path: Path) -> Path:
    return tmp_path / "data"


@pytest.fixture
def client(data_dir: Path) -> TestClient:
    return make_client(data_dir)


@pytest.fixture
def version(client, make_pdf) -> dict:
    response = client.post("/api/v1/papers", content=make_pdf(pages=3), headers={"Content-Type": "application/pdf"})
    assert response.status_code == 201
    paper = response.json()
    return {**paper["current_version"], "paper_id": paper["paper_id"]}


def anchor_body(version_id: str, **changes) -> dict:
    body = {
        "schema_version": "anchor.v1",
        "version_id": version_id,
        "page_index": 1,
        "quads": [QUAD],
        "quote": "f j k ≤ d j k",
        "display_quote": "f^j_k ≤ d^j_k",
        "prefix": "where ",
        "suffix": " holds",
    }
    body.update(changes)
    return body


def create_anchor(client: TestClient, version_id: str, **changes) -> dict:
    response = client.post("/api/v1/anchors", json=anchor_body(version_id, **changes))
    assert response.status_code == 201, response.text
    return response.json()


def create_annotation(client: TestClient, anchor_id: str, comment: str = "메모") -> dict:
    response = client.post("/api/v1/annotations", json={"anchor_id": anchor_id, "comment": comment})
    assert response.status_code == 201, response.text
    return response.json()


def count_rows(data_dir: Path, table: str) -> int:
    with closing(sqlite3.connect(data_dir / "paperloom.sqlite3")) as connection:
        return connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


def test_version_lookup_names_its_paper(client, version):
    response = client.get(f"/api/v1/versions/{version['version_id']}")

    assert response.status_code == 200
    assert response.json() == {key: version[key] for key in response.json()}
    assert response.json()["paper_id"] == version["paper_id"]
    assert client.get("/api/v1/versions/unknown").json()["code"] == "NOT_FOUND"


def test_anchor_round_trip_keeps_quote_and_estimated_quote_apart(client, version):
    anchor = create_anchor(client, version["version_id"])

    assert anchor["anchor_id"] and anchor["created_at"]
    assert anchor["quote"] == "f j k ≤ d j k"  # 추출된 그대로
    assert anchor["display_quote"] == "f^j_k ≤ d^j_k"  # 추정 표기는 따로
    assert anchor["quads"] == [QUAD]
    assert client.get(f"/api/v1/anchors/{anchor['anchor_id']}").json() == anchor


def test_display_quote_is_optional(client, version):
    body = anchor_body(version["version_id"])
    del body["display_quote"]
    response = client.post("/api/v1/anchors", json=body)
    assert response.status_code == 201
    assert response.json()["display_quote"] is None


@pytest.mark.parametrize(
    ("changes", "code"),
    [
        ({"quads": [[0.1, 0.1, 1.2, 0.1, 1.2, 0.2, 0.1, 0.2]]}, "INVALID_REQUEST"),  # 범위 밖
        ({"quads": [[-0.01, 0.1, 0.5, 0.1, 0.5, 0.2, -0.01, 0.2]]}, "INVALID_REQUEST"),
        ({"quads": [QUAD[:7]]}, "INVALID_REQUEST"),  # 꼭짓점 부족
        ({"quads": []}, "INVALID_REQUEST"),
        ({"quads": [[0.1, 0.1, 0.5, 0.1, 0.5, 0.1, 0.1, 0.1]]}, "INVALID_ANCHOR"),  # 넓이 없음
        ({"quads": [[0.1, 0.1, 0.5, 0.1, 0.1, 0.2, 0.5, 0.2]]}, "INVALID_ANCHOR"),  # 자기 교차
        ({"quads": [QUAD, [0.1, 0.1, 0.5, 0.1, 0.1, 0.2, 0.5, 0.2]]}, "INVALID_ANCHOR"),  # 둘째 줄만 잘못
        ({"page_index": 3}, "INVALID_ANCHOR"),  # 3쪽 문서의 네 번째 쪽
        ({"page_index": -1}, "INVALID_REQUEST"),
        ({"page_index": "1"}, "INVALID_REQUEST"),  # 문자열 숫자를 받지 않는다
        ({"page_index": 1.0}, "INVALID_REQUEST"),
        ({"quote": ""}, "INVALID_REQUEST"),
        ({"schema_version": "anchor.v2"}, "INVALID_REQUEST"),
        ({"owner_id": "someone"}, "INVALID_REQUEST"),  # 모르는 필드
        ({"prefix": "x" * 501}, "INVALID_REQUEST"),
    ],
)
def test_anchor_validation_rejects_and_stores_nothing(client, data_dir, version, changes, code):
    response = client.post("/api/v1/anchors", json=anchor_body(version["version_id"], **changes))

    assert response.status_code == 422, response.text
    body = response.json()
    assert body["code"] == code
    assert set(body) >= {"code", "message", "request_id", "retryable"}
    assert count_rows(data_dir, "anchors") == 0


@pytest.mark.parametrize("literal", ["NaN", "Infinity", "-Infinity"])
def test_anchor_validation_rejects_non_finite_numbers(client, data_dir, version, literal):
    # 표준 JSON에는 없지만 Python json은 읽는 값이다. 직렬화한 본문에 직접 넣는다.
    content = json.dumps(anchor_body(version["version_id"])).replace("0.12", literal, 1)

    response = client.post("/api/v1/anchors", content=content, headers={"Content-Type": "application/json"})

    assert response.status_code == 422
    assert response.json()["code"] == "INVALID_REQUEST"
    assert count_rows(data_dir, "anchors") == 0


def test_validation_errors_do_not_echo_submitted_values(client, version):
    secret = "사용자가 붙여 넣은 긴 본문"
    response = client.post("/api/v1/anchors", json=anchor_body(version["version_id"], page_index=secret))

    assert response.status_code == 422
    assert secret not in response.text
    assert response.json()["details"]["errors"][0]["loc"] == ["body", "page_index"]


def test_malformed_json_uses_error_envelope(client):
    response = client.post("/api/v1/anchors", content="{", headers={"Content-Type": "application/json"})
    assert response.status_code == 422
    assert response.json()["code"] == "INVALID_REQUEST"


def test_anchor_for_unknown_version_is_not_found(client, data_dir, version):
    response = client.post("/api/v1/anchors", json=anchor_body("no-such-version"))
    assert response.status_code == 404
    assert response.json()["code"] == "NOT_FOUND"
    assert client.get("/api/v1/anchors/no-such-anchor").status_code == 404


def test_annotations_survive_restart_and_list_in_reading_order(client, data_dir, version):
    later = create_anchor(client, version["version_id"], page_index=2)
    lower = create_anchor(client, version["version_id"], quads=[[0.1, 0.5, 0.5, 0.5, 0.5, 0.52, 0.1, 0.52]])
    upper = create_anchor(client, version["version_id"])
    for anchor in (later, lower, upper):
        created = create_annotation(client, anchor["anchor_id"], comment=f"메모 {anchor['page_index']}")
        assert created["revision"] == 1 and created["anchor"] == anchor

    restarted = make_client(data_dir)  # 새 프로세스처럼 같은 데이터 폴더로 다시 연다
    listed = restarted.get(f"/api/v1/versions/{version['version_id']}/annotations").json()["annotations"]

    assert [item["anchor"]["anchor_id"] for item in listed] == [upper["anchor_id"], lower["anchor_id"], later["anchor_id"]]
    assert restarted.get("/api/v1/versions/unknown/annotations").status_code == 404


def test_annotation_requires_existing_anchor(client, data_dir):
    response = client.post("/api/v1/annotations", json={"anchor_id": "no-such-anchor", "comment": "x"})
    assert response.status_code == 404
    assert count_rows(data_dir, "annotations") == 0


def test_update_checks_revision(client, version):
    annotation = create_annotation(client, create_anchor(client, version["version_id"])["anchor_id"])
    url = f"/api/v1/annotations/{annotation['annotation_id']}"

    updated = client.patch(url, json={"revision": 1, "comment": "고친 메모"})
    assert updated.status_code == 200
    assert (updated.json()["revision"], updated.json()["comment"]) == (2, "고친 메모")

    stale = client.patch(url, json={"revision": 1, "comment": "늦게 도착한 수정"})
    assert stale.status_code == 409
    assert stale.json()["code"] == "REVISION_CONFLICT"
    assert stale.json()["details"] == {"current_revision": 2}

    missing = client.patch(url, json={"comment": "revision 없음"})
    assert missing.status_code == 422

    listed = client.get(f"/api/v1/versions/{version['version_id']}/annotations").json()["annotations"]
    assert [(item["revision"], item["comment"]) for item in listed] == [(2, "고친 메모")]
    assert client.patch("/api/v1/annotations/unknown", json={"revision": 1, "comment": "x"}).status_code == 404


def test_delete_checks_revision_and_keeps_anchor(client, version):
    anchor = create_anchor(client, version["version_id"])
    annotation = create_annotation(client, anchor["anchor_id"])
    url = f"/api/v1/annotations/{annotation['annotation_id']}"
    client.patch(url, json={"revision": 1, "comment": "바뀜"})

    assert client.delete(url, params={"revision": 1}).status_code == 409
    assert client.delete(url).status_code == 422  # revision 없이 지울 수 없다
    assert client.delete(url, params={"revision": 2}).status_code == 204

    assert client.get(f"/api/v1/versions/{version['version_id']}/annotations").json()["annotations"] == []
    assert client.get(f"/api/v1/anchors/{anchor['anchor_id']}").status_code == 200
    assert client.delete(url, params={"revision": 2}).status_code == 404


def test_highlight_color_is_saved_changed_and_checked(client, version):
    """U5 하이라이트 3색 (UI_PLAN §5 U5): 색은 없음 또는 c1–c3. 색만, 메모만 바꿀 수 있고 revision을 확인한다."""
    anchor = create_anchor(client, version["version_id"])
    created = client.post("/api/v1/annotations", json={"anchor_id": anchor["anchor_id"], "comment": "", "color": "c2"}).json()
    assert (created["color"], created["revision"]) == ("c2", 1)
    url = f"/api/v1/annotations/{created['annotation_id']}"

    recolored = client.patch(url, json={"revision": 1, "color": "c3"}).json()
    assert (recolored["revision"], recolored["color"], recolored["comment"]) == (2, "c3", "")
    noted = client.patch(url, json={"revision": 2, "comment": "메모"}).json()  # 메모만 바꾸면 색은 그대로
    assert (noted["revision"], noted["color"], noted["comment"]) == (3, "c3", "메모")
    cleared = client.patch(url, json={"revision": 3, "color": None}).json()  # 색을 빼면 메모 주석으로 남는다
    assert (cleared["revision"], cleared["color"], cleared["comment"]) == (4, None, "메모")

    stale = client.patch(url, json={"revision": 3, "color": "c1"})  # 늦게 도착한 색 바꾸기
    assert (stale.status_code, stale.json()["code"], stale.json()["details"]) == (409, "REVISION_CONFLICT", {"current_revision": 4})
    listed = client.get(f"/api/v1/versions/{version['version_id']}/annotations").json()["annotations"]
    assert [(item["color"], item["revision"]) for item in listed] == [(None, 4)]
    # 색 없이 만든 주석은 null
    assert create_annotation(client, create_anchor(client, version["version_id"])["anchor_id"])["color"] is None


@pytest.mark.parametrize("color", ["red", "c4", "", "C1"])
def test_highlight_color_rejects_unknown_colors(client, data_dir, version, color):
    anchor = create_anchor(client, version["version_id"])
    response = client.post("/api/v1/annotations", json={"anchor_id": anchor["anchor_id"], "comment": "", "color": color})
    assert (response.status_code, response.json()["code"]) == (422, "INVALID_REQUEST")
    assert count_rows(data_dir, "annotations") == 0
    annotation = create_annotation(client, anchor["anchor_id"])
    assert client.patch(f"/api/v1/annotations/{annotation['annotation_id']}", json={"revision": 1, "color": color}).status_code == 422


def test_patch_needs_a_comment_or_a_color(client, version):
    annotation = create_annotation(client, create_anchor(client, version["version_id"])["anchor_id"])
    url = f"/api/v1/annotations/{annotation['annotation_id']}"
    assert client.patch(url, json={"revision": 1}).status_code == 422
    assert client.get(f"/api/v1/versions/{version['version_id']}/annotations").json()["annotations"][0]["revision"] == 1


def test_reader_links_serve_the_web_app(data_dir, tmp_path):
    web_dist = tmp_path / "dist"
    web_dist.mkdir()
    (web_dist / "index.html").write_text("<!doctype html><title>Paperloom</title>", encoding="utf-8")
    client = make_client(data_dir, web_dist_dir=web_dist)

    response = client.get("/reader/some-paper", params={"version": "v", "anchor": "a"})

    assert response.status_code == 200
    assert "<title>Paperloom</title>" in response.text
    # U6 답변 화면도 직접 열거나 새로고침한다
    assert "<title>Paperloom</title>" in client.get("/answers").text
    assert client.get("/api/v1/no-such-route").json()["code"] == "NOT_FOUND"
