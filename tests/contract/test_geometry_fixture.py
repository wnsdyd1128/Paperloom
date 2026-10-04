"""좌표 계약 fixture의 서버 쪽 검증 (IMPL §6.2). 웹 쪽은 apps/web/src/features/reader/geometry.test.ts."""

import json
from pathlib import Path

import pytest

from paperloom.reading.geometry import normalize_point, read_page_geometry

FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "pdf-layout"
EXPECTED = json.loads((FIXTURE_DIR / "geometry-matrix.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def geometry():
    return read_page_geometry(FIXTURE_DIR / "geometry-matrix.pdf")


def test_fixture_is_current():
    """생성기와 커밋된 fixture가 어긋나지 않았는지 확인한다."""
    import importlib.util

    spec = importlib.util.spec_from_file_location("generator", FIXTURE_DIR / "generate_geometry_matrix.py")
    generator = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(generator)
    assert generator.build_pdf() == (FIXTURE_DIR / "geometry-matrix.pdf").read_bytes()
    assert generator.expected() == EXPECTED


@pytest.mark.parametrize("page", EXPECTED["pages"], ids=lambda page: page["name"])
def test_view_box_and_rotation_match_contract(geometry, page):
    actual = geometry[page["page_index"]]

    assert list(actual.view_box) == page["view_box"]
    assert actual.rotation == page["rotation"]


@pytest.mark.parametrize("page", EXPECTED["pages"], ids=lambda page: page["name"])
def test_marker_normalization_matches_contract(geometry, page):
    view_box = geometry[page["page_index"]].view_box
    for marker in page["markers"]:
        assert normalize_point(*marker["pdf_point"], view_box) == pytest.approx(marker["normalized"], abs=1e-12)
