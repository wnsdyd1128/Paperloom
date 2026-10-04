"""쪽의 그림 후보 (그림 클릭 선택, IMPL §10.6).

일반 PDF 뷰어처럼 그림을 눌러 고를 수 있게, 쪽에 그려진 텍스트 아닌 객체(이미지, Form XObject, 벡터
경로, 음영)를 pypdfium2로 모아 서로 닿거나 가까운 것끼리 묶는다. 표의 가로줄 같은 얇은 선, 로고 같은 작은
장식, 쪽 전체를 덮는 배경, 쪽 밖으로 대부분 나간 객체는 뺀다. 결과는 §6.1 정본 좌표의 상자다.

그림 안의 글자(축 이름 등)가 그림 객체 밖에 따로 놓인 벡터 그림은 그 글자를 포함하지 않는다.
신뢰할 수 없는 PDF를 다루므로 객체 수집은 격리 하위 프로세스에서 한다:
`python -m paperloom.reading.figures <pdf> <page_index>` → stdout에 JSON.
"""

import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from paperloom.infrastructure.isolation import limit_resources

Box = tuple[float, float, float, float]  # PDF 사용자 공간 (left, bottom, right, top)

MERGE_GAP = 3.0  # pt. 이만큼 떨어진 객체는 한 그림으로 본다
MIN_SIDE = 36.0  # pt. 폭·높이가 이보다 작으면 선이나 장식(로고·아이콘)이다
MAX_PAGE_FRACTION = 0.8  # 쪽 넓이에서 이보다 크면 배경이다
MIN_VISIBLE_FRACTION = 0.5  # 객체가 쪽 안에 이만큼은 있어야 한다


@dataclass(frozen=True)
class Graphic:
    kind: str  # image, form, path, shading
    box: Box
    filled: bool = False
    stroked: bool = False


@dataclass(frozen=True)
class Figure:
    box: tuple[float, float, float, float]  # 정본 좌표 (u0, v0, u1, v1)
    source: str  # image, form, vector


class FiguresFailed(Exception):
    pass


def find_figures(path: Path, page_index: int, timeout_seconds: float) -> list[Figure]:
    try:
        result = subprocess.run(
            [sys.executable, "-m", "paperloom.reading.figures", str(path), str(page_index)],
            capture_output=True,
            timeout=timeout_seconds,
            check=False,
        )
        report = json.loads(result.stdout)
    except (subprocess.TimeoutExpired, ValueError):
        raise FiguresFailed() from None
    graphics = [Graphic(item["kind"], tuple(item["box"]), item["filled"], item["stroked"]) for item in report["graphics"]]
    return figure_candidates(graphics, tuple(report["view_box"]))


def figure_candidates(graphics: list[Graphic], view_box: Box) -> list[Figure]:
    """그림 객체들을 묶어 그림 후보로 만든다. 읽는 순서(위 → 왼쪽)로 돌려준다."""
    page_area = _area(view_box)
    items = []
    for graphic in graphics:
        if graphic.kind == "path" and not (graphic.filled or graphic.stroked):
            continue  # 잘라내기용 경로 등 보이지 않는 경로
        clipped = _intersect(graphic.box, view_box)
        if clipped is None or _area(clipped) < MIN_VISIBLE_FRACTION * _area(graphic.box):
            continue
        # 쪽 전체를 덮는 배경은 묶기 전에 뺀다. 남겨 두면 모든 객체와 닿아 그림들이 한 덩어리가 된다.
        if _area(clipped) > MAX_PAGE_FRACTION * page_area:
            continue
        items.append((clipped, graphic))

    clusters = [(box, [graphic]) for box, graphic in items]
    merged = True
    while merged:  # 묶음이 커지면 다른 묶음과 새로 닿을 수 있어 바뀌지 않을 때까지 반복한다
        merged = False
        result: list[tuple[Box, list[Graphic]]] = []
        for box, members in clusters:
            for index, (other_box, other_members) in enumerate(result):
                if _near(box, other_box):
                    result[index] = (_union(box, other_box), other_members + members)
                    merged = True
                    break
            else:
                result.append((box, members))
        clusters = result

    figures = []
    for box, members in clusters:
        width, height = box[2] - box[0], box[3] - box[1]
        if width < MIN_SIDE or height < MIN_SIDE or width * height > MAX_PAGE_FRACTION * page_area:
            continue
        kinds = {member.kind for member in members}
        # 경로 하나짜리 선(획만 있는 경로)은 그림이 아니다. 이미지·Form·음영, 여러 경로, 채운 도형은 그림이다.
        if kinds <= {"path"} and len(members) < 2 and not members[0].filled:
            continue
        source = "image" if kinds == {"image"} else "form" if "form" in kinds else "vector"
        figures.append(Figure(_normalize(box, view_box), source))
    return sorted(figures, key=lambda figure: (figure.box[1], figure.box[0]))


