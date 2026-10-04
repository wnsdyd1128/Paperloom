"""사용자 설정 REST (U6, IMPL §8): GET은 저장한 값(없으면 기본값), PUT은 모든 값을 받아 바꾼다."""

from fastapi import APIRouter

from paperloom.preferences.models import Preferences
from paperloom.preferences.service import PreferenceService


def build_router(service: PreferenceService) -> APIRouter:
    router = APIRouter(prefix="/api/v1")

    @router.get("/settings")
    def get_settings() -> Preferences:
        return service.get()

    @router.put("/settings")
    def put_settings(preferences: Preferences) -> Preferences:
        return service.put(preferences)

    return router
