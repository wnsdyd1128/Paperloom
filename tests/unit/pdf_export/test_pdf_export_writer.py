"""표시를 PDF 주석으로 붙이기 (paperloom.pdf_export.writer): 좌표 되돌리기, 메모 아이콘 자리, 하위 프로세스 실패."""

import io

import pypdf
from pypdf.annotations import Link
import pytest

from paperloom.pdf_export.marks import Mark
from paperloom.pdf_export.writer import ICON, MARGIN_INSET, ExportFailed, note_rect, to_user_space, write_annotated

VIEW = (50.0, 100.0, 562.0, 742.0)  # CropBox가 MediaBox 안으로 들어간 쪽


def test_canonical_points_go_back_to_user_space_of_the_view_box():
    assert to_user_space(0, 0, VIEW) == (50.0, 742.0)  # 좌상단
    assert to_user_space(1, 1, VIEW) == (562.0, 100.0)
    assert to_user_space(0.5, 0.25, VIEW) == (306.0, 581.5)


def test_note_icons_sit_in_the_nearer_margin_at_the_first_line():
    left_quads = [[0.1, 0.25, 0.4, 0.25, 0.4, 0.27, 0.1, 0.27], [0.1, 0.2, 0.4, 0.2, 0.4, 0.22, 0.1, 0.22]]
    assert note_rect(left_quads, VIEW, []) == (50 + MARGIN_INSET, 613.6 - ICON, 50 + MARGIN_INSET + ICON, 613.6)

    right = note_rect([[0.6, 0.25, 0.9, 0.25, 0.9, 0.27, 0.6, 0.27]], VIEW, [])
    assert (right[0], right[2]) == (562 - MARGIN_INSET - ICON, 562 - MARGIN_INSET)


def test_note_icons_on_the_same_spot_stack_downwards_but_stay_on_the_page():
    quads = [[0.1, 0.5, 0.4, 0.5, 0.4, 0.52, 0.1, 0.52]]
    first = note_rect(quads, VIEW, [])
    second = note_rect(quads, VIEW, [first])
    assert second[3] <= first[1] and second[0] == first[0]

    bottom = [[0.1, 0.99, 0.4, 0.99, 0.4, 1.0, 0.1, 1.0]]
    lowest = note_rect(bottom, VIEW, [])
    assert lowest[1] == pytest.approx(VIEW[1])  # 쪽 아래 끝에서도 아이콘이 쪽 안에 있다
    assert note_rect(bottom, VIEW, [lowest])[1] == pytest.approx(VIEW[1])  # 더 내릴 곳이 없으면 겹친다


def _pdf(tmp_path, **page_boxes) -> tuple[bytes, object]:
    writer = pypdf.PdfWriter()
    page = writer.add_blank_page(width=612, height=792)
    for name, box in page_boxes.items():
        setattr(page, name, pypdf.generic.RectangleObject(box))
    buffer = io.BytesIO()
    writer.write(buffer)
    path = tmp_path / "source.pdf"
    path.write_bytes(buffer.getvalue())
    return buffer.getvalue(), path


def test_marks_are_appended_as_pdf_annotations_after_the_untouched_original(tmp_path):
    original, path = _pdf(tmp_path, cropbox=VIEW)
    quad = [0.1, 0.25, 0.4, 0.25, 0.4, 0.27, 0.1, 0.27]
    marks = [
        Mark(0, "highlight", [quad], "주석", "핵심 가정 ✓", "ff9783"),
        Mark(0, "note", [quad], "설명", "“worst-case”\n\n설명 글", "ec3013"),
    ]

    result = write_annotated(path, marks, timeout_seconds=60)

    assert result.startswith(original)
    highlight, note = (item.get_object() for item in pypdf.PdfReader(io.BytesIO(result)).pages[0]["/Annots"])
    assert (highlight["/Subtype"], highlight["/T"], highlight["/Contents"]) == ("/Highlight", "주석", "핵심 가정 ✓")
    # 좌상 → 우상 → 좌하 → 우하
    assert [round(float(value), 2) for value in highlight["/QuadPoints"]] == [101.2, 581.5, 254.8, 581.5, 101.2, 568.66, 254.8, 568.66]
    assert [round(float(value), 3) for value in highlight["/C"]] == [1.0, 0.592, 0.514]
    assert highlight["/F"] == 4  # 인쇄된다
    assert (note["/Subtype"], note["/Name"], note["/T"], note["/Contents"]) == ("/Text", "/Comment", "설명", "“worst-case”\n\n설명 글")
    assert note["/F"] == 4 | 8 | 16  # 인쇄·확대해도 같은 크기·돌리지 않음
    assert [float(value) for value in note["/Rect"]][0] == 50 + MARGIN_INSET


def test_existing_annotations_of_the_page_are_kept(tmp_path):
    writer = pypdf.PdfWriter()
    writer.add_blank_page(width=612, height=792)
    writer.add_annotation(0, Link(rect=(10, 10, 50, 50), url="https://example.org"))
    buffer = io.BytesIO()
    writer.write(buffer)
    path = tmp_path / "linked.pdf"
    path.write_bytes(buffer.getvalue())

    result = write_annotated(path, [Mark(0, "note", [[0.1, 0.1, 0.2, 0.1, 0.2, 0.12, 0.1, 0.12]], "주석", "메모", "ff9783")], 60)

    subtypes = [item.get_object()["/Subtype"] for item in pypdf.PdfReader(io.BytesIO(result)).pages[0]["/Annots"]]
    assert subtypes == ["/Link", "/Text"]


def test_a_broken_pdf_or_a_slow_one_fails_with_its_code(tmp_path):
    broken = tmp_path / "broken.pdf"
    broken.write_bytes(b"%PDF-1.7\nnot really a pdf")
    with pytest.raises(ExportFailed) as failed:
        write_annotated(broken, [], 60)
    assert failed.value.code == "EXPORT_FAILED"

    _, path = _pdf(tmp_path)
    with pytest.raises(ExportFailed) as slow:
        write_annotated(path, [], timeout_seconds=0.001)
    assert slow.value.code == "RESOURCE_LIMIT"
