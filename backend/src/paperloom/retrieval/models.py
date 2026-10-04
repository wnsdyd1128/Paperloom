"""검색 REST 응답 계약 (IMPL §7.1). 논문 제목과 일치 표시만 돌려준다."""

from pydantic import BaseModel


class SnippetPart(BaseModel):
    text: str
    match: bool  # 검색어와 일치한 부분


class PaperHit(BaseModel):
    """제목에서 찾은 논문. 현재 버전으로 연다."""

    paper_id: str
    version_id: str
    title: list[SnippetPart]


class SearchResult(BaseModel):
    query: str
    papers: list[PaperHit]
