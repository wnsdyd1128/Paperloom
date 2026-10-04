"""AI가 쓴 답변 AnswerArtifact (IMPL §11.1, ADR 0002·0003).

출처는 둘이다. host_mcp: Claude Desktop이 MCP 도구로 저장(ADR 0002, 2026-10-05에 MCP를 빼 예전 답변만). claude_code: Reader의 Claude 대화 탭에서
이 PC의 Claude Code 브리지가 저장(ADR 0003, 차례마다 질문과 대화 ID가 있다).
답변은 packet 하나에 딸리고 검토 전(unreviewed)으로 들어온다. 연구 사실이나 Wiki 노트로 자동 승격하지 않는다.
본문은 모델이 쓴 Markdown을 그대로 보관한다. 웹은 HTML로 해석하지 않고 글자로만 보인다(PLAN A08).
근거 번호 [n]은 저장할 때 packet 근거와 맞추고, packet에 없는 번호는 unresolved_citations로 따로 둔다.
번호가 맞는다는 것은 주장이 그 근거로 뒷받침된다는 뜻이 아니다.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from paperloom.context.models import Role, Scope

MAX_ANSWER_CHARS = 50_000
MAX_PROMPT_CHARS = 4000
Origin = Literal["host_mcp", "claude_code"]
UUID_PATTERN = r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"


class AnswerIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    markdown: str = Field(max_length=MAX_ANSWER_CHARS)

    @field_validator("markdown")
    @classmethod
    def _markdown_has_text(cls, markdown: str) -> str:
        markdown = markdown.replace("\r\n", "\n").strip()
        if not markdown:
            raise ValueError("답변이 비어 있습니다.")
        if "\x00" in markdown:
            raise ValueError("답변에 쓸 수 없는 문자가 있습니다.")
        return markdown


class ChatAnswerIn(AnswerIn):
    """Claude Code 대화의 한 차례 답변 (브리지가 보낸다). 이어 묻기에 쓸 대화 ID를 함께 남긴다."""

    prompt: str = Field(min_length=1, max_length=MAX_PROMPT_CHARS)
    session_id: str = Field(pattern=UUID_PATTERN)
    # 차례가 끝난 때 그 대화의 컨텍스트 길이(입력·캐시·출력 토큰)와 모델의 창 크기. 브리지가 모르면 없다
    context_tokens: int | None = Field(default=None, ge=0)
    context_window: int | None = Field(default=None, ge=1)
    # 차례 끝 Claude Code 메시지 ID. 이 답에서 갈라질 때 --resume-session-at에 쓴다
    message_id: str | None = Field(default=None, min_length=1, max_length=100)


class Citation(BaseModel):
    """답변의 [근거 number¶paragraph]가 가리키는 packet 근거와 그 원문 위치. 문단을 짚었으면 block_id는 그 문단이다."""

    number: int
    paragraph: int | None = None  # 논문 본문 근거의 문단(¶, 1부터). 짚지 않았거나 없는 문단이면 None
    evidence_id: str
    role: Role
    page_index: int
    paper_id: str
    version_id: str
    anchor_id: str
    block_id: str | None


class AnswerContext(BaseModel):
    """답변이 딸린 packet에서 사용자가 고른 위치. 대화에서 질문 위에 인용으로 보인다."""

    kind: str  # text, 또는 영역 종류(figure·table·equation·generic)
    page_index: int
    text: str  # 고른 글(앞부분, 첨자 추정 표기가 있으면 그것). 영역이면 빈 글
    anchor_id: str
    image_url: str | None  # 영역 이미지를 넣었으면 그 주소


class AnswerOut(BaseModel):
    answer_id: str
    packet_id: str
    origin: Origin
    connection_name: str | None  # host_mcp면 저장한 연결의 이름
    prompt: str | None  # claude_code: 이 차례의 질문
    session_id: str | None  # claude_code: 이어 묻기에 쓰는 대화 ID
    markdown: str
    content_sha256: str
    citations: list[Citation]
    unresolved_citations: list[int]  # packet에 없는 근거 번호
    review_status: Literal["unreviewed"]
    created_at: str
    discarded_at: str | None
    question: str  # packet의 질문
    paper_titles: list[str]
    context: list[AnswerContext]  # packet에서 고른 위치들
    # packet의 대화 범위와 그 쪽 (U3 전 packet은 None). 대화 패널이 본문을 다시 보낼지 정한다
    scope: Scope | None = None
    scope_page: int | None = None
    # claude_code: 이 차례가 끝난 때의 컨텍스트 길이와 창 크기 (2026-10-02, 그 전 답은 None)
    context_tokens: int | None = None
    context_window: int | None = None
    message_id: str | None = None  # claude_code: 이 답에서 갈라질 자리(그 전 답은 None)


class AnswerList(BaseModel):
    answers: list[AnswerOut]
