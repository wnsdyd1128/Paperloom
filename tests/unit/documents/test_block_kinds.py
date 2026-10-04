"""본문이 아닌 문단 (쪽 번역에서 뺀다, 2026-10-03 사용자 요청): 따로 놓인 수식, 쪽마다 되풀이되는 머리글·바닥글, 표·의사코드 안.
예시 글은 사용자 논문(ACM TECS, 읽기 전용 진단)에서 뽑힌 모양을 본뜬 합성 글이다."""

import pytest

from paperloom.documents.block_kinds import is_display_math
from paperloom.documents.fonts import is_math_font
from paperloom.documents.running import running_lines
from paperloom.documents.tables import horizontal_rules, table_blocks
from paperloom.reading.figures import Graphic


@pytest.mark.parametrize(
    "text",
    [
        "(0.1)",
        "(1.9)",
        "(12)",
        "(A.3)",
        "DBF (τi,t) = max - 0, -- t − Di Ti + 1 × Ci .",
        "DBF ∗ (τi,t) = ⎧⎪ ⎨ ⎪ ⎩ 0",
        "t < Di Ci + Ui × (t − Di ) otherwise ,",  # 낱말 하나(otherwise)와 기호
        "where Ui = Ci Ti .",  # 분수가 글로 풀린 줄
        "∀t, n i=1 DBF (τi,t) ≤ t",
        "Dk ≥",
        "max",
        "τ tna ← τ tna ∪{τi}",
        # 식 번호가 없는 수식, 다른 조판의 수식 (2026-10-03 사용자 질문: 그 논문에만 맞춘 것 아닌가)
        "E = mc 2",
        "f (x) = Σ a i x i",  # Computer Modern: 그리스 문자·기호
        "𝑓(𝑥) = ∑ 𝑎𝑖 𝑥𝑖",  # Word·Cambria Math: 수학 영숫자
        "x = 1 if a > b, 0 otherwise",  # 수식 안 이음말
        "minimize Σ c i x i subject to Ax ≤ b",
        "and for all τj ∈ τ ,∀i ≤ j,Ti ≤ Tj :",  # 이음말뿐인 조건 줄
    ],
)
def test_display_equations(text):
    assert is_display_math(text)


@pytest.mark.parametrize(
    "text",
    [
        "Observe that the following inequality holds for all τi and all 0 ≤ t:",
        "3.2 The Demand-Bound Function",
        "28:7",
        "J. Xiao et al.",
        "Theorem 1.",
        "2.1 Setup",
        "x is positive.",
        "Fig. 1. Case where τ3 misses its deadline",
        "PSEUDOCODE 1: CITTA(τ , π)",  # 캡션은 번역한다(낱말 없이 그리스 문자뿐이어도)
        "모든 τi 에 대해 = 이 성립한다",  # 한글 글
        "Let x be the input of the model.",
        "where x is the input and y the output of the model.",
        "",
    ],
)
def test_text_is_not_a_display_equation(text):
    assert not is_display_math(text)


def test_a_block_set_in_math_fonts_is_an_equation_even_without_unicode_symbols():
    """기호가 유니코드로 바뀌지 않아도(글꼴 인코딩) 수식 글꼴(CMMI·CMSY·CMEX 등) 글자가 절반 이상이면 수식이다.
    글 줄 안의 수식 글자(인라인 수식)는 본문이다."""
    assert is_display_math("f x a i b", math_font_share=0.9)
    assert not is_display_math("f x a i b", math_font_share=0.2)
    assert not is_display_math("where x is the input and y the output of the model.", math_font_share=0.1)


@pytest.mark.parametrize(
    ("name", "math"),
    [
        ("CMMI10", True), ("ABCDEF+CMSY7", True), ("CMEX10", True), ("CMBSY10", True), ("MSBM10", True), ("EUFM10", True),
        ("rtxmi", True), ("txsy", True), ("txex-bar", True), ("NewTXMI", True), ("LMMathItalic10-Regular", True),
        ("STIXTwoMath-Regular", True), ("CambriaMath", True), ("XITSMath", True), ("MTMI", True), ("MTExtra", True),
        ("CMR10", False), ("Times-Roman", False), ("LinLibertineT", False), ("LinLibertineI", False), ("Helvetica-Bold", False),
        ("Symbol", False), ("", False),
    ],
)
def test_math_font_names(name, math):
    """수식 글꼴: Computer Modern·AMS·Euler 수식, newtx·txfonts·pxfonts, Latin Modern·STIX·Cambria·XITS Math, MathTime.
    CMR(본문에도 쓰는 로만)·Symbol(본문 그리스 문자에도 쓴다)은 수식 글꼴로 보지 않는다."""
    assert is_math_font(name) is math


