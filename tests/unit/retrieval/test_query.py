"""검색어 → 제목 FTS5 질의, 일치 표시 나누기 (IMPL §7.1)."""

import pytest

from paperloom.retrieval.query import MAX_TERMS, snippet_parts, title_query


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("cache partition", 'title : ("cache"* "partition"*)'),  # 낱말은 앞부분 일치
        ('"cache affinity" EDF', 'title : ("cache affinity" "EDF"*)'),  # 구절은 그대로
        ('"unterminated phrase', 'title : ("unterminated phrase")'),
        ("alphaword OR betaword", 'title : ("alphaword"* "OR"* "betaword"*)'),  # 연산자도 낱말
        ("NEAR(x y)", 'title : ("NEAR(x"* "y)"*)'),
        ("col:term*", 'title : ("col:term*"*)'),
        ('a"b', 'title : ("a"* "b")'),  # 따옴표부터는 구절
        ("ﬁxture", 'title : ("fixture"*)'),  # NFKC
        ("  - ... \" ", None),
        ("", None),
    ],
)
def test_title_query_quotes_every_term(text, expected):
    assert title_query(text) == expected


def test_title_query_limits_terms():
    assert title_query(" ".join(f"w{index}" for index in range(40))).count('"') == 2 * MAX_TERMS


def test_snippet_parts():
    assert snippet_parts("Cache \x02Partitioning\x03 for \x02Systems\x03") == [
        {"text": "Cache ", "match": False},
        {"text": "Partitioning", "match": True},
        {"text": " for ", "match": False},
        {"text": "Systems", "match": True},
    ]
