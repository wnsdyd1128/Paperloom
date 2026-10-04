"""Library REST 응답 계약 (IMPL §4.1). 저장 경로(`storage_ref`)와 `owner_id`는 노출하지 않는다."""

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator

from paperloom.documents.metadata import DOI_PATTERN


class SourceVersionOut(BaseModel):
    version_id: str
    sha256: str
    size_bytes: int
    page_count: int
    # IMPL §5.2 상태: READY_TO_READ(본문 추출 전) → PARSING → INDEXED | PARTIAL | FAILED. 어느 상태든 원본은 읽을 수 있다.
    status: str
    # FAILED의 이유: NO_TEXT_LAYER, RESOURCE_LIMIT, PARSER_ERROR, PASSWORD_REQUIRED, MALFORMED_PDF
    status_reason: str | None = None
    created_at: str


class VersionOut(SourceVersionOut):
    """버전 고정 링크(IMPL §4.3)가 버전이 어느 논문에 속하는지 확인하는 데 쓴다."""

    paper_id: str


class PaperOut(BaseModel):
    paper_id: str
    title: str
    authors: list[str]
    year: int | None
    doi: str | None
    created_at: str
    current_version: SourceVersionOut
    # 서재 표 (U6)
    tags: list[str]  # 이름 차례
    last_opened_at: str | None  # Reader로 마지막에 연 때. 연 적이 없으면 None
    annotation_count: int  # 모든 버전의 주석 수
    conversation_count: int  # 이 논문을 출처로 둔 Claude Code 대화 수(답을 모두 버린 대화는 빼고)


class PaperList(BaseModel):
    papers: list[PaperOut]


MAX_TAGS = 20
MAX_TAG_CHARS = 40


class PaperTagsIn(BaseModel):
    """논문의 태그를 이 목록으로 바꾼다 (U6). 앞뒤 빈칸은 지우고, 대소문자만 다른 이름은 같은 태그다."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    tags: list[Annotated[str, Field(min_length=1, max_length=MAX_TAG_CHARS)]] = Field(max_length=MAX_TAGS)


class TagRenameIn(BaseModel):
    """태그 이름 바꾸기 (2026-10-04 사용자 요청). 모든 논문에서 바뀐다. 앞뒤 빈칸은 지우고, 이미 있는 다른 태그 이름이면 그 태그로 합친다."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=MAX_TAG_CHARS)


class PaperMetadataIn(BaseModel):
    """논문 정보 고치기 (2026-10-02 사용자 결정 D5). 네 값을 모두 보내 바꾼다. 앞뒤 빈칸은 지우고, 빈 저자는 뺀다."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    title: str = Field(min_length=1, max_length=500)
    authors: list[str] = Field(max_length=100)
    year: int | None = Field(ge=1000, le=2100)
    doi: str | None = Field(max_length=200, pattern=DOI_PATTERN)

    @field_validator("authors")
    @classmethod
    def _clean_authors(cls, authors: list[str]) -> list[str]:
        if any(len(author) > 300 for author in authors):
            raise ValueError("저자 이름은 300자까지입니다.")
        return [author for author in authors if author]


class PageQuality(BaseModel):
    """추출 상태를 정한 값. 휴리스틱의 입력이며 보정된 확률이 아니다 (IMPL §5.3)."""

    chars: int  # 공백이 아닌 글자 수
    unmapped_chars: int  # 유니코드로 바꾸지 못한 글자 수
    image_coverage: float  # 이미지가 덮는 쪽 비율
    error: str | None = None  # 이 쪽을 추출하지 못한 이유


class PageOut(BaseModel):
    page_index: int
    page_label: str | None
    # usable, partial(일부 글자 깨짐·대부분 이미지), image_only(글자 없이 이미지), unknown(빈 쪽·추출 실패)
    text_status: str
    flags: list[str]  # no_text, mostly_image, unmapped_chars, two_columns, extract_failed
    quality: PageQuality


class PageList(BaseModel):
    version_id: str
    status: str  # 버전 상태. 추출 전이면 pages가 비어 있다
    pages: list[PageOut]


class TextBlockOut(BaseModel):
    block_id: str  # 추출(ParseRun)의 문단. 다시 추출해도 같은 쪽에 글이 같으면 그대로다. 영구 출처로 쓰지 않는다 (PLAN §8)
    reading_order: int
    text: str  # 줄을 이은 읽기용 텍스트(줄 끝 하이픈 잇기, NFKC)
    regions: list[list[float]]  # 줄마다 정본 좌표 상자 [u0, v0, u1, v1]
    quality_flags: list[str]  # unmapped_chars, in_figure(그림 안 글자: 쪽 번역에서 뺀다)
    # 굵게·기울임 구간 [시작, 끝, "b"|"i"|"bi"](text 안)과 가운데 글꼴 크기(pt). 레이아웃 유지 번역이 원문을 따른다(U7)
    styles: list[tuple[int, int, str]] = []
    font_size: float | None = None


class PageTextOut(PageOut):
    version_id: str
    # regions의 좌표계: 회전 전 view box 기준, 좌상단 원점, 0~1 (IMPL §6.1, anchor.v1 quad와 같다)
    coordinate_space: str = "view-box-unit-top-left"
    blocks: list[TextBlockOut]


class HeadingOut(BaseModel):
    """본문 제목 (documents.headings). 목차 패널이 PDF 목차가 없을 때 쓴다."""

    title: str
    page_index: int
    level: int  # 번호 단계(3.2면 2). 이름 제목은 1
    block_id: str  # 추출의 문단. 다시 추출해도 같은 쪽에 글이 같으면 그대로다
    box: list[float]  # 제목 줄의 정본 좌표 [u0, v0, u1, v1]


class HeadingList(BaseModel):
    version_id: str
    headings: list[HeadingOut]


class ParseRunOut(BaseModel):
    parse_run_id: str
    version_id: str
    status: str
