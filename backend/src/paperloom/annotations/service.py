"""주석 만들기·수정·삭제 (IMPL §8).

수정과 삭제는 기대 revision이 현재 값과 같을 때만 한 문장(UPDATE/DELETE … WHERE revision = ?)으로
적용한다. 다르면 현재 revision을 알려 주고 거부한다. 주석을 지워도 Anchor는 남는다(다른 문맥이 참조할 수 있다).
"""

import uuid
from contextlib import closing
from pathlib import Path

from paperloom.annotations import repository
from paperloom.annotations.models import AnnotationIn, AnnotationOut, AnnotationPatch
from paperloom.documents import repository as documents
from paperloom.infrastructure.clock import utc_now
from paperloom.infrastructure.database.sqlite import connect
from paperloom.reading.service import AnchorService


class NotFound(Exception):
    pass


class RevisionConflict(Exception):
    def __init__(self, current_revision: int) -> None:
        super().__init__(current_revision)
        self.current_revision = current_revision


class AnnotationService:
    def __init__(self, db_path: Path, anchors: AnchorService) -> None:
        self._db_path = db_path
        self._anchors = anchors

    def create(self, request: AnnotationIn) -> AnnotationOut:
        if self._anchors.get(request.anchor_id) is None:
            raise NotFound()
        annotation_id = str(uuid.uuid4())
        with closing(connect(self._db_path)) as connection:
            with connection:
                repository.insert_annotation(
                    connection,
                    annotation_id=annotation_id,
                    anchor_id=request.anchor_id,
                    comment=request.comment,
                    color=request.color,
                    now=utc_now(),
                )
            return self._get(connection, annotation_id)

    def list_for_version(self, version_id: str) -> list[AnnotationOut]:
        with closing(connect(self._db_path)) as connection:
            if documents.get_version(connection, version_id) is None:
                raise NotFound()
            return repository.list_for_version(connection, version_id)

    def update(self, annotation_id: str, patch: AnnotationPatch) -> AnnotationOut:
        with closing(connect(self._db_path)) as connection:
            with connection:
                updated = repository.update_annotation(
                    connection,
                    annotation_id=annotation_id,
                    expected_revision=patch.revision,
                    changes=patch.model_dump(include={"comment", "color"} & patch.model_fields_set),
                    now=utc_now(),
                )
            if not updated:
                self._raise_missing_or_conflict(connection, annotation_id)
            return self._get(connection, annotation_id)

    def delete(self, annotation_id: str, expected_revision: int) -> None:
        with closing(connect(self._db_path)) as connection:
            with connection:
                deleted = repository.delete_annotation(
                    connection, annotation_id=annotation_id, expected_revision=expected_revision
                )
            if not deleted:
                self._raise_missing_or_conflict(connection, annotation_id)

    @staticmethod
    def _get(connection, annotation_id: str) -> AnnotationOut:
        annotation = repository.get_annotation(connection, annotation_id)
        if annotation is None:  # 방금 바꾼 뒤 다른 요청이 지운 경우
            raise NotFound()
        return annotation

    @staticmethod
    def _raise_missing_or_conflict(connection, annotation_id: str):
        current = repository.get_annotation(connection, annotation_id)
        if current is None:
            raise NotFound()
        raise RevisionConflict(current.revision)
