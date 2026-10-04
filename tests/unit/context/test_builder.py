"""문맥 근거 고르기와 예산 (IMPL §7.2). 합성 Anchor·문단으로 확인한다."""

import pytest

from paperloom.context import builder
from paperloom.context.builder import MAX_IMAGES, MAX_TEXT_CHARS, Block, Choice, VersionText, build
from paperloom.reading.models import AnchorOut

LONG = "x" * 200  # 앞뒤 문단으로 고를 만큼 긴 글


def anchor(anchor_id: str, page: int, box: tuple[float, float, float, float], quote: str = "selected words", kind: str = "text", display=None):
    u0, v0, u1, v1 = box
    return AnchorOut(
        schema_version="anchor.v1",
        kind=kind,
        anchor_id=anchor_id,
        version_id="v",
        page_index=page,
        quads=[[u0, v0, u1, v0, u1, v1, u0, v1]],
        quote=quote,
        display_quote=display,
        prefix="",
        suffix="",
        created_at="now",
    )


def block(block_id: str, page: int, v0: float, v1: float, text: str = LONG, flags=()) -> Block:
    lines = []
    v = v0
    while v < v1 - 1e-9:  # 줄 높이 0.02
        lines.append((0.1, v, 0.9, min(v + 0.02, v1)))
        v += 0.025
    return Block(block_id, page, text, tuple(lines), tuple(flags), line_height=0.02)


# 1쪽: 머리글, A, B, C, 쪽 번호, 바닥글. 0쪽: D와 바닥글
PAGE0 = [block("D", 0, 0.70, 0.80, "D" + LONG), block("foot0", 0, 0.95, 0.97, "Journal footer line on page zero")]
PAGE1 = [
    block("head", 1, 0.03, 0.05, "Running header with the paper title"),
    block("A", 1, 0.20, 0.30, "A" + LONG),
    block("B", 1, 0.32, 0.42, "B" + LONG, flags=("unmapped_chars",)),
    block("num", 1, 0.50, 0.52, "28:5"),
    block("C", 1, 0.55, 0.60, "C" + LONG),
    block("foot1", 1, 0.95, 0.97, "Journal footer line on page one"),
]
TEXT = VersionText(extracted=True, pages={0: ("usable", ()), 1: ("usable", ("two_columns",))}, blocks=PAGE0 + PAGE1)
IN_B = (0.2, 0.322, 0.5, 0.338)  # B의 첫 줄
IN_A = (0.2, 0.202, 0.5, 0.218)  # A의 첫 줄


def run(*choices: Choice, text: VersionText = TEXT):
    return build(list(choices), {"v": text}, {"v": "src_1"})


def roles(evidence) -> list[tuple[str, str | None]]:
    return [(item.role, item.block_id) for item in evidence]


def test_selection_gets_its_paragraph_and_neighbours_skipping_headers_and_short_bits():
    evidence, limits = run(Choice(anchor("a1", 1, IN_B), True, True))

    assert roles(evidence) == [
        ("selected_text", None),
        ("containing_paragraph", "B"),
        ("previous_paragraph", "A"),
        ("following_paragraph", "C"),  # 쪽 번호 "28:5"는 건너뛴다
    ]
    assert [item.evidence_id for item in evidence] == ["e1", "e2", "e3", "e4"]
    assert evidence[0].regions == [[0.2, 0.322, 0.5, 0.338]] and evidence[1].regions[0] == [0.1, 0.32, 0.9, 0.34]
    assert evidence[1].quality_flags == ["unmapped_chars", "two_columns"]
    assert all(item.text_status == "usable" and item.source_ref == "src_1" for item in evidence)
    assert limits.used_text_chars == len("selected words") + 3 * len(LONG) + 3
    assert (limits.truncated, limits.excluded) == (False, [])


def test_previous_paragraph_crosses_to_the_page_before_skipping_its_footer():
    evidence, _ = run(Choice(anchor("a1", 1, IN_A), True, True))
    assert roles(evidence)[2:] == [("previous_paragraph", "D"), ("following_paragraph", "B")]
    assert evidence[2].page_index == 0


def test_selection_covering_its_paragraph_does_not_repeat_it():
    evidence, _ = run(Choice(anchor("a1", 1, IN_B, quote="B" + LONG), True, True))
    assert [role for role, _ in roles(evidence)] == ["selected_text", "previous_paragraph", "following_paragraph"]


