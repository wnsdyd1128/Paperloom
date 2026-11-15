"""번역본 PDF 그리기 (paperloom.pdf_export.overlay·fonts, 2026-11-15 사용자 요청): 회전한 쪽의 좌표, 글꼴 고르기,
원문 쪽 위에 번역문 덮기와 하이라이트 옮기기."""

import ctypes
import io

import pypdf
import pypdfium2 as pdfium
import pypdfium2.raw as raw
import pytest
from fontTools.ttLib import TTFont

from paperloom.pdf_export.fonts import SYMBOL, WANTED, Fonts
from paperloom.pdf_export.marks import Mark
from paperloom.pdf_export.overlay import PageSpace
from paperloom.pdf_export.translated import Group, TranslatedBlock, TranslatedPage
from paperloom.pdf_export.typeset import Rect
from paperloom.pdf_export.writer import write_annotated

VIEW = (50.0, 100.0, 562.0, 742.0)


@pytest.mark.parametrize("rotation", [0, 90, 180, 270])
def test_display_coordinates_go_back_to_canonical_and_user_space(rotation):
    space = PageSpace(VIEW, rotation)
    for u, v in [(0, 0), (1, 0), (0.25, 0.75), (1, 1)]:
        x, y = space.to_display(u, v)
        assert space.to_norm(x, y) == pytest.approx((u, v))
    # 화면의 오른쪽·위쪽 방향은 사용자 공간에서도 그 방향이다
    (dx, dy), (ux, uy) = space.axes()
    origin = space.to_user(10, 10)
    right = space.to_user(11, 10)
    up = space.to_user(10, 9)
    assert (right[0] - origin[0], right[1] - origin[1]) == pytest.approx((dx, dy))
    assert (up[0] - origin[0], up[1] - origin[1]) == pytest.approx((ux, uy))


def test_a_page_turned_clockwise_shows_its_top_left_at_the_top_right():
    space = PageSpace((0, 0, 600, 800), 90)
    assert space.width == 800
    assert space.to_display(0, 0) == (800, 0)
    assert space.display_rect([0.1, 0.2, 0.3, 0.25]) == Rect(600, 60, 640, 180)
    assert space.quad(Rect(600, 60, 640, 180))[:2] == pytest.approx([0.1, 0.25])  # 화면의 좌상은 정본의 (u0, v1)


def test_letters_missing_from_wanted_sans_use_symbol_or_a_look_alike():
    with Fonts() as fonts:
        assert fonts.font_of("가") == WANTED and fonts.font_of("A") == WANTED
        assert fonts.font_of("α") == SYMBOL and fonts.font_of("≤") == SYMBOL
        # Symbol은 오메가를 옴 기호로 가진다. 수학 글자는 NFKC로 바꾼다. 뮤는 Wanted Sans의 마이크로 기호다
        assert fonts.resolve("Ω(n) 𝐿 μ") == chr(0x2126) + "(n) L " + chr(0xB5)
        assert fonts.font_of(chr(0x2126)) == SYMBOL
        assert fonts.advance("가", True) > 0 and fonts.advance("α", False) == pytest.approx(0.631, abs=0.001)


def test_the_embedded_font_holds_only_the_letters_written():
    with Fonts() as fonts:
        data = fonts.subset(False, set("번역문"))
    font = TTFont(io.BytesIO(data))
    assert {chr(code) for code in font.getBestCmap()} == set("번역문")
    assert len(data) < 20_000


def _pdf(tmp_path, rotation: int = 0) -> tuple[bytes, object]:
    """두 쪽: 쪽 1에 Helvetica 원문 한 줄"""
    document = pdfium.PdfDocument.new()
    for _ in range(2):
        page = document.new_page(612, 792)
        page.close()
    page = document[0]
    item = raw.FPDFPageObj_NewTextObj(document.raw, b"Helvetica", 12.0)
    text = "Original line".encode("utf-16-le") + bytes(2)
    raw.FPDFText_SetText(item, ctypes.cast(ctypes.c_char_p(text), ctypes.POINTER(ctypes.c_ushort)))
    raw.FPDFPageObj_Transform(item, 1, 0, 0, 1, 61.2, 700)
    raw.FPDFPage_InsertObject(page.raw, item)
    raw.FPDFPage_GenerateContent(page.raw)
    if rotation:
        page.set_rotation(rotation)
    output = io.BytesIO()
    document.save(output)
    path = tmp_path / "source.pdf"
    path.write_bytes(output.getvalue())
    return output.getvalue(), path


