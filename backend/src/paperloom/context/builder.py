"""ContextPacket의 근거를 고르고 예산을 적용한다 (IMPL §7.2). 순수 함수만 둔다.

1. 사용자가 고른 위치(선택한 글·영역)를 고른 순서대로 넣는다. 글자 한도를 넘는 선택은 앞부분만 남기고 잘림으로 표시한다.
2. 텍스트 선택마다 그것이 든 문단(선택이 문단의 일부일 때), 앞 문단, 뒤 문단을 하나씩 붙인다. 이 차례로, 남은
   글자 한도 안에서 통째로 넣고 넘으면 빼고 이유를 남긴다. 같은 문단은 한 번만 넣는다.
3. 그림·표·수식 영역마다 그 캡션과 영역 안 글자를 하나씩 붙인다(2와 같은 예산 규칙, 캡션이 먼저다).
   캡션은 같은 쪽에서 "Figure 1", "Table II", "그림 3"처럼 시작하는 문단 가운데 영역에 가장 가까운 것이다
   (CAPTION_GAP 안). 영역 안 글자는 줄 상자가 대부분 영역 안에 있는 문단들을 읽는 순서로 이은 한 근거다.
4. 영역 이미지는 고른 순서대로 MAX_IMAGES개까지 붙인다. 수식 기미가 있는 글 선택(첨자를 추정했거나 그리스 문자·
   수학 기호가 있음)에도 그 줄들의 원문 이미지를 붙인다. PDF 글자층은 분수·첨자 같은 2차원 구조를 잃기 때문이다.
   수식 배치(식 번호·가운데 정렬)는 보지 않는다. 논문마다 다르고 본문 속 수식(예: EDF_np)에는 없기 때문이다.

대화 범위가 쪽·논문 본문이면(page_texts) 고른 위치의 근거 뒤에 그 쪽, 또는 앞쪽부터 모든 쪽의 본문을 쪽마다 근거
하나로 붙인다. 한도는 고른 위치의 한도(MAX_TEXT_CHARS)와 따로다(쪽 PAGE_TEXT_CHARS, 논문 본문은 요청한 한도).

추출 문단(TextBlock)은 쪽마다 나뉜다. 쪽의 첫 문단이 소문자로 시작하면 앞 쪽의 마지막 문단에서 이어진 것으로 보고,
두 조각을 한 문단으로 다룬다(근거는 쪽마다 따로 두어 쪽 출처를 지킨다). 그래야 문장 중간에서 시작하는 조각만
보내지 않는다. 문단은 쪽을 넘어도 글자 크기가 같으므로, 이어 붙일 문단과 앞뒤 문단은 줄 높이가 비슷한 것만 고른다
(쪽 아래 각주·캡션처럼 작은 글자는 건너뛴다).

근거마다 그것이 든 절(본문 제목 경로)을 단다(2026-10-04 사용자 요청). 앞뒤 문단을 고를 때 '같은 절'은 아직 확인하지 않는다. 쪽 위·아래 여백에만 놓인
문단(머리글·바닥글)과 아주 짧은 조각(쪽 번호 등)은 앞뒤 문단으로 고르지 않는다. 그림·표·수식 영역에는 앞뒤 문단을
붙이지 않는다(영역과 이어진 본문인지 알 수 없다). 그 그림을 설명하는 본문 문단("Fig. 1 shows …")은 아직 찾지 않는다.
"""

import re
from dataclasses import dataclass, field

from paperloom.context.models import Evidence, Excluded, ImageRef, Limits
from paperloom.reading.models import AnchorOut

