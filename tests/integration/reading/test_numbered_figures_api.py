"""번호 붙은 그림 API (2026-11-09 사용자 요청: 발표 슬라이드 아티팩트에 논문 원본 그림 넣기). 합성 fixture
white-background-forms.pdf(두 단, 위에 그림 둘과 그 바로 아래 캡션 "Fig. 2:"·"Fig. 3:", 그 아래 본문)로 캡션의 번호와
캡션에 붙은 그림 영역을 확인한다."""

import importlib.util
import struct
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from paperloom.bootstrap.app import create_app
from paperloom.bootstrap.config import AppSettings, Settings
from paperloom.reading.numbered_figures import PAD

FIXTURE_DIR = Path(__file__).resolve().parents[2] / "fixtures" / "pdf-layout"


def load_generator():
    spec = importlib.util.spec_from_file_location("generate_white_background_forms", FIXTURE_DIR / "generate_white_background_forms.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


GENERATOR = load_generator()


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    return TestClient(create_app(Settings(app=AppSettings(mode="test", data_dir=tmp_path / "data"))))


def upload(client: TestClient) -> str:
    response = client.post(
        "/api/v1/papers", content=(FIXTURE_DIR / "white-background-forms.pdf").read_bytes(), headers={"Content-Type": "application/pdf"}
    )
    assert response.status_code == 201
    return response.json()["current_version"]["version_id"]


def extract(client: TestClient) -> None:
    while client.app.state.parsing.run_next():
        pass


def png_size(png: bytes) -> tuple[int, int]:
    assert png.startswith(b"\x89PNG\r\n\x1a\n")
    return struct.unpack(">II", png[16:24])


def test_figures_are_listed_by_their_caption_numbers_once_the_text_is_extracted(client):
    version_id = upload(client)
    assert client.get(f"/api/v1/versions/{version_id}/figures").json() == {"version_id": version_id, "figures": []}  # 추출 전

    extract(client)
    response = client.get(f"/api/v1/versions/{version_id}/figures")

    assert response.status_code == 200
    assert response.json()["figures"] == [
        {"label": "2", "page_index": 0, "caption": "Fig. 2: the overall mechanism."},
        {"label": "3", "page_index": 0, "caption": "Fig. 3: two priority elevation implementations."},
    ]


@pytest.mark.parametrize(("label", "column"), [("2", 0), ("3", 1)])
def test_a_figure_image_is_the_drawing_above_its_caption_and_nothing_else(client, label, column):
    version_id = upload(client)
    extract(client)
    candidates = sorted(client.get(f"/api/v1/versions/{version_id}/pages/0/figures").json()["figures"], key=lambda item: item["box"][0])

    response = client.get(f"/api/v1/versions/{version_id}/figures/{label}/image?scale=1")

    assert response.status_code == 200 and response.headers["content-type"] == "image/png"
    # 그 단의 그림 후보(Form 전체를 덮는 흰 배경이 아니라 보이는 그림)와 둘레 여백뿐이다: 캡션, 그 아래 본문, 옆 단 그림은
    # 들어가지 않는다. scale=1이면 1 pt가 1 px이다
    u0, v0, u1, v1 = candidates[column]["box"]
    page_width, page_height = GENERATOR.PAGE[2], GENERATOR.PAGE[3]
    width, height = png_size(response.content)
    assert width == pytest.approx((u1 - u0 + 2 * PAD) * page_width, abs=2)
    assert height == pytest.approx((v1 - v0 + 2 * PAD) * page_height, abs=2)


def test_unknown_figures_and_versions_are_not_found(client):
    version_id = upload(client)
    assert client.get(f"/api/v1/versions/{version_id}/figures/2/image").status_code == 404  # 추출 전에는 번호를 모른다
    extract(client)
    assert client.get(f"/api/v1/versions/{version_id}/figures/9/image").json()["code"] == "NOT_FOUND"
    assert client.get("/api/v1/versions/no-such-version/figures").status_code == 404
    assert client.get("/api/v1/versions/no-such-version/figures/2/image").status_code == 404
