"""번역본 PDF에서 번역문으로 덮은 원문 글 지우기 (paperloom.pdf_export.covered_text, 2026-11-17 사용자 보고: 외부 뷰어에서
끌어 고르면 흰 상자 밑 원문 글까지 잡혔다)."""

import io

import pypdf
import pypdfium2 as pdfium
import pytest
from pypdf.generic import ArrayObject, ContentStream, DictionaryObject, NameObject, NumberObject, TextStringObject

from paperloom.pdf_export.covered_text import strip
from paperloom.pdf_export.translated import Group, TranslatedBlock, TranslatedPage
from paperloom.pdf_export.writer import write_annotated


def _text(value: str) -> TextStringObject:
    return TextStringObject(value)


def _number(value: int) -> NumberObject:
    return NumberObject(value)


# 글을 그리는 연산 A~E: B는 A에 이어 쓰고(글꼴만 바꿈), D·E는 스스로 다음 줄로 간다
LINES = [
    ([], b"BT"),
    ([NameObject("/F1"), _number(10)], b"Tf"),
    ([_number(72), _number(700)], b"Td"),
    ([_text("A")], b"Tj"),
    ([NameObject("/F2"), _number(10)], b"Tf"),
    ([ArrayObject([_text("B"), _number(-250)])], b"TJ"),
    ([_number(0), _number(-12)], b"Td"),
    ([_text("C")], b"Tj"),
    ([_text("D")], b"'"),
    ([_number(1), _number(2), _text("E")], b'"'),
    ([], b"ET"),
]


def _operators(operations) -> list:
    return [(operator, [str(value) for value in operands]) for operands, operator in operations]


def test_covered_text_goes_and_state_and_line_moves_stay():
    result = strip(LINES, [True] * 5)

    assert _operators(result) == [
        (b"BT", []),
        (b"Tf", ["/F1", "10"]),
        (b"Td", ["72", "700"]),
        (b"Tf", ["/F2", "10"]),
        (b"Td", ["0", "-12"]),
        (b"T*", []),  # ' 는 다음 줄로 옮기기만 남는다
        (b"Tw", ["1"]),  # " 는 글 간격 설정과 줄 옮기기가 남는다
        (b"Tc", ["2"]),
        (b"T*", []),
        (b"ET", []),
    ]


def test_text_that_a_kept_text_continues_from_stays():
    # A를 지우면 이어 쓰는 B가 A 폭만큼 당겨지므로 A도 남긴다. C 뒤의 D는 스스로 다음 줄로 가므로 C는 지운다
    result = strip(LINES, [True, False, True, True, False])

    assert [operator for _, operator in result] == [b"BT", b"Tf", b"Td", b"Tj", b"Tf", b"TJ", b"Td", b"T*", b'"', b"ET"]
    assert str(result[3][0][0]) == "A"


def test_empty_text_and_spacing_only_arrays_are_not_text_objects():
    operations = [
        ([], b"BT"),
        ([_text("")], b"Tj"),
        ([ArrayObject([_number(-500)])], b"TJ"),
        ([_text("F")], b"Tj"),
        ([], b"ET"),
    ]

    assert [operator for _, operator in strip(operations, [True])] == [b"BT", b"Tj", b"TJ", b"ET"]
    assert strip(operations, [True, True]) is None  # pdfium 글 객체 수와 다르면 그 쪽은 덮기만 한다


def _source(tmp_path):
    """쪽 하나: 덮을 두 줄(y 700·686), 덮지 않을 한 줄(y 400), 파란 네모(300~350)"""
    writer = pypdf.PdfWriter()
    page = writer.add_blank_page(612, 792)
    helvetica = DictionaryObject(
        {NameObject("/Type"): NameObject("/Font"), NameObject("/Subtype"): NameObject("/Type1"), NameObject("/BaseFont"): NameObject("/Helvetica")}
    )
    page[NameObject("/Resources")] = DictionaryObject({NameObject("/Font"): DictionaryObject({NameObject("/F1"): helvetica})})
    content = ContentStream(None, writer)
    content.set_data(
        b"BT /F1 12 Tf 61.2 700 Td (Covered first) Tj 0 -14 Td (Covered second) Tj ET\n"
        b"0 0 1 rg 300 300 50 50 re f\n"
        b"BT /F1 12 Tf 61.2 400 Td (Kept line) Tj ET\n"
    )
    page.replace_contents(content)
    output = io.BytesIO()
    writer.write(output)
    path = tmp_path / "source.pdf"
    path.write_bytes(output.getvalue())
    return output.getvalue(), path


def test_the_exported_page_keeps_only_text_that_shows(tmp_path):
    original, path = _source(tmp_path)
    region = [0.1, 0.104, 0.33, 0.14]  # 두 원문 줄 자리(사용자 공간 y 약 681~710)
    block = TranslatedBlock("b1", "Covered first Covered second", [region], 12.0, "", [Group("덮은 번역문", [(0, 28)])])

    result = write_annotated(path, [], 60, [TranslatedPage(0, [block])])

    assert result.startswith(original)  # 지워도 원본 뒤에 덧붙여 쓴다
    page = pdfium.PdfDocument(result)[0]
    text = page.get_textpage().get_text_range()
    assert "덮은 번역문" in text and "Kept line" in text
    assert "Covered" not in text  # 흰 상자 밑 원문은 끌어 고르거나 복사해도 잡히지 않는다
    textpage = page.get_textpage()
    [index, _] = textpage.search("Kept").get_next()
    assert textpage.get_charbox(index)[0] == pytest.approx(61.2, abs=1)  # 남은 글은 제자리다
    assert page.render(scale=1).to_pil().convert("RGB").getpixel((325, 792 - 325)) == (0, 0, 255)  # 그림은 그대로
