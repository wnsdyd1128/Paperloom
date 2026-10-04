"""주석 REST 계약 (IMPL §4.1, §8). 수정·삭제는 클라이언트가 본 revision을 함께 보내야 한다."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt, model_validator

from paperloom.reading.models import AnchorOut

MAX_COMMENT_CHARS = 20_000
# 하이라이트 색 (U5): 웹의 --mark-c1(연한 주황)·c2(주황)·c3(회색). 없으면(None) 색 없는 주석이다.
HighlightColor = Literal["c1", "c2", "c3"]


class AnnotationIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    anchor_id: Annotated[str, Field(min_length=1, max_length=64)]
    comment: Annotated[str, Field(max_length=MAX_COMMENT_CHARS)] = ""  # 빈 메모는 강조 표시만 남긴다
    color: HighlightColor | None = None


class AnnotationPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    revision: Annotated[StrictInt, Field(ge=1)]  # 클라이언트가 본 현재 revision. 다르면 409
    # 보낸 것만 바꾼다. color를 null로 보내면 색을 뺀다(메모 주석으로 남는다).
    comment: Annotated[str, Field(max_length=MAX_COMMENT_CHARS)] | None = None
    color: HighlightColor | None = None

    @model_validator(mode="after")
    def _changes_something(self) -> "AnnotationPatch":
        if "comment" not in self.model_fields_set and "color" not in self.model_fields_set:
            raise ValueError("comment나 color 가운데 하나는 보내야 합니다.")
        if "comment" in self.model_fields_set and self.comment is None:
            raise ValueError("comment는 null일 수 없습니다.")
        return self


class AnnotationOut(BaseModel):
    annotation_id: str
    anchor: AnchorOut
    comment: str
    color: HighlightColor | None
    revision: int
    created_at: str
    updated_at: str


class AnnotationList(BaseModel):
    annotations: list[AnnotationOut]
