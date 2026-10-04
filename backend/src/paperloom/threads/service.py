"""선택 설명·질문 대화 남기기·목록·자리 바꾸기·지우기 (docs/UI_PLAN.md A4).

대화 ID는 이 PC의 브리지가 그 논문에 대한 답을 저장한 것만 받는다. 그래서 임의의 Claude Code 세션을 가리키는
기록을 만들 수 없다(ADR 0003의 이어 묻기 경계와 같다). 모델·외부 서비스를 호출하지 않는다.
"""

from contextlib import closing
from pathlib import Path

from paperloom.answers import repository as answers
from paperloom.documents import repository as documents
from paperloom.infrastructure.clock import utc_now
from paperloom.infrastructure.database.sqlite import connect
from paperloom.reading.repository import anchor_from_row, get_anchor
from paperloom.threads import repository
from paperloom.threads.models import ConversationOut, ForkIn, Placement, SessionTitle, SessionTitleIn, ThreadIn, ThreadOut

TITLE_FROM_QUESTION_CHARS = 80


class NotFound(Exception):
    pass


class UnknownSession(Exception):
    pass


class ThreadService:
    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path

    def conversations(self, limit: int) -> "list[ConversationOut]":
        """모든 논문의 대화, 최근 것부터 (U6 답변 화면, D8)."""
        with closing(connect(self._db_path)) as connection:
            rows = repository.list_conversations(connection, limit)
        return [
            ConversationOut(
                session_id=row["chat_session"],
                kind=row["thread_kind"] or "chat",
                title=row["custom_title"] or row["thread_title"] or " ".join((row["first_prompt"] or "").split())[:TITLE_FROM_QUESTION_CHARS],
                paper_id=row["paper_id"],
                paper_title=row["paper_title"],
                version_id=row["version_id"],
                placement=row["placement"],
                anchor_id=row["anchor_id"],
                page_index=row["page_index"],
                answer_count=row["answer_count"],
                last_answer_at=row["last_answer_at"],
            )
            for row in rows
        ]

    def create(self, request: ThreadIn) -> tuple[ThreadOut, bool]:
        """(대화, 새로 남겼는지). 같은 대화 ID를 다시 보내면 앞의 것을 준다."""
        with closing(connect(self._db_path)) as connection, connection:
            existing = repository.get_thread(connection, request.session_id)
            if existing is not None:
                return _thread_out(existing), False
            anchor = get_anchor(connection, request.anchor_id)
            version = anchor and documents.get_version(connection, anchor.version_id)
            if version is None or version.paper_id != request.paper_id:
                raise NotFound()
            saved = answers.list_answers(connection, 1, paper_id=request.paper_id, chat_session=request.session_id, origin="claude_code")
            if not saved:
                raise UnknownSession()
            repository.insert_thread(
                connection, request.session_id, request.paper_id, request.anchor_id, request.kind, request.title, utc_now()
            )
            return _thread_out(repository.get_thread(connection, request.session_id)), True

    def list(self, paper_id: str) -> list[ThreadOut]:
        with closing(connect(self._db_path)) as connection:
            return [_thread_out(row) for row in repository.list_threads(connection, paper_id)]

    def set_placement(self, session: str, placement: Placement) -> ThreadOut:
        with closing(connect(self._db_path)) as connection, connection:
            if repository.get_thread(connection, session) is None:
                raise NotFound()
            repository.set_placement(connection, session, placement, utc_now())
            return _thread_out(repository.get_thread(connection, session))

    def delete(self, session: str) -> None:
        with closing(connect(self._db_path)) as connection, connection:
            if repository.get_thread(connection, session) is None:
                raise NotFound()
            repository.delete_thread(connection, session, utc_now())

    # 사이드바 대화 (2026-10-02 사용자 요청) ---------------------------------------------

    def titles(self, paper_id: str) -> "list[SessionTitle]":  # 문자열: 이 클래스의 list 메서드가 내장 list를 가린다
        with closing(connect(self._db_path)) as connection:
            return [
                SessionTitle(
                    session_id=row["chat_session"], title=row["title"], parent_session_id=row["parent_session"], fork_answer_id=row["fork_answer_id"]
                )
                for row in repository.list_titles(connection, paper_id)
            ]

    def rename(self, session: str, request: SessionTitleIn) -> SessionTitle:
        """그 논문에 대해 버리지 않은 답이 있는 대화만 이름을 바꾼다."""
        with closing(connect(self._db_path)) as connection, connection:
            if not answers.list_answers(connection, 1, paper_id=request.paper_id, chat_session=session, origin="claude_code"):
                raise NotFound()
            repository.set_title(connection, session, request.paper_id, request.title, utc_now())
        return SessionTitle(session_id=session, title=request.title)

    def record_fork(self, session: str, request: ForkIn) -> SessionTitle:
        """갈래와 원래 대화 모두 그 논문에 대해 버리지 않은 답이 있어야 한다."""
        with closing(connect(self._db_path)) as connection, connection:
            for wanted in (session, request.parent_session_id):
                if not answers.list_answers(connection, 1, paper_id=request.paper_id, chat_session=wanted, origin="claude_code"):
                    raise NotFound()
            repository.set_fork(
                connection, session, request.paper_id, request.parent_session_id, request.title, utc_now(), request.fork_answer_id
            )
        return SessionTitle(
            session_id=session, title=request.title, parent_session_id=request.parent_session_id, fork_answer_id=request.fork_answer_id
        )

    def delete_session(self, session: str) -> None:
        """버리지 않은 답이 남은 대화만 지운다. 답을 모두 버리고 대화 기록·이름도 지운다."""
        with closing(connect(self._db_path)) as connection, connection:
            if not answers.list_answers(connection, 1, chat_session=session, origin="claude_code"):
                raise NotFound()
            repository.delete_session(connection, session, utc_now())


def _thread_out(row) -> ThreadOut:
    return ThreadOut(
        session_id=row["chat_session"],
        paper_id=row["paper_id"],
        anchor=anchor_from_row(row),
        kind=row["thread_kind"],
        title=row["title"],
        placement=row["placement"],
        answer_count=row["answer_count"],
        last_answer_at=row["last_answer_at"],
        created_at=row["thread_created_at"],
        updated_at=row["updated_at"],
    )
