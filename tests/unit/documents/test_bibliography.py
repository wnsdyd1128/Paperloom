"""서지 조회의 식별자 찾기와 응답 읽기 (documents.bibliography, 2026-11-16 사용자 결정). 네트워크는 쓰지 않는다. 이름·번호는 합성이다."""

import pytest

from paperloom.documents.bibliography import Record, arxiv_record, crossref_record, find_arxiv_id, identifiers

STAMP = "arXiv:2401.01234v2 [cs.LG] 3 Jan 2024"


def stamp_blocks(text: str, upward: bool = True) -> list[dict]:
    """여백의 세로 표기: 글자마다 문단이고(side_text) 읽는 차례는 쪽 위에서 아래다. upward면 글이 아래에서 위로 쓰였다."""
    chars = [char for char in text if not char.isspace()]
    blocks = []
    for index, char in enumerate(chars):
        top = 0.8 - index * 0.01 if upward else 0.2 + index * 0.01
        blocks.append({"text": char, "regions": [[0.02, top, 0.03, top + 0.008]], "quality_flags": ["side_text"]})
    return sorted(blocks, key=lambda block: block["regions"][0][1])


def body(text: str, *flags: str) -> dict:
    return {"text": text, "regions": [[0.1, 0.3, 0.9, 0.32]], "quality_flags": list(flags)}


@pytest.mark.parametrize("upward", [True, False])
def test_arxiv_id_comes_from_the_turned_margin_stamp(upward):
    blocks = [body("Synthetic Title"), *stamp_blocks(STAMP, upward), body("Abstract text.")]
    assert find_arxiv_id(blocks) == "2401.01234"


def test_arxiv_id_comes_from_a_header_line_but_not_from_references():
    assert find_arxiv_id([body("Preprint. arXiv:hep-th/9901001v1"), body("Abstract.")]) == "hep-th/9901001"
    assert find_arxiv_id([body("Abstract."), body("[1] A. Writer. Old idea. arXiv:2001.00001, 2020.", "reference")]) is None


def test_no_arxiv_id_without_a_stamp():
    assert find_arxiv_id([body("Title"), *stamp_blocks("979-8-3315-0000-0/25/$31.00 2025 IEEE")]) is None


def test_identifiers_ask_the_doi_first_and_the_arxiv_number_next():
    stamp = stamp_blocks(STAMP)
    assert identifiers("10.1234/synthetic.5678", stamp) == [("doi", "10.1234/synthetic.5678"), ("arxiv", "2401.01234")]
    # arXiv DOI는 Crossref에 없으므로 arXiv에 묻는다(같은 번호는 한 번만)
    assert identifiers("10.48550/arXiv.2401.01234", stamp) == [("arxiv", "2401.01234")]
    # 없거나 사용자가 지운 DOI(빈 글)
    assert identifiers(None, [body("Title")]) == []
    assert identifiers("", stamp) == [("arxiv", "2401.01234")]


def test_crossref_record_reads_authors_and_the_first_year():
    message = {
        "author": [
            {"given": "Ada", "family": "Lovelace", "sequence": "first"},
            {"family": "Babbage"},
            {"name": "Synthetic  Consortium"},
            {"given": " ", "family": ""},
        ],
        "issued": {"date-parts": [[2022, 5, 6]]},
        "published-print": {"date-parts": [[2023, 1]]},
    }
    assert crossref_record({"status": "ok", "message": message}) == Record(["Ada Lovelace", "Babbage", "Synthetic Consortium"], 2022)


def test_crossref_record_falls_back_to_another_date_and_drops_strange_years():
    assert crossref_record({"message": {"issued": {"date-parts": [[None]]}, "published-online": {"date-parts": [[2021]]}}}) == Record([], 2021)
    assert crossref_record({"message": {"issued": {"date-parts": [[20221]]}}}) == Record([], None)


ARXIV_FEED = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <id>http://arxiv.org/abs/2401.01234v2</id>
    <published>2024-01-03T18:00:00Z</published>
    <updated>2024-03-01T10:00:00Z</updated>
    <title>Synthetic Paper</title>
    <author><name>Ada  Lovelace</name></author>
    <author><name>Alan Turing</name></author>
  </entry>
</feed>"""


def test_arxiv_record_reads_authors_and_the_first_version_year():
    assert arxiv_record(ARXIV_FEED) == Record(["Ada Lovelace", "Alan Turing"], 2024)


@pytest.mark.parametrize(
    "feed",
    [
        '<feed xmlns="http://www.w3.org/2005/Atom"></feed>',
        '<feed xmlns="http://www.w3.org/2005/Atom"><entry><id>http://arxiv.org/api/errors#incorrect_id_format_for_x</id>'
        "<title>Error</title></entry></feed>",
    ],
)
def test_arxiv_record_is_none_for_an_unknown_number(feed):
    assert arxiv_record(feed) is None