def page(index, *blocks):
    """blocks: (글, 위 v, 아래 v[, 줄 수])"""
    return {
        "page_index": index,
        "blocks": [{"text": text, "regions": [[0.1, top + (bottom - top) * line / lines, 0.9, top + (bottom - top) * (line + 1) / lines] for line in range(lines)]}
                   for text, top, bottom, *rest in blocks for lines in [rest[0] if rest else 1]],
    }


def test_running_headers_and_footers_repeat_at_the_page_edges_apart_from_numbers():
    pages = [
        page(0, ("Cover title", 0.05, 0.07), ("Body starts here and goes on.", 0.2, 0.5, 6), ("Journal X, Vol. 1, Article 7.", 0.93, 0.95)),
        page(1, ("28:2", 0.077, 0.09), ("J. Xiao et al.", 0.077, 0.09), ("Body text.", 0.2, 0.8, 9), ("Journal X, Vol. 1, Article 7.", 0.92, 0.93)),
        page(2, ("Partitioned Scheduling", 0.077, 0.09), ("28:3", 0.077, 0.09), ("Body text again.", 0.12, 0.8, 9), ("Journal X, Vol. 1, Article 7.", 0.92, 0.93)),
        page(3, ("28:4", 0.077, 0.09), ("J. Xiao et al.", 0.077, 0.09), ("A heading near the top", 0.095, 0.099), ("Journal X, Vol. 1, Article 7.", 0.92, 0.93)),
        page(4, ("Partitioned Scheduling", 0.077, 0.09), ("28:5", 0.077, 0.09), ("Last body.", 0.2, 0.6, 5), ("12", 0.95, 0.96)),
    ]
    assert running_lines(pages) == {
        (0, 2): "page_footer",
        (1, 0): "page_header", (1, 1): "page_header", (1, 3): "page_footer",
        (2, 0): "page_header", (2, 1): "page_header", (2, 3): "page_footer",
        (3, 0): "page_header", (3, 1): "page_header", (3, 3): "page_footer",
        (4, 0): "page_header", (4, 1): "page_header", (4, 3): "page_footer",  # 쪽 번호 하나뿐인 줄
    }  # 첫 쪽 제목·쪽 위의 다른 제목·본문은 되풀이되지 않는다


def test_a_single_page_document_has_only_page_numbers_as_running_lines():
    assert running_lines([page(0, ("Title", 0.05, 0.07), ("Body.", 0.2, 0.5, 3), ("1", 0.95, 0.96))]) == {(0, 2): "page_footer"}


VIEW = (0.0, 0.0, 500.0, 800.0)


def rule(v, left=0.1, right=0.9, height=0.8, filled=False):
    """정본 v(위에서)에 놓인 가로줄 객체 (PDF 사용자 공간)"""
    y = 800 * (1 - v)
    return Graphic("path", (500 * left, y - height / 2, 500 * right, y + height / 2), filled=filled, stroked=not filled)


def test_horizontal_rules_are_thin_wide_paths():
    graphics = [
        rule(0.127),
        rule(0.3, height=0.4, filled=True),  # 채운 얇은 사각형으로 그린 줄
        rule(0.5, left=0.49, right=0.55),  # 분수 막대: 짧다
        Graphic("path", (50, 100, 450, 300), stroked=True),  # 그림 테두리: 두껍다
        Graphic("image", (50, 400, 450, 401)),
        Graphic("path", (50, 500, 450, 500.5)),  # 보이지 않는 경로(잘라내기)
    ]
    assert horizontal_rules(graphics, VIEW) == [pytest.approx((0.1, 0.1265, 0.9, 0.1275)), pytest.approx((0.1, 0.29975, 0.9, 0.30025))]


def box(text, top, bottom, left=0.12, right=0.5, lines=1):
    return ([[left, top + (bottom - top) * line / lines, right, top + (bottom - top) * (line + 1) / lines] for line in range(lines)], text)


def rules_at(*vs, left=0.1, right=0.9):
    return [(left, v - 0.0005, right, v + 0.0005) for v in vs]


def test_blocks_between_table_rules_are_table_content_but_the_caption_is_not():
    blocks = [
        box("Table 1. Description of CAC", 0.105, 0.116, 0.3, 0.7),  # 0 표 위 캡션
        box("Notation", 0.128, 0.139),  # 1
        box("Description", 0.128, 0.139, 0.5, 0.6),  # 2
        box("CAC", 0.142, 0.153),  # 3
        box("the access to r is uncertain at cache level L", 0.195, 0.219, 0.11, 0.58, lines=2),  # 4
        box("Body paragraph after the table that spans the column and goes on.", 0.33, 0.43, 0.09, 0.91, lines=6),  # 5
    ]
    assert table_blocks(blocks, rules_at(0.127, 0.140, 0.207, 0.300)) == {1, 2, 3, 4}


