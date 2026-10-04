"""정본 좌표계의 서버 쪽 어댑터 (IMPL §6.1).

좌표는 회전 전 유효 view box(CropBox ∩ MediaBox) 기준, 좌상단 원점, 0~1로 정규화한다.
웹의 PDF.js 어댑터(apps/web/src/features/reader/geometry.ts)와 같은 계약이며,
tests/fixtures/pdf-layout/geometry-matrix.* contract fixture로 두 구현을 함께 검증한다.
UserUnit은 PDF 사용자 공간 좌표를 바꾸지 않으므로 정규화에 영향이 없다.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

Box = tuple[float, float, float, float]

# 정규화 공간에서 사실상 넓이가 없는 quad. 글자 하나(6pt, letter 용지)도 약 4e-5이므로 여유가 크다.
MIN_QUAD_AREA = 1e-9


@dataclass(frozen=True)
class PageGeometry:
    view_box: Box  # x0, y0, x1, y1 (PDF 사용자 공간)
    rotation: int  # 페이지 /Rotate (0, 90, 180, 270)


def normalize_point(x: float, y: float, view_box: Box) -> tuple[float, float]:
    x0, y0, x1, y1 = view_box
    return (x - x0) / (x1 - x0), (y1 - y) / (y1 - y0)


def quad_shape_problem(quad: Sequence[float]) -> str | None:
    """anchor.v1 quad(8개 수, 0~1 범위는 호출 전에 확인)의 모양 문제를 설명한다. 문제가 없으면 None.

    꼭짓점 순서는 좌상 → 우상 → 우하 → 좌하다. 마주 보는 변이 교차하는(나비 모양) quad와
    넓이가 없는 quad를 거부한다 (IMPL §6.2 서버 검사).
    """
    p0, p1, p2, p3 = zip(quad[0::2], quad[1::2], strict=True)
    if _segments_cross(p0, p1, p2, p3) or _segments_cross(p1, p2, p3, p0):
        return "자기 교차하는 quad입니다."
    area = 0.5 * abs(sum(a[0] * b[1] - b[0] * a[1] for a, b in ((p0, p1), (p1, p2), (p2, p3), (p3, p0))))
    if area < MIN_QUAD_AREA:
        return "넓이가 없는 quad입니다."
    return None


def _segments_cross(a, b, c, d) -> bool:
    """선분 ab와 cd가 끝점이 아닌 곳에서 교차하는지."""

    def side(p, q, r) -> float:
        return (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])

    return side(a, b, c) * side(a, b, d) < 0 and side(c, d, a) * side(c, d, b) < 0


def read_page_geometry(path: Path) -> list[PageGeometry]:
    """PDF 각 쪽의 view box와 회전을 읽는다.

    신뢰할 수 없는 업로드에 쓸 때는 documents.inspect처럼 격리 하위 프로세스에서 호출해야 한다.
    """
    import pypdfium2 as pdfium

    document = pdfium.PdfDocument(path)
    try:
        return [page_geometry(document[index]) for index in range(len(document))]
    finally:
        document.close()


def page_geometry(page) -> PageGeometry:
    """열린 pypdfium2 쪽의 view box와 회전."""
    media = _ordered(page.get_mediabox())
    crop = _ordered(page.get_cropbox())  # CropBox가 없으면 MediaBox
    # PDF.js의 page.view와 같은 규칙: CropBox와 MediaBox의 교집합
    view_box = (max(media[0], crop[0]), max(media[1], crop[1]), min(media[2], crop[2]), min(media[3], crop[3]))
    return PageGeometry(view_box=view_box, rotation=page.get_rotation())


def _ordered(box: tuple[float, float, float, float]) -> Box:
    x0, y0, x1, y1 = box
    return min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1)
