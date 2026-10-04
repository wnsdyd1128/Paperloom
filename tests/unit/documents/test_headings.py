"""본문 제목 찾기 (2026-10-02 사용자 결정 D6: PDF에 목차가 없으면 본문 제목으로 목차를 만든다)."""

from paperloom.documents.headings import headings, section_paths

LINE = [0.1, 0.1, 0.9, 0.12]


def doc(*pages: list) -> list[dict]:
    """쪽마다 문단들. 문단은 글(한 줄) 또는 (글, 줄 수)."""
    return [
        {
            "page_index": index,
            "blocks": [
                {"text": block, "regions": [LINE]} if isinstance(block, str) else {"text": block[0], "regions": [LINE] * block[1]}
                for block in blocks
            ],
        }
        for index, blocks in enumerate(pages)
    ]


def found(pages: list[dict]) -> list[tuple]:
    return [(item["title"], item["page_index"], item["order"], item["level"]) for item in headings(pages)]


def test_numbered_headings_and_their_levels():
    pages = doc(
        ["Paper Title", "Abstract", ("We study caches across many lines of text.", 3), "1 Introduction", ("Body text.", 2)],
        ["2 System Model", "2.1 Tasks", ("Body.", 2), "2.1.1 Periods", "2.2 Caches"],
        ["3 RESULTS", "10 Conclusion"],
    )
    assert found(pages) == [
        ("Abstract", 0, 1, 1),
        ("1 Introduction", 0, 3, 1),
        ("2 System Model", 1, 0, 1),
        ("2.1 Tasks", 1, 1, 2),
        ("2.1.1 Periods", 1, 3, 3),
        ("2.2 Caches", 1, 4, 2),
        ("3 RESULTS", 2, 0, 1),
    ]  # "10 Conclusion"은 3 다음으로 너무 멀리 뛴다(표의 수 같은 것)


def test_each_paragraph_gets_the_path_of_the_headings_above_it():
    """근거의 절 (2026-10-04 사용자 요청: "3.3 Motivation의 문단"처럼 어느 절인지 함께 보낸다). 가장 가까운 앞 제목까지의
    제목 경로다. 쪽을 넘어도 이어진다. 첫 제목 앞(제목·저자)에는 없다. 이름 제목(References)은 처음부터 다시."""
    pages = doc(
        ["Paper Title", "Abstract", ("We study caches across many lines of text.", 3), "1 Introduction", ("Body text.", 2)],
        [("Continued body.", 2), "2 System Model", "2.1 Tasks", ("Body.", 2)],
        [("More body.", 2), "2.2 Caches", ("Cache body.", 2), "References", ("[1] A paper.", 2)],
    )
    assert section_paths(pages) == {
        (0, 1): "Abstract",
        (0, 2): "Abstract",
        (0, 3): "1 Introduction",
        (0, 4): "1 Introduction",
        (1, 0): "1 Introduction",
        (1, 1): "2 System Model",
        (1, 2): "2 System Model › 2.1 Tasks",
        (1, 3): "2 System Model › 2.1 Tasks",
        (2, 0): "2 System Model › 2.1 Tasks",
        (2, 1): "2 System Model › 2.2 Caches",
        (2, 2): "2 System Model › 2.2 Caches",
        (2, 3): "References",
        (2, 4): "References",
    }


def test_a_numbered_heading_wrapped_onto_two_lines():
    """사용자 논문 CAAS 2쪽: 좁은 단에서 "3.1 RTEMS (Real-Time Executive for Multiprocessor Systems)"가 두 줄로 넘어갔다. 여러 줄
    문단은 첫머리에 이어 쓴 제목만 찾아 이 제목을 놓쳤고, 그 아래 문단의 절이 "3 Background"가 되었다(2026-10-04). 문단 전체가
    짧으면(12낱말 이하) 넘어간 제목이다."""
    pages = doc(["1 Background", ("1.1 RTEMS (Real-Time Executive for Multiprocessor Systems)", 2), ("RTEMS originated in the 1980s as a program.", 4)])
    assert found(pages) == [("1 Background", 0, 0, 1), ("1.1 RTEMS (Real-Time Executive for Multiprocessor Systems)", 0, 1, 2)]
    assert section_paths(pages)[(0, 2)] == "1 Background › 1.1 RTEMS (Real-Time Executive for Multiprocessor Systems)"