# 쪽 1의 원문 줄 자리(정본 좌표): x 61.2~200, 기준선 700 근처
REGION = [0.1, 0.105, 0.33, 0.125]
BLOCK = TranslatedBlock("b1", "Original line", [REGION], 12.0, "", [Group("번역한 α 줄", [(0, 13)])])


def test_translated_pages_are_covered_and_others_stay_original(tmp_path):
    original, path = _pdf(tmp_path)
    highlight = Mark(0, "highlight", [[0.1, 0.105, 0.2, 0.105, 0.2, 0.125, 0.1, 0.125]], "하이라이트", "", "ff9783", (("b1", 0),))

    result = write_annotated(path, [highlight], 60, [TranslatedPage(0, [BLOCK])])

    assert result.startswith(original)  # 원본은 그대로, 뒤에 덧붙인다
    document = pdfium.PdfDocument(result)
    textpage = document[0].get_textpage()
    assert "번역한" in textpage.get_text_range()
    assert document[1].get_textpage().get_text_range() == ""  # 번역하지 않은 쪽
    last = textpage.get_charbox(textpage.search("줄").get_next()[0])
    # 번역문 오른쪽에 남은 원문 글자 자리는 흰 상자로 덮인다
    before = _dark_columns(pdfium.PdfDocument(original)[0])
    after = _dark_columns(document[0])
    covered = [x for x in before if x > last[2] + 2]
    assert covered and not any(x in after for x in covered)
    # 하이라이트는 번역 문장 자리로 옮겨 그 번역문 끝까지 칠한다(원래 quad는 x 61.2~122.4)
    [annotation] = [item.get_object() for item in pypdf.PdfReader(io.BytesIO(result)).pages[0]["/Annots"]]
    points = [float(value) for value in annotation["/QuadPoints"]]
    assert points[0] == pytest.approx(61.2, abs=0.1)
    assert points[2] == pytest.approx(last[2], abs=2)


def _dark_columns(page) -> set[int]:
    """원문 줄 높이(사용자 공간 y 700~709)에서 어두운 화소가 있는 x (pt)"""
    image = page.render(scale=1).to_pil().convert("L")
    return {x for x in range(612) for y in range(792 - 709, 792 - 699) if image.getpixel((x, y)) < 128}


def test_a_rotated_page_is_written_along_the_screen(tmp_path):
    _, path = _pdf(tmp_path, rotation=90)
    region = PageSpace((0, 0, 612, 792), 90)
    # 화면에서 가로로 놓인 줄: 화면 (100~400, 50~64) → 정본
    u0, v0 = region.to_norm(100, 50)
    u1, v1 = region.to_norm(400, 64)
    block = TranslatedBlock("b1", "x", [[min(u0, u1), min(v0, v1), max(u0, u1), max(v0, v1)]], 12.0, "", [Group("돌린 쪽 번역", [(0, 1)])])

    result = write_annotated(path, [], 60, [TranslatedPage(0, [block])])

    textpage = pdfium.PdfDocument(result)[0].get_textpage()
    [index, _] = textpage.search("돌린").get_next()
    first, second = textpage.get_charbox(index), textpage.get_charbox(index + 1)
    # 화면에서 오른쪽으로 쓴 글은 시계 방향으로 돌린 쪽의 사용자 공간에서 위로 나아간다
    assert second[1] > first[3] - 1 and abs(second[0] - first[0]) < 2
    assert 100 < first[1] < 140  # 화면 x 100 → 사용자 y 100 근처