MAX_TEXT_CHARS = 12_000
PAGE_TEXT_CHARS = 30_000  # 쪽 범위의 본문 한도. 빽빽한 두 단 쪽도 대개 1만 자 아래다
MAX_IMAGES = 2
IMAGE_SCALE = 2.0
CONTAINED_SHARE = 0.9  # 선택이 문단 글자의 이 비율 이상이면 그 문단을 따로 붙이지 않는다
OVERLAP_SHARE = 0.5  # 선택 사각형 넓이의 이 비율 이상이 줄 상자와 겹치면 그 문단 안의 선택이다
MARGIN_BAND = 0.10  # 쪽 위·아래 이 비율 안에만 놓인 문단은 머리글·바닥글로 본다
MIN_CONTEXT_CHARS = 20
SIZE_SLACK = 0.15  # 줄 높이가 이 비율 안에서 같으면 같은 크기의 본문 글자로 본다
SPLIT_FLAG = "split_across_pages"  # 쪽을 넘어 이어지는 문단의 조각
PAGE_REACH = 2  # 선택한 쪽에서 앞뒤로 이만큼의 쪽까지 문단을 찾는다 (서비스가 이만큼 읽는다)
# 캡션의 첫머리: 그림·표·알고리즘 이름과 번호(아라비아·로마 숫자)
CAPTION = re.compile(r"(fig(ure)?\.?|table|tab\.|algorithm|listing|그림|표|알고리즘)\s*(\d+|[ivxlc]+)\b", re.IGNORECASE)
CAPTION_GAP = 0.08  # 영역 상자와 캡션 문단 상자 사이가 쪽 크기의 이 비율 안이어야 그 영역의 캡션이다
INSIDE_SHARE = 0.5  # 문단 줄 상자 넓이의 이 비율 이상이 영역 안이면 영역 안 글자다
CONTEXT_ROLES = ("caption", "region_text", "containing_paragraph", "previous_paragraph", "following_paragraph")  # 예산 차례
# 수식에 쓰이는 글자: 그리스 문자, 수학 연산자, 바닥·천장 괄호, 수학 기호, 수학 영숫자(𝜏 등)
MATH_CHARS = re.compile("[\u0370-\u03ff\u2200-\u22ff\u2308-\u230b\u27c0-\u27ef\u2980-\u2aff\U0001d400-\U0001d7ff]")


def looks_mathematical(anchor: AnchorOut) -> bool:
    """글 선택에 수식 기미가 있는가: 첨자·분수 추정 표기가 있거나 수식 글자가 있다."""
    return anchor.kind == "text" and (anchor.display_quote is not None or MATH_CHARS.search(anchor.quote) is not None)

Box = tuple[float, float, float, float]  # u0, v0, u1, v1


@dataclass(frozen=True)
class Block:
    block_id: str
    page_index: int
    text: str
    regions: tuple[Box, ...]
    quality_flags: tuple[str, ...]
    line_height: float  # 줄 상자 짧은 변의 중앙값(pt). 글줄이 돌아간 쪽에서도 글자 크기를 뜻한다


@dataclass(frozen=True)
class Choice:
    anchor: AnchorOut
    include_context: bool
    include_image: bool


@dataclass(frozen=True)
class VersionText:
    extracted: bool  # 본문 추출이 끝나 쪽·문단이 있다
    pages: dict[int, tuple[str, tuple[str, ...]]]  # page_index → (text_status, flags)
    blocks: list[Block]  # 필요한 쪽들의 문단, (쪽, 읽는 순서) 순
    sections: dict[str, str] = field(default_factory=dict)  # block_id → 그 문단이 든 절(제목 경로). 모든 쪽에서 찾는다
    headings: frozenset[str] = frozenset()  # 제목 문단의 block_id


@dataclass
class _Item:
    role: str
    anchor: AnchorOut
    text: str = ""
    blocks: tuple[Block, ...] = ()  # 주변 문단. 쪽을 넘어 이어지면 조각이 여럿이다
    truncated: bool = False
    image: bool = False


