"""1쪽 글에서 DOI 찾기 (2026-10-02 사용자 결정 D5: DOI는 자동, 나머지 논문 정보는 직접 고친다)."""

from paperloom.documents.metadata import find_doi


def test_finds_the_first_doi_in_reading_order():
    assert find_doi(["Latest updates: https://dl.acm.org/doi/10.1145/3487581", "DOI 10.9999/other"]) == "10.1145/3487581"
    assert find_doi(["Title", "https://doi.org/10.1007/978-3-030-12345-6_7."]) == "10.1007/978-3-030-12345-6_7"


def test_trailing_punctuation_and_unbalanced_brackets_are_not_part_of_the_doi():
    assert find_doi(["(see 10.1000/xyz123), and"]) == "10.1000/xyz123"
    assert find_doi(["doi:10.1002/(SICI)1097-0258(199801)17:1;"]) == "10.1002/(SICI)1097-0258(199801)17:1"


def test_no_doi():
    assert find_doi(["Version 10.2 of the tool", "10.1/too-short-prefix"]) is None
    assert find_doi([]) is None
