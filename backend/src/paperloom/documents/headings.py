"""본문 제목 찾기 (2026-10-02 사용자 결정 D6: PDF에 목차가 없으면 본문 제목으로 목차를 만든다). 순수 함수만 둔다.

웹 목차 패널이 PDF 목차(outline)가 없을 때 쓴다(GET /api/v1/versions/{id}/headings). 휴리스틱이다.
- 번호 제목: "3", "3.2", "3.2.1" 뒤에 글자로 시작하는 짧은 제목(12낱말 이하, 마침표로 끝나지 않음). 번호는 앞 번호 제목보다
  뒤이고 첫 번호가 두 칸 넘게 뛰지 않아야 한다(본문 속 번호 목록이나 표의 수를 거른다).
  - 한 줄 문단이면 문단 전체가 제목이다. 여러 줄이어도 문단 전체가 짧고 제목 꼴이면(네 글자 넘는 낱말이 모두 대문자로 시작)
    좁은 단에서 넘어간 제목이다(2026-10-04 사용자 논문 CAAS "3.1 RTEMS (Real-Time Executive for Multiprocessor Systems)").
  - 여러 줄 문단이면 첫머리에 이어 쓴 제목이다("5.2.1 IP Formulation. In the …", 제목 줄이 다음 문단과 묶인
    "5.2 Calculation of …: The …"). 처음 나오는 마침표·쌍점까지이고, 네 글자 넘는 낱말이 모두 대문자로 시작해야 한다.
- IEEE 장·절(한 줄, 2026-10-03): 장은 "I. INTRODUCTION"(로마 숫자, 제목이 모두 대문자 — 작은 대문자 조판), 절은 장 안의
  "A. Overall Framework Design"(대문자 한 글자). 장 번호는 앞 장 뒤로 두 칸까지, 절 글자는 장마다 A부터 두 칸까지 뛸 수 있다
  (저자 이름 첫 글자 "I. Smith", "J. Xiao et al." 같은 줄을 거른다).
- 부록 번호 제목(한 줄): "A.1 Proofs"(글자.숫자). 부록 머리("A Appendix", "Appendix B: …")는 이름 제목이다.
- 이름 제목(한 줄): 문단 전체가 Abstract·References·Acknowledgments·참고문헌 같은 낱말(끝 쌍점 가능).
"""

import re

MAX_WORDS = 12
MAX_CHARS = 120
MAX_JUMP = 2  # 번호 제목의 첫 번호가 앞 제목보다 이만큼까지 뛸 수 있다(추출에서 빠진 제목)

_NUMBERED = re.compile(r"^(\d{1,2}(?:\.\d{1,2}){0,3})\.?\s+(\S.*)$")
_RUN_IN_END = re.compile(r"[.:](?=\s)")
_APPENDIX_NUMBERED = re.compile(r"^[A-Z](?:\.\d{1,2}){1,3}\.?\s+(\S.*)$")
_ROMAN = re.compile(r"^(X{0,3}(?:IX|IV|V?I{0,3}))\.\s+(\S.*)$")
_ROMAN_VALUES = {"I": 1, "V": 5, "X": 10}
_LETTER = re.compile(r"^([A-Z])\.\s+(\S.*)$")
_APPENDIX = re.compile(r"^(?:[A-Z]\.?\s+)?(?:appendix|appendices)\b", re.IGNORECASE)
_NAMED = re.compile(
    r"^(?:abstract|introduction|related work|background|conclusions?|discussion|references|bibliography"
    r"|acknowledge?ments?|초록|요약|서론|결론|참고\s*문헌)\s*:?$",
    re.IGNORECASE,
)


