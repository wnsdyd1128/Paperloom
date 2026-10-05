"""첫 쪽에서 논문 제목 찾기 (2026-10-05 사용자 요청 "등록 시에 파일 명이 아닌 해당 논문의 이름으로 해줘"). 순수 함수만 둔다.

PDF 메타데이터에 제목이 없으면(arXiv 등) 예전에는 파일 이름(1706.03762v7)을 제목으로 썼다. 첫 쪽 위쪽 절반에서 글꼴이 가장
큰 문단이 제목이다(본문 글꼴보다 TITLE_RATIO배 이상 커야 한다). 여백의 세로 도장(arXiv 번호, 글자마다 문단으로 나뉜다)·
쪽 번호는 폭과 낱말 수로, 수식은 문단 표시로 뺀다. 같은 크기로 이어진 문단(문단으로 나뉜 여러 줄 제목)은 잇는다.
실제 논문 넷(CAAS·CBANA·TCPS·사용자 논문)의 첫 쪽에서 맞았다. 휴리스틱이다.
"""

import re

from paperloom.documents.block_kinds import NOT_BODY

TITLE_RATIO = 1.15  # 제목 글꼴은 본문 글꼴보다 이만큼 이상 크다
TOP = 0.5  # 쪽 높이 비율. 제목은 이보다 위에서 시작한다
MIN_WIDTH = 0.2  # 쪽 너비 비율. 이보다 좁은 문단(여백의 도장 글자 등)은 제목이 아니다
SAME_SIZE = 0.5  # pt. 이 안이면 같은 크기다(나뉜 제목 문단 잇기)
MAX_PARTS = 3  # 제목으로 이을 문단 수
MAX_LENGTH = 300
_WORD = re.compile(r"[^\W\d_]{2,}")
_FOOTNOTE_MARKS = "*∗†‡§¶"


def looks_like_filename(title: str) -> bool:
    """파일 이름에서 온 제목인지. 빈칸이 없다(1706.03762v7, paper_final-v2). 사람이 쓴 제목은 거의 늘 낱말이 둘 이상이다."""
    return bool(title) and not any(char.isspace() for char in title)


def title_from_blocks(blocks: list[dict]) -> str | None:
    """첫 쪽 문단들(읽는 차례; text·regions·font_size·quality_flags)에서 제목. 못 찾으면 None."""
    sized = [block for block in blocks if block.get("font_size") and block["text"].strip()]
    if not sized:
        return None
    body = _body_size(sized)
    candidates = [block for block in sized if _candidate(block)]
    if not candidates:
        return None
    best = max(candidates, key=lambda block: block["font_size"])
    if best["font_size"] < TITLE_RATIO * body:
        return None
    # 같은 크기로 앞뒤에 이어진 문단을 함께 잇는다(읽는 차례)
    def same(index: int) -> bool:
        return 0 <= index < len(blocks) and blocks[index] in candidates and abs(blocks[index]["font_size"] - best["font_size"]) <= SAME_SIZE

    start = end = blocks.index(best)
    while end - start + 1 < MAX_PARTS and same(start - 1):
        start -= 1
    while end - start + 1 < MAX_PARTS and same(end + 1):
        end += 1
    title = " ".join(" ".join(block["text"].split()) for block in blocks[start : end + 1]).rstrip(_FOOTNOTE_MARKS).strip()
    return title if 0 < len(title) <= MAX_LENGTH else None


def _candidate(block: dict) -> bool:
    regions = block["regions"]
    left, top, right = min(r[0] for r in regions), min(r[1] for r in regions), max(r[2] for r in regions)
    return (
        top < TOP
        and right - left >= MIN_WIDTH
        and len(_WORD.findall(block["text"])) >= 2
        and NOT_BODY.isdisjoint(block.get("quality_flags", []))
    )


def _body_size(blocks: list[dict]) -> float:
    """본문 글꼴 크기: 글자 수로 무게를 단 가운데값(글자마다 나뉜 도장 문단이 많아도 본문이 이긴다)"""
    weighted = sorted((block["font_size"], len(block["text"])) for block in blocks)
    half, seen = sum(length for _, length in weighted) / 2, 0
    for size, length in weighted:
        seen += length
        if seen >= half:
            break
    return size
