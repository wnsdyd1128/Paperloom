"""Evidence Bundle REST 계약 (docs/integration/paperloom/03-api-spec.md §3–§4). 모르는 필드는 거부한다.

여기서는 형식과 개수만 본다. 판본·Anchor·답변이 있는지, 서로 맞는지는 서비스가 본다.
"""

from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, StrictInt, field_validator, model_validator

MAX_PAPERS = 20
MAX_ANCHORS = 200
MAX_RANGES = 20
MAX_ANSWERS = 20
MAX_PROPOSALS = 20
MAX_TITLE_CHARS = 500
MAX_CONTENT_CHARS = 200_000
DEFAULT_LIST = 50
MAX_LIST = 200

Id = Annotated[str, Field(min_length=1, max_length=64)]
TextMode = Literal["none", "anchor_pages", "all", "ranges"]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PageRange(_Strict):
    """쪽 범위. 0부터, 양 끝 포함."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    start: StrictInt = Field(alias="from")
    to: StrictInt


class TextChoice(_Strict):
    # 기본은 고른 위치가 있는 쪽이다(요구사항 Q3). LLM Wiki 수신기는 2026-11-02부터 texts/를 받는다 (03-api-spec §7)
    mode: TextMode = Field(default="anchor_pages", description="none: 싣지 않음, anchor_pages: 고른 위치가 있는 쪽, all: 모든 쪽, ranges: ranges의 쪽")
    ranges: Annotated[list[PageRange], Field(max_length=MAX_RANGES)] = []

    @model_validator(mode="after")
    def _ranges_for_mode(self) -> Self:
        if self.mode == "ranges" and not self.ranges:
            raise ValueError("쪽 범위를 하나 이상 보내야 합니다.")
        return self


class PaperChoice(_Strict):
    version_id: Id
    anchor_ids: Annotated[list[Id], Field(max_length=MAX_ANCHORS)] = []
    include_comments: bool = True
    include_region_images: bool = False
    text: TextChoice = TextChoice()


class ProposalIn(_Strict):
    """Wiki 노트 후보 하나. 판본 하나에만 속한다."""

    version_id: Id
    title: Annotated[str, Field(min_length=1, max_length=MAX_TITLE_CHARS)]
    content_markdown: Annotated[str, Field(min_length=1, max_length=MAX_CONTENT_CHARS)]
    anchor_ids: Annotated[list[Id], Field(max_length=MAX_ANCHORS)] = []

    @field_validator("title", mode="before")
    @classmethod
    def _strip_title(cls, title: object) -> object:
        return title.strip() if isinstance(title, str) else title

    @field_validator("content_markdown")
    @classmethod
    def _content_has_text(cls, content: str) -> str:
        if not content.strip():
            raise ValueError("본문이 비어 있습니다.")
        return content


class BundleRequest(_Strict):
    """내보낼 논문·답변·제안. `/preview`와 만들기가 같은 본문을 받는다."""

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {
                    "papers": [{"version_id": "판본 ID", "anchor_ids": ["위치 ID"], "text": {"mode": "ranges", "ranges": [{"from": 0, "to": 2}]}}],
                    "proposals": [{"version_id": "판본 ID", "title": "노트 제목", "content_markdown": "# 노트 본문", "anchor_ids": ["위치 ID"]}],
                }
            ]
        },
    )

    papers: Annotated[list[PaperChoice], Field(min_length=1, max_length=MAX_PAPERS)]
    answer_ids: Annotated[list[Id], Field(max_length=MAX_ANSWERS)] = []
    proposals: Annotated[list[ProposalIn], Field(max_length=MAX_PROPOSALS)] = []


class BundleFilePreview(BaseModel):
    path: str
    kind: str  # manifest, sources, anchors, proposal, artifact, asset, text
    size_bytes: int


class AutoAddedAnchor(BaseModel):
    version_id: str
    anchor_id: str
    reason: Literal["cited_by_answer", "linked_by_proposal"]


class BundleWarning(BaseModel):
    code: str
    detail: str  # 화면에 그대로 보인다. 쪽 번호는 1부터다


class BundleLimits(BaseModel):
    max_files: int
    max_file_bytes: int
    max_total_bytes: int


class BundlePreview(BaseModel):
    file_count: int
    total_bytes: int
    files: list[BundleFilePreview]
    auto_added_anchors: list[AutoAddedAnchor]
    warnings: list[BundleWarning]
    limits: BundleLimits
    schema_version: str


class BundlePaper(BaseModel):
    paper_id: str
    version_id: str
    title: str


class BundleCounts(BaseModel):
    anchors: int
    proposals: int
    answers: int
    assets: int
    texts: int


class BundleOut(BaseModel):
    bundle_id: str
    directory: str
    status: Literal["written", "failed"]
    schema_version: str | None  # 실패한 기록은 None
    manifest_sha256: str | None
    file_count: int  # manifest 포함
    size_bytes: int
    papers: list[BundlePaper]
    counts: BundleCounts
    created_at: str


class BundleFileRecord(BaseModel):
    path: str
    sha256: str
    size_bytes: int


class BundleDetail(BundleOut):
    files: list[BundleFileRecord]
    error_code: str | None
    present_in_outbox: bool


class BundleListItem(BaseModel):
    bundle_id: str
    status: Literal["written", "failed"]
    created_at: str
    file_count: int
    size_bytes: int
    papers: list[BundlePaper]
    present_in_outbox: bool


class BundleList(BaseModel):
    bundles: list[BundleListItem]
