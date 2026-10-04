"""선택 설명·질문 대화 REST 계약 (docs/UI_PLAN.md A4).

Reader 선택 메뉴의 설명·번역·질문은 각각 따로 이어지는 Claude Code 대화다. 대화의 질문·답은 답변(answers)에 있고,
여기에는 그 대화가 어느 원문 위치에서 시작했는지와 화면 자리(원문 위·사이드바)만 남긴다.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from paperloom.answers.models import UUID_PATTERN
from paperloom.reading.models import AnchorOut

ThreadKind = Literal["explain", "translate", "ask"]
Placement = Literal["inline", "sidebar"]
MAX_TITLE_CHARS = 200


class ThreadIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str = Field(pattern=UUID_PATTERN)  # 브리지가 답을 저장한 대화 ID
    paper_id: str = Field(min_length=1, max_length=100)
    anchor_id: str = Field(min_length=1, max_length=100)
    kind: ThreadKind
    title: str = Field(max_length=MAX_TITLE_CHARS)

    @field_validator("title")
    @classmethod
    def _title_has_text(cls, title: str) -> str:
        return _clean_title(title)


class ThreadPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    placement: Placement


class ThreadOut(BaseModel):
    session_id: str
    paper_id: str
    anchor: AnchorOut
    kind: ThreadKind
    title: str
    placement: Placement
    answer_count: int  # 버리지 않은 차례 수
    last_answer_at: str | None
    created_at: str
    updated_at: str


class ThreadList(BaseModel):
    threads: list[ThreadOut]


class SessionTitleIn(BaseModel):
    """사이드바 대화의 새 이름 (2026-10-02 사용자 요청). 그 논문에 대해 저장된 대화만 받는다."""

    model_config = ConfigDict(extra="forbid")

    paper_id: str = Field(min_length=1, max_length=100)
    title: str = Field(max_length=MAX_TITLE_CHARS)

    @field_validator("title")
    @classmethod
    def _title_has_text(cls, title: str) -> str:
        return _clean_title(title)


class SessionTitle(BaseModel):
    session_id: str
    title: str
    parent_session_id: str | None = None  # 갈래면 갈라져 나온 대화
    fork_answer_id: str | None = None  # 그 대화의 이 답까지 이어받았다(없으면 갈래를 만든 때까지)


class ForkIn(BaseModel):
    """갈래 기록 (2026-10-02 사용자 요청). 브리지가 갈래의 첫 답을 저장한 뒤 웹이 보낸다."""

    model_config = ConfigDict(extra="forbid")

    paper_id: str = Field(min_length=1, max_length=100)
    parent_session_id: str = Field(pattern=UUID_PATTERN)
    title: str = Field(max_length=MAX_TITLE_CHARS)
    fork_answer_id: str | None = Field(default=None, min_length=1, max_length=100)  # 답에서 갈라졌으면 그 답

    @field_validator("title")
    @classmethod
    def _title_has_text(cls, title: str) -> str:
        return _clean_title(title)


class SessionTitleList(BaseModel):
    """이름이 있는 대화: 이름을 바꾼 사이드바 대화와 원문 위에서 시작한 대화. 나머지는 웹이 첫 질문으로 보인다."""

    sessions: list[SessionTitle]


class ConversationOut(BaseModel):
    """답변 화면의 대화 한 줄 (U6, 사용자 결정 D8). 사이드바 대화(chat)와 원문 위에서 시작한 대화(설명·번역·질문)."""

    session_id: str
    kind: Literal["chat", "explain", "translate", "ask"]
    title: str  # 바꾼 이름 → 원문 위 대화의 제목 → 첫 질문
    paper_id: str
    paper_title: str
    version_id: str  # 첫 차례 문맥의 버전
    placement: Placement | None  # 원문 위 대화의 자리. 사이드바 대화는 None
    anchor_id: str | None  # 원문 위 대화가 시작한 위치
    page_index: int | None
    answer_count: int  # 버리지 않은 차례 수
    last_answer_at: str


class ConversationList(BaseModel):
    conversations: list[ConversationOut]


def _clean_title(title: str) -> str:
    title = " ".join(title.split())
    if not title:
        raise ValueError("제목이 비어 있습니다.")
    return title
