"""번호 붙은 논문 그림 (2026-11-09 사용자 요청: "논문의 발표 슬라이드에서 논문에서 사용한 figure도 같이 첨부해서 만들어줘").

Claude는 받은 그림을 옮겨 적지 못하고, 아티팩트는 바깥 주소를 불러오지 못한다. 그래서 아티팩트에는 그림 번호
(`paperloom-figure:3`)만 쓰고, 웹이 그릴 때 이 모듈이 찾은 그림 영역의 PNG로 바꿔 넣는다(apps/web features/artifacts/paperFigures.ts).
순수 함수만 둔다. 좌표는 §6.1 정본 좌표(좌상단 원점, 0~1)다.

- 그림 번호는 캡션 문단에서 읽는다: "Figure 3: …", "Fig. 2. …", "FIGURE 4 Overview", "그림 1. …", "<그림 2> …".
  "Figure 3 shows …"·"그림 3은 …"처럼 번호 뒤가 문장으로 이어지면 본문이다. 같은 번호는 읽는 차례로 처음 것이다. 본문이 아닌
  문단(그림·표 안 글자, 머리글·바닥글, 참고문헌)과 그림 목록 줄(점선 뒤 쪽 번호)은 캡션으로 보지 않는다.
- 그림 영역은 캡션 바로 위(없으면 아래)의 그림 후보(reading.figures)에서 시작한다: 캡션과 가로로 겹치고, 틈이 FIGURE_GAP 안이며,
  그 사이에 본문 문단이 없는 후보들이다. 그 상자에 GROW 안으로 닿는 다른 후보와 그림의 글(그림 안 글자, 축 이름·눈금·범례·
  하위 그림 설명 같은 짧은 글)을 바뀌지 않을 때까지 붙인다. 벡터 그림의 축 글자는 그림 후보 밖에 있기 때문이다
  (reading.figures 머리 설명). 본문 문단과 다른 캡션은 붙이지 않고, 캡션 너머로는 넓히지 않는다.
"""

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from paperloom.documents.block_kinds import IN_FIGURE, NOT_BODY, is_caption

Box = tuple[float, float, float, float]  # 정본 좌표 (u0, v0, u1, v1)

# 그림 캡션의 머리: 이름과 번호(부록·보충 그림의 A1·S2 포함)
_HEAD = re.compile(r"[<\[(]?\s*(?:fig(?:ure)?\.?|그림)\s*([A-Z]?\d+)(?!\w)", re.IGNORECASE)
# 번호 뒤: 끝, 구두점·닫는 괄호, 또는 띄우고 소문자·숫자 아닌 글자(제목 첫 글자). "Figure 3 shows"·"그림 3은"은 본문이다
_AFTER_LABEL = re.compile(r"$|\s*[:.|>\])\-–—]|\s+[^a-z0-9]")
_LISTING = re.compile(r"(?:\.\s*){3,}\d+\s*$")  # 그림 목록 줄: "Figure 1. Overview ........ 3"

CAPTION_CHARS = 300  # 목록에 싣는 캡션 길이
FIGURE_GAP = 0.08  # 캡션과 그림 사이 틈의 상한(쪽 크기 비율). context.builder.CAPTION_GAP과 같은 값
GROW = 0.015  # 그림 상자에 이만큼 안으로 닿는 후보·그림의 글은 그림의 일부다(쪽 크기 비율, 약 10 pt). 두 단 사이(약 24 pt)보다 작다
TOUCH = 0.005  # 캡션과 이만큼 겹쳐도 캡션 너머로 보지 않는다
LABEL_CHARS = 60  # 본문 표시가 없는 문단이 이보다 짧으면 그림의 글(축 이름·범례·하위 그림 설명)일 수 있다
PAD = 0.005  # 그릴 때 그림 상자 둘레 여백


@dataclass(frozen=True)
class Paragraph:
    """추출된 문단 하나 (documents text_blocks)."""

    block_id: str
    text: str
    regions: Sequence[Sequence[float]]  # 줄마다 정본 좌표 상자
    flags: Sequence[str]

    @property
    def box(self) -> Box:
        return _union_all([(region[0], region[1], region[2], region[3]) for region in self.regions])


@dataclass(frozen=True)
class NumberedFigure:
    label: str  # 캡션의 번호(대문자): "3", "S1"
    page_index: int
    caption: str  # 캡션 문단(CAPTION_CHARS까지)
    block_id: str  # 캡션 문단


def figure_label(text: str) -> str | None:
    """그림 캡션이면 그 번호(글자는 대문자), 아니면 None."""
    stripped = text.strip()
    head = _HEAD.match(stripped)
    if head is None or _AFTER_LABEL.match(stripped, head.end()) is None or _LISTING.search(stripped):
        return None
    return head.group(1).upper()