def test_numbered_lines_that_are_not_headings():
    pages = doc(
        ["1 Introduction"],
        [
            "2 We propose a new method for this problem.",  # 마침표로 끝나는 문장
            "2 of the tasks are late",  # 소문자로 시작
            "2 0.25 0.50 0.75",  # 글자가 없다
            ("2 Model spans two lines", 2),  # 여러 줄 문단
            "2 A heading that is far too long to be a section heading in any normal paper at all",  # 12낱말 넘음
            "1 Restarted list",  # 앞 번호보다 앞
            "3 Results",
        ],
    )
    assert found(pages) == [("1 Introduction", 0, 0, 1), ("3 Results", 1, 6, 1)]


def test_run_in_headings_at_the_start_of_a_paragraph():
    """제목이 다음 문단과 한 문단으로 묶였거나 문단 첫머리에 이어 쓴 제목(사용자 논문의 5.2·5.2.1)"""
    pages = doc(
        ["1 Partitioning", "1.1 The Algorithm"],
        [
            ("1.2 Calculation of the Upper Bound on Cache Interference: The algorithm needs the bound first.", 3),
            ("1.2.1 IP Formulation. In the following discussion we compute the bound.", 2),
            ("2 Tasks are assigned to cores. Each core runs one task at a time.", 2),  # 제목 꼴(낱말 첫 글자 대문자)이 아니다
            ("2 Results Of The Study continue here without any stop", 2),  # 끊는 곳이 없다
        ],
    )
    assert found(pages) == [
        ("1 Partitioning", 0, 0, 1),
        ("1.1 The Algorithm", 0, 1, 2),
        ("1.2 Calculation of the Upper Bound on Cache Interference", 1, 0, 2),
        ("1.2.1 IP Formulation", 1, 1, 3),
    ]


def test_named_and_appendix_headings():
    pages = doc(
        ["ABSTRACT", "1 Introduction"],
        ["Acknowledgments:", "REFERENCES", "[1] A. Author. 2020."],
        ["A Appendix", "A.1 Proofs", "Appendix B: Extra Results", "참고문헌"],
    )
    assert found(pages) == [
        ("ABSTRACT", 0, 0, 1),
        ("1 Introduction", 0, 1, 1),
        ("Acknowledgments", 1, 0, 1),
        ("REFERENCES", 1, 1, 1),
        ("A Appendix", 2, 0, 1),
        ("A.1 Proofs", 2, 1, 2),
        ("Appendix B: Extra Results", 2, 2, 1),
        ("참고문헌", 2, 3, 1),
    ]


def test_a_sentence_starting_with_a_heading_word_is_not_a_heading():
    pages = doc(["References to prior work are in Section 2.", "Abstract interpretation", "A method"])
    assert found(pages) == []
    assert headings([]) == []


def test_ieee_roman_sections_and_lettered_subsections():
    """IEEE 논문: "I. INTRODUCTION"(로마 숫자, 대문자) 장과 "A. Overall Framework Design"(글자) 절. 장마다 A부터 다시 센다
    (2026-10-03 사용자 논문 CBANA: 목차에 ACKNOWLEDGMENT·REFERENCES만 보였다)."""
    pages = doc(
        ["I. Smith and J. Doe", "A. Line before any section", "I. INTRODUCTION", ("ADVANCEMENTS in chip design have widened the gap.", 4)],
        ["II. RELATED WORK", ("Body.", 3), "J. Xiao et al.", "III. CBANA FOR ANALYZING CACHE BEHAVIOR", "A. Overall Framework Design"],
        ["B. CFG and Program State Graph Generation", ("Body.", 3), "D. Skipped too far", "C. Input-Aware Path Analysis"],
        ["IV. EVALUATION", "A. Experimental Setup", "B. Precision of CBANA", "VII. NOT NEXT", "V. CONCLUSION", "ACKNOWLEDGMENT", "REFERENCES"],
    )
    assert found(pages) == [
        ("I. INTRODUCTION", 0, 2, 1),
        ("II. RELATED WORK", 1, 0, 1),
        ("III. CBANA FOR ANALYZING CACHE BEHAVIOR", 1, 3, 1),
        ("A. Overall Framework Design", 1, 4, 2),
        ("B. CFG and Program State Graph Generation", 2, 0, 2),
        ("D. Skipped too far", 2, 2, 2),  # 글자는 두 칸까지 뛸 수 있다(추출에서 빠진 제목)
        ("IV. EVALUATION", 3, 0, 1),
        ("A. Experimental Setup", 3, 1, 2),
        ("B. Precision of CBANA", 3, 2, 2),
        ("V. CONCLUSION", 3, 4, 1),
        ("ACKNOWLEDGMENT", 3, 5, 1),
        ("REFERENCES", 3, 6, 1),
    ]  # "I. Smith …"(대문자 아님)·"A. Line before …"(장 앞)·"J. Xiao et al."(J는 너무 뜀)·"C."(D 뒤)·"VII."(너무 뜀)은 제목이 아니다
