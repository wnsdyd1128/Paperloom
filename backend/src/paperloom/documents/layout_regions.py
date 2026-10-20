"""레이아웃 모델이 찾은 영역(documents.layout_model)으로 문단의 본문 아님 표시를 고친다 (2026-10-19 사용자 요청: "알고리즘이나
표 이런 게 자꾸 번역되네"). 순수 함수만 둔다.

문단 상자의 COVER 이상을 덮는 영역 가운데 점수가 가장 높은 것을 그 문단의 분류로 본다(평가 기록
docs/gates/evidence/ui/2026-10-19_dla-evaluation.md와 같은 셈. 규칙은 번역하는데 모델이 뺀 100자 넘는 문단에 본문 문장이 없었다).
- 표·알고리즘 → in_table, 수식·식 번호 → math, 그림·차트·도장 → in_figure, 머리글 → page_header, 바닥글 → page_footer,
  쪽 번호 → 쪽 위 반이면 page_header 아니면 page_footer. 캡션(block_kinds.is_caption)은 상자 안이어도 본문이다.
- 규칙의 in_figure(벡터 그림 후보, reading.figures)는 모델이 본문으로 확신하고(BODY_SCORE) 본문 아닌 영역이 덮지 않으면 뗀다.
  그림 후보가 본문 단을 덮던 오판(The Power of 10 1–3쪽)을 바로잡는다. 규칙의 표·수식 표시는 둔다: 평가에서 모델이 본문으로 본
  것 대부분이 실제 표 칸의 코드·수식 줄이었다.
- 참고문헌(reference·reference_content)과 목차(content)는 지금 규칙(documents.references)을 따른다.
바꾸면 text_layout.LAYOUT_VERSION을 올린다(저장된 논문을 다시 추출한다).
"""

from paperloom.documents.block_kinds import IN_FIGURE, IN_TABLE, MATH, PAGE_FOOTER, PAGE_HEADER, is_caption
from paperloom.documents.layout_model import Region
from paperloom.reading.region_image import displayed_box

COVER = 0.5  # 문단 상자의 이 비율 이상을 덮는 영역만 그 문단의 분류 후보다(본문 안 인라인 수식 영역은 문단을 덮지 못한다)
BODY_SCORE = 0.92  # 모델이 본문으로 이 점수 이상 확신해야 규칙의 in_figure를 뗀다(평가: XML 코드 그림 0.91은 그림으로 둔다)
_FLAGS = {
    "table": IN_TABLE, "algorithm": IN_TABLE, "formula": MATH, "formula_number": MATH,
    "image": IN_FIGURE, "chart": IN_FIGURE, "seal": IN_FIGURE, "header": PAGE_HEADER, "footer": PAGE_FOOTER,
}
_BODY = frozenset({"text", "paragraph_title", "doc_title", "abstract", "figure_title", "footnote", "aside_text"})


def apply_layout(page: dict, regions: list[Region]) -> dict:
    """본문 추출 결과 한 쪽(page_index·rotation·blocks[]의 text·regions·quality_flags)의 문단 표시를 모델 영역으로 고친 쪽.
    regions는 /Rotate를 적용한 화면 쪽 기준이다(layout_model이 본 쪽 그림)."""
    back = (360 - page["rotation"]) % 360
    found = [(region, displayed_box(region.box, back)) for region in regions]  # 회전 전 정본 좌표로
    return {**page, "blocks": [_marked(block, found) for block in page["blocks"]]}


def _marked(block: dict, found: list[tuple[Region, tuple[float, float, float, float]]]) -> dict:
    if not block["regions"]:
        return block
    bounds = _bounds(block["regions"])
    area = max((bounds[2] - bounds[0]) * (bounds[3] - bounds[1]), 1e-9)
    covering = [(region, box) for region, box in found if _overlap(bounds, box) >= COVER * area]
    if not covering:
        return block
    best, box = max(covering, key=lambda item: item[0].score)
    flags = list(block["quality_flags"])
    flag = _FLAGS.get(best.label)
    if best.label == "number":
        flag = PAGE_HEADER if (box[1] + box[3]) / 2 < 0.5 else PAGE_FOOTER
    if flag:
        if not is_caption(block["text"]) and flag not in flags:
            flags.append(flag)
    elif (
        best.label in _BODY and best.score >= BODY_SCORE and IN_FIGURE in flags
        and not any(region.label in _FLAGS or region.label == "number" for region, _ in covering)
    ):
        flags.remove(IN_FIGURE)
    return {**block, "quality_flags": flags} if flags != block["quality_flags"] else block


def _bounds(regions: list[list[float]]) -> tuple[float, float, float, float]:
    return min(r[0] for r in regions), min(r[1] for r in regions), max(r[2] for r in regions), max(r[3] for r in regions)


def _overlap(a, b) -> float:
    return max(0.0, min(a[2], b[2]) - max(a[0], b[0])) * max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
