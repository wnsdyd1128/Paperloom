"""anchor.v1 REST 계약 (IMPL §4.1, §6.1–6.2, §10.6).

형식·범위(8개 수, 유한, 0~1, 길이 제한)는 여기서 선언하고, 모양(넓이·자기 교차)과 쪽 존재 여부는
서비스가 검사한다. 모르는 필드는 거부한다.

kind: `text`는 텍스트 선택(줄별 quad, 인용 필수), 나머지는 사용자가 끈 사각형 영역(quad 하나,
인용은 비어도 되고 첨자 추정 표기는 없다)이다.
"""

from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, StrictInt, model_validator

ANCHOR_SCHEMA_VERSION = "anchor.v1"
MAX_QUADS = 500  # 한 쪽 전체를 줄 단위로 선택해도 넉넉한 값
MAX_QUOTE_CHARS = 20_000
MAX_CONTEXT_CHARS = 500  # prefix·suffix

RegionKind = Literal["figure", "table", "equation", "generic"]
AnchorKind = Literal["text", "figure", "table", "equation", "generic"]

Coordinate = Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)]
Quad = Annotated[list[Coordinate], Field(min_length=8, max_length=8)]


class AnchorIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["anchor.v1"]
    kind: AnchorKind = "text"
    version_id: Annotated[str, Field(min_length=1, max_length=64)]
    page_index: Annotated[StrictInt, Field(ge=0)]
    quads: Annotated[list[Quad], Field(min_length=1, max_length=MAX_QUADS)]
    # 추출된 그대로의 인용. 첨자 추정 표기는 display_quote에만 둔다 (IMPL §5.4).
    quote: Annotated[str, Field(max_length=MAX_QUOTE_CHARS)]
    display_quote: Annotated[str | None, Field(max_length=MAX_QUOTE_CHARS)] = None
    prefix: Annotated[str, Field(max_length=MAX_CONTEXT_CHARS)] = ""
    suffix: Annotated[str, Field(max_length=MAX_CONTEXT_CHARS)] = ""

    @model_validator(mode="after")
    def check_kind(self) -> Self:
        if self.kind == "text":
            if not self.quote:
                raise ValueError("텍스트 위치에는 인용(quote)이 있어야 합니다.")
        elif len(self.quads) != 1 or self.display_quote is not None:
            raise ValueError("영역 위치는 quad 하나이고 첨자 추정 표기(display_quote)가 없어야 합니다.")
        return self


class AnchorKindPatch(BaseModel):
    """영역의 종류만 바꿀 수 있다. 위치·인용은 바꾸지 않는다."""

    model_config = ConfigDict(extra="forbid")

    kind: RegionKind


class FigureOut(BaseModel):
    """쪽의 그림 후보. box는 §6.1 정본 좌표 [u0, v0, u1, v1], source는 image·form·vector."""

    box: list[float]
    source: str


class FigureList(BaseModel):
    figures: list[FigureOut]


class AnchorOut(BaseModel):
    schema_version: str
    kind: str
    anchor_id: str
    version_id: str
    page_index: int
    quads: list[list[float]]
    quote: str
    display_quote: str | None
    prefix: str
    suffix: str
    created_at: str
