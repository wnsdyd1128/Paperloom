"""번역본 PDF의 레이아웃 유지 조판 (paperloom.pdf_export.typeset, 2026-11-15 사용자 요청).
웹의 레이아웃 유지 번역(apps/web/src/features/translation/typeset.ts·TranslatedPage.tsx)과 같은 규칙인지 본다."""

import pytest

from paperloom.pdf_export.typeset import (
    MIN_FONT,
    SCRIPT_SCALE,
    SUB_DROP,
    Rect,
    SourceBlock,
    block_frame,
    layout_block,
    single_line_room,
    whole_mark,
)


class Even:
    """글자는 모두 0.5em(굵게 0.6em), 공백은 0.25em인 글꼴"""

    ascent = 0.8
    descent = 0.2

    def advance(self, char: str, bold: bool) -> float:
        return 0.25 if char == " " else 0.6 if bold else 0.5


def line(top: float, left: float = 100, right: float = 400, height: float = 12) -> Rect:
    return Rect(left, top, right, top + height)


def test_block_frame_takes_the_font_size_and_line_pitch_of_the_original_like_the_web():
    frame = block_frame([line(200), line(216), line(232)], 10, 1)
    assert (frame.single, frame.left, frame.width, frame.font_size, frame.line_height, frame.height, frame.top) == (False, 100, 300, 10, 1.6, 48, 198)
    assert block_frame([line(200), line(216), line(232)], 10, 0.8).font_size == pytest.approx(8)  # 번역 글꼴 배율
    assert block_frame([line(200), line(216)], None, 1).font_size == pytest.approx(12 * 0.78)  # 옛 추출: 줄 높이로 어림
    # 첨자로 줄 상자가 줄 사이보다 높아도 줄 사이는 잰 값이다
    tall = block_frame([line(100, height=16.5), line(112.5, height=16.5), line(125, height=16.5)], 10, 1)
    assert (tall.height, tall.line_height, tall.top) == (37.5, 1.25, 102)


def test_a_single_line_keeps_a_fixed_line_height_centered_on_the_original_line():
    frame = block_frame([line(300, 100, 260, 8)], 20, 1)
    assert (frame.single, frame.left, frame.width, frame.font_size, frame.height, frame.line_height, frame.top) == (True, 100, 160, 20, 24, 24, 292)
    big = block_frame([line(300, 100, 260, 30)], 10, 1)  # 큰 첫 글자: 위쪽에 둔다
    assert (big.top, big.height, big.line_height) == (300, 30, 14)


def test_single_lines_widen_up_to_the_middle_of_the_page_or_its_right_margin():
    frame = block_frame([line(0, 50, 150)], 10, 1)
    assert single_line_room(frame, 600) == pytest.approx(238)  # 300 - 12 - 50
    assert single_line_room(block_frame([line(0, 350, 450)], 10, 1), 600) == pytest.approx(214)  # 564 - 350
    assert single_line_room(block_frame([line(0, 200, 600)], 10, 1), 600) == 400  # 이미 더 넓다


def test_whole_mark_is_the_style_of_a_paragraph_styled_as_a_whole():
    assert whole_mark("5.2 Scheduling", [[0, 14, "b"]]) == "b"
    assert whole_mark("5.2 Scheduling", [[4, 14, "b"]]) == ""
    assert whole_mark("Plain", []) == ""
    assert whole_mark("Odd", [[0, 3, "x"]]) == ""


def block(groups: list[str], lines: list[Rect], font_size: float | None = 10, mark: str = "") -> SourceBlock:
    return SourceBlock("b1", lines, font_size, mark, groups)


