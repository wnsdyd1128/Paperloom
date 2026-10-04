"""답변 저장·목록·버리기 (IMPL §11.1, ADR 0002).

저장은 Reader 대화 탭의 Claude Code 브리지가 한다(MCP 호스트 저장은 2026-10-05에 뺐다). 이 서비스는 권한을 판단하지 않는다.
모델·외부 서비스를 호출하지 않는다. 같은 packet에 같은 질문·내용을 다시 저장하면 새로 만들지 않고 앞의 답변을 준다
(브리지가 다시 보내도 한 건이다).
"""

import hashlib
import json
import re
import uuid
from contextlib import closing
from pathlib import Path

from paperloom.answers import repository
from paperloom.answers.models import AnswerContext, AnswerOut, Citation, Origin

CONTEXT_CHARS = 300  # 대화의 인용에 보일 고른 글의 길이
from paperloom.context import repository as packets
from paperloom.infrastructure.clock import utc_now
from paperloom.infrastructure.database.sqlite import connect

# [근거 1], [근거 2, 3], [근거 22¶3]처럼 쓴 근거 번호(¶는 논문 본문 근거의 문단). 대괄호 번호만([12])은 논문의 참고문헌
# 번호와 헷갈리므로 근거로 읽지 않는다(2026-10-02 사용자 요청). 이 표기 전에 저장한 답변은 저장할 때 읽은 번호를 그대로 둔다.
# 문단은 하나(¶3) 또는 범위(¶4–5, 2026-10-02 사용자 확인: 모델이 범위를 쓴다). 범위는 첫 문단을 가리킨다.
_ITEM = r"\d{1,3}(?:\s*¶\s*\d{1,3}(?:\s*[–—~-]\s*\d{1,3})?)?"
_CITATION = re.compile(rf"\[근거\s*({_ITEM}(?:\s*,\s*(?:근거\s*)?{_ITEM})*)\]")
_PART = re.compile(r"(\d{1,3})(?:\s*¶\s*(\d{1,3})(?:\s*[–—~-]\s*\d{1,3})?)?")
MAX_LIST = 200  # 한 논문의 대화를 한 번에 받는다


def cited_items(markdown: str) -> list[tuple[int, int | None]]:
    """답변에 나온 (근거 번호, 문단 또는 None), 처음 나온 차례로 한 번씩."""
    items = (
        (int(number), int(paragraph) if paragraph else None)
        for match in _CITATION.finditer(markdown)
        for number, paragraph in _PART.findall(match.group(1))
    )
    return list(dict.fromkeys(items))


def cited_numbers(markdown: str) -> list[int]:
    """답변에 나온 근거 번호, 처음 나온 차례로 한 번씩."""
    return list(dict.fromkeys(number for number, _ in cited_items(markdown)))


class AnswerService:
    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path

    def save(
        self,
        packet_id: str,
        markdown: str,
        *,
        origin: Origin,
        prompt: str | None = None,
        chat_session: str | None = None,
        context: tuple[int | None, int | None] = (None, None),
        message_id: str | None = None,
    ) -> tuple[AnswerOut, bool]:
        """(답변, 새로 만들었는지). packet은 IMPORTED가 된다. packet이 있고 전달된 상태인지는 호출자가 확인한다."""
        digest = hashlib.sha256(markdown.encode()).hexdigest()
        with closing(connect(self._db_path)) as connection, connection:
            existing = repository.find_answer(connection, packet_id, digest, prompt)
            if existing is not None:
                answer_id, created = existing["answer_id"], False
            else:
                evidence = json.loads(packets.get_packet(connection, packet_id)["content_json"])["evidence"]
                citations = _resolve(cited_items(markdown), evidence)
                answer_id, created, now = str(uuid.uuid4()), True, utc_now()
                repository.insert_answer(
                    connection, answer_id, packet_id, None, origin, prompt, chat_session, markdown, digest, json.dumps(citations), now,
                    context,
                    message_id,
                )
                packets.import_answer(connection, packet_id, now)
        return self.get(answer_id), created

    def packet_status(self, packet_id: str) -> str | None:
        """답변을 받을 packet의 상태. 없으면 None."""
        with closing(connect(self._db_path)) as connection:
            row = packets.get_packet(connection, packet_id)
        return row["status"] if row else None

    def get(self, answer_id: str) -> AnswerOut | None:
        with closing(connect(self._db_path)) as connection:
            row = repository.get_answer(connection, answer_id)
        return _answer_out(row) if row else None

    def list(
        self,
        packet_id: str | None = None,
        limit: int = MAX_LIST,
        *,
        paper_id: str | None = None,
        session_id: str | None = None,
        origin: Origin | None = None,
    ) -> list[AnswerOut]:
        with closing(connect(self._db_path)) as connection:
            rows = repository.list_answers(connection, limit, packet_id=packet_id, paper_id=paper_id, chat_session=session_id, origin=origin)
            return [_answer_out(row) for row in rows]

    def discard(self, answer_id: str) -> AnswerOut | None:
        """목록에서 뺀다(지우지 않고 버린 때를 남긴다). 없으면 None."""
        with closing(connect(self._db_path)) as connection, connection:
            if repository.get_answer(connection, answer_id) is None:
                return None
            repository.discard_answer(connection, answer_id, utc_now())
        return self.get(answer_id)


