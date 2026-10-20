"""레이아웃 모델 영역으로 문단의 본문 아님 표시 고치기 (documents.layout_regions, 2026-10-19 사용자 요청: "알고리즘이나 표 이런 게
자꾸 번역되네"). 영역은 정해 둔다(진짜 모델은 tests/real_papers)."""

import pytest

from paperloom.documents.layout_model import Region
from paperloom.documents.layout_regions import BODY_SCORE, apply_layout
from paperloom.reading.region_image import displayed_box

BOX = (0.1, 0.4, 0.5, 0.45)  # 문단 상자 (u0, v0, u1, v1)


def page(*blocks: dict, rotation: int = 0) -> dict:
    return {"page_index": 0, "rotation": rotation, "blocks": list(blocks)}


def block(text: str = "for t ← 0 to C − 1 do", box=BOX, flags=()) -> dict:
    return {"text": text, "regions": [list(box)], "quality_flags": list(flags)}


def flags_after(*regions: Region, target: dict | None = None, rotation: int = 0) -> list[str]:
    [marked] = apply_layout(page(target or block(), rotation=rotation), list(regions))["blocks"]
    return marked["quality_flags"]


AROUND = (0.05, 0.3, 0.55, 0.6)  # 문단을 덮는 영역


@pytest.mark.parametrize(
    ("label", "flag"),
    [
        ("algorithm", "in_table"),
        ("table", "in_table"),
        ("formula", "math"),
        ("formula_number", "math"),
        ("image", "in_figure"),
        ("chart", "in_figure"),
        ("header", "page_header"),
        ("footer", "page_footer"),
    ],
)
def test_paragraphs_inside_algorithms_tables_formulas_and_figures_leave_translation(label, flag):
    assert flags_after(Region(label, 0.8, AROUND)) == [flag]


def test_page_numbers_are_headers_or_footers_by_where_they_sit():
    top, bottom = (0.45, 0.02, 0.55, 0.04), (0.45, 0.95, 0.55, 0.97)
    assert flags_after(Region("number", 0.8, top), target=block("12", top)) == ["page_header"]
    assert flags_after(Region("number", 0.8, bottom), target=block("12", bottom)) == ["page_footer"]


def test_captions_inside_an_algorithm_or_table_box_are_still_translated():
    """평가 기록: 캡션("Algorithm 1: RA-CU-WFD", "TABLE II")은 상자 안이어도 번역한다(block_kinds.is_caption)."""
    assert flags_after(Region("algorithm", 0.9, AROUND), target=block("Algorithm 1: RA-CU-WFD")) == []
    assert flags_after(Region("table", 0.9, AROUND), target=block("Table 2. Notation")) == []


def test_a_region_covering_less_than_half_the_paragraph_does_not_count():
    """본문 문단 안의 인라인 수식 영역은 문단을 덮지 못해 문단은 번역한다."""
    inline = (0.1, 0.4, 0.25, 0.45)  # 문단 넓이의 37.5%
    assert flags_after(Region("formula", 0.95, inline)) == []


def test_the_most_confident_covering_region_decides():
    assert flags_after(Region("text", 0.95, AROUND), Region("table", 0.6, AROUND)) == []
    assert flags_after(Region("text", 0.6, AROUND), Region("table", 0.9, AROUND)) == ["in_table"]


@pytest.mark.parametrize("label", ["reference", "reference_content", "content"])
def test_references_and_contents_follow_the_rules(label):
    assert flags_after(Region(label, 0.9, AROUND)) == []
    assert flags_after(Region(label, 0.9, AROUND), target=block(flags=["reference"])) == ["reference"]


def test_confident_body_text_clears_a_rule_figure_mark():
    """규칙의 그림 후보가 본문 단을 덮던 오판(The Power of 10 1–3쪽)을 모델이 바로잡는다. 모델이 덜 확신하거나 그림·표 영역도
    문단을 덮으면 규칙 표시를 둔다(평가: XML 코드 그림의 글은 본문 0.91)."""
    figure_text = block("Among the many coding guidelines that have been written", flags=["in_figure"])
    assert flags_after(Region("text", BODY_SCORE, AROUND), target=figure_text) == []
    assert flags_after(Region("text", BODY_SCORE - 0.01, AROUND), target=figure_text) == ["in_figure"]
    assert flags_after(Region("text", 0.98, AROUND), Region("image", 0.6, AROUND), target=figure_text) == ["in_figure"]
    assert flags_after(target=figure_text) == ["in_figure"]  # 덮는 영역이 없다


def test_rule_table_and_math_marks_stay_when_the_model_sees_body_text():
    """평가에서 모델이 본문으로 본 규칙의 표·수식 문단은 대부분 실제 표 칸의 코드·수식 줄이었다."""
    assert flags_after(Region("text", 0.99, AROUND), target=block(flags=["in_table"])) == ["in_table"]
    assert flags_after(Region("text", 0.99, AROUND), target=block(flags=["math"])) == ["math"]


def test_a_mark_the_rules_already_gave_is_not_repeated():
    assert flags_after(Region("algorithm", 0.9, AROUND), target=block(flags=["in_table"])) == ["in_table"]
    assert flags_after(Region("algorithm", 0.9, AROUND), target=block(flags=["math"])) == ["math", "in_table"]


def test_regions_of_a_rotated_page_are_turned_back_to_page_coordinates():
    """모델은 /Rotate를 적용한 화면 쪽을 본다. 문단 상자는 회전 전 정본 좌표다."""
    shown = displayed_box(AROUND, 90)
    assert shown != AROUND
    assert flags_after(Region("table", 0.9, shown), rotation=90) == ["in_table"]
    assert flags_after(Region("table", 0.9, AROUND), rotation=90) == []


def test_paragraphs_without_regions_are_left_alone():
    empty = {"text": "", "regions": [], "quality_flags": []}
    assert flags_after(Region("table", 0.9, (0, 0, 1, 1)), target=empty) == []