def numbered_figures(pages: Iterable[tuple[int, Sequence[Paragraph]]]) -> list[NumberedFigure]:
    """(쪽 번호, 그 쪽의 문단을 읽는 차례로)에서 번호 붙은 그림을 문서 차례로. 같은 번호는 처음 캡션이다."""
    found: dict[str, NumberedFigure] = {}
    for page_index, paragraphs in pages:
        for paragraph in paragraphs:
            if not paragraph.regions or not NOT_BODY.isdisjoint(paragraph.flags):
                continue
            label = figure_label(paragraph.text)
            if label is not None and label not in found:
                caption = " ".join(paragraph.text.split())
                if len(caption) > CAPTION_CHARS:
                    caption = caption[: CAPTION_CHARS - 1] + "…"
                found[label] = NumberedFigure(label, page_index, caption, paragraph.block_id)
    return list(found.values())


def figure_box(caption: Paragraph, candidates: Sequence[Box], paragraphs: Sequence[Paragraph]) -> Box | None:
    """캡션이 단 그림의 영역(둘레 여백 포함). candidates는 같은 쪽의 그림 후보, paragraphs는 같은 쪽의 문단(캡션이 있어도 된다).
    캡션 위를 먼저 보고, 없으면 아래(표처럼 캡션이 위에 오는 그림)를 본다. 찾지 못하면 None."""
    texts = [(paragraph.box, _figure_text(paragraph)) for paragraph in paragraphs if paragraph.block_id != caption.block_id and paragraph.regions]
    for above in (True, False):
        box = _figure_beside(caption.box, candidates, texts, above)
        if box is not None:
            return max(0.0, box[0] - PAD), max(0.0, box[1] - PAD), min(1.0, box[2] + PAD), min(1.0, box[3] + PAD)
    return None


def _figure_text(paragraph: Paragraph) -> bool:
    """그림의 일부가 될 수 있는 글: 그림 안 글자, 또는 본문 표시가 없는 짧은 글(캡션은 빼고)."""
    if IN_FIGURE in paragraph.flags:
        return True
    text = paragraph.text.strip()
    return NOT_BODY.isdisjoint(paragraph.flags) and len(text) < LABEL_CHARS and not is_caption(text) and figure_label(text) is None


def _figure_beside(caption: Box, candidates: Sequence[Box], texts: Sequence[tuple[Box, bool]], above: bool) -> Box | None:
    def beside(box: Box) -> bool:  # 캡션의 그쪽에 있다(캡션 너머로 넘지 않는다)
        return box[3] <= caption[1] + TOUCH if above else box[1] >= caption[3] - TOUCH

    def gap(box: Box) -> float:
        return caption[1] - box[3] if above else box[1] - caption[3]

    def between(wall: Box, box: Box) -> bool:  # 문단이 후보와 캡션 사이에 있다
        if above:
            return wall[1] >= box[3] - TOUCH and wall[3] <= caption[1] + TOUCH
        return wall[1] >= caption[3] - TOUCH and wall[3] <= box[1] + TOUCH

    walls = [box for box, figure_text in texts if not figure_text and beside(box)]
    seeds = [
        box
        for box in candidates
        if beside(box)
        and _spans_overlap(box, caption)
        and gap(box) <= FIGURE_GAP
        and not any(_spans_overlap(wall, box) and between(wall, box) for wall in walls)
    ]
    if not seeds:
        return None
    figure = _union_all(seeds)
    parts = [box for box in candidates if beside(box)] + [box for box, figure_text in texts if figure_text and beside(box)]
    grown = True
    while grown:  # 붙인 것 때문에 새로 닿는 것이 생길 수 있어 바뀌지 않을 때까지
        grown = False
        for part in parts:
            if not _contains(figure, part) and _near(part, figure):
                figure = _union_all([figure, part])
                grown = True
    return figure


def _spans_overlap(a: Box, b: Box) -> bool:
    """가로 범위가 겹친다."""
    return a[0] < b[2] and b[0] < a[2]


def _near(a: Box, b: Box) -> bool:
    return a[0] - GROW <= b[2] and b[0] - GROW <= a[2] and a[1] - GROW <= b[3] and b[1] - GROW <= a[3]


def _contains(outer: Box, inner: Box) -> bool:
    return outer[0] <= inner[0] and outer[1] <= inner[1] and inner[2] <= outer[2] and inner[3] <= outer[3]


def _union_all(boxes: Sequence[Box]) -> Box:
    return min(box[0] for box in boxes), min(box[1] for box in boxes), max(box[2] for box in boxes), max(box[3] for box in boxes)
