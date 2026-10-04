"""검색어를 FTS5 질의로 바꾸고, 일치 표시를 나눈다 (IMPL §7.1).

검색은 논문 제목만 찾는다(2026-10-01 사용자 결정). 사용자 입력을 FTS5 문법으로 해석하지 않는다. 낱말은
FTS5 문자열("…")로 감싸 앞부분 일치(`*`)로 찾고, 큰따옴표로 묶은 구절은 그대로 찾는다. 모두 제목에 있어야 한다.
그래서 AND·OR·NOT·NEAR·^·:·괄호 같은 연산자는 글자로만 다뤄진다. 글자나 숫자가 없는 조각은 버린다(빈 구절은
FTS5 오류다). 색인과 같게 NFKC로 정규화한다.
"""

import re
import unicodedata

MAX_QUERY_CHARS = 200
MAX_TERMS = 16
# 일치한 부분을 감싸는 표시. 제목에는 제어 문자가 없다(documents.inspect.clean_text).
MARK_START = "\x02"
MARK_END = "\x03"

_TERM = re.compile(r'"([^"]*)"?|([^\s"]+)')


def title_query(text: str) -> str | None:
    """제목 열만 찾는 FTS5 MATCH 식. 찾을 낱말이 없으면 None."""
    normalized = unicodedata.normalize("NFKC", text)[:MAX_QUERY_CHARS]
    terms = []
    for phrase, word in _TERM.findall(normalized):
        value = " ".join((phrase or word).split())
        if any(ch.isalnum() for ch in value):
            quoted = '"' + value.replace('"', '""') + '"'
            terms.append(quoted if phrase else quoted + "*")
    return f"title : ({' '.join(terms[:MAX_TERMS])})" if terms else None


def snippet_parts(marked: str) -> list[dict]:
    """MARK_START·MARK_END로 표시한 글 → [{"text", "match"}]. 클라이언트는 HTML 없이 그린다."""
    parts = []
    for index, piece in enumerate(re.split(f"[{MARK_START}{MARK_END}]", marked)):
        if piece:
            parts.append({"text": piece, "match": index % 2 == 1})
    return parts
