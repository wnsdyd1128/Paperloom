"""번호 붙은 그림: 캡션 번호 읽기와 캡션에 붙은 그림 영역 (reading.numbered_figures, 2026-11-09 사용자 요청: 발표 슬라이드
아티팩트에 논문 원본 그림 넣기). 좌표는 정본 좌표(좌상단 원점, 0~1)다."""

import pytest

from paperloom.reading.numbered_figures import CAPTION_CHARS, PAD, Paragraph, figure_box, figure_label, numbered_figures


def paragraph(block_id: str, text: str, box: tuple[float, float, float, float], flags: tuple[str, ...] = ()) -> Paragraph:
    return Paragraph(block_id, text, [list(box)], list(flags))


def padded(box: tuple[float, float, float, float]) -> tuple[float, float, float, float]:
    return box[0] - PAD, box[1] - PAD, box[2] + PAD, box[3] + PAD


@pytest.mark.parametrize(
    ("text", "label"),
    [
        ("Figure 3: Overview of the pipeline.", "3"),
        ("Fig. 2. Results on the benchmark.", "2"),
        ("Fig. 2: the overall mechanism.", "2"),  # 구두점 뒤는 소문자여도 캡션이다
        ("FIGURE 4 Overview of the system", "4"),  # 번호 뒤에 제목이 바로 온다(Springer·IEEE)
        ("Fig. 5 | Pipeline", "5"),  # Nature
        ("Fig.7: tight spacing", "7"),
        ("Figure S1: Supplementary result", "S1"),
        ("figure a2. appendix plot", "A2"),
        ("Figure 8", "8"),
        ("그림 1. 시스템 구조", "1"),
        ("<그림 2> 실험 결과", "2"),
        ("[Fig. 6] Latency", "6"),
    ],
)
def test_a_caption_gives_its_figure_number(text, label):
    assert figure_label(text) == label


@pytest.mark.parametrize(
    "text",
    [
        "Figure 3 shows the pipeline.",  # 본문 문장
        "Figures 3 and 4 show the results.",
        "Figure 2 and 3 compare the two.",
        "그림 3은 결과를 보여 준다.",
        "In Figure 3, we see the result.",
        "Fig. 3a shows the first part.",
        "Table 1: Results",  # 표는 그림 번호가 아니다
        "Figure 1. Overview ........ 3",  # 그림 목록 줄
    ],
)
def test_body_sentences_tables_and_listings_are_not_figure_captions(text):
    assert figure_label(text) is None


def test_figures_are_listed_in_document_order_with_the_first_caption_of_each_number():
    long = "Figure 4: " + "word " * 100
    pages = [
        (0, [
            paragraph("a", "Figure 1 inside a screenshot", (0.1, 0.1, 0.3, 0.12), ("in_figure",)),  # 그림 안 글자
            paragraph("b", "Figure 2:   An   overview.", (0.1, 0.5, 0.5, 0.52)),
            Paragraph("c", "Figure 3: no regions", [], []),
        ]),
        (1, [
            paragraph("d", "Figure 1. The real caption.", (0.1, 0.4, 0.5, 0.42)),
            paragraph("e", "Figure 2: repeated later.", (0.1, 0.6, 0.5, 0.62)),
            paragraph("f", long, (0.1, 0.7, 0.9, 0.8)),
            paragraph("g", "Figure 5. A cited figure caption.", (0.1, 0.9, 0.5, 0.92), ("reference",)),
        ]),
    ]

    figures = numbered_figures(pages)

    assert [(figure.label, figure.page_index, figure.block_id) for figure in figures] == [("2", 0, "b"), ("1", 1, "d"), ("4", 1, "f")]
    assert figures[0].caption == "Figure 2: An overview."  # 공백을 줄인다
    assert len(figures[2].caption) == CAPTION_CHARS and figures[2].caption.endswith("…")


CAPTION = paragraph("caption", "Figure 1: Throughput under load.", (0.15, 0.50, 0.45, 0.52))


def test_the_figure_is_the_candidate_just_above_its_caption():
    figure = (0.12, 0.30, 0.48, 0.49)
    body_above = paragraph("body", "A long body paragraph that ends just above the figure in the same column of text.", (0.1, 0.20, 0.5, 0.28))
    previous = (0.12, 0.05, 0.48, 0.18)  # 앞 문단 위의 다른 그림

    assert figure_box(CAPTION, [previous, figure], [body_above, CAPTION]) == pytest.approx(padded(figure))


def test_a_figure_below_its_caption_is_found_when_nothing_is_above():
    figure = (0.12, 0.53, 0.48, 0.70)
    assert figure_box(CAPTION, [figure], []) == pytest.approx(padded(figure))


def test_side_by_side_subfigures_their_labels_and_axis_text_are_one_figure():
    left, right = (0.10, 0.30, 0.27, 0.46), (0.30, 0.30, 0.48, 0.46)
    texts = [
        paragraph("sa", "(a) Throughput", (0.14, 0.465, 0.24, 0.48)),  # 하위 그림 설명은 그림과 캡션 사이에 있다
        paragraph("sb", "(b) Latency", (0.34, 0.465, 0.44, 0.48)),
        paragraph("axis", "Time (s)", (0.06, 0.35, 0.095, 0.40)),  # 그림 후보 밖의 축 이름
        paragraph("inside", "0 10 20 30 40", (0.29, 0.20, 0.49, 0.295), ("in_figure",)),
    ]

    box = figure_box(CAPTION, [left, right], [*texts, CAPTION])

    assert box == pytest.approx(padded((0.06, 0.20, 0.49, 0.48)))


def test_body_text_other_columns_and_the_caption_side_are_not_part_of_the_figure():
    figure = (0.12, 0.30, 0.48, 0.49)
    other_column = (0.55, 0.30, 0.90, 0.49)  # 같은 높이의 오른쪽 단 그림
    body = paragraph("body", "Body text right next to the figure that is long enough to be a paragraph of prose.", (0.12, 0.25, 0.48, 0.295))
    below = paragraph("below", "short label", (0.15, 0.525, 0.30, 0.54))  # 캡션 너머

    assert figure_box(CAPTION, [figure, other_column], [body, below]) == pytest.approx(padded(figure))


def test_no_figure_when_the_nearest_candidate_is_too_far_or_behind_body_text():
    far = (0.12, 0.10, 0.48, 0.40)  # 캡션까지 0.10
    assert figure_box(CAPTION, [far], []) is None
    figure = (0.12, 0.30, 0.48, 0.45)
    between = paragraph("between", "A body paragraph placed between the drawing and the caption, long enough.", (0.1, 0.455, 0.5, 0.495))
    assert figure_box(CAPTION, [figure], [between]) is None
    assert figure_box(CAPTION, [], []) is None
