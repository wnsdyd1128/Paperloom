"""논문 제목 검색 (IMPL §7.1): SQLite FTS5, bm25 순위.

검색 대상은 사용자 논문의 제목이다(2026-10-01 사용자 결정으로 본문 문단 결과는 보이지 않는다). 본문 색인
(`text_blocks_fts`)은 추출 때 계속 만들어 두며, 공유 범위 안의 검색(W07 `paper_search`)에서 쓴다.
질의는 query.title_query로만 만들고 값은 바인딩한다. 의미 검색은 하지 않는다.
"""

from contextlib import closing
from pathlib import Path

from paperloom.documents.repository import LOCAL_OWNER_ID
from paperloom.infrastructure.database.sqlite import connect
from paperloom.retrieval.models import PaperHit, SearchResult
from paperloom.retrieval.query import MARK_END, MARK_START, snippet_parts, title_query

_PAPERS = """
SELECT p.paper_id, p.current_version_id, highlight(papers_fts, 1, ?, ?) AS title
FROM papers_fts JOIN papers AS p ON p.paper_id = papers_fts.paper_id
WHERE papers_fts MATCH ? AND p.owner_id = ?
ORDER BY rank
LIMIT ?
"""


class SearchService:
    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path

    def search(self, text: str, limit: int) -> SearchResult | None:
        """찾을 낱말이 없으면 None."""
        query = title_query(text)
        if query is None:
            return None
        with closing(connect(self._db_path)) as connection:
            rows = connection.execute(_PAPERS, (MARK_START, MARK_END, query, LOCAL_OWNER_ID, limit)).fetchall()
        return SearchResult(
            query=text,
            papers=[
                PaperHit(paper_id=row["paper_id"], version_id=row["current_version_id"], title=snippet_parts(row["title"]))
                for row in rows
            ],
        )
