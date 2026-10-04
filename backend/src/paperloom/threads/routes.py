"""선택 설명·질문 대화 REST (IMPL §8, docs/UI_PLAN.md A4). 웹이 첫 답을 받은 뒤 대화를 남긴다."""

from typing import Annotated

from fastapi import APIRouter, Query, Response

from paperloom.api.errors import NOT_FOUND_MESSAGE, ApiError
from paperloom.threads.models import (
    ConversationList,
    ForkIn,
    SessionTitle,
    SessionTitleIn,
    SessionTitleList,
    ThreadIn,
    ThreadList,
    ThreadOut,
    ThreadPatch,
)
from paperloom.threads.service import NotFound, ThreadService, UnknownSession


def build_router(service: ThreadService) -> APIRouter:
    router = APIRouter(prefix="/api/v1")

    @router.get("/conversations")
    def list_conversations(limit: Annotated[int, Query(ge=1, le=200)] = 100) -> ConversationList:
        """모든 논문의 Claude Code 대화, 마지막 답이 최근인 것부터 (U6 답변 화면, 사용자 결정 D8)."""
        return ConversationList(conversations=service.conversations(limit))

    @router.get("/chat-threads")
    def list_threads(paper_id: str) -> ThreadList:
        return ThreadList(threads=service.list(paper_id))

    @router.post("/chat-threads", status_code=201)
    def create_thread(body: ThreadIn, response: Response) -> ThreadOut:
        """같은 대화 ID를 다시 보내면 앞의 것을 200으로 준다."""
        try:
            thread, created = service.create(body)
        except NotFound:
            raise ApiError(404, "NOT_FOUND", NOT_FOUND_MESSAGE) from None
        except UnknownSession:
            raise ApiError(409, "UNKNOWN_SESSION", "이 논문에 대해 저장된 대화가 아닙니다.") from None
        response.status_code = 201 if created else 200
        return thread

    @router.patch("/chat-threads/{session_id}")
    def move_thread(session_id: str, body: ThreadPatch) -> ThreadOut:
        try:
            return service.set_placement(session_id, body.placement)
        except NotFound:
            raise ApiError(404, "NOT_FOUND", NOT_FOUND_MESSAGE) from None

    @router.delete("/chat-threads/{session_id}", status_code=204)
    def delete_thread(session_id: str) -> Response:
        """대화를 지우고 그 대화의 답변을 버린다."""
        try:
            service.delete(session_id)
        except NotFound:
            raise ApiError(404, "NOT_FOUND", NOT_FOUND_MESSAGE) from None
        return Response(status_code=204)

    # 사이드바 "Claude와 대화"의 대화 이름 바꾸기·지우기 (2026-10-02 사용자 요청)
    @router.get("/chat-sessions")
    def list_session_titles(paper_id: str) -> SessionTitleList:
        return SessionTitleList(sessions=service.titles(paper_id))

    @router.put("/chat-sessions/{session_id}/title")
    def rename_session(session_id: str, body: SessionTitleIn) -> SessionTitle:
        try:
            return service.rename(session_id, body)
        except NotFound:
            raise ApiError(404, "NOT_FOUND", NOT_FOUND_MESSAGE) from None

    @router.put("/chat-sessions/{session_id}/fork")
    def record_fork(session_id: str, body: ForkIn) -> SessionTitle:
        """갈래가 갈라져 나온 대화와 이름을 남긴다(웹이 갈래의 첫 답을 받은 뒤)."""
        if body.parent_session_id == session_id:
            raise ApiError(422, "INVALID_REQUEST", "자기 자신에서 갈라질 수 없습니다.")
        try:
            return service.record_fork(session_id, body)
        except NotFound:
            raise ApiError(404, "NOT_FOUND", NOT_FOUND_MESSAGE) from None

    @router.delete("/chat-sessions/{session_id}", status_code=204)
    def delete_session(session_id: str) -> Response:
        """대화의 답을 모두 버리고 대화 기록·이름을 지운다."""
        try:
            service.delete_session(session_id)
        except NotFound:
            raise ApiError(404, "NOT_FOUND", NOT_FOUND_MESSAGE) from None
        return Response(status_code=204)

    return router