def _resolve(items: list[tuple[int, int | None]], evidence: list[dict]) -> dict:
    """저장할 근거: resolved는 [번호, 문단 또는 None](문단이 그 근거에 없으면 None), unresolved는 packet에 없는 번호."""
    resolved, unresolved = [], []
    for number, paragraph in items:
        if not 1 <= number <= len(evidence):
            unresolved.append(number)
            continue
        paragraphs = len(evidence[number - 1].get("block_ids") or [])
        entry = [number, paragraph if paragraph and paragraph <= paragraphs else None]
        if entry not in resolved:
            resolved.append(entry)
    return {"resolved": resolved, "unresolved": list(dict.fromkeys(unresolved))}


def _answer_out(row) -> AnswerOut:
    content = json.loads(row["content_json"])
    evidence = content["evidence"]
    papers = {source["source_ref"]: source["paper_id"] for source in content["sources"]}
    stored = json.loads(row["citations_json"])
    # 저장한 뒤에 읽게 된 표기(문단 범위 등)도 근거가 되도록 글을 다시 읽어 저장된 근거에 더한다.
    # 문단 근거 전에 저장한 답변은 번호만 있다. 옛 표기([3])로 저장한 근거는 다시 읽지 않으므로 그대로 둔다.
    fresh = _resolve(cited_items(row["markdown"]), evidence)
    resolved = [(entry, None) if isinstance(entry, int) else tuple(entry) for entry in stored["resolved"]]
    resolved += [entry for entry in map(tuple, fresh["resolved"]) if entry not in resolved]
    return AnswerOut(
        answer_id=row["answer_id"],
        packet_id=row["packet_id"],
        origin=row["origin"],
        connection_name=row["connection_name"],
        prompt=row["prompt"],
        session_id=row["chat_session"],
        markdown=row["markdown"],
        content_sha256=row["content_sha256"],
        citations=[
            Citation(
                number=number,
                paragraph=paragraph,
                evidence_id=item["evidence_id"],
                role=item["role"],
                page_index=item["page_index"],
                paper_id=papers[item["source_ref"]],
                version_id=item["version_id"],
                anchor_id=item["anchor_id"],
                block_id=item["block_ids"][paragraph - 1] if paragraph else item["block_id"],
            )
            for number, paragraph in resolved
            for item in [evidence[number - 1]]
        ],
        unresolved_citations=list(dict.fromkeys([*stored["unresolved"], *fresh["unresolved"]])),
        review_status=row["review_status"],
        created_at=row["created_at"],
        discarded_at=row["discarded_at"],
        question=content["question"],
        paper_titles=[source["title"] for source in content["sources"]],
        context=[
            AnswerContext(
                kind="text" if item["role"] == "selected_text" else item["kind"] or "generic",
                page_index=item["page_index"],
                text=(item["display_text"] or item["text"])[:CONTEXT_CHARS] if item["role"] == "selected_text" else "",
                anchor_id=item["anchor_id"],
                image_url=item["image"]["url"] if item["image"] else None,
            )
            for item in evidence
            if item["role"] in ("selected_text", "selected_region")
        ],
        scope=content.get("scope"),
        scope_page=content.get("scope_page"),
        context_tokens=row["context_tokens"],
        context_window=row["context_window"],
        message_id=row["cc_message_id"],
    )