def build(choices: list[Choice], texts: dict[str, VersionText], source_refs: dict[str, str]) -> tuple[list[Evidence], Limits]:
    groups: list[list[_Item]] = []
    excluded: list[Excluded] = []
    for choice in choices:
        anchor = choice.anchor
        group = [_Item("selected_text" if anchor.kind == "text" else "selected_region", anchor, anchor.quote)]
        if choice.include_context:
            text = texts[anchor.version_id]
            if anchor.kind != "text":
                found = _region_context(anchor, text.blocks) if text.extracted else None  # 찾지 못해도 이유를 남기지 않는다
            else:
                found = _surroundings(anchor, text.blocks) if text.extracted else None
                if found is None:
                    reason = "no_extracted_text" if text.extracted else "text_not_extracted"
                    excluded.append(Excluded(role="context", anchor_id=anchor.anchor_id, page_index=anchor.page_index, reason=reason))
            # 문단 조각은 이어 붙여 글자 수를 센다(근거는 조각마다 따로 둔다). 영역 안 글자는 줄을 나눠 한 근거로 둔다.
            for role, blocks in found or ():
                group.append(_Item(role, anchor, ("\n" if role == "region_text" else "").join(block.text for block in blocks), blocks))
        groups.append(group)

    remaining = MAX_TEXT_CHARS
    for group in groups:  # 고른 위치가 먼저다
        selected = group[0]
        if len(selected.text) > remaining:
            selected.text, selected.truncated = selected.text[:remaining], True
        remaining -= len(selected.text)
    used_blocks: set[str] = set()
    for role in CONTEXT_ROLES:
        for group in groups:
            for item in [item for item in group if item.role == role]:
                ids = {block.block_id for block in item.blocks}
                if ids & used_blocks:
                    group.remove(item)
                elif len(item.text) > remaining:
                    group.remove(item)
                    page = item.blocks[0].page_index
                    excluded.append(Excluded(role=role, anchor_id=item.anchor.anchor_id, page_index=page, reason="text_budget"))
                else:
                    used_blocks |= ids
                    remaining -= len(item.text)
    images = 0
    for choice, group in zip(choices, groups, strict=True):
        selected = group[0]
        if choice.include_image and (selected.role == "selected_region" or looks_mathematical(choice.anchor)):
            if images < MAX_IMAGES:
                selected.image, images = True, images + 1
            else:
                excluded.append(Excluded(role=selected.role, anchor_id=choice.anchor.anchor_id, page_index=choice.anchor.page_index, reason="image_limit"))

    parts = [
        (item, block)
        for group in groups
        for item in group
        for block in ((None,) if item.role == "region_text" or not item.blocks else item.blocks)
    ]
    evidence = [
        _evidence(f"e{number}", item, block, texts[item.anchor.version_id], source_refs[item.anchor.version_id])
        for number, (item, block) in enumerate(parts, start=1)
    ]
    limits = Limits(
        max_text_chars=MAX_TEXT_CHARS,
        used_text_chars=MAX_TEXT_CHARS - remaining,
        max_images=MAX_IMAGES,
        used_images=images,
        truncated=any(item.truncated for item in evidence) or any(item.reason == "text_budget" for item in excluded),
        excluded=excluded,
    )
    return evidence, limits


def page_texts(
    text: VersionText, wanted: list[int] | None, budget: int, source_ref: str, version_id: str, first_number: int
) -> tuple[list[Evidence], int, list[Excluded]]:
    """쪽 본문 근거 (대화 범위 page·paper, docs/UI_PLAN.md U3): (근거, 쓴 글자 수, 넣지 않은 것).

    wanted가 None이면 앞쪽부터 모든 쪽, 아니면 그 쪽들이다. 쪽마다 본문 문단을 이어 근거 하나로 두고 번호는
    first_number부터 붙인다(고른 위치의 근거 뒤에 이어진다). 문서의 첫 쪽은 위·아래 여백의 문단도 넣는다(제목·저자가
    쪽 위에 있다). 그 밖의 쪽은 여백에만 놓인 문단(머리글·바닥글·쪽 번호)을 뺀다. 한도에 걸린 쪽은 앞부분만 넣고,
    그 뒤 쪽은 그 쪽부터 빠졌다고 남긴다. 글이 없는 쪽은 그렇다고 남긴다."""
    if not text.extracted:
        return [], 0, [Excluded(role="paper_text", anchor_id="", page_index=None, reason="text_not_extracted")]
    # 글이 있는 첫 쪽. 쪽 범위는 앞뒤 쪽 문단만 읽으므로 읽은 문단이 아니라 모든 쪽의 추출 상태로 정한다.
    first_page = min((page for page, (status, _) in text.pages.items() if status in ("usable", "partial")), default=0)
    pages: dict[int, list[Block]] = {}
    for block in text.blocks:
        if (wanted is None or block.page_index in wanted) and (block.page_index == first_page or not _in_margin(block)):
            pages.setdefault(block.page_index, []).append(block)
    evidence: list[Evidence] = []
    excluded = [
        Excluded(role="paper_text", anchor_id="", page_index=page_index, reason="no_extracted_text")
        for page_index in (wanted or [])
        if page_index not in pages
    ]
    remaining = budget
    for page_index, blocks in sorted(pages.items()):
        content = "\n\n".join(block.text for block in blocks)
        if remaining <= 0:
            excluded.append(Excluded(role="paper_text", anchor_id="", page_index=page_index, reason="text_budget"))
            break
        truncated = len(content) > remaining
        content = content[:remaining]
        paragraphs = content.count("\n\n") + 1  # 잘렸으면 넣은 문단까지
        remaining -= len(content)
        status, page_flags = text.pages.get(page_index, (None, ()))
        evidence.append(
            Evidence(
                evidence_id=f"e{first_number + len(evidence)}",
                role="paper_text",
                source_ref=source_ref,
                version_id=version_id,
                page_index=page_index,
                anchor_id="",
                kind=None,
                text=content,
                display_text=None,
                truncated=truncated,
                regions=[list(region) for block in blocks for region in block.regions],
                block_id=blocks[0].block_id,
                block_ids=[block.block_id for block in blocks][:paragraphs],
                section=_continued_section(text, blocks[0]),
                image=None,
                text_status=status,
                quality_flags=list(dict.fromkeys(flag for flag in (*page_flags, *(f for b in blocks for f in b.quality_flags)))),
            )
        )
    return evidence, budget - remaining, excluded


