"""본문이 아닌 문단의 표시와 따로 놓인 수식 찾기 (2026-10-03 사용자 요청: 쪽 번역은 본문만). 순수 함수만 둔다.

문단 표시(quality_flags)는 본문 추출(text_layout·running·tables)이 붙이고, 쪽 번역(Core translation·브리지)은 이 표시가
있는 문단을 빼고 원문 그대로 둔다. 그림 설명(캡션)은 본문으로 보고 번역한다.

따로 놓인 수식은 PDF 글자로 찾는다(이미지로 찾지 않는다): 디지털 PDF는 수식도 글자이고, 수식 줄은 산문 낱말이 거의 없고
수학 기호가 있다. 휴리스틱이다. 바꾸면 text_layout.LAYOUT_VERSION을 올린다(저장된 논문을 다시 추출한다).
"""

import re
import unicodedata

IN_FIGURE = "in_figure"  # 그림 후보 안의 글자(축 이름 등)
IN_TABLE = "in_table"  # 표·의사코드 안(가로줄 사이)
MATH = "math"  # 따로 놓인 수식 줄·식 번호
PAGE_HEADER = "page_header"  # 쪽마다 되풀이되는 머리글·쪽 번호
PAGE_FOOTER = "page_footer"  # 쪽마다 되풀이되는 바닥글·쪽 번호
REFERENCE = "reference"  # 참고문헌 부분(머리부터 부록 앞까지, references.reference_blocks)
NOT_BODY = frozenset({IN_FIGURE, IN_TABLE, MATH, PAGE_HEADER, PAGE_FOOTER, REFERENCE})  # 쪽 번역에서 빼는 문단
NO_BODY_TEXT = "no_body_text"  # 쪽 표시: 글은 있지만 모두 본문이 아니다(참고문헌·그림·표뿐). 쪽 번역 차례가 건너뛴다

# 그림·표·의사코드 설명(캡션)의 머리: 본문으로 보고 번역한다
_CAPTION = re.compile(r"^(?:table|tab\.|fig\.|figure|algorithm|pseudocode|listing)\s*[A-Z]?\d+", re.IGNORECASE)
# 식 번호만 있는 문단: (0.1), (12), (A.3), (2a)
_LABEL = re.compile(r"^\(\s*(?:[A-Z]\.)?\d+(?:\.\d+)*[a-z]?\s*\)$")
_TOKEN = re.compile(r"[^\W\d_]+")
# 수식 안에서 낱말처럼 보이는 연산자 이름
_OPERATORS = frozenset({"max", "min", "sup", "inf", "lim", "log", "exp", "sin", "cos", "tan", "arg", "argmax", "argmin", "det", "mod", "gcd", "deg", "dim", "ker"})
# 수식 줄 안의 이음말(경우 나누기·조건·제약): 산문 낱말로 세지 않는다
_CONNECTIVES = frozenset({"and", "for", "all", "otherwise", "subject", "where", "such", "that", "when", "else", "then", "with"})
MATH_FONT_SHARE = 0.5  # 문단 글자의 이만큼 이상이 수식 글꼴(fonts.is_math_font)이면 수식이다
# 수식에 붙은 설명(밑·위 괄호의 "Saving-state contribution" 등): 본문 글꼴의 이 비율보다 작고 이만큼 이하 낱말인 한 줄
LABEL_SIZE = 0.85
LABEL_WORDS = 6


def is_caption(text: str) -> bool:
    """그림·표·의사코드 설명(Table 1. …, Fig. 2. …, PSEUDOCODE 1: …)인지."""
    return bool(_CAPTION.match(text.strip()))


