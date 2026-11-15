"""번역본 바탕의 자료 (2026-11-15 사용자 요청: PDF로 내보낼 때 원본 대신 레이아웃 유지 번역본을 바탕으로 고른다).

번역한 쪽마다 번역한 문단(줄 상자·원문 글꼴 크기·문단 모양)과 번역 문장 묶음을 내보내기 하위 프로세스(writer)에 넘긴다.
번역하지 않은 쪽은 원문 그대로 둔다(사용자 결정).

하이라이트는 원문 낱말에 칠한 것이라 그 자리의 번역문 낱말과 맞지 않는다. 그래서 하이라이트가 걸친 원문 문장 묶음을
찾아 그 번역문 전체에 칠한다(사용자 결정). 인용을 그 쪽 번역한 문단 글에서 찾는데, 웹(locate.ts)처럼 공백·하이픈·합자·
대소문자를 빼고 견준다. 찾지 못하면(그림 같은 영역, 번역하지 않는 문단) 원래 자리에 칠한다.
"""

import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass

from paperloom.translation.models import TranslatedSentence

_HYPHENS = frozenset(chr(code) for code in (0x2D, 0xAD, 0x2010, 0x2011))
_CONTEXT = 30  # 같은 인용이 여럿일 때 견줄 앞뒤 글 길이(접은 글자 수)


@dataclass(frozen=True)
class Group:
    """번역 문장 묶음: 번역문과 그 원문 범위들(문단 text 안의 [시작, 끝))."""

    text: str
    ranges: list[tuple[int, int]]


@dataclass(frozen=True)
class TranslatedBlock:
    block_id: str
    text: str  # 원문 문단 글
    regions: list[list[float]]  # 줄 상자 [u0, v0, u1, v1] (정본 좌표)
    font_size: float | None  # 원문 글꼴 크기(pt)
    mark: str  # 문단 전체 모양: "", "b", "i", "bi" (typeset.whole_mark)
    groups: list[Group]


@dataclass(frozen=True)
class TranslatedPage:
    page_index: int
    blocks: list[TranslatedBlock]

    def drawing(self) -> dict:
        """하위 프로세스에 넘길 것(원문 글과 원문 범위는 넘기지 않는다)"""
        return {
            "page_index": self.page_index,
            "blocks": [
                {"block_id": block.block_id, "regions": block.regions, "font_size": block.font_size, "mark": block.mark, "groups": [group.text for group in block.groups]}
                for block in self.blocks
            ],
        }


def sentence_groups(sentences: Sequence[TranslatedSentence]) -> list[Group]:
    """웹 sentences.ts sentenceGroups: 빈 번역은 어순 때문에 앞 문장 번역에 합쳐 옮긴 것이라 그 원문 범위를 앞 묶음에 더한다."""
    groups: list[Group] = []
    for sentence in sentences:
        if sentence.text or not groups:
            groups.append(Group(sentence.text, [(sentence.start, sentence.end)]))
        else:
            groups[-1].ranges.append((sentence.start, sentence.end))
    return groups


def highlight_targets(quote: str, prefix: str | None, suffix: str | None, blocks: Sequence[TranslatedBlock]) -> tuple[tuple[str, int], ...]:
    """인용이 걸친 (문단 ID, 문장 묶음 차례)들. 찾지 못하면 빈 튜플. 같은 인용이 여럿이면 앞뒤 글이 맞는 자리를 고른다."""
    target = _fold(quote)[0]
    if not target:
        return ()
    text = ""
    owners: list[tuple[int, int]] = []  # 접은 글자마다 (문단 차례, 문단 text 안 자리)
    for number, block in enumerate(blocks):
        folded, origins = _fold(block.text)
        text += folded
        owners += [(number, origin) for origin in origins]
    starts = []
    at = text.find(target)
    while at >= 0:
        starts.append(at)
        at = text.find(target, at + 1)
    if not starts:
        return ()
    before = _fold(prefix or "")[0][-_CONTEXT:]
    after = _fold(suffix or "")[0][:_CONTEXT]

    def context(start: int) -> int:
        return int(bool(before) and text[:start].endswith(before)) + int(bool(after) and text[start + len(target) :].startswith(after))

    best = max(starts, key=context)  # 같으면 앞 자리
    touched: dict[int, list[int]] = {}
    for number, origin in owners[best : best + len(target)]:
        touched.setdefault(number, []).append(origin)
    targets = []
    for number, origins in touched.items():
        low, high = min(origins), max(origins) + 1
        block = blocks[number]
        targets += [(block.block_id, index) for index, group in enumerate(block.groups) if any(start < high and low < end for start, end in group.ranges)]
    return tuple(targets)


def _fold(text: str) -> tuple[str, list[int]]:
    """견줄 글(NFKC·소문자, 공백·하이픈 뺌)과 그 글자마다 원래 글의 자리."""
    folded: list[str] = []
    origins: list[int] = []
    for index, char in enumerate(text):
        for item in unicodedata.normalize("NFKC", char).lower():
            if not item.isspace() and item not in _HYPHENS:
                folded.append(item)
                origins.append(index)
    return "".join(folded), origins
