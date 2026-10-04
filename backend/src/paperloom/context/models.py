"""ContextPacket 계약 context-packet.v1 (IMPL §4.1·§7.2–7.3).

packet은 사용자가 고른 원문 위치(Anchor)와 그 주변 문단으로 만든 **불변 스냅샷**이다. 질문·의도·근거를 바꾸려면
새 packet을 만든다. 전달 상태(status)만 바뀐다. 모델을 호출하지 않는다.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

SCHEMA_VERSION = "context-packet.v1"

# 사용자가 고르는 요청 종류. 질문 문장은 사용자가 고칠 수 있다.
Intent = Literal["explain", "translate", "summarize", "ask"]
Role = Literal[
    "selected_text",
    "selected_region",
    "containing_paragraph",
    "previous_paragraph",
    "following_paragraph",
    "caption",  # 영역의 캡션 문단
    "region_text",  # 영역 안에서 추출한 글자
    "paper_text",  # 고른 위치 없이 논문에 물을 때의 본문(쪽마다, 앞쪽부터)
]
# IMPL §7.3. USER_CONFIRMED는 AI 호스트 공유를 허락함(W07, 2026-10-05에 MCP 공유를 빼 예전 packet에만 있다), IMPORTED는 답변을 받음.
Status = Literal["PREPARED", "USER_CONFIRMED", "HANDED_OFF", "IMPORTED", "CANCELLED"]
# 대화 범위 (docs/UI_PLAN.md U3): 고른 위치만(selection), 고른 위치 + 그 쪽 본문(page), 고른 위치 + 논문 본문(paper).
# until_page: 고른 위치 + 논문 앞쪽부터 page_index쪽까지와 참고문헌 쪽 (원문 위 설명·질문이 고른 쪽 다음 쪽으로 쓴다, 2026-10-04 사용자 요청).
# around_page: 고른 위치 + page_index쪽과 그 앞뒤 한 쪽, 참고문헌 쪽 (2026-10-02–04 원문 위 설명·질문. 저장된 packet용).
Scope = Literal["selection", "page", "paper", "until_page", "around_page"]
# 논문 본문 범위의 글자 한도. 설정에서 고른다(D2). 120,000자면 보통 20–30쪽 논문이 거의 다 들어간다.
PaperTextChars = Literal[12_000, 40_000, 120_000, 300_000]
DEFAULT_PAPER_TEXT_CHARS = 120_000


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PacketAnchor(_Strict):
    anchor_id: str = Field(min_length=1, max_length=100)
    include_context: bool = True  # 텍스트 선택이면 그것이 든 문단·앞뒤 문단을, 영역이면 캡션·영역 안 글자를 붙인다
    include_image: bool = True  # 영역, 수식 기미가 있는 글 선택이면 원문 이미지를 붙인다(packet당 최대 2개)


class ContextPacketIn(_Strict):
    intent: Intent
    question: str = Field(max_length=4000)
    anchors: list[PacketAnchor] = Field(default_factory=list, max_length=10)
    # 범위. 적지 않으면 예전 요청과 같다: 고른 위치만 주면 selection, 논문 버전만 주면 paper.
    scope: Scope | None = None
    # page·paper 범위가 본문을 읽을 논문 버전. 고른 위치와 함께 쓸 수 있다.
    version_id: str | None = Field(default=None, min_length=1, max_length=100)
    # page·around_page 범위의 쪽, until_page 범위의 마지막 쪽(넘으면 문서 끝까지)
    page_index: int | None = Field(default=None, ge=0)
    paper_text_chars: PaperTextChars | None = None  # paper·until_page·around_page 범위의 본문 한도. 없으면 DEFAULT_PAPER_TEXT_CHARS

    @field_validator("question")
    @classmethod
    def _question_has_text(cls, question: str) -> str:
        question = question.strip()
        if not question:
            raise ValueError("질문이 비어 있습니다.")
        return question

    @property
    def resolved_scope(self) -> Scope:
        return self.scope or ("paper" if self.version_id is not None else "selection")

    @model_validator(mode="after")
    def _scope_fits(self) -> "ContextPacketIn":
        if self.scope is None and bool(self.anchors) == (self.version_id is not None):
            raise ValueError("원문 위치(anchors)나 논문 버전(version_id) 가운데 하나만 주거나 범위(scope)를 정하세요.")
        scope = self.resolved_scope
        if scope == "selection" and (not self.anchors or self.version_id is not None):
            raise ValueError("고른 위치만 보내는 범위에는 원문 위치가 있어야 하고 논문 버전은 없어야 합니다.")
        if scope != "selection" and self.version_id is None:
            raise ValueError("쪽·논문 본문 범위에는 논문 버전(version_id)이 있어야 합니다.")
        if (scope in ("page", "until_page", "around_page")) != (self.page_index is not None):
            raise ValueError("쪽 번호(page_index)는 쪽·어느 쪽까지 범위에만, 그리고 반드시 줍니다.")
        if scope not in ("paper", "until_page", "around_page") and self.paper_text_chars is not None:
            raise ValueError("본문 한도(paper_text_chars)는 논문 본문·어느 쪽까지 범위에만 줍니다.")
        ids = [anchor.anchor_id for anchor in self.anchors]
        if len(set(ids)) != len(ids):
            raise ValueError("같은 원문 위치를 두 번 넣었습니다.")
        return self


class ImageRef(BaseModel):
    """영역 이미지. 바이트는 packet에 넣지 않고 Anchor 영역 이미지 주소로 가리킨다(W04a)."""

    url: str
    scale: float


class Evidence(BaseModel):
    evidence_id: str  # packet 안의 번호 e1, e2 …
    role: Role
    source_ref: str
    version_id: str
    page_index: int
    anchor_id: str  # 선택이면 그 위치, 주변 문단·캡션·영역 안 글자면 그것이 딸린 위치. 논문 본문(paper_text)이면 빈 글
    kind: str | None  # 영역 종류(figure·table·equation·generic). 텍스트 선택과 그 주변 문단이면 None
    text: str  # 선택은 추출된 원문 인용(quote), 문단은 서버 추출 텍스트
    display_text: str | None  # 첨자·분수 추정 표기(IMPL §5.4). 추정이다
    truncated: bool
    regions: list[list[float]]  # 정본 좌표 상자 [u0, v0, u1, v1] (선택은 quad마다, 문단은 줄마다)
    block_id: str | None  # 문단의 추출 블록. 다시 추출해도 같은 쪽에 글이 같으면 그대로다(바뀐 문단이면 쪽만 연다)
    # 논문 본문(paper_text) 근거의 문단마다 추출 블록(¶1부터, 글의 빈 줄로 나뉜 문단 차례). 그 밖에는 빈 목록
    block_ids: list[str] = Field(default_factory=list)
    # 이 근거가 든 논문의 절(본문 제목 경로, documents.headings.section_paths). 논문 본문(paper_text)이면 그 쪽이 앞 쪽의 절에서
    # 이어질 때 그 절(쪽이 제목으로 시작하면 없다). 모르면 None (2026-10-04 사용자 요청)
    section: str | None = None
    image: ImageRef | None
    text_status: str | None  # 그 쪽의 본문 추출 상태. None이면 아직 추출 전
    quality_flags: list[str]


class Source(BaseModel):
    source_ref: str
    paper_id: str
    title: str
    version_id: str
    sha256: str


class Excluded(BaseModel):
    role: Role | Literal["context"]
    anchor_id: str
    page_index: int | None
    # text_budget(글자 한도), image_limit(이미지 한도), text_not_extracted(본문 추출 전·실패),
    # no_extracted_text(그 자리에 추출된 글이 없음, 이미지뿐인 쪽 등)
    reason: str


class Limits(BaseModel):
    max_text_chars: int
    used_text_chars: int
    max_images: int
    used_images: int
    truncated: bool  # 글자 한도로 자르거나 뺀 근거가 있음
    excluded: list[Excluded]


class PacketContent(BaseModel):
    """내용 해시(content_sha256)를 계산하는 부분. 만든 뒤 바뀌지 않는다."""

    schema_version: Literal["context-packet.v1"] = SCHEMA_VERSION
    intent: Intent
    question: str
    evidence: list[Evidence]
    sources: list[Source]
    limits: Limits
    # 범위와 그 쪽 (2026-10-02 U3부터). 그 전에 만든 packet은 None이다(내용 해시는 만들 때 한 번만 계산한다).
    scope: Scope | None = None
    scope_page: int | None = None


class ContextPacketOut(PacketContent):
    packet_id: str
    created_at: str
    content_sha256: str
    status: Status
    handed_off_at: str | None = None
    # mcp: 공유된 packet을 호스트가 읽음 (W07, 2026-10-05에 뺐다 — 예전 packet). claude_code: Reader 대화 탭에서 이 PC의 Claude Code에 보냄 (ADR 0003)
    handoff_method: Literal["clipboard", "file", "mcp", "claude_code"] | None = None
    cancelled_at: str | None = None


class PacketStatusPatch(_Strict):
    """전달 상태 바꾸기. 복사·파일 내보내기·대화 탭에서 묻기는 HANDED_OFF(사용자가 확인하고 직접 전달), 버리기는 CANCELLED."""

    status: Literal["HANDED_OFF", "CANCELLED"]
    handoff_method: Literal["clipboard", "file", "claude_code"] | None = None

    @model_validator(mode="after")
    def _method_matches_status(self) -> "PacketStatusPatch":
        if (self.status == "HANDED_OFF") != (self.handoff_method is not None):
            raise ValueError("HANDED_OFF에는 handoff_method가 필요하고, CANCELLED에는 없어야 합니다.")
        return self
