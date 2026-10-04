"""쪽 번역 REST (U7, IMPL §8). 저장은 이 PC의 Claude Code 브리지가 번역을 검사한 뒤 부르고, 웹은 읽는다."""

from fastapi import APIRouter, Response

from paperloom.api.errors import NOT_FOUND_MESSAGE, ApiError
from paperloom.translation.models import Language, PageTranslationIn, PageTranslationOut, TranslatedPages
from paperloom.translation.service import InvalidTranslation, PageNotFound, TextNotReady, TranslationService


def build_router(service: TranslationService) -> APIRouter:
    router = APIRouter(prefix="/api/v1")

    @router.get("/versions/{version_id}/pages/{page_index}/translations/{language}")
    def get_translation(version_id: str, page_index: int, language: Language) -> PageTranslationOut:
        found = _call(lambda: service.get(version_id, page_index, language))
        if found is None:
            raise ApiError(404, "NOT_TRANSLATED", "이 쪽은 아직 번역하지 않았습니다.")
        return found

    @router.put("/versions/{version_id}/pages/{page_index}/translations/{language}")
    def put_translation(version_id: str, page_index: int, language: Language, body: PageTranslationIn) -> PageTranslationOut:
        return _call(lambda: service.put(version_id, page_index, language, body))

    @router.get("/versions/{version_id}/translations/{language}")
    def translated_pages(version_id: str, language: Language) -> TranslatedPages:
        return _call(lambda: service.pages(version_id, language))

    @router.delete("/versions/{version_id}/translations/{language}", status_code=204)
    def delete_translations(version_id: str, language: Language) -> Response:
        _call(lambda: service.delete(version_id, language))
        return Response(status_code=204)

    return router


def _call(action):
    try:
        return action()
    except PageNotFound:
        raise ApiError(404, "NOT_FOUND", NOT_FOUND_MESSAGE) from None
    except TextNotReady:
        raise ApiError(409, "TEXT_NOT_READY", "이 버전의 본문 추출이 아직 끝나지 않았습니다.", retryable=True) from None
    except InvalidTranslation as invalid:
        raise ApiError(422, "INVALID_TRANSLATION", invalid.message, details=invalid.details) from None
