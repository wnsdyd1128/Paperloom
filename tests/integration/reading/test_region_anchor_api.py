"""영역 Anchor (G2 R13 서버 부분, IMPL §10.6): 종류·검증·종류 바꾸기·영역 이미지.

영역 이미지는 좌표 fixture의 두 색 사각형(왼쪽 빨강, 오른쪽 파랑)으로 확인한다. 회전·CropBox·음수 원점·
UserUnit 쪽 모두에서 지정한 영역만 잘리고, 화면에 보이는 방향으로 그려져야 한다.
"""

import json
import math
import sqlite3
from contextlib import closing
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from paperloom.bootstrap.app import create_app
from paperloom.bootstrap.config import AppSettings, Settings
from paperloom.infrastructure.database.sqlite import MIGRATIONS, connect, migrate

FIXTURE_DIR = Path(__file__).resolve().parents[2] / "fixtures" / "pdf-layout"
EXPECTED = json.loads((FIXTURE_DIR / "geometry-matrix.json").read_text(encoding="utf-8"))
SCALE = 2
COLOR_TOLERANCE = 12


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    return TestClient(create_app(Settings(app=AppSettings(mode="test", data_dir=tmp_path / "data"))))


@pytest.fixture
def version_id(client) -> str:
    pdf = (FIXTURE_DIR / "geometry-matrix.pdf").read_bytes()
    response = client.post("/api/v1/papers", content=pdf, headers={"Content-Type": "application/pdf"})
    assert response.status_code == 201
    return response.json()["current_version"]["version_id"]


def box_quad(u0: float, v0: float, u1: float, v1: float) -> list[float]:
    return [u0, v0, u1, v0, u1, v1, u0, v1]


def region_body(version_id: str, page_index: int = 0, **changes) -> dict:
    body = {
        "schema_version": "anchor.v1",
        "kind": "figure",
        "version_id": version_id,
        "page_index": page_index,
        "quads": [box_quad(*EXPECTED["pages"][page_index]["region"]["normalized"])],
        "quote": "",
    }
    body.update(changes)
    return body


def create_region(client: TestClient, version_id: str, page_index: int = 0, **changes) -> dict:
    response = client.post("/api/v1/anchors", json=region_body(version_id, page_index, **changes))
    assert response.status_code == 201, response.text
    return response.json()


def test_region_anchor_keeps_kind_and_allows_empty_quote(client, version_id):
    anchor = create_region(client, version_id)

    assert (anchor["kind"], anchor["quote"], anchor["display_quote"]) == ("figure", "", None)
    assert client.get(f"/api/v1/anchors/{anchor['anchor_id']}").json() == anchor


def test_text_anchor_defaults_to_text_kind(client, version_id):
    body = region_body(version_id, quote="GEOMETRY LINE ONE")
    del body["kind"]
    response = client.post("/api/v1/anchors", json=body)
    assert response.status_code == 201
    assert response.json()["kind"] == "text"


@pytest.mark.parametrize(
    "changes",
    [
        {"quads": [box_quad(0.1, 0.1, 0.2, 0.2), box_quad(0.3, 0.3, 0.4, 0.4)]},  # 영역은 quad 하나
        {"display_quote": "x_i"},  # 영역에는 첨자 추정 표기가 없다
        {"kind": "text"},  # 텍스트 위치에는 인용이 있어야 한다
        {"kind": "photo"},
    ],
)
def test_region_contract_violations_are_rejected(client, version_id, changes):
    response = client.post("/api/v1/anchors", json=region_body(version_id, **changes))
    assert response.status_code == 422
    assert response.json()["code"] == "INVALID_REQUEST"


def test_degenerate_region_is_rejected_by_shape_check(client, version_id):
    response = client.post("/api/v1/anchors", json=region_body(version_id, quads=[box_quad(0.2, 0.3, 0.5, 0.3)]))
    assert response.status_code == 422
    assert response.json()["code"] == "INVALID_ANCHOR"


