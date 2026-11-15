"""번역본 PDF의 레이아웃 유지 번역 조판 (2026-11-15 사용자 요청: PDF로 내보낼 때 레이아웃 유지 번역본도 바탕으로 고른다).

웹의 레이아웃 유지 번역(apps/web/src/features/translation/TranslatedPage.tsx·typeset.ts·translation.css)과 같은 규칙으로
원문 문단 상자마다 번역문을 그 자리에 넣는다. 원문 글꼴 크기·줄 간격에서 시작해 상자에 넘치면 그 문단만 글꼴을 0.95배씩
줄이고, 한 줄 문단(제목 등)은 줄이기 전에 그 단 안에서 넓힌다. 여러 줄 문단은 양쪽 맞춤이고 줄은 낱말 사이에서만
나눈다(word-break: keep-all). 한 줄에 들지 않는 낱말만 아무 데서나 나눈다(overflow-wrap: anywhere).

좌표는 화면에 보이는 방향(회전 뒤) 쪽의 pt이고 좌상단이 원점이다(웹 viewport의 배율 1과 같다). 글자 폭은 Metrics가 준다.
글꼴 파일·PDF를 읽지 않는 계산만 한다.
"""

import math
import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

SCRIPT_SCALE = 0.72  # 위·아래첨자 글자 크기 (웹 translation.css)
SUP_RISE = 0.33  # 위첨자 기준선을 올리는 양(문단 글꼴 크기 비율). 브라우저의 vertical-align: super 어림
SUB_DROP = 0.2
MIN_FONT = 3.0  # pt. 웹은 4px까지 줄인다
SHRINK = 0.95
TOLERANCE = 0.75  # pt. 웹은 1px 넘게 넘쳐야 줄인다
_TAG = re.compile(r"<(/?)(b|i|sub|sup)>", re.IGNORECASE)
_MARKS = ("b", "i", "bi")
_BREAKS = frozenset(chr(code) for code in (9, 10, 12, 13, 32))  # CSS가 낱말 사이로 보는 공백


class Metrics(Protocol):
    @property
    def ascent(self) -> float:
        """기준선 위 높이(글꼴 크기 비율)"""
        ...

    @property
    def descent(self) -> float:
        """기준선 아래 깊이(글꼴 크기 비율, 양수)"""
        ...

    def advance(self, char: str, bold: bool) -> float:
        """글자 폭(글꼴 크기 비율)"""
        ...


@dataclass(frozen=True)
class Rect:
    left: float
    top: float
    right: float
    bottom: float


@dataclass(frozen=True)
class SourceBlock:
    """번역한 원문 문단: 줄 상자, 원문 글꼴 크기(pt, 옛 추출이면 None), 문단 전체 모양(whole_mark), 번역 문장 묶음
    (<b>·<i>·<sub>·<sup> 표시가 든 글, 웹 sentences.ts sentenceGroups)."""

    block_id: str
    lines: Sequence[Rect]
    font_size: float | None
    mark: str
    groups: Sequence[str]


@dataclass(frozen=True)
class Frame:
    left: float
    top: float
    width: float
    height: float
    font_size: float  # 처음 글꼴 크기. 넘치면 그리는 쪽에서 줄인다
    line_height: float  # 한 줄 문단은 글줄 높이(pt, 글꼴을 줄여도 그대로), 여러 줄 문단은 글꼴 크기 비율
    single: bool


@dataclass(frozen=True)
class Run:
    """한 모양으로 이어 쓰는 글자들: 기준선 왼쪽 끝 자리와 글꼴 크기."""

    x: float
    baseline: float
    size: float
    text: str
    bold: bool
    italic: bool


@dataclass(frozen=True)
class BlockLayout:
    block_id: str
    mask: Rect  # 원문 글을 가리는 흰 상자
    runs: list[Run]
    groups: dict[int, list[Rect]]  # 문장 묶음 차례 → 그 번역문이 놓인 줄 조각들


@dataclass(frozen=True)
class _Char:
    text: str
    bold: bool
    italic: bool
    script: str | None
    group: int


def whole_mark(text: str, styles: Sequence[Sequence]) -> str:
    """문단 전체가 한 모양(굵게·기울임)이면 그 모양(웹 typeset.ts wholeMark)."""
    if len(styles) != 1:
        return ""
    start, end, mark = styles[0]
    return mark if start == 0 and end >= len(text) and mark in _MARKS else ""