def is_display_math(text: str, math_font_share: float = 0.0) -> bool:
    """따로 놓인 수식 줄이거나 식 번호만 있는 문단인지. 식 번호는 없어도 된다. 다음 가운데 하나면 수식이다.
    - 문단 글자의 절반 이상이 수식 글꼴이다(math_font_share: 기호가 유니코드로 바뀌지 않는 조판도 잡는다).
    - 산문 낱말(이음말 if·otherwise·for all·subject to 등과 변수·약어·연산자 이름은 빼고)이 하나 이하이고 수학 기호(유니코드
      Sm·그리스 문자·수학 영숫자)가 있거나 연산자 이름뿐이다.
    글이 섞인 줄과 캡션("PSEUDOCODE 1: CITTA(τ, π)")은 본문으로 둔다."""
    stripped = text.strip()
    if is_caption(stripped):
        return False
    if _LABEL.match(stripped) or math_font_share >= MATH_FONT_SHARE:
        return True
    tokens = _TOKEN.findall(stripped)
    if len({token for token in tokens if _prose_word(token)}) > 1:  # 되풀이되는 변수 이름(τ tna ← τ tna)은 한 번만 센다
        return False
    if any(_math_char(char) for char in stripped):
        return True
    return bool(tokens) and all(token.lower() in _OPERATORS for token in tokens)


def equation_labels(blocks: list[tuple[list[list[float]], str, float | None, list[str]]]) -> set[int]:
    """따로 놓인 수식에 붙은 작은 글씨 설명 문단의 차례. blocks는 쪽 문단마다 (줄 상자들(정본 좌표), 글, 글꼴 크기, 표시)다.
    본문 글꼴보다 작은 짧은 한 줄이 수식 문단 바로 위나 아래에 닿아 있으면(가로로 겹치고 세로 틈이 그 줄 높이 이하) 수식의
    일부다. 낱말뿐이라 is_display_math가 본문으로 두면 번역되어, 수식이 빠진 번역 쪽에 혼자 떠 있었다(2026-10-16 사용자 논문
    IEEE TIM 7쪽 식 (14)의 밑 괄호 설명). 캡션과 이미 본문이 아닌 문단은 두고, 본문 크기 글은 수식에 닿아도 본문이다."""
    body = _body_size([(size, len(text)) for _, text, size, flags in blocks if size and NOT_BODY.isdisjoint(flags)])
    if body is None:
        return set()
    equations = [_bounds(regions) for regions, _, _, flags in blocks if MATH in flags]
    found = set()
    for index, (regions, text, size, flags) in enumerate(blocks):
        if not NOT_BODY.isdisjoint(flags) or len(regions) != 1 or not size or size >= LABEL_SIZE * body:
            continue
        if len(text.split()) > LABEL_WORDS or is_caption(text):
            continue
        left, top, right, bottom = _bounds(regions)
        height = bottom - top
        if any(
            other_left < right and left < other_right and (abs(top - other_bottom) <= height or abs(other_top - bottom) <= height)
            for other_left, other_top, other_right, other_bottom in equations
        ):
            found.add(index)
    return found


def _body_size(weighted: list[tuple[float, int]]) -> float | None:
    """본문 글꼴 크기: 글자 수로 무게를 단 가운데값. 본문 문단이 없으면 None."""
    half, seen = sum(length for _, length in weighted) / 2, 0
    for size, length in sorted(weighted):
        seen += length
        if seen >= half:
            return size
    return None


def _bounds(regions: list[list[float]]) -> tuple[float, float, float, float]:
    return min(r[0] for r in regions), min(r[1] for r in regions), max(r[2] for r in regions), max(r[3] for r in regions)


def _prose_word(token: str) -> bool:
    """산문 낱말: 세 글자 이상의 소문자·첫 글자만 대문자 영어 낱말(연산자 이름 제외), 또는 한글·한자·가나가 든 낱말.
    변수(Di, τi)·약어(DBF)는 낱말이 아니다."""
    if token.isascii():
        return len(token) >= 3 and (token.islower() or token[1:].islower()) and token.lower() not in _OPERATORS | _CONNECTIVES
    return any("가" <= char <= "힣" or "぀" <= char <= "鿿" for char in token)


def _math_char(char: str) -> bool:
    code = ord(char)
    return unicodedata.category(char) == "Sm" or 0x0370 <= code <= 0x03FF or 0x1D400 <= code <= 0x1D7FF