def test_region_kind_can_change_but_text_kind_cannot(client, version_id):
    region = create_region(client, version_id)
    url = f"/api/v1/anchors/{region['anchor_id']}"

    changed = client.patch(url, json={"kind": "table"})
    assert changed.status_code == 200
    assert changed.json() == {**region, "kind": "table"}  # 위치·인용은 그대로
    assert client.get(url).json()["kind"] == "table"

    assert client.patch(url, json={"kind": "text"}).status_code == 422  # 영역 → 텍스트는 안 된다
    assert client.patch(url, json={"kind": "table", "quads": []}).status_code == 422  # 종류 말고는 못 바꾼다

    text = create_region(client, version_id, kind="text", quote="GEOMETRY LINE ONE")
    rejected = client.patch(f"/api/v1/anchors/{text['anchor_id']}", json={"kind": "figure"})
    assert rejected.status_code == 422
    assert rejected.json()["code"] == "INVALID_ANCHOR"
    assert client.patch("/api/v1/anchors/no-such-anchor", json={"kind": "figure"}).status_code == 404


def pixel(rows: list[bytes], x: float, y: float) -> tuple[int, int, int]:
    row = rows[int(y)]
    return tuple(row[3 * int(x) : 3 * int(x) + 3])


def close_to(actual: tuple[int, int, int], expected: list[int]) -> bool:
    return all(abs(a - e) <= COLOR_TOLERANCE for a, e in zip(actual, expected, strict=True))


@pytest.mark.parametrize("page", EXPECTED["pages"], ids=lambda page: page["name"])
def test_region_image_is_exactly_the_region_in_display_orientation(client, version_id, page, decode_png):
    anchor = create_region(client, version_id, page_index=page["page_index"])

    response = client.get(f"/api/v1/anchors/{anchor['anchor_id']}/image", params={"scale": SCALE})

    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
    width, height, rows = decode_png(response.content)
    _, _, rect_width, rect_height = page["region"]["pdf_rect"]
    rotated = page["rotation"] in (90, 270)
    expected_size = (rect_height, rect_width) if rotated else (rect_width, rect_height)
    assert abs(width - expected_size[0] * SCALE) <= 1 and abs(height - expected_size[1] * SCALE) <= 1

    colors = page["region"]["colors"]
    # 왼쪽 절반(빨강)은 시계 방향 90° 회전된 쪽에서 위쪽에 보인다.
    first, second = ((width / 2, height / 4), (width / 2, 3 * height / 4)) if rotated else ((width / 4, height / 2), (3 * width / 4, height / 2))
    assert close_to(pixel(rows, *first), colors["left"])
    assert close_to(pixel(rows, *second), colors["right"])
    # 잘린 영역 안쪽 가장자리도 사각형 색이다 (영역 밖이 섞이지 않는다).
    for x, y in [(2, 2), (width - 3, 2), (2, height - 3), (width - 3, height - 3)]:
        assert close_to(pixel(rows, x, y), colors["left"]) or close_to(pixel(rows, x, y), colors["right"])


def test_region_image_of_larger_region_shows_white_margin(client, version_id, decode_png):
    u0, v0, u1, v1 = EXPECTED["pages"][0]["region"]["normalized"]
    du, dv = (u1 - u0) / 4, (v1 - v0) / 4  # 사방으로 4분의 1씩 넓힌다
    anchor = create_region(client, version_id, quads=[box_quad(u0 - du, v0 - dv, u1 + du, v1 + dv)])

    width, height, rows = decode_png(client.get(f"/api/v1/anchors/{anchor['anchor_id']}/image").content)

    assert pixel(rows, width / 2 - 2, height / 2) != (255, 255, 255)
    for x, y in [(width * 0.05, height / 2), (width * 0.95, height / 2), (width / 2, height * 0.05), (width / 2, height * 0.95)]:
        assert pixel(rows, x, y) == (255, 255, 255)
    # 사각형은 가운데 2/3를 차지한다 (가로 120 pt → 180 pt 영역의 1/6부터 5/6까지)
    assert close_to(pixel(rows, width * 0.2, height / 2), EXPECTED["pages"][0]["region"]["colors"]["left"])
    assert pixel(rows, width * 0.14, height / 2) == (255, 255, 255)


