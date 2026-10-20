"""참고문헌 쪽 찾기 (2026-10-02 사용자 요청). 순수 함수만 둔다.

원문 위 설명·질문은 논문 앞쪽부터 고른 쪽 근처까지와 참고문헌 쪽을 보낸다(context). 참고문헌 쪽은 본문 추출(parsing)이
문서 전체의 문단을 본 뒤 정해 그 쪽에 "references" 표시를 남긴다. 휴리스틱이다:
- 머리: 문단 전체가 References·Bibliography·참고문헌 같은 낱말(앞에 장 번호 가능)이거나, 그 낱말 뒤에 첫 항목([1], 1.)이
  바로 이어진 문단. 문장 속 낱말("References to prior work …")은 머리가 아니다. 여러 개면 마지막 것(목차 등을 피한다).
- 끝: 머리 뒤에 부록 머리가 오면 그 앞 문단이 놓인 쪽까지, 없으면 마지막 쪽까지. 부록 머리는 Appendix·Supplementary material
  낱말이나, 그 낱말 없이 A로 시작하는 부록 첫 절 머리("A Version Control")다: 한 줄, 짧고 쉼표가 없으며 마침표로 끝나지 않고,
  글꼴이 참고문헌 머리만 하다(2026-10-19 사용자 논문 SayCan: 부록 17쪽이 참고문헌으로 보여 쪽 번역에서 빠졌다).
"""

import re

# 찾는 방법이 바뀌면 올린다. 추출기 버전에 들어가 저장된 버전을 다시 추출한다(documents.parsing).
REFERENCES_VERSION = "2"
REFERENCES_FLAG = "references"

_HEADING = re.compile(
    r"^(?:\d+(?:\.\d+)*\.?\s+|[IVXLC]+\.\s+)?"
    r"(?:references|bibliography|reference list|works cited|literature cited|참고\s*문헌)\s*:?"
    r"(?:\s*$|\s+(?=\[\d+\]|\d+\.\s))",
    re.IGNORECASE,
)
_APPENDIX = re.compile(r"^(?:[A-Z]\.?\s+|\d+\.?\s+)?(?:appendix|appendices|supplementary materials?|supplemental materials?)\b", re.IGNORECASE)
_APPENDIX_SECTION = re.compile(r"^A\.?\s+[A-Z][^,]*[^.,]$")  # "A Version Control", "A. Proofs"
SECTION_WORDS = 8  # 부록 첫 절 머리의 낱말 수 상한(A 빼고)
SECTION_SIZE = 0.95  # 부록 첫 절 머리의 글꼴은 참고문헌 머리의 이 배수 이상(참고문헌 항목은 더 작다)


def reference_blocks(pages: list[dict]) -> list[tuple[int, int]]:
    """참고문헌 부분의 문단 (쪽 page_index, 그 쪽 문단 차례): 머리부터 부록 머리 앞까지, 읽는 차례로. 같은 쪽의 머리 앞 본문
    (결론·감사의 글)은 들지 않는다. pages는 본문 추출 결과(쪽마다 page_index·blocks[].text). 없으면 []."""
    blocks = [(page["page_index"], index, block) for page in pages for index, block in enumerate(page["blocks"])]
    headings = [position for position, (_, _, block) in enumerate(blocks) if _HEADING.match(block["text"].strip())]
    if not headings:
        return []
    start = headings[-1]
    size = blocks[start][2].get("font_size")
    end = next((position for position in range(start + 1, len(blocks)) if _appendix_head(blocks[position][2], size)), len(blocks))
    return [(page_index, index) for page_index, index, _ in blocks[start:end]]


def _appendix_head(block: dict, heading_size: float | None) -> bool:
    """부록 머리인지. heading_size는 참고문헌 머리의 글꼴 크기(모르면 None, 그러면 크기를 보지 않는다)."""
    text = block["text"].strip()
    if _APPENDIX.match(text):
        return True
    if not _APPENDIX_SECTION.match(text) or len(text.split()) > SECTION_WORDS + 1 or len(block.get("regions") or [None]) != 1:
        return False
    size = block.get("font_size")
    return not (size and heading_size) or size >= SECTION_SIZE * heading_size


def reference_pages(pages: list[dict]) -> list[int]:
    """참고문헌이 놓인 쪽(0부터, 차례대로). 없으면 []."""
    section = reference_blocks(pages)
    return list(range(section[0][0], section[-1][0] + 1)) if section else []