def test_pseudocode_boxes_are_tables_and_their_caption_is_translated():
    blocks = [
        box("PSEUDOCODE 1: CITTA(τ , π)", 0.628, 0.641, 0.09, 0.36),  # 0 위 두 줄 사이의 캡션
        box("1: sort τ in non-decreasing order by a selected criterion 2: ...", 0.649, 0.728, 0.107, 0.636, lines=5),  # 1
        box("return Failed 11: end if=0", 0.799, 0.828, 0.1, 0.27, lines=2),  # 2
        box("Lines 5–7 in the procedure of TaskPartition perform step", 0.853, 0.901, 0.09, 0.91, lines=3),  # 3 아래 본문
    ]
    assert table_blocks(blocks, rules_at(0.624, 0.643, 0.831, left=0.093, right=0.908)) == {1, 2}


def test_pseudocode_box_with_a_wide_input_paragraph_is_still_a_table():
    """의사코드 상자 안에 넓은 여러 줄 입력 문단(Input:·Require:)이 있어도 줄 번호(1:, 12:)가 여럿이면 의사코드다
    (TCPS·CAAS 6쪽 Algorithm 1, 2026-10-05 사용자 요청: 알고리즘 수도코드는 번역하지 않는다). 캡션은 그대로 번역한다."""
    blocks = [
        box("Algorithm 1 partitioned LLC for partitioned scheduling", 0.094, 0.106, 0.519, 0.896),  # 0 캡션
        box("Input: Task parameters, number of cores: m, number of tasks: n, sensitivity vector, cache size", 0.114, 0.173, 0.52, 0.913, lines=4),  # 1
        box("1: TaskBuckets θ ← groupbySensitivity(G, n, m, maxI)", 0.176, 0.188, 0.53, 0.89),  # 2
        box("6:", 0.256, 0.265, 0.53, 0.539),  # 3
        box("return schedulable 11: Sort the utilization of cores π in increasing order 12: for all πi ∈ π do 13:", 0.314, 0.371, 0.524, 0.871, lines=4),  # 4
        box("We observe that a taskset can be unschedulable onto m cores but may become schedulable", 0.759, 0.906, 0.519, 0.915, lines=11),  # 5 아래 본문
    ]
    assert table_blocks(blocks, rules_at(0.091, 0.1095, 0.5555, left=0.519, right=0.912)) == {1, 2, 3, 4}
    # 줄 번호처럼 보이는 글이 둘뿐인 본문 문단(비율 1:2, 시각 10:30은 줄 번호가 아니다)은 그대로 본문이다
    prose = [box("Ratio 1:2 at 10:30, see step 1: then step 2: for the whole column width of the page.", 0.3, 0.4, 0.1, 0.9, lines=6)]
    assert table_blocks(prose, rules_at(0.25, 0.29, 0.41)) == set()  # 가로줄 셋(둘이면 짧은 줄 조건이 먼저 뺀다)


def test_body_paragraphs_between_rules_are_not_tables():
    # 위아래 줄로 둘러싼 초록(본문 폭 여러 줄 문단)과, 멀리 떨어진 두 줄(머리글 밑줄과 바닥글 윗줄)
    abstract = [box("Abstract text that runs over the full width of the column for several lines.", 0.3, 0.4, 0.1, 0.9, lines=6)]
    assert table_blocks(abstract, rules_at(0.29, 0.41)) == set()
    page_lines = [box("Short line", 0.3, 0.31), box("Another short line", 0.5, 0.51)]
    assert table_blocks(page_lines, rules_at(0.095, 0.91)) == set()


def test_two_rules_make_a_table_only_around_short_lines():
    cells = [box("Name", 0.2, 0.21), box("expint", 0.22, 0.23), box("630,291", 0.22, 0.23, 0.6, 0.7)]
    assert table_blocks(cells, rules_at(0.19, 0.24)) == {0, 1, 2}
    one = [box("Only one short line", 0.2, 0.21)]
    assert table_blocks(one, rules_at(0.19, 0.24)) == set()


def test_body_text_between_two_tables_in_the_same_column_is_not_a_table():
    """같은 폭 가로줄이 이어져도(표 둘이 한 단에 위아래로) 그 사이 본문 문단은 표가 아니다."""
    blocks = [
        box("a", 0.11, 0.115),  # 0 위 표 칸
        box("Body paragraph between the two tables that spans the full column width.", 0.27, 0.40, 0.1, 0.9, lines=6),  # 1
        box("b", 0.45, 0.455),  # 2 아래 표 칸
    ]
    assert table_blocks(blocks, rules_at(0.10, 0.12, 0.25, 0.42, 0.44, 0.55)) == {0, 2}
