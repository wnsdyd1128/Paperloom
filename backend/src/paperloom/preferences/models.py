"""사용자 설정 계약 (U6, UI_PLAN §5 U6·A2·A3, 사용자 결정 D2·D4·D7). 세 화면(기본·화면·프롬프트 개인화)의 값을 한 벌로 다룬다.

PUT은 모든 값을 보내 바꾼다(빠진 값은 422). 저장한 적이 없으면 DEFAULT_PREFERENCES다.
"""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from paperloom.context.models import DEFAULT_PAPER_TEXT_CHARS, PaperTextChars

MAX_PROMPT_CHARS = 2000
PromptText = Annotated[str, Field(max_length=MAX_PROMPT_CHARS)]


class PromptPreferences(BaseModel):
    """프롬프트 개인화 (A3). 브리지가 기본 규칙 뒤에 붙인다. 전체(system)는 모든 차례, 나머지는 그 종류의 요청에만."""

    model_config = ConfigDict(extra="forbid")

    system: PromptText
    explain: PromptText
    translate: PromptText
    summary: PromptText


class Preferences(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # 기본 설정. 화면 언어는 한국어로 고정한다(D4)
    answer_language: Literal["ko", "en"]
    default_model: Literal["sonnet", "opus", "haiku"]  # D7: 대화창에서 고르지 않으면 이 모델(처음은 sonnet)
    paper_text_chars: PaperTextChars  # D2: 논문 본문 범위의 글자 한도
    # 화면 설정
    theme: Literal["system", "light", "dark"]
    font_size: Annotated[int, Field(ge=12, le=20)]  # 설명·대화·번역 창의 글자 크기(px)
    translation_font_size: Annotated[int, Field(ge=12, le=24)] | None  # 번역 창만 따로(없으면 font_size)
    math_delimiters: Literal["bracket", "dollar", "none"]  # 수식·추정 표기를 복사할 때
    prompts: PromptPreferences


DEFAULT_PREFERENCES = Preferences(
    answer_language="ko",
    default_model="sonnet",
    paper_text_chars=DEFAULT_PAPER_TEXT_CHARS,
    theme="system",
    font_size=14,
    translation_font_size=None,
    math_delimiters="dollar",
    prompts=PromptPreferences(system="", explain="", translate="", summary=""),
)
