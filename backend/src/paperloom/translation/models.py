"""쪽 번역 계약 (U7, IMPL §8). 번역은 쪽의 문단마다, 문단을 나눈 문장(documents.sentences)마다 하나다."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

Language = Literal["ko", "en"]  # 설정의 답변·번역 언어 (U6, D4)

# 문장 하나의 번역 글자 수 한도. 원문 한 문장보다 훨씬 길면 응답이 깨진 것이다.
MAX_SENTENCE_CHARS = 5_000


class TranslatedBlockIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    block_id: str = Field(min_length=1, max_length=100)
    # 원문을 나눈 문장마다 번역 하나. 빈 글은 앞 문장의 번역에 합쳤다는 뜻이다(어순 때문에 두 문장을 한 문장으로 옮길 때).
    sentences: list[Annotated[str, Field(max_length=MAX_SENTENCE_CHARS)]] = Field(min_length=1, max_length=500)


class PageTranslationIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model: str | None = Field(default=None, max_length=50)  # 번역한 Claude 모델(설정의 기본 모델, D9)
    blocks: list[TranslatedBlockIn] = Field(min_length=1, max_length=2_000)


class TranslatedSentence(BaseModel):
    start: int  # 원문 문장의 [start, end) 글자 위치(그 문단 text 안)
    end: int
    text: str  # 번역. 빈 글이면 앞 문장과 합쳐 옮겼다


class TranslatedBlockOut(BaseModel):
    block_id: str  # 지금 추출의 문단 ID
    sentences: list[TranslatedSentence]


class PageTranslationOut(BaseModel):
    version_id: str
    page_index: int
    language: Language
    model: str | None
    created_at: str
    blocks: list[TranslatedBlockOut]  # 읽는 차례


class TranslatedPages(BaseModel):
    version_id: str
    language: Language
    pages: list[int]  # 번역을 저장한 쪽(다시 추출로 글이 바뀐 쪽도 들어 있을 수 있다)
