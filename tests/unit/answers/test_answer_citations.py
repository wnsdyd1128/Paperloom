"""답의 근거 표기 (2026-10-02 사용자 요청): 근거는 [근거 n]으로 쓴다. 논문 글의 참고문헌 번호 [12]와 헷갈리지 않게,
대괄호 번호만으로는 근거로 읽지 않는다."""

from paperloom.answers.service import cited_items, cited_numbers


def test_only_evidence_marks_are_citations_in_first_seen_order():
    markdown = "캐시 집합으로 나눈다 [근거 1, 3]. 논문은 참고문헌 [12]를 따른다 [근거 2][근거 1]."
    assert cited_numbers(markdown) == [1, 3, 2]


def test_spacing_and_repeated_word_inside_one_mark_are_accepted():
    assert cited_numbers("[근거1] [근거 2,근거 4] [근거 5 , 6]") == [1, 2, 4, 5, 6]


def test_bare_bracket_numbers_and_outside_mark_are_not_citations():
    assert cited_numbers("참고문헌 [3], [4, 5]\n\n> [근거 밖] 일반 지식") == []


def test_paragraph_marks_name_a_paragraph_of_a_paper_text_evidence():
    """문단 근거 (2026-10-02 사용자 요청: 근거 위치가 쪽 첫 문단이라 내용과 안 맞았다). [근거 22¶3]은 근거 22의 셋째 문단."""
    markdown = "결과 [근거 22¶3]. 같은 쪽 [근거 22]와 [근거 20¶1, 22¶3, 5], 띄어 써도 [근거 7 ¶ 2]."
    assert cited_items(markdown) == [(22, 3), (22, None), (20, 1), (5, None), (7, 2)]
    assert cited_numbers(markdown) == [22, 20, 5, 7]


def test_paragraph_ranges_cite_their_first_paragraph():
    """2026-10-02 사용자 확인: 모델이 쓴 [근거 4¶4–5]와 범위가 섞인 표기가 통째로 근거가 아니었다(링크 없음)."""
    markdown = "방법 [근거 4¶4–5]. 증명 [근거 12¶8, 근거 13¶1-12, 근거 19¶35] [근거 24 ¶ 66 ~ 68]"
    assert cited_items(markdown) == [(4, 4), (12, 8), (13, 1), (19, 35), (24, 66)]