def headings(pages: list[dict]) -> list[dict]:
    """본문 추출 결과(쪽마다 page_index·blocks[].text·regions)에서 제목을 읽는 순서로.

    항목: title(끝 쌍점 뺀 제목), page_index, order(쪽 안 읽는 순서), level(번호 단계, 이름 제목은 1).
    """
    found: list[dict] = []
    last: tuple[int, ...] = (0,)
    section = letter = 0  # IEEE 장 번호(로마 숫자 값)와 그 장의 절 글자 차례
    for page in pages:
        for order, block in enumerate(page["blocks"]):
            text = block["text"].strip()
            single = len(block["regions"]) == 1
            title = level = None
            if numbered := _NUMBERED.match(text):
                wrapped = _short(text) and _is_title(numbered.group(2)) and _title_case(numbered.group(2))
                whole = numbered.group(2) if single or wrapped else None
                rest = whole or _run_in(numbered.group(2))
                number = tuple(int(part) for part in numbered.group(1).split("."))
                if rest and _short(rest) and _is_title(rest) and number > last and number[0] <= last[0] + MAX_JUMP:
                    title, level, last = text[: numbered.start(2)] + rest, len(number), number
            elif not single or not _short(text):
                continue
            elif value := _section(text, section):
                title, level, section, letter = text, 1, value, 0
            elif appendix := _APPENDIX_NUMBERED.match(text):
                if _is_title(appendix.group(1)):
                    title, level = text, text.split()[0].count(".") + 1
            elif _APPENDIX.match(text) or _NAMED.match(text):
                title, level = text, 1
            elif section and (ordinal := _subsection(text, letter)):
                title, level, letter = text, 2, ordinal
            if title is not None:
                found.append({"title": title.rstrip(":").rstrip(), "page_index": page["page_index"], "order": order, "level": level})
    return found


def section_paths(pages: list[dict]) -> dict[tuple[int, int], str]:
    """문단(쪽, 쪽 안 읽는 순서)마다 그 문단이 든 절: 가장 가까운 앞 제목까지의 제목 경로("3 Background › 3.3 Motivation").
    근거를 Claude에 보낼 때 어느 절의 글인지 함께 적는다(2026-10-04 사용자 요청). 쪽을 넘어 이어진다. 제목 문단은 그 제목까지의
    경로다. 첫 제목 앞(제목·저자) 문단은 없다. 목차와 같은 휴리스틱(headings)이라 제목을 찾지 못하면 앞 절이 이어진다."""
    found = {(item["page_index"], item["order"]): item for item in headings(pages)}
    path: list[str] = []
    paths: dict[tuple[int, int], str] = {}
    for page in pages:
        for order in range(len(page["blocks"])):
            item = found.get((page["page_index"], order))
            if item:
                path = [*path[: item["level"] - 1], item["title"]]
            if path:
                paths[(page["page_index"], order)] = " › ".join(path)
    return paths


def _section(text: str, last: int) -> int:
    """IEEE 장 제목이면 장 번호(로마 숫자 값), 아니면 0. 제목은 모두 대문자이고 번호는 앞 장 뒤로 MAX_JUMP까지다."""
    match = _ROMAN.match(text)
    if not match or not match.group(1):
        return 0
    values = [_ROMAN_VALUES[numeral] for numeral in match.group(1)]
    value = sum(-current if index + 1 < len(values) and current < values[index + 1] else current for index, current in enumerate(values))
    rest = match.group(2)
    return value if _is_title(rest) and rest == rest.upper() and last < value <= last + MAX_JUMP else 0


def _subsection(text: str, last: int) -> int:
    """IEEE 절 제목이면 글자 차례(A=1), 아니면 0. 글자는 장의 앞 절 뒤로 MAX_JUMP까지다."""
    match = _LETTER.match(text)
    if not match or not _is_title(match.group(2)):
        return 0
    ordinal = ord(match.group(1)) - ord("A") + 1
    return ordinal if last < ordinal <= last + MAX_JUMP else 0


def _run_in(rest: str) -> str | None:
    """여러 줄 문단 첫머리의 제목: 처음 나오는 마침표·쌍점 앞. 제목 꼴(네 글자 넘는 낱말이 대문자로 시작)이 아니면 None."""
    end = _RUN_IN_END.search(rest)
    if end is None:
        return None
    head = rest[: end.start()]
    return head if _title_case(head) else None


def _title_case(text: str) -> bool:
    """제목 꼴: 네 글자 넘는 낱말(첫 글자가 글자인)이 모두 대문자로 시작한다."""
    return all(word[0].isupper() for word in text.split() if len(word) > 3 and word[0].isalpha())


def _short(text: str) -> bool:
    return len(text) <= MAX_CHARS and len(text.split()) <= MAX_WORDS


def _is_title(rest: str) -> bool:
    """번호 뒤의 글이 제목다운가: 대문자(또는 대소문자 없는 글자)로 시작하고, 글자가 둘 이상이며, 마침표로 끝나지 않는다."""
    first = rest[0]
    return first.isalpha() and not first.islower() and sum(ch.isalpha() for ch in rest) >= 2 and not rest.endswith(".")
