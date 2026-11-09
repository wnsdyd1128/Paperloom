"""Evidence Bundle의 파일 내용 만들기 (03-api-spec §5–§8). 순수 함수만 둔다. DB·디스크를 건드리지 않는다.

LLM Wiki 수신기는 bundle을 통째로 받거나 통째로 거부한다. 그래서 글자 수 한도가 있는 칸은 여기서 잘라 둔다: 한 칸이 길다고 bundle
전체가 거부되면 안 된다. 잘리는 값은 메모·절 제목처럼 원문 쪽에 그대로 남아 있는 것뿐이다.
값은 Paperloom에 있는 그대로 옮긴다. 새로 계산하는 것은 해시·크기·bundle 안 참조 이름(src_1, anc_1)뿐이다. 모델을 부르지 않는다.
"""

import hashlib
import json
import re
from dataclasses import dataclass, field
from urllib.parse import quote, urlencode

from paperloom.answers.models import AnswerOut, Citation
from paperloom.artifacts.blocks import Block as ArtifactBlock
from paperloom.context.builder import Block
from paperloom.documents.block_kinds import IN_FIGURE, IN_TABLE, MATH, PAGE_FOOTER, PAGE_HEADER, REFERENCE, is_caption
from paperloom.documents.models import PaperOut, VersionOut
from paperloom.reading.models import AnchorOut

BUNDLE_SCHEMA = "paperloom-bundle.v1"
BUNDLE_SCHEMA_WITH_TEXTS = "paperloom-bundle.v1.1"
PROPOSAL_SCHEMA = "wiki-proposal.v1"
TEXT_SCHEMA = "paperloom-text.v1"
EXTRACTOR_NAME = "paperloom-parse"
PRODUCER = "paperloom"
MANIFEST = "manifest.json"
NOT_EXTRACTED = "not_extracted"  # 쪽 추출 상태(usable 등)가 아직 없는 쪽

MAX_FILES = 64  # manifest 포함
MAX_FILE_BYTES = 8 * 1024 * 1024
MAX_TOTAL_BYTES = 32 * 1024 * 1024
NEAR_LIMIT_SHARE = 0.8

# 수신기(LLM Wiki domain/intake.py)의 칸 한도
MAX_LONG_TEXT = 100_000
MAX_TITLE = 2000
MAX_SECTION = 2000
MAX_PAGE_LABEL = 100
MAX_AUTHORS = 500
MAX_DOI = 500
QUESTION_CHARS = 200  # 답변 머리에 적는 질문 앞부분

_SAFE_ID = re.compile(r"[A-Za-z0-9_-]+")
_BACKTICKS = re.compile(r"`+")
_FENCE_LANGUAGES = {"html": "html", "svg": "svg", "mermaid": "mermaid", "react": "jsx"}
_BODY_FLAGS = (REFERENCE, IN_TABLE, IN_FIGURE, MATH, PAGE_HEADER, PAGE_FOOTER)
_FILE_KINDS = {"proposals": "proposal", "artifacts": "artifact", "assets": "asset", "texts": "text"}


@dataclass(frozen=True)
class AnchorEntry:
    anchor: AnchorOut
    page_label: str | None
    section: str | None
    comment: str | None  # 넣지 않기로 했거나 메모가 없으면 None
    image: bytes | None  # 넣을 PNG


@dataclass(frozen=True)
class TextEntry:
    extractor: dict
    pages: list[dict]  # paperloom-text.v1의 pages 값, 쪽 차례


@dataclass(frozen=True)
class SourceEntry:
    paper: PaperOut
    version: VersionOut
    anchors: list[AnchorEntry]
    text: TextEntry | None


@dataclass(frozen=True)
class ProposalEntry:
    proposal_id: str
    version_id: str
    title: str
    content: str
    anchor_ids: list[str]


@dataclass(frozen=True)
class ArtifactEntry:
    """답변 안의 아티팩트 하나 (paperloom.artifacts.blocks). index는 답변 안 차례(0부터)다."""

    answer: AnswerOut
    index: int
    block: ArtifactBlock


@dataclass(frozen=True)
class BundleContent:
    bundle_id: str
    created_at: str
    producer_version: str
    base_url: str  # Paperloom 웹 주소. Reader 복귀 링크에 쓴다
    sources: list[SourceEntry]
    proposals: list[ProposalEntry]
    answers: list[AnswerOut]
    artifacts: list[ArtifactEntry] = field(default_factory=list)


class _Names:
    """파일 이름에 쓸 ID. [A-Za-z0-9_-]가 아닌 ID는 n001처럼 바꾼다(§5.1). 원래 ID는 파일 안에 적혀 있다."""

    def __init__(self) -> None:
        self._replaced = 0

    def __call__(self, identifier: str) -> str:
        if _SAFE_ID.fullmatch(identifier):
            return identifier
        self._replaced += 1
        return f"n{self._replaced:03d}"