def test_context_can_be_turned_off_per_selection():
    evidence, limits = run(Choice(anchor("a1", 1, IN_B), False, True))
    assert roles(evidence) == [("selected_text", None)] and limits.excluded == []


def test_shared_paragraph_appears_once():
    evidence, _ = run(Choice(anchor("a1", 1, IN_B), True, True), Choice(anchor("a2", 1, (0.2, 0.347, 0.5, 0.363)), True, True))
    assert roles(evidence) == [
        ("selected_text", None),
        ("containing_paragraph", "B"),
        ("previous_paragraph", "A"),
        ("following_paragraph", "C"),
        ("selected_text", None),
    ]


def test_long_selection_is_truncated_and_context_is_left_out_with_reasons():
    evidence, limits = run(Choice(anchor("a1", 1, IN_B, quote="q" * (MAX_TEXT_CHARS + 500)), True, True))

    assert roles(evidence) == [("selected_text", None)]
    assert (len(evidence[0].text), evidence[0].truncated) == (MAX_TEXT_CHARS, True)
    # 문단보다 긴 선택은 든 문단을 따로 붙이지 않는다. 앞뒤 문단은 한도 때문에 빠진다.
    assert [(item.role, item.reason) for item in limits.excluded] == [
        ("previous_paragraph", "text_budget"),
        ("following_paragraph", "text_budget"),
    ]
    assert (limits.used_text_chars, limits.truncated) == (MAX_TEXT_CHARS, True)


def test_context_is_added_whole_in_priority_order_while_it_fits(monkeypatch):
    # 선택(14자)과 든 문단(201자)만 들어가는 한도
    monkeypatch.setattr(builder, "MAX_TEXT_CHARS", len("selected words") + len(LONG) + 1 + 5)
    evidence, limits = run(Choice(anchor("a1", 1, IN_B), True, True))

    assert [role for role, _ in roles(evidence)] == ["selected_text", "containing_paragraph"]
    assert [item.role for item in limits.excluded] == ["previous_paragraph", "following_paragraph"]
    assert not evidence[0].truncated and limits.truncated


@pytest.mark.parametrize(
    ("text", "box", "reason", "status"),
    [
        (VersionText(extracted=False, pages={}, blocks=[]), IN_B, "text_not_extracted", None),
        (TEXT, (0.2, 0.44, 0.5, 0.46), "no_extracted_text", "usable"),  # 문단 사이 빈 곳
    ],
)
def test_missing_text_is_reported(text, box, reason, status):
    evidence, limits = run(Choice(anchor("a1", 1, box), True, True), text=text)

    assert roles(evidence) == [("selected_text", None)]
    assert evidence[0].text_status == status
    assert [(item.role, item.reason, item.page_index) for item in limits.excluded] == [("context", reason, 1)]


def test_regions_get_images_up_to_the_limit_and_no_neighbouring_paragraphs():
    figures = [Choice(anchor(f"f{n}", 1, IN_B, quote="", kind="figure"), True, True) for n in range(MAX_IMAGES + 1)]
    no_image = Choice(anchor("table", 1, IN_A, quote="", kind="table"), True, False)
    evidence, limits = run(*figures, no_image)

    assert [(item.role, item.kind, item.image is not None) for item in evidence] == [
        ("selected_region", "figure", True),
        ("selected_region", "figure", True),
        ("selected_region", "figure", False),
        ("selected_region", "table", False),
    ]
    assert evidence[0].image.url == "/api/v1/anchors/f0/image?scale=2"
    assert [(item.anchor_id, item.reason) for item in limits.excluded] == [(f"f{MAX_IMAGES}", "image_limit")]
    assert (limits.used_images, limits.used_text_chars, limits.truncated) == (MAX_IMAGES, 0, False)


# 그림 영역(1쪽 0.20–0.40) 안에 축 글자 둘, 바로 아래 캡션, 조금 아래 "Table 2"로 시작하는 본문, 멀리 표 캡션
FIGURE_BOX = (0.1, 0.20, 0.9, 0.40)


def small(block_id: str, box: tuple[float, float, float, float], text: str) -> Block:
    return Block(block_id, 1, text, (box,), (), line_height=0.015)


