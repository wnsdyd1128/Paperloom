"""원본 PDF에 표시(marks.Mark)를 PDF 표준 주석으로 붙인다.

원본은 고치지 않고 뒤에 덧붙여 쓴다(pypdf 증분 저장). 그래서 결과의 앞부분은 원본과 바이트까지 같고, 원문 쪽은 그대로다.
좌표는 anchor.v1 정본 좌표(회전 전 view box = CropBox ∩ MediaBox 기준, 좌상단 원점, 0~1, reading.geometry)를 PDF 사용자
공간으로 되돌린다. 주석 좌표는 회전 전 공간이므로 /Rotate와 상관없다.

신뢰할 수 없는 PDF를 다루므로 영역 이미지(reading.region_image)처럼 시간 제한이 있는 하위 프로세스에서 쓴다.
하위 프로세스: `python -m paperloom.pdf_export.writer <pdf>`, stdin에 표시 목록(JSON) → stdout에 PDF.
"""

import io
import json
import subprocess
import sys
from collections.abc import Sequence
from dataclasses import asdict
from pathlib import Path

from paperloom.infrastructure.isolation import limit_resources
from paperloom.pdf_export.marks import Mark

Box = tuple[float, float, float, float]  # x0, y0, x1, y1 (PDF 사용자 공간)

ICON = 18.0  # 메모 아이콘 한 변 (pt). 확대해도 크기가 그대로다(NoZoom)
ICON_GAP = 2.0
MARGIN_INSET = 8.0  # 쪽 가장자리에서 아이콘까지


class ExportFailed(Exception):
    """code: RESOURCE_LIMIT(시간 초과), EXPORT_FAILED(그 밖의 실패)."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def write_annotated(path: Path, marks: Sequence[Mark], timeout_seconds: float) -> bytes:
    try:
        result = subprocess.run(
            [sys.executable, "-m", "paperloom.pdf_export.writer", str(path)],
            input=json.dumps([asdict(mark) for mark in marks]).encode("utf-8"),
            capture_output=True,
            timeout=timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired:
        raise ExportFailed("RESOURCE_LIMIT") from None
    if result.returncode != 0 or not result.stdout.startswith(b"%PDF"):
        raise ExportFailed("EXPORT_FAILED")
    return result.stdout


def to_user_space(u: float, v: float, view_box: Box) -> tuple[float, float]:
    """reading.geometry.normalize_point의 역."""
    x0, y0, x1, y1 = view_box
    return x0 + u * (x1 - x0), y1 - v * (y1 - y0)


def note_rect(quads: Sequence[Sequence[float]], view_box: Box, taken: Sequence[Box]) -> Box:
    """메모 아이콘 자리: 표시의 첫 줄 높이에서, 표시가 쪽 왼쪽 반에 있으면 왼쪽, 아니면 오른쪽 여백.
    같은 쪽의 앞 아이콘(taken)과 겹치면 쪽 아래 끝까지 한 칸씩 내린다."""
    us = [u for quad in quads for u in quad[0::2]]
    x0, y0, x1, y1 = view_box
    left = x0 + MARGIN_INSET if (min(us) + max(us)) / 2 < 0.5 else x1 - MARGIN_INSET - ICON
    top = to_user_space(0, min(v for quad in quads for v in quad[1::2]), view_box)[1]
    top = max(y0 + ICON, top)
    rect = (left, top - ICON, left + ICON, top)
    while any(_overlaps(rect, other) for other in taken) and rect[1] - ICON - ICON_GAP >= y0:
        rect = (rect[0], rect[1] - ICON - ICON_GAP, rect[2], rect[3] - ICON - ICON_GAP)
    return rect


def _overlaps(a: Box, b: Box) -> bool:
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


def _view_box(page) -> Box:
    """reading.geometry.page_geometry와 같은 규칙: CropBox(없으면 MediaBox)와 MediaBox의 교집합."""
    media = _ordered(page.mediabox)
    crop = _ordered(page.cropbox)
    return max(media[0], crop[0]), max(media[1], crop[1]), min(media[2], crop[2]), min(media[3], crop[3])


def _ordered(box) -> Box:
    x0, y0, x1, y1 = (float(value) for value in box)
    return min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1)


def _annotate(path: str, marks: list[dict]) -> bytes:
    import pypdf
    from pypdf.annotations import Highlight, Text
    from pypdf.constants import AnnotationFlag
    from pypdf.generic import ArrayObject, FloatObject, NameObject, NumberObject, TextStringObject

    writer = pypdf.PdfWriter(path, incremental=True)
    taken: dict[int, list[Box]] = {}
    for mark in marks:
        page_index = mark["page_index"]
        view_box = _view_box(writer.pages[page_index])
        if mark["kind"] == "highlight":
            points: list[float] = []
            for quad in mark["quads"]:
                corners = [to_user_space(u, v, view_box) for u, v in zip(quad[0::2], quad[1::2], strict=True)]
                # 정본 quad는 좌상 → 우상 → 우하 → 좌하, /QuadPoints는 좌상 → 우상 → 좌하 → 우하(Acrobat이 쓰는 순서)다
                for x, y in (corners[0], corners[1], corners[3], corners[2]):
                    points += [x, y]
            xs, ys = points[0::2], points[1::2]
            annotation = Highlight(
                rect=(min(xs), min(ys), max(xs), max(ys)),
                quad_points=ArrayObject(FloatObject(value) for value in points),
                highlight_color=mark["rgb"],
                printing=True,
            )
            if mark["contents"]:
                annotation[NameObject("/Contents")] = TextStringObject(mark["contents"])
        else:
            rect = note_rect(mark["quads"], view_box, taken.setdefault(page_index, []))
            taken[page_index].append(rect)
            annotation = Text(rect=rect, text=mark["contents"])
            # pypdf의 flags 인자는 표준 키(/F)가 아닌 /Flags에 써서 뷰어가 읽지 못한다
            del annotation["/Flags"]
            annotation[NameObject("/F")] = NumberObject(AnnotationFlag.PRINT | AnnotationFlag.NO_ZOOM | AnnotationFlag.NO_ROTATE)
            annotation[NameObject("/Name")] = NameObject("/Comment")
            annotation[NameObject("/C")] = ArrayObject(FloatObject(int(mark["rgb"][i : i + 2], 16) / 255) for i in (0, 2, 4))
        annotation[NameObject("/T")] = TextStringObject(mark["label"])
        writer.add_annotation(page_index, annotation)
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()


def _main() -> None:
    limit_resources()
    marks = json.loads(sys.stdin.buffer.read())
    sys.stdout.buffer.write(_annotate(sys.argv[1], marks))


if __name__ == "__main__":
    _main()
