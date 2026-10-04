"""웹앱이 쓰는 답변 REST (IMPL §8, §11.1): 답변 목록과 버리기, Claude Code 대화 답변 저장(ADR 0003).

대화 답변은 이 PC의 브리지가 loopback 웹 REST로 보낸다(다른 웹 REST와
같은 로컬 경계, IMPL §3). 전달하지 않은(PREPARED)·버린(CANCELLED) packet에는 저장하지 않는다.
"""

from typing import Annotated

from fastapi import APIRouter, Query, Response

from paperloom.answers.models import AnswerList, AnswerOut, ChatAnswerIn, Origin
from paperloom.answers.service import MAX_LIST, AnswerService
from paperloom.api.errors import NOT_FOUND_MESSAGE, ApiError


def build_router(service: AnswerService) -> APIRouter:
    router = APIRouter(prefix="/api/v1")

    @router.get("/answers")
    def list_answers(
        packet_id: str | None = None,
        paper_id: str | None = None,
        session_id: str | None = None,
        origin: Origin | None = None,
        limit: Annotated[int, Query(ge=1, le=MAX_LIST)] = 20,
    ) -> AnswerList:
        """paper_id: 그 논문을 출처로 둔 packet의 답변(Reader 대화 탭의 대화 목록). session_id: 한 대화."""
        return AnswerList(answers=service.list(packet_id, limit, paper_id=paper_id, session_id=session_id, origin=origin))

    @router.post("/context-packets/{packet_id}/answers", status_code=201)
    def save_chat_answer(packet_id: str, body: ChatAnswerIn, response: Response) -> AnswerOut:
        """같은 질문·같은 내용을 다시 보내면 앞의 답변을 200으로 준다."""
        status = service.packet_status(packet_id)
        if status is None:
            raise ApiError(404, "NOT_FOUND", NOT_FOUND_MESSAGE)
        if status in ("PREPARED", "CANCELLED"):
            raise ApiError(409, "INVALID_TRANSITION", f"{status} 상태의 문맥에는 답변을 저장할 수 없습니다.", details={"status": status})
        answer, created = service.save(
            packet_id, body.markdown, origin="claude_code", prompt=body.prompt, chat_session=body.session_id,
            context=(body.context_tokens, body.context_window),
            message_id=body.message_id,
        )
        response.status_code = 201 if created else 200
        return answer

    @router.delete("/answers/{answer_id}")
    def discard_answer(answer_id: str) -> AnswerOut:
        answer = service.discard(answer_id)
        if answer is None:
            raise ApiError(404, "NOT_FOUND", NOT_FOUND_MESSAGE)
        return answer

    return router
