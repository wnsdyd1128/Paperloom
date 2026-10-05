"""첫 쪽에서 논문 제목 찾기 (2026-10-05 사용자 요청 "등록 시에 파일 명이 아닌 해당 논문의 이름으로 해줘").

문단 상자는 정본 좌표(u0, v0, u1, v1, 0–1)다. 실제 논문 넷(CAAS·CBANA·TCPS·사용자 논문)의 첫 쪽에서는 위쪽 절반에서 글꼴이
가장 큰 문단이 제목이었다(본문보다 1.2–2.4배).
"""

from paperloom.documents.titles import looks_like_filename, title_from_blocks


def block(text: str, size: float, u0: float = 0.1, v0: float = 0.1, u1: float = 0.9, v1: float = 0.14, flags=()) -> dict:
    return {"text": text, "font_size": size, "regions": [[u0, v0, u1, v1]], "quality_flags": list(flags)}


BODY = [
    block("Abstract", 11, 0.1, 0.30, 0.2, 0.31),
    block("Transformers replace recurrence with attention and train much faster than earlier sequence models do.", 10, 0.1, 0.32, 0.9, 0.45),
    block("We evaluate the model on two translation tasks and report results that improve over prior work.", 10, 0.1, 0.47, 0.9, 0.60),
]


def test_the_largest_block_in_the_upper_half_is_the_title():
    blocks = [
        block("Provided proper attribution is provided, this paper may be reproduced.", 8, v0=0.05, v1=0.07),
        block("Attention Is All You Need", 17, 0.3, 0.12, 0.7, 0.15),
        block("Ashish Vaswani Noam Shazeer", 11, 0.2, 0.18, 0.8, 0.2),
        *BODY,
    ]
    assert title_from_blocks(blocks) == "Attention Is All You Need"


def test_margin_stamps_page_numbers_and_math_are_not_titles():
    blocks = [
        block("arXiv:1706.03762v7 [cs.CL] 2 Aug 2023", 20, 0.02, 0.25, 0.05, 0.75),  # 왼쪽 여백의 세로 도장(좁다)
        block("Attention Is All You Need", 17, 0.3, 0.12, 0.7, 0.15),
        block("x = y + z", 24, 0.3, 0.2, 0.7, 0.24, flags=("math",)),
        block("Running header of a very long journal name here", 26, 0.1, 0.92, 0.9, 0.95),  # 아래쪽 절반
        *BODY,
    ]
    assert title_from_blocks(blocks) == "Attention Is All You Need"


def test_a_title_split_into_blocks_of_the_same_size_is_joined_and_footnote_marks_dropped():
    blocks = [
        block("A Synthetic Study of Woven Paper Titles", 18, 0.15, 0.10, 0.85, 0.13),
        block("for Readers Without Metadata∗", 18.1, 0.25, 0.135, 0.75, 0.165),
        block("Ada Example", 11, 0.4, 0.2, 0.6, 0.22),
        *BODY,
    ]
    assert title_from_blocks(blocks) == "A Synthetic Study of Woven Paper Titles for Readers Without Metadata"


def test_no_title_when_nothing_stands_out_from_the_body():
    assert title_from_blocks(BODY) is None  # "Abstract"(11pt)는 한 낱말이고 본문보다 크게 두드러지지 않는다
    assert title_from_blocks([]) is None
    assert title_from_blocks([{"text": "Title", "font_size": None, "regions": [[0.1, 0.1, 0.9, 0.2]], "quality_flags": []}]) is None


def test_titles_without_spaces_look_like_file_names():
    assert looks_like_filename("1706.03762v7")
    assert looks_like_filename("paper_final-v2")
    assert not looks_like_filename("Attention Is All You Need")
    assert not looks_like_filename("")
