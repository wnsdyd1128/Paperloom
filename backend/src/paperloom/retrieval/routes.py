"""논문 제목 검색 REST (IMPL §8): GET /api/v1/search."""

from typing import Annotated

from fastapi import APIRouter, Query

from paperloom.api.errors import ApiError
from paperloom.retrieval.models import SearchResult
from paperloom.retrieval.service import SearchService


def build_router(service: SearchService) -> APIRouter:
    router = APIRouter(prefix="/api/v1")

    @router.get("/search")
    def search(
        q: Annotated[str, Query(max_length=1000, description="제목의 낱말(앞부분만 써도 됨) 또는 큰따옴표로 묶은 구절. 모두 들어 있는 제목을 찾는다")],
        limit: Annotated[int, Query(ge=1, le=50)] = 20,
    ) -> SearchResult:
        result = service.search(q, limit)
        if result is None:
            raise ApiError(422, "INVALID_QUERY", "검색어에 글자나 숫자가 있어야 합니다.")
        return result

    return router
