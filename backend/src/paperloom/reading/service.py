"""원문 위치(Anchor) 저장·조회·영역 이미지 (IMPL §6.2–6.3, §10.6).

Anchor는 한 SourceVersion의 한 쪽에 속하고, 위치(쪽·quad)와 인용은 만든 뒤 바꾸지 않는다. 영역의
종류(그림·표·수식·영역)만 바꿀 수 있다. 서버는 형식 검사(models) 뒤에 쪽 존재 여부와 quad 모양을 검사한다.
"""

import uuid
from contextlib import closing
from pathlib import Path

from paperloom.documents import repository as documents
from paperloom.infrastructure.clock import utc_now
from paperloom.infrastructure.database.sqlite import connect
from paperloom.infrastructure.files.source_store import SourceStore
from paperloom.reading import repository
from paperloom.reading.figures import Figure, find_figures
from paperloom.reading.geometry import quad_shape_problem
from paperloom.reading.models import AnchorIn, AnchorOut
from paperloom.reading.region_image import render_region

_FIGURE_CACHE_LIMIT = 512  # (버전, 쪽) 수. SourceVersion은 바뀌지 않으므로 결과도 바뀌지 않는다.
TEXT_PAD_LINES = 0.5  # 글 Anchor 이미지의 위아래 여백(줄 높이 배)
TEXT_PAD_U = 0.01  # 글 Anchor 이미지의 좌우 여백(쪽 폭 비율)


class VersionNotFound(Exception):
    pass


class InvalidAnchor(Exception):
    def __init__(self, message: str, details: dict) -> None:
        super().__init__(message)
        self.message = message
        self.details = details


class AnchorService:
    def __init__(self, db_path: Path, store: SourceStore, render_timeout_seconds: float = 30) -> None:
        self._db_path = db_path
        self._store = store
        self._render_timeout_seconds = render_timeout_seconds
        self._figure_cache: dict[tuple[str, int], list[Figure]] = {}

    def create(self, request: AnchorIn) -> AnchorOut:
        with closing(connect(self._db_path)) as connection:
            version = documents.get_version(connection, request.version_id)
            if version is None:
                raise VersionNotFound()
            if request.page_index >= version.page_count:
                raise InvalidAnchor(
                    "page_index가 문서의 쪽 범위를 벗어났습니다.",
                    {"field": "page_index", "page_count": version.page_count},
                )
            for index, quad in enumerate(request.quads):
                if problem := quad_shape_problem(quad):
                    raise InvalidAnchor(problem, {"field": "quads", "index": index})
            anchor = AnchorOut(anchor_id=str(uuid.uuid4()), created_at=utc_now(), **request.model_dump())
            with connection:
                repository.insert_anchor(connection, anchor)
        return anchor

    def get(self, anchor_id: str) -> AnchorOut | None:
        with closing(connect(self._db_path)) as connection:
            anchor = repository.get_anchor(connection, anchor_id)
            # 소유 범위 밖(다른 사용자의 버전)은 없는 것과 같게 다룬다.
            if anchor is None or documents.get_version(connection, anchor.version_id) is None:
                return None
            return anchor

    def change_kind(self, anchor_id: str, kind: str) -> AnchorOut | None:
        """영역의 종류를 바꾼다. 없으면 None, 텍스트 위치면 InvalidAnchor."""
        anchor = self.get(anchor_id)
        if anchor is None:
            return None
        if anchor.kind == "text":
            raise InvalidAnchor("텍스트 선택 위치의 종류는 바꿀 수 없습니다.", {"field": "kind"})
        with closing(connect(self._db_path)) as connection:
            with connection:
                repository.update_kind(connection, anchor_id, kind)
        return anchor.model_copy(update={"kind": kind})

    def _source_path(self, version_id: str, page_index: int) -> Path | None:
        """버전 원본 PDF의 경로. 버전이 없거나 쪽이 범위 밖이면 None."""
        with closing(connect(self._db_path)) as connection:
            version = documents.get_version(connection, version_id)
            storage_ref = documents.get_storage_ref(connection, version_id) if version else None
        if version is None or storage_ref is None or not 0 <= page_index < version.page_count:
            return None
        return self._store.path_for(storage_ref)

    def figures(self, version_id: str, page_index: int) -> list[Figure] | None:
        """쪽의 그림 후보. 버전이나 쪽이 없으면 None. 실패하면 FiguresFailed."""
        key = (version_id, page_index)
        if key in self._figure_cache:
            return self._figure_cache[key]
        path = self._source_path(version_id, page_index)
        if path is None:
            return None
        figures = find_figures(path, page_index, self._render_timeout_seconds)
        if len(self._figure_cache) >= _FIGURE_CACHE_LIMIT:
            self._figure_cache.clear()
        self._figure_cache[key] = figures
        return figures

    def image(self, anchor_id: str, scale: float) -> bytes | None:
        """Anchor quad들을 감싸는 영역의 PNG (화면에 보이는 방향). 없으면 None. 실패하면 RenderFailed."""
        anchor = self.get(anchor_id)
        if anchor is None:
            return None
        us = [value for quad in anchor.quads for value in quad[0::2]]
        vs = [value for quad in anchor.quads for value in quad[1::2]]
        box = (min(us), min(vs), max(us), max(vs))
        if anchor.kind == "text":
            # 글 선택(수식)은 줄 상자 밖으로 나온 괄호·분수선·첨자까지 담도록 위아래로 줄 높이의 절반, 좌우로 쪽 폭의 1%를 넓힌다.
            pad_v = TEXT_PAD_LINES * max(max(quad[1::2]) - min(quad[1::2]) for quad in anchor.quads)
            box = (max(0.0, box[0] - TEXT_PAD_U), max(0.0, box[1] - pad_v), min(1.0, box[2] + TEXT_PAD_U), min(1.0, box[3] + pad_v))
        return self.page_image(anchor.version_id, anchor.page_index, box, scale)

    def page_image(self, version_id: str, page_index: int, box: tuple[float, float, float, float], scale: float) -> bytes | None:
        """쪽의 정본 좌표 상자(u0, v0, u1, v1) 영역의 PNG. 저장하지 않은 선택(그림 복사)에 쓴다.
        버전·쪽이 없으면 None. 실패하면 RenderFailed."""
        path = self._source_path(version_id, page_index)
        if path is None:
            return None
        return render_region(path, page_index, box, scale, self._render_timeout_seconds)