def build_files(content: BundleContent) -> dict[str, bytes]:
    """bundle 안 경로 → 파일 내용. manifest.json이 맨 뒤다(§5.3)."""
    names = _Names()
    source_refs = {entry.version.version_id: f"src_{number}" for number, entry in enumerate(content.sources, start=1)}
    anchor_refs: dict[str, str] = {}
    sources, anchors, assets, texts = [], [], {}, {}
    for entry in content.sources:
        version_id = entry.version.version_id
        sources.append(_source(entry, source_refs[version_id], content.base_url))
        for item in entry.anchors:
            anchor_id = item.anchor.anchor_id
            anchor_refs[anchor_id] = f"anc_{len(anchor_refs) + 1}"
            asset = f"assets/{names(anchor_id)}.png" if item.image is not None else None
            if asset:
                assets[asset] = item.image
            anchors.append(_anchor(item, anchor_refs[anchor_id], source_refs[version_id], asset, entry.paper.paper_id, content.base_url))
        if entry.text:
            texts[f"texts/{names(version_id)}.json"] = _json(_text_document(entry, source_refs[version_id]))

    files = {"sources.json": _json(sources), "anchors.json": _json(anchors)}
    for proposal in content.proposals:
        name = names(proposal.proposal_id)
        content_file = f"artifacts/proposal-{name}.md"
        files[f"proposals/{name}.json"] = _json(
            {
                "schema_version": PROPOSAL_SCHEMA,
                "proposal_id": proposal.proposal_id,
                "bundle_id": content.bundle_id,
                "operation": "propose_note",
                "target_note_id": None,
                "base_content_sha256": None,
                "title": proposal.title[:MAX_TITLE],
                "content_file": content_file,
                "source_refs": [source_refs[proposal.version_id]],
                "anchor_refs": [anchor_refs[anchor_id] for anchor_id in dict.fromkeys(proposal.anchor_ids)],
                "requires_user_approval": True,
            }
        )
        files[content_file] = proposal.content.encode()
    for answer in content.answers:
        files[f"artifacts/answer-{names(answer.answer_id)}.md"] = _answer_markdown(answer, anchor_refs).encode()
    for item in content.artifacts:
        files[f"artifacts/artifact-{names(item.answer.answer_id)}-{item.index + 1}.md"] = _artifact_markdown(item).encode()
    files |= assets | texts

    manifest = {
        "schema_version": BUNDLE_SCHEMA_WITH_TEXTS if texts else BUNDLE_SCHEMA,
        "bundle_id": content.bundle_id,
        "created_at": content.created_at,
        "producer": {"name": PRODUCER, "version": content.producer_version},
        **({"features": ["texts"]} if texts else {}),
        "files": [{"path": path, "sha256": sha256(data), "size_bytes": len(data)} for path, data in files.items()],
    }
    files[MANIFEST] = _json(manifest)
    return files


def reader_url(base_url: str, paper_id: str, version_id: str, anchor_id: str | None = None) -> str:
    """Reader로 돌아가는 링크 (§8). LLM Wiki는 http://127.0.0.1:<port>/reader/… 꼴만 남기고 나머지는 버린다."""
    query = {"version": version_id} | ({"anchor": anchor_id} if anchor_id else {})
    return f"{base_url.rstrip('/')}/reader/{quote(paper_id, safe='')}?{urlencode(query)}"


def block_kind(block: Block, headings: frozenset[str]) -> str:
    """문단 종류. 본문 표시(block_kinds)가 있으면 그 값 그대로, 없으면 heading·caption·body다."""
    flag = next((flag for flag in _BODY_FLAGS if flag in block.quality_flags), None)
    if flag:
        return flag
    if block.block_id in headings:
        return "heading"
    return "caption" if is_caption(block.text) else "body"


