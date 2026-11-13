"""PDF로 내보낼 표시 (2026-11-13 사용자 요청: 업로드한 논문을 PDF로 내보내며 하이라이트·주석·설명·AI 질문을 골라 넣는다).

표시 하나가 PDF 표준 주석 하나다. 하이라이트는 원문 위 색칠(/Highlight)이고, 주석의 메모·설명·AI 질문은 그 위치의 메모
아이콘(/Text)이다. 하이라이트한 주석에 메모가 있고 둘 다 고르면 메모는 따로 아이콘을 두지 않고 하이라이트의 글이 된다.
Reader 사이드바의 Claude 대화와 선택 메뉴의 번역은 넣지 않는다(사용자 결정: 대화는 나중에, 번역은 빼기).
"""

from collections.abc import Collection, Sequence
from dataclasses import dataclass
from typing import Literal

from paperloom.annotations.models import AnnotationOut
from paperloom.artifacts.blocks import without_artifacts
from paperloom.reading.models import AnchorOut

Part = Literal["highlights", "notes", "explanations", "questions"]
PARTS: tuple[Part, ...] = ("highlights", "notes", "explanations", "questions")

# 웹의 하이라이트 색과 같다(--mark-c1…c3, apps/web/src/shared/theme/tokens.css)
HIGHLIGHT_RGB = {"c1": "ffe0d9", "c2": "ff9783", "c3": "d7d3d3"}
# 메모 아이콘 색: 주석은 웹의 메모 표시(--mark-note-line), 설명은 강조색, AI 질문은 회색
NOTE_RGB = {"주석": "ff9783", "설명": "ec3013", "AI 질문": "605d5d"}
QUOTE_CHARS = 200  # 메모 첫 줄에 보이는 인용의 길이
_REGION_NAMES = {"figure": "그림", "table": "표", "equation": "수식", "generic": "영역"}


@dataclass(frozen=True)
class Mark:
    page_index: int
    kind: Literal["highlight", "note"]
    quads: list[list[float]]  # anchor.v1 정본 좌표
    label: str  # 메모 창 제목(/T)
    contents: str  # 메모 글(/Contents). 빈 글이면 표시만 한다
    rgb: str  # RRGGBB


@dataclass(frozen=True)
class Turn:
    """대화 한 차례: 질문과 Claude의 답(Markdown)."""

    prompt: str | None
    markdown: str


@dataclass(frozen=True)
class Thread:
    """원문 위에서 시작한 설명·질문 대화와 버리지 않은 차례들(오래된 것부터)."""

    kind: Literal["explain", "ask"]
    anchor: AnchorOut
    turns: Sequence[Turn]


def marks_for(annotations: Sequence[AnnotationOut], threads: Sequence[Thread], parts: Collection[Part]) -> list[Mark]:
    """고른 부분(parts)의 표시를 읽는 순서(쪽, 위, 왼쪽)로. 같은 자리면 주석이 대화보다 앞이다."""
    marks = [mark for annotation in annotations for mark in _annotation_marks(annotation, parts)]
    wanted = {"explain": "explanations" in parts, "ask": "questions" in parts}
    marks += [_thread_mark(thread) for thread in threads if wanted[thread.kind] and thread.turns]
    return sorted(marks, key=lambda mark: (mark.page_index, mark.quads[0][1], mark.quads[0][0]))


def _annotation_marks(annotation: AnnotationOut, parts: Collection[Part]) -> list[Mark]:
    anchor = annotation.anchor
    comment = annotation.comment.strip() if "notes" in parts else ""
    if annotation.color is not None and "highlights" in parts:
        label = "주석" if comment else "하이라이트"
        return [Mark(anchor.page_index, "highlight", anchor.quads, label, comment, HIGHLIGHT_RGB[annotation.color])]
    if comment:
        return [_note(anchor, "주석", comment)]
    return []


def _thread_mark(thread: Thread) -> Mark:
    blocks: list[str] = []
    for index, turn in enumerate(thread.turns):
        # 설명의 첫 질문은 선택 메뉴가 넣은 정해진 문장이라 보이지 않는다
        if turn.prompt and not (thread.kind == "explain" and index == 0):
            blocks.append(f"질문: {turn.prompt.strip()}")
        blocks.append(without_artifacts(turn.markdown).strip())
    return _note(thread.anchor, "설명" if thread.kind == "explain" else "AI 질문", "\n\n".join(blocks))


def _note(anchor: AnchorOut, label: str, text: str) -> Mark:
    """메모 아이콘은 글의 범위를 칠하지 않으므로 첫 줄에 어느 글(영역)인지 적는다."""
    return Mark(anchor.page_index, "note", anchor.quads, label, f"{_where(anchor)}\n\n{text}", NOTE_RGB[label])


def _where(anchor: AnchorOut) -> str:
    if anchor.kind != "text":
        return f"[{_REGION_NAMES.get(anchor.kind, '영역')}]"
    quote = " ".join((anchor.display_quote or anchor.quote).split())
    if len(quote) > QUOTE_CHARS:
        quote = quote[:QUOTE_CHARS].rstrip() + "…"
    return f"“{quote}”"