FIGURE_TEXT = VersionText(
    extracted=True,
    pages={1: ("usable", ())},
    blocks=[
        small("axis", (0.2, 0.30, 0.3, 0.315), "time (s)"),
        small("label", (0.6, 0.25, 0.7, 0.265), "τ1 τ2"),
        small("cap", (0.1, 0.41, 0.8, 0.425), "Fig. 3. Cache interference delays τ3."),
        block("body", 1, 0.45, 0.60, "Table 2 is discussed later. " + LONG),
        small("tcap", (0.1, 0.80, 0.8, 0.815), "TABLE II. A table far below the figure"),
    ],
)


def figure(box=FIGURE_BOX, context=True):
    return Choice(anchor("fig", 1, box, quote="", kind="figure"), context, True)


def test_region_gets_its_nearest_caption_and_the_text_inside_it():
    evidence, limits = run(figure(), text=FIGURE_TEXT)

    assert [(item.role, item.kind, item.block_id) for item in evidence] == [
        ("selected_region", "figure", None),
        ("caption", "figure", "cap"),  # 가까운 "Table 2 …" 본문보다 더 가깝다
        ("region_text", "figure", None),
    ]
    assert evidence[1].text == "Fig. 3. Cache interference delays τ3."
    assert evidence[2].text == "time (s)\nτ1 τ2"  # 읽는 순서, 줄을 나눠 한 근거
    assert evidence[2].regions == [[0.2, 0.30, 0.3, 0.315], [0.6, 0.25, 0.7, 0.265]]
    assert evidence[2].anchor_id == "fig" and evidence[2].image is None
    assert limits.used_text_chars == len(evidence[1].text) + len(evidence[2].text)


def test_caption_inside_the_region_is_the_caption_not_region_text():
    evidence, _ = run(figure((0.1, 0.20, 0.9, 0.43)), text=FIGURE_TEXT)
    assert [(item.role, item.block_id) for item in evidence] == [("selected_region", None), ("caption", "cap"), ("region_text", None)]
    assert evidence[2].text == "time (s)\nτ1 τ2"


def test_caption_far_from_the_region_is_not_used():
    evidence, limits = run(figure((0.1, 0.05, 0.9, 0.15)), text=FIGURE_TEXT)  # 가장 가까운 캡션도 0.26 떨어짐
    assert roles(evidence) == [("selected_region", None)]
    assert limits.excluded == []


def test_region_context_can_be_turned_off():
    evidence, _ = run(figure(context=False), text=FIGURE_TEXT)
    assert roles(evidence) == [("selected_region", None)]


def test_caption_comes_before_region_text_in_the_budget(monkeypatch):
    monkeypatch.setattr(builder, "MAX_TEXT_CHARS", len("Fig. 3. Cache interference delays τ3.") + 3)
    evidence, limits = run(figure(), text=FIGURE_TEXT)
    assert [item.role for item in evidence] == ["selected_region", "caption"]
    assert [(item.role, item.reason) for item in limits.excluded] == [("region_text", "text_budget")]


@pytest.mark.parametrize(
    ("text", "is_caption"),
    [
        ("Figure 1: Overview", True),
        ("Fig.3 Results", True),
        ("TABLE II. Parameters", True),
        ("Algorithm 2 Partitioning", True),
        ("그림 4. 구조", True),
        ("표 1 결과", True),
        ("Figure illustrates the idea", False),
        ("Tables are listed below", False),
        ("Table is shown", False),
        ("The figure 1 shows", False),
    ],
)
def test_caption_pattern(text, is_caption):
    assert bool(builder.CAPTION.match(text)) is is_caption


def test_estimated_display_text_is_marked():
    evidence, _ = run(Choice(anchor("a1", 1, IN_B, display="f^j_k"), False, True))
    assert (evidence[0].display_text, evidence[0].quality_flags) == ("f^j_k", ["display_text_estimated", "two_columns"])


