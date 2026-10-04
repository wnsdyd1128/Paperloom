"""쪽마다 되풀이되는 머리글·바닥글 찾기 (2026-10-03 사용자 요청: 쪽 번역은 본문만). 순수 함수만 둔다.

본문 추출(documents.parsing)이 문서 전체의 문단을 본 뒤 정한다. 쪽 위·아래 끝 띠에 놓인 짧은(두 줄 이하) 문단 가운데,
숫자를 빼면 같은 글이 여러 쪽에 되풀이되는 것(저널 이름·저자·논문 제목 줄·"28:7")과 쪽 번호뿐인 것이다. 첫 쪽 제목처럼
한 번만 나오는 글은 본문이다. 휴리스틱이다. 바꾸면 text_layout.LAYOUT_VERSION을 올린다.
"""

import math
import re

from paperloom.documents.block_kinds import PAGE_FOOTER, PAGE_HEADER

EDGE_BAND = 0.1  # 쪽 높이 비율. 위·아래 이 안에 문단 전체가 들어야 머리글·바닥글 후보다
MAX_LINES = 2
REPEAT_SHARE = 0.2  # 쪽 수의 이 비율 이상(그리고 두 쪽 이상)에 되풀이되면 머리글·바닥글이다

_PAGE_NUMBER = re.compile(r"^\W*(?:\d+|[ivxlcdm]+)\W*$", re.IGNORECASE)


def running_lines(pages: list[dict]) -> dict[tuple[int, int], str]:
    """(쪽 page_index, 그 쪽 문단 차례) → "page_header" | "page_footer". pages는 본문 추출 결과(쪽마다 page_index·blocks[]의
    text·regions(정본 좌표))."""
    candidates = []
    for page in pages:
        for index, block in enumerate(page["blocks"]):
            regions = block["regions"]
            if not regions or len(regions) > MAX_LINES:
                continue
            top, bottom = min(region[1] for region in regions), max(region[3] for region in regions)
            band = PAGE_HEADER if bottom <= EDGE_BAND else PAGE_FOOTER if top >= 1 - EDGE_BAND else None
            if band:
                candidates.append((page["page_index"], index, band, block["text"]))
    pages_with: dict[tuple[str, str], set[int]] = {}  # (띠, 글) → 그 글이 놓인 쪽들
    for page_index, _, band, text in candidates:
        pages_with.setdefault((band, _key(text)), set()).add(page_index)
    least = max(2, math.ceil(REPEAT_SHARE * len(pages)))
    return {
        (page_index, index): band
        for page_index, index, band, text in candidates
        if len(pages_with[(band, _key(text))]) >= least or _PAGE_NUMBER.match(text.strip())
    }


def _key(text: str) -> str:
    """숫자를 빼고 대소문자·공백을 맞춘 글(쪽마다 바뀌는 쪽 번호를 같게 본다)."""
    return " ".join(re.sub(r"\d+", "#", text.lower()).split())