def test_text_anchor_image_and_errors(client, version_id, decode_png):
    marker = EXPECTED["pages"][0]["markers"][0]
    u, v = marker["normalized"]
    text = create_region(client, version_id, kind="text", quote=marker["text"], quads=[box_quad(u, v - 0.02, u + 0.3, v + 0.005)])

    width, height, _ = decode_png(client.get(f"/api/v1/anchors/{text['anchor_id']}/image", params={"scale": 1}).content)
    # 글 Anchor 이미지는 수식의 괄호·분수선까지 담도록 위아래로 줄 높이의 절반, 좌우로 쪽 폭의 1%를 넓힌다(바깥쪽 픽셀까지)
    pad = 0.5 * 0.025
    assert (width, height) == (
        math.ceil((u + 0.31) * 612) - math.floor((u - 0.01) * 612),
        math.ceil((v + 0.005 + pad) * 792) - math.floor((v - 0.02 - pad) * 792),
    )
    assert client.get("/api/v1/anchors/no-such-anchor/image").status_code == 404
    assert client.get(f"/api/v1/anchors/{text['anchor_id']}/image", params={"scale": 10}).status_code == 422


def test_migrate_v2_anchors_become_text_kind(tmp_path):
    db_path = tmp_path / "paperloom.sqlite3"
    with closing(connect(db_path)) as connection:
        for number, script in enumerate(MIGRATIONS[:2], start=1):
            connection.executescript(f"BEGIN;\n{script}\nPRAGMA user_version = {number};\nCOMMIT;")
        with connection:
            connection.execute("INSERT INTO papers VALUES ('p', 'local', 'T', '[]', NULL, NULL, 'v', 'now')")
            connection.execute("INSERT INTO source_versions VALUES ('v', 'p', 'h', 1, 1, 'r', 'READY_TO_READ', 'now')")
            connection.execute(
                "INSERT INTO anchors (anchor_id, version_id, page_index, quads_json, quote, display_quote, prefix, suffix,"
                " schema_version, created_at) VALUES ('a', 'v', 0, '[]', 'q', NULL, '', '', 'anchor.v1', 'now')"
            )

    migrate(db_path)

    with closing(sqlite3.connect(db_path)) as connection:
        assert connection.execute("SELECT kind FROM anchors").fetchone()[0] == "text"


def test_page_region_image_without_anchor(client, version_id, decode_png):
    # 저장하지 않은 선택(그림 복사)도 같은 렌더러로 그린다. /Rotate 90 쪽: 왼쪽 빨강이 위에 온다.
    page = EXPECTED["pages"][1]
    box = ",".join(repr(value) for value in page["region"]["normalized"])

    response = client.get(f"/api/v1/versions/{version_id}/pages/1/image", params={"box": box, "scale": SCALE})

    assert response.status_code == 200
    width, height, rows = decode_png(response.content)
    assert (width, height) == (60 * SCALE, 120 * SCALE)
    assert close_to(pixel(rows, width / 2, height / 4), page["region"]["colors"]["left"])
    assert close_to(pixel(rows, width / 2, 3 * height / 4), page["region"]["colors"]["right"])


@pytest.mark.parametrize(
    "box",
    ["0.1,0.1,0.2", "0.1,0.1,0.2,x", "", "0.3,0.1,0.2,0.2", "0.1,0.2,0.2,0.2", "-0.1,0.1,0.2,0.2", "0.1,0.1,1.2,0.2", "nan,0.1,0.2,0.2"],
)
def test_page_region_image_rejects_bad_boxes(client, version_id, box):
    response = client.get(f"/api/v1/versions/{version_id}/pages/0/image", params={"box": box})
    assert response.status_code == 422
    assert response.json()["code"] == "INVALID_REQUEST"


def test_page_region_image_unknown_version_or_page(client, version_id):
    box = "0.1,0.1,0.2,0.2"
    assert client.get(f"/api/v1/versions/{version_id}/pages/5/image", params={"box": box}).status_code == 404
    assert client.get("/api/v1/versions/no-such-version/pages/0/image", params={"box": box}).status_code == 404
    assert client.get(f"/api/v1/versions/{version_id}/pages/0/image").status_code == 422  # box 없음