def _continued_section(text: VersionText, first: Block) -> str | None:
    """쪽 본문이 앞 쪽의 절에서 이어지면 그 절. 그 쪽에서 first까지 제목이 있으면 없다(쪽 위 여백에 놓여 본문에서 뺀 제목도 본다)."""
    page = [block.block_id for block in text.blocks if block.page_index == first.page_index]
    lead = page[: page.index(first.block_id) + 1]
    return None if any(block_id in text.headings for block_id in lead) else text.sections.get(first.block_id)


def _in_margin(block: Block) -> bool:
    """쪽 위·아래 여백에만 놓인 문단(머리글·바닥글·쪽 번호)"""
    return all(region[3] <= MARGIN_BAND for region in block.regions) or all(region[1] >= 1 - MARGIN_BAND for region in block.regions)


def _surroundings(anchor: AnchorOut, blocks: list[Block]) -> list[tuple[str, tuple[Block, ...]]] | None:
    """(역할, 문단 조각들). 선택이 놓인 문단을 찾지 못하면 None."""
    inside = [index for index, block in enumerate(blocks) if block.page_index == anchor.page_index and _overlaps(anchor.quads, block.regions)]
    if not inside:
        return None
    like = blocks[inside[0]]  # 선택한 본문과 같은 크기의 문단만 고른다
    first, last = _paragraph(blocks, inside[0])[0], _paragraph(blocks, inside[-1])[-1]
    found = []
    containing = [index for index in range(first, last + 1) if index in inside or _is_paragraph(blocks[index], like)]
    if len(anchor.quote) < CONTAINED_SHARE * sum(len(blocks[index].text) for index in containing):
        found.append(("containing_paragraph", tuple(blocks[index] for index in containing)))
    previous = next((index for index in range(first - 1, -1, -1) if _is_paragraph(blocks[index], like)), None)
    following = next((index for index in range(last + 1, len(blocks)) if _is_paragraph(blocks[index], like)), None)
    if previous is not None:
        found.append(("previous_paragraph", tuple(blocks[index] for index in _paragraph(blocks, previous))))
    if following is not None:
        found.append(("following_paragraph", tuple(blocks[index] for index in _paragraph(blocks, following))))
    return found


def _region_context(anchor: AnchorOut, blocks: list[Block]) -> list[tuple[str, tuple[Block, ...]]]:
    """영역의 (역할, 문단들): 가장 가까운 캡션 하나, 영역 안 문단들(캡션 제외)."""
    box = _quad_box(anchor.quads[0])
    page = [block for block in blocks if block.page_index == anchor.page_index]
    gaps = [(_gap(box, _bounds(block.regions)), index) for index, block in enumerate(page) if CAPTION.match(block.text.lstrip())]
    near = [pair for pair in gaps if pair[0] <= CAPTION_GAP]
    caption = page[min(near)[1]] if near else None
    inside = tuple(block for block in page if block is not caption and _inside_share(block.regions, box) >= INSIDE_SHARE)
    return [*([("caption", (caption,))] if caption else []), *([("region_text", inside)] if inside else [])]


def _quad_box(quad) -> Box:
    return min(quad[0::2]), min(quad[1::2]), max(quad[0::2]), max(quad[1::2])


def _bounds(regions: tuple[Box, ...]) -> Box:
    return min(r[0] for r in regions), min(r[1] for r in regions), max(r[2] for r in regions), max(r[3] for r in regions)


def _gap(a: Box, b: Box) -> float:
    """두 상자 사이의 거리(겹치면 0). 쪽이 돌아가 있어도 같도록 가로·세로를 함께 본다."""
    dx = max(0.0, max(a[0], b[0]) - min(a[2], b[2]))
    dy = max(0.0, max(a[1], b[1]) - min(a[3], b[3]))
    return (dx * dx + dy * dy) ** 0.5


def _inside_share(regions: tuple[Box, ...], box: Box) -> float:
    total = sum((r[2] - r[0]) * (r[3] - r[1]) for r in regions)
    inside = sum(
        max(0.0, min(r[2], box[2]) - max(r[0], box[0])) * max(0.0, min(r[3], box[3]) - max(r[1], box[1])) for r in regions
    )
    return inside / total if total > 0 else 0.0


