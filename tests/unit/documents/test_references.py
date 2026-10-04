"""참고문헌 쪽 찾기 (2026-10-02 사용자 요청: 원문 위 설명·질문에 참고문헌 쪽도 보낸다)."""

from paperloom.documents.references import reference_blocks, reference_pages


def doc(*pages: list[str]) -> list[dict]:
    return [{"page_index": index, "blocks": [{"text": text} for text in texts]} for index, texts in enumerate(pages)]


def test_from_the_heading_page_to_the_end():
    pages = doc(["1 Introduction", "Prior work [1] studied caches."], ["5 Conclusion", "REFERENCES", "[1] A. Author. 2020."], ["[2] B. Author. 2021."])
    assert reference_pages(pages) == [1, 2]


def test_stops_before_the_appendix():
    pages = doc(["Body"], ["References", "[1] A."], ["[2] B."], ["A Appendix", "Proof."], ["More appendix."])
    assert reference_pages(pages) == [1, 2]
    # 부록 머리 앞에 참고문헌 항목이 있으면 그 쪽까지다
    assert reference_pages(doc(["Body"], ["Bibliography", "[1] A."], ["[2] B.", "APPENDIX A: PROOFS"])) == [1, 2]


def test_heading_merged_with_the_first_entry_and_numbered_or_korean_headings():
    assert reference_pages(doc(["Body"], ["REFERENCES [1] Sebastian Altmeyer. 2011."])) == [1]
    assert reference_pages(doc(["Body"], ["7 References"])) == [1]
    assert reference_pages(doc(["본문"], ["참고 문헌", "[1] 홍길동. 2020."])) == [1]


def test_the_last_heading_wins_and_a_sentence_is_not_a_heading():
    pages = doc(["Contents", "References"], ["References to prior work are in Section 2."], ["Body"], ["References", "[1] A."])
    assert reference_pages(pages) == [3]


def test_no_heading_means_no_reference_pages():
    assert reference_pages(doc(["Body"], ["More body [12]."])) == []
    assert reference_pages([]) == []


def test_reference_blocks_are_the_section_from_the_heading_not_the_whole_page():
    """참고문헌 쪽 전체가 아니라 참고문헌 부분만(머리부터 부록 앞까지) 쪽 번역에서 뺀다 (2026-10-03 사용자 요청: 결론·감사의
    글과 참고문헌이 한 쪽에 있다)."""
    pages = doc(["Body"], ["5 Conclusion", "We thank reviewers.", "REFERENCES", "[1] A."], ["[2] B."], ["A Appendix", "Proof."])
    assert reference_blocks(pages) == [(1, 2), (1, 3), (2, 0)]
    assert reference_pages(pages) == [1, 2]
    assert reference_blocks(doc(["Body"])) == []
