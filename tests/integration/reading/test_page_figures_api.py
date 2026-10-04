"""쪽의 그림 후보 API (그림 클릭 선택, IMPL §10.6). 합성 fixture로 그림이 될 것과 안 될 것을 확인한다."""

import importlib.util
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from paperloom.bootstrap.app import create_app
from paperloom.bootstrap.config import AppSettings, Settings

FIXTURE_DIR = Path(__file__).resolve().parents[2] / "fixtures" / "pdf-layout"
FIGURES = json.loads((FIXTURE_DIR / "figures.json").read_text(encoding="utf-8"))
GEOMETRY = json.loads((FIXTURE_DIR / "geometry-matrix.json").read_text(encoding="utf-8"))


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    return TestClient(create_app(Settings(app=AppSettings(mode="test", data_dir=tmp_path / "data"))))


def upload(client: TestClient, name: str) -> str:
    response = client.post(
        "/api/v1/papers", content=(FIXTURE_DIR / name).read_bytes(), headers={"Content-Type": "application/pdf"}
    )
    assert response.status_code == 201
    return response.json()["current_version"]["version_id"]


def test_fixture_is_current():
    spec = importlib.util.spec_from_file_location("figures_generator", FIXTURE_DIR / "generate_figures.py")
    generator = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(generator)
    assert generator.build_pdf() == (FIXTURE_DIR / "figures.pdf").read_bytes()
    assert generator.expected() == FIGURES


def test_image_form_and_vector_figures_are_found_and_nothing_else(client):
    version_id = upload(client, "figures.pdf")

    response = client.get(f"/api/v1/versions/{version_id}/pages/0/figures")

    assert response.status_code == 200
    figures = response.json()["figures"]
    # 흰 배경, 표 가로줄, 대각선, 쪽 밖 선, 20 pt 아이콘, 본문 글자는 후보가 아니다.
    assert [f["source"] for f in figures] == [f["source"] for f in FIGURES["figures"]]
    page_width, page_height = FIGURES["page"][2], FIGURES["page"][3]
    for actual, expected in zip(figures, FIGURES["figures"], strict=True):
        tolerance = (FIGURES["tolerance_pt"] / page_width, FIGURES["tolerance_pt"] / page_height)
        for index, (a, e) in enumerate(zip(actual["box"], expected["normalized"], strict=True)):
            assert abs(a - e) <= tolerance[index % 2], (expected["name"], actual["box"])


@pytest.mark.parametrize("page", GEOMETRY["pages"], ids=lambda page: page["name"])
def test_geometry_fixture_region_is_the_figure_on_every_page_geometry(client, page):
    # 두 색 사각형(채운 경로 둘)이 회전·CropBox·음수 원점·UserUnit 쪽 모두에서 정본 좌표 그대로 후보가 된다.
    version_id = upload(client, "geometry-matrix.pdf")

    figures = client.get(f"/api/v1/versions/{version_id}/pages/{page['page_index']}/figures").json()["figures"]

    assert [f["source"] for f in figures] == ["vector"]
    assert figures[0]["box"] == pytest.approx(page["region"]["normalized"], abs=1e-9)


def test_unknown_version_or_page_is_not_found(client):
    version_id = upload(client, "figures.pdf")
    assert client.get(f"/api/v1/versions/{version_id}/pages/1/figures").status_code == 404
    assert client.get(f"/api/v1/versions/{version_id}/pages/-1/figures").status_code == 404
    assert client.get("/api/v1/versions/no-such-version/pages/0/figures").status_code == 404