# 쪽을 넘어 이어지는 문단: 2쪽 P(끝 문단) → 3쪽 첫 문단 Q가 소문자로 시작한다. 3쪽 머리글은 건너뛴다.
SPLIT = VersionText(
    extracted=True,
    pages={2: ("usable", ()), 3: ("usable", ())},
    blocks=[
        block("O", 2, 0.30, 0.40, "O starts a paragraph that ends on page two." + LONG),
        block("P", 2, 0.70, 0.88, "P begins a paragraph that is continued on the next" + LONG),
        block("head3", 3, 0.03, 0.05, "Running header with the paper title"),
        block("Q", 3, 0.12, 0.20, "is preempted and continues the paragraph from page two" + LONG),
        block("R", 3, 0.25, 0.35, "R is the next paragraph on page three." + LONG),
        block("S", 3, 0.40, 0.50, "S follows R." + LONG),
    ],
)
IN_R = (0.2, 0.252, 0.5, 0.268)
IN_Q = (0.2, 0.122, 0.5, 0.138)
IN_O = (0.2, 0.302, 0.5, 0.318)


def test_previous_paragraph_split_across_pages_is_sent_whole():
    evidence, limits = run(Choice(anchor("a1", 3, IN_R), True, True), text=SPLIT)

    assert roles(evidence) == [
        ("selected_text", None),
        ("containing_paragraph", "R"),
        ("previous_paragraph", "P"),  # 문장 중간에서 시작하는 Q만 보내지 않는다
        ("previous_paragraph", "Q"),
        ("following_paragraph", "S"),
    ]
    assert [(item.page_index, "split_across_pages" in item.quality_flags) for item in evidence[2:4]] == [(2, True), (3, True)]
    assert "split_across_pages" not in evidence[1].quality_flags
    assert limits.used_text_chars == sum(len(item.text) for item in evidence)


def test_selection_in_a_continued_part_gets_the_whole_paragraph():
    evidence, _ = run(Choice(anchor("a1", 3, IN_Q), True, True), text=SPLIT)
    assert roles(evidence) == [
        ("selected_text", None),
        ("containing_paragraph", "P"),
        ("containing_paragraph", "Q"),
        ("previous_paragraph", "O"),
        ("following_paragraph", "R"),
    ]


def test_following_paragraph_continues_onto_the_next_page():
    evidence, _ = run(Choice(anchor("a1", 2, IN_O), True, True), text=SPLIT)
    assert roles(evidence)[2:] == [("following_paragraph", "P"), ("following_paragraph", "Q")]


def test_capitalised_first_paragraph_is_a_new_paragraph():
    blocks = [b if b.block_id != "Q" else Block("Q", 3, "It starts a new paragraph" + LONG, b.regions, (), 0.02) for b in SPLIT.blocks]
    evidence, _ = run(Choice(anchor("a1", 3, IN_R), True, True), text=VersionText(True, SPLIT.pages, blocks))
    assert roles(evidence)[2] == ("previous_paragraph", "Q")


def test_footnote_at_the_bottom_of_the_page_is_not_where_the_paragraph_continues():
    # 2쪽 아래에 작은 글자의 각주가 있다(줄 높이 0.012, 본문 0.02). 3쪽 Q는 각주가 아니라 P에서 이어진다.
    footnote = Block("note", 2, "Authors' address: somewhere, some university" + LONG, ((0.1, 0.85, 0.9, 0.862), (0.1, 0.865, 0.9, 0.877)), (), 0.012)
    blocks = [*SPLIT.blocks[:2], footnote, *SPLIT.blocks[2:]]
    evidence, _ = run(Choice(anchor("a1", 3, IN_R), True, True), text=VersionText(True, SPLIT.pages, blocks))
    assert roles(evidence)[2:4] == [("previous_paragraph", "P"), ("previous_paragraph", "Q")]


def test_split_paragraph_is_left_out_whole_when_it_does_not_fit(monkeypatch):
    budget = len("selected words") + len(SPLIT.blocks[4].text) + len(SPLIT.blocks[3].text) + 5  # 선택 + R + Q만
    monkeypatch.setattr(builder, "MAX_TEXT_CHARS", budget)
    evidence, limits = run(Choice(anchor("a1", 3, IN_R), True, True), text=SPLIT)

    assert [role for role, _ in roles(evidence)] == ["selected_text", "containing_paragraph", "following_paragraph"]
    assert [(item.role, item.page_index) for item in limits.excluded] == [("previous_paragraph", 2)]


