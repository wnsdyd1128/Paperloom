"""본문 추출 fixture(G3)가 생성기와 일치하고, 격리 하위 프로세스의 추출 결과가 기대값과 맞는지."""

import importlib.util
import json
from pathlib import Path

import pytest

from paperloom.documents.extract import extract_pages
from paperloom.documents.headings import headings
from paperloom.documents.metadata import paper_doi
from paperloom.documents.references import reference_pages
from paperloom.documents.text_layout import document_status

FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "pdf-layout"
EXPECTED = json.loads((FIXTURE_DIR / "text-extraction.json").read_text(encoding="utf-8"))


def test_fixture_is_current():
    spec = importlib.util.spec_from_file_location("text_generator", FIXTURE_DIR / "generate_text_extraction.py")
    generator = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(generator)

    for name, build in generator.DOCUMENTS.items():
        assert build() == (FIXTURE_DIR / name).read_bytes(), name
    assert generator.expected() == EXPECTED


@pytest.fixture(scope="module")
def extracted() -> dict[str, list[dict]]:
    return {
        name: extract_pages(FIXTURE_DIR / name, 0, len(document["pages"]), timeout_seconds=60)
        for name, document in EXPECTED["documents"].items()
    }


@pytest.mark.parametrize("name", list(EXPECTED["documents"]))
def test_page_and_document_status(extracted, name):
    document = EXPECTED["documents"][name]
    pages = extracted[name]

    assert [(page["page_index"], page["text_status"], page["flags"]) for page in pages] == [
        (page["page_index"], page["text_status"], page["flags"]) for page in document["pages"]
    ]
    assert document_status([(page["text_status"], page["quality"]) for page in pages]) == (
        document["status"],
        document["status_reason"],
    )


@pytest.mark.parametrize("name", list(EXPECTED["documents"]))
def test_reference_pages(extracted, name):
    assert reference_pages(extracted[name]) == EXPECTED["documents"][name].get("reference_pages", [])


@pytest.mark.parametrize("name", list(EXPECTED["documents"]))
def test_headings(extracted, name):
    found = [[item["title"], item["page_index"], item["level"]] for item in headings(extracted[name])]
    assert found == EXPECTED["documents"][name].get("headings", [])


@pytest.mark.parametrize("name", list(EXPECTED["documents"]))
def test_doi(extracted, name):
    assert paper_doi(extracted[name]) == EXPECTED["documents"][name].get("doi")


def test_paragraphs_in_reading_order(extracted):
    pages = extracted["text-digital.pdf"]
    for page_index, texts in EXPECTED["documents"]["text-digital.pdf"]["blocks"].items():
        assert [block["text"] for block in pages[int(page_index)]["blocks"]] == texts, page_index


def test_scripts_stay_in_their_line(extracted):
    expected = EXPECTED["documents"]["text-digital.pdf"]["script_line"]
    [block] = extracted["text-digital.pdf"][expected["page_index"]]["blocks"]

    assert all(part in block["text"] for part in expected["contains"])
    assert len(block["regions"]) == expected["regions"]


def test_regions_use_the_canonical_view_box_on_a_rotated_cropped_page(extracted):
    expected = EXPECTED["documents"]["text-digital.pdf"]["rotated_line"]
    [block] = extracted["text-digital.pdf"][expected["page_index"]]["blocks"]
    [(u0, v0, u1, v1)] = block["regions"]
    u, v = expected["baseline_start"]

    assert block["text"] == expected["text"]
    # 줄 상자가 기준선 시작점을 포함하고, 높이는 글꼴 크기의 1–1.4배다 (loose box는 ascent·descent를 포함한다)
    assert u0 <= u + 1e-3 and u0 > u - 0.01 and u1 > u
    assert v0 < v < v1
    assert expected["font_size_v"] <= v1 - v0 <= 1.4 * expected["font_size_v"]
