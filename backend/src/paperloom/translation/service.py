"""쪽 번역 읽기·저장 (U7). 번역은 원문 문단 글과 함께 두고, 읽을 때 지금 추출의 문단과 글로 맞춘다.

다시 추출하면 문단 ID가 바뀌지만 글이 같으면 번역을 그대로 쓴다. 지금 문단 가운데 하나라도 번역이 없으면(글이 바뀜)
그 쪽은 번역하지 않은 것으로 본다(다시 번역한다).
"""

import json
from contextlib import closing
from pathlib import Path

from paperloom.documents import repository, text_repository
from paperloom.documents.block_kinds import NOT_BODY
from paperloom.documents.sentences import sentence_spans
from paperloom.infrastructure.clock import utc_now
from paperloom.infrastructure.database.sqlite import connect
from paperloom.translation.models import (
    Language,
    PageTranslationIn,
    PageTranslationOut,
    TranslatedBlockOut,
    TranslatedPages,
    TranslatedSentence,
)


class PageNotFound(Exception):
    """버전이 없거나 쪽 번호가 범위 밖이다."""


class TextNotReady(Exception):
    """본문 추출이 아직 끝나지 않았다."""


class InvalidTranslation(Exception):
    def __init__(self, message: str, details: dict) -> None:
        super().__init__(message)
        self.message = message
        self.details = details


class TranslationService:
    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path

    def get(self, version_id: str, page_index: int, language: Language) -> PageTranslationOut | None:
        """그 쪽의 번역. 저장하지 않았거나 지금 문단과 맞지 않으면 None."""
        with closing(connect(self._db_path)) as connection:
            current = self._blocks(connection, version_id, page_index)
            row = connection.execute(
                "SELECT model, blocks_json, created_at FROM page_translations WHERE version_id = ? AND page_index = ? AND language = ?",
                (version_id, page_index, language),
            ).fetchone()
        if row is None:
            return None
        stored = json.loads(row["blocks_json"])
        used: set[int] = set()
        blocks: list[TranslatedBlockOut] = []
        for block in current:
            spans = sentence_spans(block["text"])
            match = next(
                (index for index, item in enumerate(stored) if index not in used and item["source"] == block["text"] and len(item["sentences"]) == len(spans)),
                None,
            )
            if match is None:
                return None
            used.add(match)
            sentences = [TranslatedSentence(start=start, end=end, text=text) for (start, end), text in zip(spans, stored[match]["sentences"])]
            blocks.append(TranslatedBlockOut(block_id=block["block_id"], sentences=sentences))
        return PageTranslationOut(
            version_id=version_id, page_index=page_index, language=language, model=row["model"], created_at=row["created_at"], blocks=blocks
        )

    def put(self, version_id: str, page_index: int, language: Language, body: PageTranslationIn) -> PageTranslationOut:
        """그 쪽의 번역을 바꾼다. 지금 문단 모두를, 문단마다 원문 문장 수만큼 받아야 한다. 빈 번역은 앞 문장에 합쳐 옮긴
        것이다. 문단의 첫 문장도 비울 수 있다(PDF에서 문장 가운데서 나뉜 문단을 앞 문단 끝 문장에 합쳤다). 쪽의 첫 문장만은
        합칠 앞 문장이 없어 비울 수 없다."""
        with closing(connect(self._db_path)) as connection, connection:
            current = self._blocks(connection, version_id, page_index)
            received = {block.block_id: block.sentences for block in body.blocks}
            expected = [block["block_id"] for block in current]
            if len(received) != len(body.blocks) or set(received) != set(expected):
                raise InvalidTranslation(
                    "쪽의 문단마다 번역이 하나씩 있어야 합니다.",
                    {"missing": [block for block in expected if block not in received], "unknown": sorted(set(received) - set(expected))},
                )
            stored = []
            for position, block in enumerate(current):
                sentences = received[block["block_id"]]
                count = len(sentence_spans(block["text"]))
                if len(sentences) != count:
                    raise InvalidTranslation("원문 문장마다 번역이 하나씩 있어야 합니다.", {"block_id": block["block_id"], "expected": count, "received": len(sentences)})
                if position == 0 and not sentences[0].strip():
                    raise InvalidTranslation("쪽의 첫 문장 번역이 비어 있습니다.", {"block_id": block["block_id"]})
                stored.append({"source": block["text"], "sentences": [sentence.strip() for sentence in sentences]})
            connection.execute(
                "INSERT INTO page_translations (version_id, page_index, language, model, blocks_json, created_at) VALUES (?, ?, ?, ?, ?, ?)"
                " ON CONFLICT (version_id, page_index, language) DO UPDATE SET model = excluded.model, blocks_json = excluded.blocks_json,"
                " created_at = excluded.created_at",
                (version_id, page_index, language, body.model, json.dumps(stored, ensure_ascii=False), utc_now()),
            )
        saved = self.get(version_id, page_index, language)
        assert saved is not None
        return saved

    def pages(self, version_id: str, language: Language) -> TranslatedPages:
        with closing(connect(self._db_path)) as connection:
            if repository.get_version(connection, version_id) is None:
                raise PageNotFound()
            rows = connection.execute(
                "SELECT page_index FROM page_translations WHERE version_id = ? AND language = ? ORDER BY page_index", (version_id, language)
            ).fetchall()
        return TranslatedPages(version_id=version_id, language=language, pages=[row["page_index"] for row in rows])

    def delete(self, version_id: str, language: Language) -> None:
        """그 버전의 그 언어 번역을 모두 지운다(다음에 볼 때 다시 번역한다)."""
        with closing(connect(self._db_path)) as connection, connection:
            if repository.get_version(connection, version_id) is None:
                raise PageNotFound()
            connection.execute("DELETE FROM page_translations WHERE version_id = ? AND language = ?", (version_id, language))

    @staticmethod
    def _blocks(connection, version_id: str, page_index: int) -> list:
        """그 쪽의 번역할 문단(글이 있고 그림 안 글자가 아닌 것, 읽는 차례). 버전·쪽이 없으면 PageNotFound, 추출 전이거나
        다시 추출하는 중이면(문단이 곧 바뀐다) TextNotReady. 본문이 아닌 문단(그림·표 안, 따로 놓인 수식, 머리글·바닥글,
        block_kinds.NOT_BODY)은 번역하지 않는다(2026-10-03 사용자 요청)."""
        version = repository.get_version(connection, version_id)
        if version is None or not 0 <= page_index < version.page_count:
            raise PageNotFound()
        if text_repository.get_page(connection, version_id, page_index) is None or text_repository.active_run(connection, version_id):
            raise TextNotReady()
        return [
            block
            for block in text_repository.page_blocks(connection, version_id, page_index)
            if sentence_spans(block["text"]) and NOT_BODY.isdisjoint(json.loads(block["quality_flags_json"]))
        ]
