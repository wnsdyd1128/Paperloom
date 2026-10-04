"""문단의 글꼴 모양·크기와 그림 안 글자 (U7 쪽 번역, 2026-10-03 사용자 요청).

레이아웃 유지 번역이 원문처럼 굵게·기울임·크기를 따르고, 그림 안 글자(축 이름 등)는 번역하지 않는다.
글자 모양은 pdfium의 글꼴 이름·플래그·굵기에서 추정한다(사용자 논문: LinLibertineTB 굵게, LinLibertineTI 기울임).
"""

import pytest

from paperloom.documents.fonts import font_style
from paperloom.documents.text_layout import Char, layout_page

H = 10.0
W = 5.0
PAGE = (0.0, 0.0, 600.0, 800.0)


def styled(parts: list[tuple[str, str]], x: float, bottom: float, size: float = 10.0) -> list[Char]:
    """(글, 모양) 조각을 이어 한 줄로. 글자마다 W 폭, 공백은 위치 없는 글자다."""
    chars = []
    index = 0
    for text, style in parts:
        for ch in text:
            box = (x + index * W, bottom, x + (index + 1) * W, bottom + H)
            chars.append(Char(ch, None) if ch == " " else Char(ch, box, False, style, size))
            index += 1
    return chars + [Char("\n", None)]


@pytest.mark.parametrize(
    ("name", "flags", "weight", "style"),
    [
        ("LinLibertineT", 524294, 395, ""),
        ("LinLibertineTB", 786438, 650, "b"),  # ForceBold 플래그·굵기
        ("LinLibertineTI", 524358, 380, "i"),  # Italic 플래그
        ("EAAAAB+LinBiolinumB", 524321, 0, "b"),  # 굵기를 모르면 이름 끝(…B)
        ("Times-BoldItalic", 0, -1, "bi"),
        ("NimbusRomNo9L-Medi", 0, -1, "b"),
        ("NimbusRomNo9L-ReguItal", 0, -1, "i"),
        ("CMBX10", 0, -1, "b"),
        ("CMTI10", 0, -1, "i"),
        ("CMR10", 0, -1, ""),
        ("Helvetica-Oblique", 0, -1, "i"),
        ("ArialMT", 0, 700, "b"),
        ("", 0, -1, ""),
    ],
)
def test_font_style_from_name_flags_and_weight(name, flags, weight, style):
    assert font_style(name, flags, weight) == style


def test_a_paragraph_keeps_bold_and_italic_runs_and_its_font_size():
    chars = (
        styled([("Real-time Scheduling.", "b"), (" To run the ", ""), ("deg2rad", "i"), (" task the sched-", "")], 72, 700)
        + styled([("ulability test uses ", ""), ("both", "bi"), (" cores.", "")], 72, 700 - 1.2 * H)
    )
    [block] = layout_page(chars, PAGE, 0.0).blocks
    assert block.text == "Real-time Scheduling. To run the deg2rad task the schedulability test uses both cores."
    assert block.styles == [[0, 21, "b"], [33, 40, "i"], [75, 79, "bi"]]
    assert [block.text[start:end] for start, end, _ in block.styles] == ["Real-time Scheduling.", "deg2rad", "both"]
    assert block.font_size == 10.0


def test_superscripts_and_subscripts_are_marked_for_translation():
    """위·아래첨자(본문보다 작고 위·아래로 비킨 글자)는 모양 표시 ^·_로 남긴다. 쪽 번역이 <sup>·<sub>로 보내 지킨다
    (2026-10-04 사용자 확인: 인라인 수식이 "C k", "τ na p"로 납작해져 번역에 들어갔다). 기울임과 겹치면 "i_"·"i^"다."""
    def glyph(ch, x, bottom, height, size, style=""):
        return Char(ch, (x, bottom, x + W, bottom + height), False, style, size)

    chars = [glyph(ch, 72 + index * W, 700, H, 10.0) for index, ch in enumerate("Let C")]
    chars += [glyph("k", 72 + 5 * W, 697, 7, 7.0), Char(" ", None)]
    chars += [glyph(ch, 72 + (6 + index) * W, 700, H, 10.0) for index, ch in enumerate("and ")]
    chars += [glyph("τ", 72 + 10 * W, 700, H, 10.0, "i")]
    chars += [glyph(ch, 72 + (11 + index) * W, 704, 7, 7.0, "i") for index, ch in enumerate("na")]
    chars += [glyph("p", 72 + 11 * W, 697, 7, 7.0, "i")]
    chars += [glyph(ch, 72 + (13 + index) * W, 700, H, 10.0) for index, ch in enumerate(" hold.")]
    [block] = layout_page(chars, PAGE, 0.0).blocks
    assert block.text == "Let Ck and τnap hold."
    assert [(block.text[start:end], mark) for start, end, mark in block.styles] == [("k", "_"), ("τ", "i"), ("na", "i^"), ("p", "i_")]


def test_a_hyphenated_word_keeps_its_style_and_plain_text_has_no_runs():
    chars = styled([("the ", ""), ("sched-", "i")], 72, 700) + styled([("ulability", "i"), (" test", "")], 72, 700 - 1.2 * H)
    plain = styled([("Plain text only.", "")], 72, 500, size=12.0)
    first, second = layout_page(chars + plain, PAGE, 0.0).blocks
    assert first.text == "the schedulability test" and first.styles == [[4, 18, "i"]]
    assert second.styles == [] and second.font_size == 12.0


def test_text_inside_a_figure_is_marked_but_its_caption_is_not():
    figure = (0.1, 0.1, 0.5, 0.4)  # 정본 좌표 (u0, v0, u1, v1): x 60–300, 위에서 80–320pt
    label = styled([("Axis label", "")], 100, 600)  # 그림 안
    caption = styled([("Fig. 1. Caption under the figure.", "")], 72, 440)  # 그림 아래
    body = styled([("Body text elsewhere.", "")], 72, 200)
    blocks = layout_page(label + caption + body, PAGE, 0.0, figures=[figure]).blocks
    flags = {block.text: block.quality_flags for block in blocks}
    assert flags == {"Axis label": ["in_figure"], "Fig. 1. Caption under the figure.": [], "Body text elsewhere.": []}