def _paragraph(blocks: list[Block], index: int) -> list[int]:
    """그 문단 조각이 속한 문단(쪽을 넘어 이어지는 조각까지)의 인덱스들."""
    indices = [index]
    while (before := _continued_from(blocks, indices[0])) is not None:
        indices.insert(0, before)
    while (after := _continues_into(blocks, indices[-1])) is not None:
        indices.append(after)
    return indices


def _continued_from(blocks: list[Block], index: int) -> int | None:
    """이 조각이 쪽의 첫 문단이고 소문자로 시작하면, 앞 쪽에서 같은 크기 글자의 마지막 문단 인덱스."""
    block = blocks[index]
    if not block.text[:1].islower() or any(
        _is_paragraph(other, block) for other in blocks[:index] if other.page_index == block.page_index
    ):
        return None
    previous = next((i for i in range(index - 1, -1, -1) if _is_paragraph(blocks[i], block)), None)
    return previous if previous is not None and blocks[previous].page_index == block.page_index - 1 else None


def _continues_into(blocks: list[Block], index: int) -> int | None:
    following = next((i for i in range(index + 1, len(blocks)) if _is_paragraph(blocks[i], blocks[index])), None)
    return following if following is not None and _continued_from(blocks, following) == index else None


def _overlapping_block(anchor: AnchorOut, blocks: list[Block]) -> Block | None:
    """고른 위치와 겹치는 그 쪽의 첫 문단"""
    return next((block for block in blocks if block.page_index == anchor.page_index and _overlaps(anchor.quads, block.regions)), None)


def _overlaps(quads, regions: tuple[Box, ...]) -> bool:
    for quad in quads:
        u0, u1, v0, v1 = min(quad[0::2]), max(quad[0::2]), min(quad[1::2]), max(quad[1::2])
        area = (u1 - u0) * (v1 - v0)
        for r0, s0, r1, s1 in regions:
            overlap = max(0.0, min(u1, r1) - max(u0, r0)) * max(0.0, min(v1, s1) - max(v0, s0))
            if area > 0 and overlap >= OVERLAP_SHARE * area:
                return True
    return False


def _is_paragraph(block: Block, like: Block) -> bool:
    """앞뒤 문단으로 고를 만한 본문인가: 머리글·바닥글·짧은 조각이 아니고 like와 글자 크기가 같다."""
    same_size = abs(block.line_height - like.line_height) <= SIZE_SLACK * like.line_height
    return len(block.text) >= MIN_CONTEXT_CHARS and not _in_margin(block) and same_size


def _evidence(evidence_id: str, item: _Item, block: Block | None, text: VersionText, source_ref: str) -> Evidence:
    anchor = item.anchor
    page_index = block.page_index if block else anchor.page_index
    status, page_flags = text.pages.get(page_index, (None, ()))
    if block:
        regions = [list(region) for region in block.regions]
        flags = [*block.quality_flags, *page_flags, *([SPLIT_FLAG] if len(item.blocks) > 1 else [])]
        content = block.text
    elif item.blocks:  # 영역 안 글자: 여러 문단을 한 근거로
        regions = [list(region) for each in item.blocks for region in each.regions]
        flags = [*(flag for each in item.blocks for flag in each.quality_flags), *page_flags]
        content = item.text
    else:
        regions = [[min(q[0::2]), min(q[1::2]), max(q[0::2]), max(q[1::2])] for q in anchor.quads]
        flags = [*(["display_text_estimated"] if anchor.display_quote else []), *page_flags]
        content = item.text
    # 절: 문단이면 그 문단, 고른 위치면 그 자리에 겹친 그 쪽의 문단의 절
    owner = block or (item.blocks[0] if item.blocks else _overlapping_block(anchor, text.blocks))
    return Evidence(
        evidence_id=evidence_id,
        role=item.role,
        source_ref=source_ref,
        version_id=anchor.version_id,
        page_index=page_index,
        anchor_id=anchor.anchor_id,
        kind=None if anchor.kind == "text" else anchor.kind,
        text=content,
        display_text=anchor.display_quote if item.role == "selected_text" else None,
        truncated=item.truncated,
        regions=regions,
        block_id=block.block_id if block else None,
        section=text.sections.get(owner.block_id) if owner else None,
        image=ImageRef(url=f"/api/v1/anchors/{anchor.anchor_id}/image?scale={IMAGE_SCALE:g}", scale=IMAGE_SCALE) if item.image else None,
        text_status=status,
        quality_flags=list(dict.fromkeys(flags)),
    )
