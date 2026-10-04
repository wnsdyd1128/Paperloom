"""문맥 REST (IMPL §8): 만들기(재전송 방지 키), 조회, 전달 상태, Markdown·zip 내보내기. 모델을 호출하지 않는다."""

from typing import Annotated

from typing import Literal

from fastapi import APIRouter, Header, Request, Response

from paperloom.api.errors import NOT_FOUND_MESSAGE, ApiError
from paperloom.api.idempotency import IdempotencyStore
from paperloom.context.models import ContextPacketIn, ContextPacketOut, PacketStatusPatch
from paperloom.context.service import ContextService, InvalidPacket, InvalidTransition
from paperloom.reading.region_image import RenderFailed


def build_router(service: ContextService, keys: IdempotencyStore) -> APIRouter:
    router = APIRouter(prefix="/api/v1")

    @router.post("/context-packets", status_code=201, response_model=ContextPacketOut)
    def create_packet(request: ContextPacketIn, idempotency_key: Annotated[str | None, Header()] = None) -> Response:
        def create() -> ContextPacketOut:
            try:
                return service.create(request)
            except InvalidPacket as invalid:
                raise ApiError(422, "INVALID_PACKET", invalid.message, details=invalid.details) from None

        return keys.respond("POST /api/v1/context-packets", idempotency_key, request, create)

    @router.get("/context-packets/{packet_id}")
    def get_packet(packet_id: str) -> ContextPacketOut:
        packet = service.get(packet_id)
        if packet is None:
            raise _not_found()
        return packet

    @router.patch("/context-packets/{packet_id}")
    def update_status(packet_id: str, patch: PacketStatusPatch) -> ContextPacketOut:
        try:
            packet = service.update_status(packet_id, patch)
        except InvalidTransition as invalid:
            raise _invalid_transition(invalid) from None
        if packet is None:
            raise _not_found()
        return packet

    @router.get("/context-packets/{packet_id}/export.md")
    def export_markdown(packet_id: str, request: Request, images: Literal["paste", "attached"] = "paste") -> Response:
        """images=attached: 이미지를 메시지에 함께 붙이는 Claude Code 대화 브리지용 안내 (ADR 0003)."""
        try:
            text = service.export_markdown(packet_id, str(request.base_url), images)
        except InvalidTransition as invalid:
            raise _invalid_transition(invalid) from None
        if text is None:
            raise _not_found()
        return Response(text, media_type="text/markdown; charset=utf-8", headers=_attachment(packet_id, "md"))

    @router.get("/context-packets/{packet_id}/export.zip")
    def export_zip(packet_id: str, request: Request) -> Response:
        try:
            data = service.export_zip(packet_id, str(request.base_url))
        except InvalidTransition as invalid:
            raise _invalid_transition(invalid) from None
        except RenderFailed:
            raise ApiError(503, "RESOURCE_LIMIT", "영역 이미지를 시간 안에 그리지 못했습니다.", retryable=True) from None
        if data is None:
            raise _not_found()
        return Response(data, media_type="application/zip", headers=_attachment(packet_id, "zip"))

    return router


def _attachment(packet_id: str, extension: str) -> dict[str, str]:
    return {"Content-Disposition": f'attachment; filename="paperloom-context-{packet_id[:8]}.{extension}"'}


def _invalid_transition(invalid: InvalidTransition) -> ApiError:
    return ApiError(
        409, "INVALID_TRANSITION", f"{invalid.status} 상태의 문맥은 바꾸거나 내보낼 수 없습니다.", details={"status": invalid.status}
    )


def _not_found() -> ApiError:
    return ApiError(404, "NOT_FOUND", NOT_FOUND_MESSAGE)