def _normalize(box: Box, view_box: Box) -> tuple[float, float, float, float]:
    x0, y0, x1, y1 = view_box
    left, bottom, right, top = box
    return (left - x0) / (x1 - x0), (y1 - top) / (y1 - y0), (right - x0) / (x1 - x0), (y1 - bottom) / (y1 - y0)


def _intersect(a: Box, b: Box) -> Box | None:
    box = (max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3]))
    return box if box[0] <= box[2] and box[1] <= box[3] else None


def _union(a: Box, b: Box) -> Box:
    return min(a[0], b[0]), min(a[1], b[1]), max(a[2], b[2]), max(a[3], b[3])


def _near(a: Box, b: Box) -> bool:
    return (
        a[0] - MERGE_GAP <= b[2]
        and b[0] - MERGE_GAP <= a[2]
        and a[1] - MERGE_GAP <= b[3]
        and b[1] - MERGE_GAP <= a[3]
    )


def _area(box: Box) -> float:
    # 가로선·세로선은 넓이가 0이므로 두께를 1 pt로 본다.
    return max(box[2] - box[0], 1.0) * max(box[3] - box[1], 1.0)


def _collect(path: str, page_index: int) -> dict:
    import pypdfium2 as pdfium

    document = pdfium.PdfDocument(path)
    try:
        page = document[page_index]
        graphics = [
            {"kind": graphic.kind, "box": list(graphic.box), "filled": graphic.filled, "stroked": graphic.stroked}
            for graphic in page_graphics(page)
        ]
        return {"view_box": list(page.get_bbox()), "graphics": graphics}
    finally:
        document.close()


def page_graphics(page) -> list[Graphic]:
    """열린 pypdfium2 쪽의 텍스트 아닌 객체. 본문 추출(documents.extract)도 그림 안 글자를 가리려고 쓴다."""
    import ctypes

    import pypdfium2.raw as pdfium_c

    kinds = {
        pdfium_c.FPDF_PAGEOBJ_PATH: "path",
        pdfium_c.FPDF_PAGEOBJ_IMAGE: "image",
        pdfium_c.FPDF_PAGEOBJ_SHADING: "shading",
        pdfium_c.FPDF_PAGEOBJ_FORM: "form",
    }
    graphics = []
    for obj in page.get_objects(max_depth=1):  # Form XObject는 안을 들여다보지 않고 하나로 본다
        kind = kinds.get(obj.type)
        if kind is None:
            continue
        fill, stroke = ctypes.c_int(0), ctypes.c_int(0)
        if kind == "path":
            pdfium_c.FPDFPath_GetDrawMode(obj.raw, ctypes.byref(fill), ctypes.byref(stroke))
        graphics.append(Graphic(kind, tuple(obj.get_bounds()), fill.value != 0, bool(stroke.value)))
    return graphics


def _main() -> None:
    limit_resources()
    print(json.dumps(_collect(sys.argv[1], int(sys.argv[2]))))


if __name__ == "__main__":
    _main()