@pytest.mark.parametrize(
    ("quote", "display", "image"),
    [
        ("DBF (τi , t ) = max ( 0, ( ⌊ t − Di Ti ⌋ + 1 ) × Ci )", None, True),  # 2026-10-02 사용자 확인: 분수가 납작해진 식
        ("scheduled by EDFnp on each core", "scheduled by EDF_np on each core", True),  # 식 번호·정렬 없는 본문 속 수식
        ("𝜏𝑘 interferes", None, True),
        ("A plain sentence without math.", None, False),
    ],
)
def test_math_like_selection_gets_its_line_image(quote, display, image):
    evidence, limits = run(Choice(anchor("m", 1, IN_B, quote=quote, display=display), False, True))
    assert (evidence[0].image is not None) is image
    assert limits.used_images == int(image)


def test_math_images_share_the_image_limit_and_can_be_turned_off():
    math = [Choice(anchor(f"m{n}", 1, IN_B, quote="x ≤ y"), False, True) for n in range(MAX_IMAGES)]
    figure = Choice(anchor("f", 1, IN_A, quote="", kind="figure"), False, True)
    off = Choice(anchor("off", 1, IN_A, quote="a ≤ b"), False, False)
    evidence, limits = run(*math, figure, off)
    assert [item.image is not None for item in evidence] == [True] * MAX_IMAGES + [False, False]
    assert [(item.anchor_id, item.role, item.reason) for item in limits.excluded] == [("f", "selected_region", "image_limit")]


def pages_of(pages, budget, first_number=1, text=TEXT):
    return builder.page_texts(text, pages, budget, "src_1", "v", first_number)


def test_page_texts_take_pages_in_order_without_headers_up_to_the_budget():
    evidence, used, excluded = pages_of(None, 100_000)
    assert [(item.role, item.page_index, item.block_id) for item in evidence] == [("paper_text", 0, "D"), ("paper_text", 1, "A")]
    # 첫 쪽은 여백의 글도 넣고(제목·저자가 쪽 위에 있다), 둘째 쪽부터는 머리글·바닥글을 뺀다
    assert "Journal footer line on page zero" in evidence[0].text
    assert "Running header" not in evidence[1].text and "page one" not in evidence[1].text
    assert evidence[1].text.startswith("A" + LONG) and "28:5" in evidence[1].text  # 짧은 조각은 머리글·바닥글이 아니면 남긴다
    assert (used, excluded) == (sum(len(item.text) for item in evidence), [])
    # 문단 근거(¶)를 위해 문단마다 추출 블록을 차례대로 둔다. 글은 문단 사이를 빈 줄로 잇는다
    assert [len(item.text.split("\n\n")) for item in evidence] == [len(item.block_ids) for item in evidence]
    assert evidence[1].block_ids[0] == "A" and evidence[0].block_ids[0] == "D"

    first_page = len(evidence[0].text)
    evidence, used, excluded = pages_of(None, first_page + 50)
    assert [(item.page_index, item.truncated, len(item.text)) for item in evidence] == [(0, False, first_page), (1, True, 50)]
    assert len(evidence[1].block_ids) == len(evidence[1].text.split("\n\n"))  # 잘린 쪽은 넣은 문단까지만
    assert (used, excluded) == (first_page + 50, [])

    evidence, used, excluded = pages_of(None, first_page)
    assert [item.page_index for item in evidence] == [0]
    assert [(item.role, item.page_index, item.reason) for item in excluded] == [("paper_text", 1, "text_budget")]


def test_page_texts_of_one_page_continue_the_evidence_numbers():
    evidence, _, excluded = pages_of([1], 100_000, first_number=3)
    assert [(item.evidence_id, item.page_index, item.block_id) for item in evidence] == [("e3", 1, "A")]
    assert "Running header" not in evidence[0].text and excluded == []


def test_page_texts_report_pages_without_text():
    evidence, used, excluded = pages_of([5], 100_000)
    assert (evidence, used) == ([], 0)
    assert [(item.role, item.page_index, item.reason) for item in excluded] == [("paper_text", 5, "no_extracted_text")]
    evidence, _, excluded = pages_of(None, 100_000, text=VersionText(extracted=False, pages={}, blocks=[]))
    assert evidence == [] and [(item.role, item.reason) for item in excluded] == [("paper_text", "text_not_extracted")]