def text_sha256(pages: list[dict]) -> str:
    """pages 값의 해시: 키를 정렬한 UTF-8 JSON(공백 없음). LLM Wiki가 모델에 보내기 직전 글이 그대로인지 확인한다."""
    return sha256(json.dumps(pages, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode())


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def file_kind(path: str) -> str:
    return _FILE_KINDS.get(path.split("/")[0], path.removesuffix(".json"))


def limit_excess(files: dict[str, bytes]) -> dict | None:
    """한도(§5.2)를 넘으면 BUNDLE_TOO_LARGE의 details, 아니면 None."""
    total = sum(map(len, files.values()))
    largest = max(files, key=lambda path: len(files[path]))
    if len(files) <= MAX_FILES and total <= MAX_TOTAL_BYTES and len(files[largest]) <= MAX_FILE_BYTES:
        return None
    return {"file_count": len(files), "total_bytes": total, "largest_path": largest}


def near_limit(files: dict[str, bytes]) -> bool:
    return len(files) > NEAR_LIMIT_SHARE * MAX_FILES or sum(map(len, files.values())) > NEAR_LIMIT_SHARE * MAX_TOTAL_BYTES


def _json(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, indent=2).encode()


def _source(entry: SourceEntry, source_ref: str, base_url: str) -> dict:
    paper, version = entry.paper, entry.version
    return {
        "source_ref": source_ref,
        "paper_id": paper.paper_id,
        "version_id": version.version_id,
        "sha256": version.sha256,
        "page_count": version.page_count,
        "title": paper.title[:MAX_TITLE],
        "authors": paper.authors[:MAX_AUTHORS],
        "year": paper.year,
        "doi": paper.doi[:MAX_DOI] if paper.doi else None,
        "reader_url": reader_url(base_url, paper.paper_id, version.version_id),
    }


def _anchor(item: AnchorEntry, anchor_ref: str, source_ref: str, asset: str | None, paper_id: str, base_url: str) -> dict:
    anchor = item.anchor
    return {
        "anchor_ref": anchor_ref,
        "anchor_id": anchor.anchor_id,
        "source_ref": source_ref,
        "kind": anchor.kind,
        "page_index": anchor.page_index,
        "page_label": item.page_label[:MAX_PAGE_LABEL] if item.page_label else None,
        "quads": anchor.quads,
        "quote": anchor.quote,
        "display_quote": anchor.display_quote,
        "prefix": anchor.prefix,
        "suffix": anchor.suffix,
        "section": item.section[:MAX_SECTION] if item.section else None,
        "comment": item.comment[:MAX_LONG_TEXT] if item.comment else None,
        "asset": asset,
        "reader_url": reader_url(base_url, paper_id, anchor.version_id, anchor.anchor_id),
    }


def _text_document(entry: SourceEntry, source_ref: str) -> dict:
    return {
        "schema_version": TEXT_SCHEMA,
        "source_ref": source_ref,
        "version_id": entry.version.version_id,
        "sha256": entry.version.sha256,
        "extractor": entry.text.extractor,
        "pages": entry.text.pages,
        "text_sha256": text_sha256(entry.text.pages),
    }


def _answer_markdown(answer: AnswerOut, anchor_refs: dict[str, str]) -> str:
    """머리에 근거 번호를 bundle 안 Anchor로 풀어 두고 답변을 그대로 잇는다(§6.5). 논문 본문 근거는 Anchor가 없어 풀지 못한다.
    그 근거도 쪽은 알므로 함께 적는다."""
    resolved, unresolved = [], []
    for citation in answer.citations:
        ref = anchor_refs.get(citation.anchor_id)
        page = f"쪽 {citation.page_index + 1}"
        if ref:
            resolved.append(f"{_citation_label(citation)} = {ref} ({page})")
        else:
            unresolved.append(f"{_citation_label(citation)} ({page})")
    unresolved += [f"[근거 {number}]" for number in answer.unresolved_citations]
    parts = [*resolved, *([f"풀지 못함: {', '.join(unresolved)}"] if unresolved else [])]
    question = " ".join((answer.prompt or answer.question).split())[:QUESTION_CHARS]
    head = [
        f"> Paperloom 답변 · answer_id {answer.answer_id} · origin {answer.origin} · review {answer.review_status} · {answer.created_at}",
        f"> 질문: {question}",
        f"> 근거: {' · '.join(parts) or '없음'}",
    ]
    return "\n".join([*head, "", answer.markdown, ""])


def _artifact_markdown(item: ArtifactEntry) -> str:
    """머리 뒤에 아티팩트를 둔다(§6.5). LLM Wiki는 artifacts/에 Markdown만 받으므로 HTML·SVG 파일로 따로 넣지 않는다: 문서는 그대로
    두고, 나머지는 소스가 그대로 보이게 울타리 코드 블록에 담는다. 울타리는 안에 든 어떤 백틱 줄보다 길게 한다."""
    answer, block = item.answer, item.block
    kind = f"{block.type} · {block.language}" if block.language else block.type
    question = " ".join((answer.prompt or answer.question).split())[:QUESTION_CHARS]
    head = [
        f"> Paperloom 아티팩트 · answer_id {answer.answer_id} · 답변의 {item.index + 1}번째 · type {kind} · review {answer.review_status} · {answer.created_at}",
        f"> 제목: {' '.join(block.title.split())[:MAX_TITLE]}",
        f"> 질문: {question}",
    ]
    if block.type == "markdown":
        body = block.content
    else:
        fence = "`" * max(3, 1 + max(map(len, _BACKTICKS.findall(block.content)), default=0))
        info = re.sub(r"[\s`]", "", block.language or "") if block.type == "code" else _FENCE_LANGUAGES[block.type]
        body = f"{fence}{info}\n{block.content}\n{fence}"
    return "\n".join([*head, "", body, ""])


def _citation_label(citation: Citation) -> str:
    return f"[근거 {citation.number}¶{citation.paragraph}]" if citation.paragraph else f"[근거 {citation.number}]"
