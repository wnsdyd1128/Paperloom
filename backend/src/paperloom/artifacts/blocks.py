"""대화 답 Markdown 안의 아티팩트 (2026-11-09 사용자 요청: 대화에서 만든 아티팩트를 모아 두는 보관함).

아티팩트는 답 Markdown의 울타리 코드 블록이다(형식은 브리지의 시스템 프롬프트, integrations/claude_code/cli.py). 답과 함께
저장되므로 따로 보관하지 않고, 읽을 때 찾는다. 웹이 답을 그릴 때 아티팩트 자리로 바꾸는 규칙
(apps/web/src/features/artifacts/artifact.ts의 parseArtifact·fencedArtifact)과 같게 찾는다.
웹은 Markdown 해석기(remark)가 찾은 울타리 블록을 보고, 여기는 CommonMark의 울타리 규칙을 줄 단위로 따른다. 그래서 네 칸 넘게
들인 블록(깊은 목록 안)이나 인용문(>) 안의 블록은 찾지 못한다.
"""

import re
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Literal

ArtifactType = Literal["html", "svg", "mermaid", "react", "markdown", "code"]
TYPES: tuple[ArtifactType, ...] = ("html", "svg", "mermaid", "react", "markdown", "code")
DEFAULT_TITLES: dict[ArtifactType, str] = {
    "html": "HTML 페이지",
    "svg": "그림",
    "mermaid": "다이어그램",
    "react": "React 화면",
    "markdown": "문서",
    "code": "코드",
}

_OPENING = re.compile(r"( {0,3})(`{3,}|~{3,})(.*)")
_CLOSING = re.compile(r" {0,3}(`{3,}|~{3,})[ \t]*")
_FIELD = re.compile(r'([A-Za-z0-9_]+)="([^"]*)"')  # 웹의 /(\w+)="([^"]*)"/ (JavaScript의 \w는 ASCII뿐)
_HTML_START = re.compile(r"<html[\s>]")
_SVG_START = re.compile(r"<svg[\s>]")
_TITLE = re.compile(r"<title[^>]*>([^<]*)</title>", re.IGNORECASE)


@dataclass(frozen=True)
class Block:
    type: ArtifactType
    title: str
    language: str | None  # code의 언어(python 등). 다른 종류는 None
    content: str


def artifacts_in(markdown: str) -> list[Block]:
    """답에 나온 순서대로. 아티팩트가 아닌 울타리 블록은 건너뛴다."""
    return [block for _, _, block in _artifact_lines(_lines(markdown))]


def without_artifacts(markdown: str) -> str:
    """아티팩트 블록을 `[아티팩트: 제목]` 한 줄로 바꾼 답. 코드를 펼쳐 둘 수 없는 곳(PDF 메모)에 쓴다."""
    lines = _lines(markdown)
    kept: list[str] = []
    last = 0
    for start, end, block in _artifact_lines(lines):
        kept += [*lines[last:start], f"[아티팩트: {block.title}]"]
        last = end
    return "\n".join([*kept, *lines[last:]])


def _lines(markdown: str) -> list[str]:
    return markdown.removesuffix("\n").split("\n")  # 끝 줄바꿈 뒤는 줄이 아니다


def _artifact_lines(lines: list[str]) -> Iterator[tuple[int, int, Block]]:
    """(여는 줄, 닫는 줄 다음 줄, 아티팩트)를 나온 순서대로."""
    index = 0
    while index < len(lines):
        start = index
        opening = _OPENING.fullmatch(lines[index])
        index += 1
        if not opening or (opening.group(2)[0] == "`" and "`" in opening.group(3)):
            continue  # 백틱 울타리의 정보 글에는 백틱이 없다
        indent, fence = len(opening.group(1)), opening.group(2)
        body: list[str] = []
        while index < len(lines):  # 닫는 줄이 없으면 답 끝까지가 블록이다
            line = lines[index]
            index += 1
            closing = _CLOSING.fullmatch(line)
            if closing and closing.group(1)[0] == fence[0] and len(closing.group(1)) >= len(fence):
                break
            body.append(line[min(indent, len(line) - len(line.lstrip(" "))) :])
        language, *meta = re.split(r"[ \t]+", opening.group(3).strip(), maxsplit=1)  # 첫 낱말이 언어, 나머지가 meta
        if artifact := _artifact(language, meta[0] if meta else "", "\n".join(body)):
            yield start, index, artifact


def _artifact(language: str, meta: str, content: str) -> Block | None:
    if language == "artifact":
        fields = {key: value.strip() for key, value in _FIELD.findall(meta)}
        kind = fields.get("type")
        if kind not in TYPES:
            return None
        return Block(kind, fields.get("title") or DEFAULT_TITLES[kind], (fields.get("language") or None) if kind == "code" else None, content)
    return _fenced(language.lower(), content) if language else None


def _fenced(kind: str, content: str) -> Block | None:
    """형식 없이 보통 코드 블록으로 온 것 가운데 그대로 열 수 있는 html 문서·svg 요소·mermaid (웹의 fencedArtifact)"""
    start = content.lstrip()[:32].lower()
    if kind == "html" and (start.startswith("<!doctype html") or _HTML_START.match(start)):
        title = _TITLE.search(content)
        return Block("html", (title.group(1).strip() if title else "") or DEFAULT_TITLES["html"], None, content)
    if kind == "svg" and _SVG_START.match(start):
        return Block("svg", DEFAULT_TITLES["svg"], None, content)
    if kind == "mermaid" and content.strip():
        return Block("mermaid", DEFAULT_TITLES["mermaid"], None, content)
    return None
