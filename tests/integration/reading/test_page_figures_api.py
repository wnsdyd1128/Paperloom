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


def load_generator(name: str):
    spec = importlib.util.spec_from_file_location(name, FIXTURE_DIR / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_a_form_clipped_inside_is_only_its_visible_part_and_text_below_stays_body(client):
    """2026-10-17 실제 논문 LLVM Static Analysis 4쪽: Form 안에서 잘린 그림의 객체 상자가 잘린 부분까지 덮어 그 아래 본문
    17줄이 그림 안 글자가 되어 번역에서 빠졌다. 그림 후보는 보이는 부분(잘라내기 상자)뿐이고, 그 아래 본문·캡션은 그림 밖이다."""
    generator = load_generator("generate_clipped_form")
    assert generator.build_pdf() == (FIXTURE_DIR / "clipped-form.pdf").read_bytes()
    version_id = upload(client, "clipped-form.pdf")
    figure, chart = sorted(client.get(f"/api/v1/versions/{version_id}/pages/0/figures").json()["figures"], key=lambda item: item["box"][0])
    # 잘라내기 없이 그린 축·축 글자가 있는 Form은 작게 잘린 채움이 있어도 축 글자까지 그림이다(Form 좌표 0..200 × −15..100)
    assert chart["source"] == "form" and chart["box"][0] == pytest.approx(350 / 612, abs=0.01) and chart["box"][2] == pytest.approx(550 / 612, abs=0.01)
    assert chart["box"][3] > 1 - 490 / 792
    left, bottom, right, top = generator.VISIBLE
    width, height = generator.PAGE[2], generator.PAGE[3]
    assert figure["source"] == "form"
    assert figure["box"][1] == pytest.approx(1 - top / height, abs=2 / height)  # 위·아래는 잘라내기 상자다
    assert figure["box"][3] == pytest.approx(1 - bottom / height, abs=2 / height)
    assert left / width - 2 / width <= figure["box"][0] and figure["box"][2] <= right / width + 2 / width
    while client.app.state.parsing.run_next():
        pass
    flags = {block["text"]: block["quality_flags"] for block in client.get(f"/api/v1/versions/{version_id}/pages/0").json()["blocks"]}
    body = " ".join(generator.BODY)
    assert flags[body] == [] and flags["Figure 1. A clipped drawing of a graph."] == []
    assert flags["BB3"] == flags["axis label"] == ["in_figure"]  # 보이는 그림 안 글자는 그대로 그림 안
    assert not any("HIDDEN" in text for text in flags)  # 잘려 보이지 않는 Form 안 글자는 뽑지 않는다


def test_a_white_background_covering_a_whole_form_is_not_part_of_the_figure(client):
    """2026-10-21 사용자 알림(Resource-Aware Task Scheduling 5쪽 "그림 영역이 잘못 잡히는데?"): PowerPoint 슬라이드째·A4 쪽째로 넣은
    그림 Form은 첫 객체가 Form 전체를 덮는 흰 사각형이라 객체 상자가 그림보다 훨씬 컸다. 두 상자가 닿아 쪽의 79%가 그림 하나로
    잡혔고(배경 문턱 80% 아래) 오른쪽 단 본문이 그림 안 글자가 되었다. Form 전체를 덮는 흰 배경은 그림 상자에 넣지 않는다."""
    generator = load_generator("generate_white_background_forms")
    assert generator.build_pdf() == (FIXTURE_DIR / "white-background-forms.pdf").read_bytes()
    version_id = upload(client, "white-background-forms.pdf")
    figures = client.get(f"/api/v1/versions/{version_id}/pages/0/figures").json()["figures"]
    width, height = generator.PAGE[2], generator.PAGE[3]
    assert len(figures) == 2
    for figure, (left, bottom, right, top) in zip(sorted(figures, key=lambda item: item["box"][0]), (generator.SLIDE_DRAWING, generator.PAGE_DRAWING)):
        assert figure["source"] == "form"
        assert figure["box"] == pytest.approx([left / width, 1 - top / height, right / width, 1 - bottom / height], abs=3 / width)
    while client.app.state.parsing.run_next():
        pass
    flags = {block["text"]: block["quality_flags"] for block in client.get(f"/api/v1/versions/{version_id}/pages/0").json()["blocks"]}
    assert flags[" ".join(generator.LEFT_BODY)] == flags[" ".join(generator.RIGHT_BODY)] == []
    assert flags["Fig. 2: the overall mechanism."] == flags["Fig. 3: two priority elevation implementations."] == []
    assert flags["Initial Setup"] == flags["1st adjust"] == ["in_figure"]


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