def block_frame(lines: Sequence[Rect], font_size: float | None, scale: float) -> Frame:
    """웹 typeset.ts blockFrame(viewport 배율 1). scale은 사용자가 고른 번역 글꼴 배율이다.
    여러 줄 상자는 원문 줄 수 × 줄 사이 높이이고, 반 줄 간격만큼 위로 올려 글줄이 원문 줄과 겹치게 한다."""
    left = min(line.left for line in lines)
    right = max(line.right for line in lines)
    top = min(line.top for line in lines)
    heights = sorted(min(line.bottom - line.top, line.right - line.left) for line in lines)
    line_box = heights[len(heights) // 2]
    base = font_size if font_size else line_box * 0.78
    size = base * scale
    if len(lines) == 1:
        # 줄이 글꼴보다 훨씬 높으면(큰 첫 글자·큰 기호) 글줄은 위쪽에 있다
        height = max(line_box, size * 1.2)
        return Frame(left, top + (line_box - height) / 2, right - left, height, size, min(height, size * 1.4), True)
    tops = sorted(line.top for line in lines)
    measured = (tops[-1] - tops[0]) / (len(lines) - 1)
    # 줄 사이를 못 재면 어림한다. 위·아래첨자·큰 기호가 든 줄은 상자가 줄 사이보다 높아 글꼴 크기와 견준다
    reference = base if font_size else line_box
    pitch = measured if measured > reference * 0.8 else reference * 1.2
    ratio = max(1.0, math.floor(pitch / base * 1000 + 0.5) / 1000)
    return Frame(left, top - (pitch - line_box) / 2, right - left, len(lines) * pitch, size, ratio, False)


def single_line_room(frame: Frame, page_width: float) -> float:
    """한 줄 문단을 넓힐 수 있는 폭(웹 typeset.ts singleLineRoom): 쪽 왼쪽 반에만 놓인 줄은 가운데 앞까지, 아니면 오른쪽 여백까지."""
    limit = page_width * 0.48 if frame.left + frame.width <= page_width / 2 else page_width * 0.94
    return max(frame.width, limit - frame.left)


def layout_block(block: SourceBlock, page_width: float, scale: float, metrics: Metrics) -> BlockLayout:
    frame = block_frame(block.lines, block.font_size, scale)
    words = _words(block.groups, block.mark)
    ems = [[metrics.advance(char.text, char.bold) * (SCRIPT_SCALE if char.script else 1) for char in word] for word in words]
    space = metrics.advance(" ", "b" in block.mark)
    size, lines = _fit(frame, ems, space, single_line_room(frame, page_width))
    runs, groups = _place(frame, size, lines, words, ems, space, metrics)
    return BlockLayout(block.block_id, Rect(frame.left, frame.top, frame.left + frame.width, frame.top + frame.height), runs, groups)


def _words(groups: Sequence[str], mark: str) -> list[list[_Char]]:
    """번역 묶음들(웹은 묶음 사이에 공백을 둔다)을 낱말로 나눈다. 표시 밖은 모두 글 그대로다(HTML로 읽지 않는다)."""
    words: list[list[_Char]] = []
    word: list[_Char] = []
    for group, text in enumerate(groups):
        for char, bold, italic, script in _styled(text):
            if char in _BREAKS:
                if word:
                    words.append(word)
                    word = []
            else:
                word.append(_Char(char, bold or "b" in mark, italic or "i" in mark, script, group))
        if word:
            words.append(word)
            word = []
    return words


def _styled(text: str):
    """웹 typeset.ts styledRuns: 닫지 않은 표시는 글 끝까지, 짝 없는 닫기는 무시한다."""
    depth = {"b": 0, "i": 0, "sub": 0, "sup": 0}
    at = 0
    for match in [*_TAG.finditer(text), None]:
        script = "sub" if depth["sub"] > 0 else "sup" if depth["sup"] > 0 else None
        for char in text[at : match.start() if match else len(text)]:
            yield char, depth["b"] > 0, depth["i"] > 0, script
        if match:
            at = match.end()
            name = match.group(2).lower()
            depth[name] = max(0, depth[name] + (-1 if match.group(1) else 1))


def _fit(frame: Frame, ems: list[list[float]], space: float, room: float) -> tuple[float, list[list[tuple[int, int, int]]]]:
    """넘치지 않을 때까지 글꼴만 줄인다. 한 줄 문단은 넓힐 수 있는 폭(room)에, 여러 줄 문단은 상자 높이에 맞춘다."""
    size = frame.font_size
    while True:
        if frame.single:
            lines = [[(index, 0, len(word)) for index, word in enumerate(ems)]] if ems else []
            fits = (sum(map(sum, ems)) + space * max(0, len(ems) - 1)) * size <= room + TOLERANCE
        else:
            lines = _wrap(ems, space, frame.width / size)
            fits = len(lines) * frame.line_height * size <= frame.height + TOLERANCE
        if fits or size <= MIN_FONT:
            return size, lines
        size = max(MIN_FONT, size * SHRINK)


def _wrap(ems: list[list[float]], space: float, width: float) -> list[list[tuple[int, int, int]]]:
    """줄마다 (낱말 차례, 시작 글자, 끝 글자) 조각들. 폭은 모두 글꼴 크기 비율이다."""
    lines: list[list[tuple[int, int, int]]] = []
    line: list[tuple[int, int, int]] = []
    used = 0.0
    for index, word in enumerate(ems):
        total = sum(word)
        if line and used + space + total <= width + 1e-6:
            line.append((index, 0, len(word)))
            used += space + total
            continue
        if line:
            lines.append(line)
            line, used = [], 0.0
        start = 0
        while start < len(word):
            end, filled = start, 0.0
            while end < len(word) and (end == start or filled + word[end] <= width + 1e-6):
                filled += word[end]
                end += 1
            if end < len(word):
                lines.append([(index, start, end)])  # 나눈 낱말의 앞 조각은 제 줄을 다 쓴다
            else:
                line, used = [(index, start, end)], filled
            start = end
    if line:
        lines.append(line)
    return lines


def _place(frame, size, lines, words, ems, space, metrics: Metrics) -> tuple[list[Run], dict[int, list[Rect]]]:
    """글줄은 줄 높이 가운데에 놓는다(CSS line-height). 낱말 뒤 공백은 PDF에서 글을 복사할 때 낱말이 붙지 않게 함께 쓴다."""
    runs: list[Run] = []
    groups: dict[int, list[Rect]] = {}
    pitch = frame.line_height if frame.single else frame.line_height * size
    half = (pitch - (metrics.ascent + metrics.descent) * size) / 2
    for number, line in enumerate(lines):
        baseline = frame.top + number * pitch + half + metrics.ascent * size
        widths = [sum(ems[index][start:end]) * size for index, start, end in line]
        gap = space * size
        if not frame.single and number < len(lines) - 1 and len(line) > 1:
            gap += max(0.0, frame.width - sum(widths) - gap * (len(line) - 1)) / (len(line) - 1)
        x = frame.left
        spans: dict[int, list[float]] = {}
        for position, ((index, start, end), width) in enumerate(zip(line, widths, strict=True)):
            cursor = x
            pieces = _pieces(words[index][start:end], ems[index][start:end])
            for number_in_word, (chars, char_ems) in enumerate(pieces):
                first = chars[0]
                trailing = " " if position < len(line) - 1 and number_in_word == len(pieces) - 1 else ""
                shift = -SUP_RISE * size if first.script == "sup" else SUB_DROP * size if first.script == "sub" else 0.0
                text = "".join(char.text for char in chars) + trailing
                runs.append(Run(cursor, baseline + shift, size * (SCRIPT_SCALE if first.script else 1), text, first.bold, first.italic))
                for char, em in zip(chars, char_ems, strict=True):
                    span = spans.setdefault(char.group, [cursor, cursor])
                    cursor += em * size
                    span[1] = max(span[1], cursor)
            x += width + gap
        for group, (left, right) in spans.items():
            groups.setdefault(group, []).append(Rect(left, baseline - metrics.ascent * size, right, baseline + metrics.descent * size))
    return runs, groups


def _pieces(chars: list[_Char], ems: list[float]) -> list[tuple[list[_Char], list[float]]]:
    """같은 모양(굵게·기울임·첨자)으로 이어진 글자 조각들."""
    pieces: list[tuple[list[_Char], list[float]]] = []
    for char, em in zip(chars, ems, strict=True):
        if pieces and (pieces[-1][0][-1].bold, pieces[-1][0][-1].italic, pieces[-1][0][-1].script) == (char.bold, char.italic, char.script):
            pieces[-1][0].append(char)
            pieces[-1][1].append(em)
        else:
            pieces.append(([char], [em]))
    return pieces
