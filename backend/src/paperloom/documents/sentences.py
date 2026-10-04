"""문단을 문장으로 나눈다 (U7 쪽 번역). 문장마다 번역해 원문 문장과 짝지으므로(번역문에 마우스를 올리면 원문 문장을
강조, 2026-10-03 사용자 요청) 나누는 규칙은 결정적이어야 한다. Core와 브리지가 같은 함수를 쓴다.

문장 끝: `.`·`!`·`?`(와 닫는 따옴표·괄호) 뒤에 공백이 오고, 다음 글자가 소문자가 아닐 때. 약어(Fig., e.g., et al.)와
이름 첫 글자(J.) 뒤의 마침표는 문장 끝이 아니다. 잘못 나눠도 번역이 그 조각에 맞춰질 뿐 글이 빠지지는 않는다.
"""

import re

# 논문에 자주 나오는 약어(마침표 앞 낱말, 소문자). 뒤에 대문자·숫자가 와도 문장 끝으로 보지 않는다.
ABBREVIATIONS = frozenset({
    "e.g", "i.e", "al", "etc", "vs", "cf", "fig", "figs", "eq", "eqs", "sec", "secs", "ref", "refs", "no", "nos",
    "vol", "pp", "p", "resp", "approx", "ch", "def", "thm", "lem", "prop", "alg", "tab", "dr", "prof", "mr", "ms",
})
_END = re.compile(r"[.!?。！？][\"'”’)\]]*(?=\s)")


def sentence_spans(text: str) -> list[tuple[int, int]]:
    """문장마다 [시작, 끝) 글자 위치. 앞뒤 공백은 빼고, 빈 글이면 빈 목록이다."""
    spans: list[tuple[int, int]] = []
    start = _skip_space(text, 0)
    for match in _END.finditer(text):
        if match.start() < start:
            continue
        following = _skip_space(text, match.end())
        if following >= len(text) or not _is_boundary(text, start, match.start(), following):
            continue
        spans.append((start, match.end()))
        start = following
    end = len(text.rstrip())
    if start < end:
        spans.append((start, end))
    return spans


def _is_boundary(text: str, start: int, mark: int, following: int) -> bool:
    if text[following].islower():
        return False
    if text[mark] != ".":
        return True
    word = re.search(r"(\S+)$", text[start:mark])
    token = word.group(1).lower().lstrip("([\"'“‘") if word else ""
    if token in ABBREVIATIONS:
        return False
    return not (len(token) == 1 and token.isalpha())  # 이름 첫 글자(J. Xiao)


def _skip_space(text: str, index: int) -> int:
    while index < len(text) and text[index].isspace():
        index += 1
    return index