def test_paragraphs_wrap_between_words_and_justify_every_line_but_the_last():
    lines = [line(200, 0, 100, 12), line(212, 0, 100, 12)]  # 줄 사이 12pt, 글꼴 10pt → 줄 높이 1.2
    layout = layout_block(block(["aaaa bbbb cccc dddd eeee"], lines), 600, 1, Even())

    assert [run.text for run in layout.runs] == ["aaaa ", "bbbb ", "cccc ", "dddd", "eeee"]
    # 첫 줄: 낱말 넷(20pt씩)을 상자 폭 100에 맞춰 벌린다. 끝 줄은 왼쪽부터
    assert [round(run.x, 3) for run in layout.runs] == [0, 26.667, 53.333, 80, 0]
    assert {run.size for run in layout.runs} == {10}
    # 글줄은 줄 높이(12) 가운데: 반 줄 간격 (12 - 10) / 2 + 위 높이 8
    assert [run.baseline for run in layout.runs] == [200 + 9] * 4 + [212 + 9]
    assert layout.mask == Rect(0, 200, 100, 224)


def test_a_paragraph_that_overflows_its_box_shrinks_only_its_font():
    lines = [line(200, 0, 100, 12), line(212, 0, 100, 12)]
    layout = layout_block(block(["aaaa bbbb cccc dddd eeee ffff gggg hhhh iiii"], lines), 600, 1, Even())

    sizes = {run.size for run in layout.runs}
    assert len(sizes) == 1 and sizes.pop() < 10
    assert max(run.baseline for run in layout.runs) < 224  # 두 줄 상자 안


def test_a_word_wider_than_the_box_breaks_anywhere():
    lines = [line(200 + 12 * index, 0, 100, 12) for index in range(4)]
    layout = layout_block(block(["a" * 30], lines), 600, 1, Even())
    assert [len(run.text) for run in layout.runs] == [20, 10]  # 글자 5pt씩, 폭 100


def test_a_single_line_widens_before_it_shrinks():
    title = [line(100, 0, 50, 12)]
    fits = layout_block(block(["a" * 40], title), 600, 1, Even())  # 200pt: 넓힐 폭 288 안
    assert {run.size for run in fits.runs} == {10}
    assert fits.mask == Rect(0, 100, 50, 112)  # 가리는 상자는 원문 줄(넓힌 폭이 아니다)

    long = layout_block(block(["a" * 80], title), 600, 1, Even())  # 400pt: 288에 맞을 때까지 줄인다
    [size] = {run.size for run in long.runs}
    assert 80 * 0.5 * size <= 288.75 < 80 * 0.5 * size / 0.95
    assert size > MIN_FONT


def test_marks_become_bold_italic_and_scripts_and_paragraph_marks_apply_to_all():
    layout = layout_block(block(["<b>굵게</b> 보통 C<sub>k</sub><i>x</i>"], [line(100, 0, 300, 12)]), 600, 1, Even())
    assert [(run.text, run.bold, run.italic) for run in layout.runs] == [("굵게 ", True, False), ("보통 ", False, False), ("C", False, False), ("k", False, False), ("x", False, True)]
    script = layout.runs[3]
    assert script.size == pytest.approx(10 * SCRIPT_SCALE)
    assert script.baseline == pytest.approx(layout.runs[2].baseline + SUB_DROP * 10)
    assert layout.runs[3].x == pytest.approx(layout.runs[2].x + 5)  # C 다음

    heading = layout_block(block(["제목 <i>a</i>"], [line(100, 0, 300, 12)], mark="b"), 600, 1, Even())
    assert [(run.bold, run.italic) for run in heading.runs] == [(True, False), (True, True)]


def test_groups_record_where_each_translated_sentence_lies_line_by_line():
    lines = [line(200, 0, 100, 12), line(212, 0, 100, 12)]
    layout = layout_block(block(["aaaa bbbb cccc", "dddd eeee"], lines), 600, 1, Even())
    # 첫 줄: aaaa bbbb cccc | dddd (벌린 사이 26.667), 둘째 줄: eeee
    first, second = layout.groups[0], layout.groups[1]
    assert [(round(rect.left, 3), round(rect.right, 3)) for rect in first] == [(0, 73.333)]
    assert [(round(rect.left, 3), round(rect.right, 3)) for rect in second] == [(80, 100), (0, 20)]
    assert (first[0].top, first[0].bottom) == (201, 211)  # 글줄 위 높이 8, 아래 깊이 2
