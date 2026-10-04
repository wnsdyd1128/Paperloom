"""글자 → 줄 → 문단, 읽는 순서, 쪽·문서 추출 상태 (IMPL §5.3). 합성 글자 상자로 확인한다."""

from dataclasses import replace

import pytest

from paperloom.documents.text_layout import (
    Char,
    block_text,
    build_blocks,
    build_lines,
    classify_page,
    document_status,
    layout_page,
    reading_order,
)

H = 10.0  # 본문 글자 높이(loose box)
W = 5.0  # 글자 폭
PAGE = (0.0, 0.0, 600.0, 800.0)


def word(text: str, x: float, bottom: float, height: float = H, unmapped: bool = False) -> list[Char]:
    """글자마다 W 폭의 상자. 공백은 위치 없는 글자(pdfium이 넣은 공백)다."""
    chars = []
    for index, ch in enumerate(text):
        box = (x + index * W, bottom, x + (index + 1) * W, bottom + height)
        chars.append(Char(ch, None) if ch == " " else Char(ch, box, unmapped))
    return chars


def line(text: str, x: float, bottom: float, height: float = H) -> list[Char]:
    return word(text, x, bottom, height) + [Char("\n", None)]


def texts(lines) -> list[str]:
    return [item.text for item in lines]


class TestLines:
    def test_scripts_stay_on_the_line_and_stacked_scripts_may_step_back(self):
        # f, 위첨자 j(올림), 같은 x로 돌아간 아래첨자 k(내림), 이어지는 본문
        chars = word("f", 0, 100) + word("j", W, 104, 7) + word("k", W - 1, 97, 7) + word(" = d", 2 * W, 100)
        assert texts(build_lines(chars)) == ["fjk = d"]

    def test_a_subscript_under_a_wide_superscript_stays_on_the_line(self):
        """사용자 논문 τ^na_p: 위첨자 "na" 끝에서 아래첨자 p가 9.8pt 돌아갔다(줄 높이 9.4pt보다 멀리). 줄이 끊겨 수식 조각만 원문으로
        남고 앞뒤는 번역되어 겹쳤다(2026-10-04). 앞의 본 크기 글자(τ)보다 왼쪽으로 가지 않으면 같은 줄이다."""
        chars = word("is ", 0, 100) + word("τ", 3 * W, 100) + word("max", 4 * W, 104, 7) + word("p", 4 * W, 97, 7) + word("), next", 7 * W, 100)
        assert texts(build_lines(chars)) == ["is τmaxp), next"]

    def test_a_word_after_stacked_scripts_is_measured_from_the_end_of_the_wider_script(self):
        """사용자 논문 16쪽 "let I^min_k be the smallest …": 아래첨자 k는 위첨자 "min" 앞쪽 아래에 있어, k 끝에서 다음 낱말까지는
        줄 높이의 1.5배를 넘었지만 "min" 끝에서는 가깝다. 앞 글자 끝에서 재어 한 줄이 둘로 끊겼다(2026-10-04)."""
        chars = word("let ", 0, 100) + word("I", 20, 100) + word("min", 25, 104, 7) + word("k", 24, 97, 7) + word(" be", 41, 100)
        assert texts(build_lines(chars)) == ["let Imink be"]

    def test_a_deep_script_of_an_inline_fraction_stays_on_the_line(self):
        """사용자 논문 16쪽 "γ = max_k (D_k−C_k)/I^min_k iterations": 분모의 아래첨자 k는 줄의 가장 큰 글자 범위보다 아래지만 이미
        줄에 든 분모와 겹친다. 따로 떨어져 한 글자 문단이 되고 뒤 "iterations …"도 새 문단이 되었다(2026-10-04)."""
        chars = word("at x", 0, 100) + word("(a-c)", 20, 105, 7) + word("b", 25, 96, 7) + word("k", 30, 92, 5) + word(" iter", 47, 100)
        assert texts(build_lines(chars)) == ["at x(a-c)bk iter"]

    def test_symbol_with_a_taller_box_does_not_push_the_next_subscript_out(self):
        # 실제 논문: ≤의 상자가 본문보다 위로 0.7pt 크고, 바로 뒤 아래첨자 k의 가운데가 그 아래로 벗어났다
        chars = word("d", 0, 100) + word("≤", W, 100.7, 10.3) + word("k", 2 * W, 96.8, 7)
        assert texts(build_lines(chars)) == ["d≤k"]

    def test_next_line_and_far_gap_start_new_lines(self):
        chars = line("left cell", 0, 100) + word("right cell", 200, 100) + line(" next", 0, 88)
        assert texts(build_lines(chars)) == ["left cell", "right cell", "next"]

    def test_line_end_hyphen_marker_becomes_a_hyphen(self):
        assert texts(build_lines(word("compo\x02", 0, 100))) == ["compo-"]


class TestBlocks:
    def blocks(self, chars):
        return [block_text(block.lines) for block in build_blocks(build_lines(chars))]

    def test_a_drop_cap_paragraph_stays_one_paragraph(self):
        """IEEE 논문 들어가기의 큰 첫 글자(두 줄 높이): 그 옆 두 줄과 아래 줄이 한 문단이다. 큰 글자가 둘째 줄까지 내려와
        첫 줄 상자가 둘째 줄과 겹쳐도 새 문단이 아니다 (2026-10-03 사용자 논문: 첫 줄만 따로 떨어져 번역이 가려졌다)."""
        cap = [Char("A", (0, 676, 20, 712))]
        chars = (
            cap
            + line("DVANCEMENTS in chip design have widened the", 22, 700)
            + line("gap between memory and processor. The recent", 22, 688)
            + line("processor has a long latency for memory.", 0, 676)
            + line("Next paragraph starts indented here", 12, 652)
            + line("and continues.", 0, 640)
        )
        blocks = build_blocks(build_lines(chars))
        assert [block_text(block.lines) for block in blocks] == [
            "ADVANCEMENTS in chip design have widened the gap between memory and processor. The recent processor has a long latency for memory.",
            "Next paragraph starts indented here and continues.",
        ]
        assert blocks[0].box[1] == 676  # 문단 상자는 큰 글자를 덮는다

    def test_first_line_indent_starts_a_paragraph(self):
        chars = (
            line("Para one starts indented here", 12, 700)
            + line("and continues on the left edge", 0, 688)
            + line("short end.", 0, 676)
            + line("Para two starts indented", 12, 664)
            + line("and ends.", 0, 652)
        )
        assert self.blocks(chars) == [
            "Para one starts indented here and continues on the left edge short end.",
            "Para two starts indented and ends.",
        ]

    def test_an_indented_full_line_after_indented_lines_starts_the_paragraph_that_continues_at_the_margin(self):
        """사용자 논문 16쪽: 들여 쓴 짧은 문단 줄들("Proof Sketch: …", "From condition 1.9 …") 뒤의 들여 쓴 줄 "By the above …"이
        다음 줄 "of IP(…) is also feasible …"(왼쪽 끝)과 한 문단이다. 앞 줄들과 같은 들여쓰기라 묶이고 다음 줄만 따로 떨어져, 그 한 줄
        번역이 한 줄 자리에 눌려 아주 작아졌다(2026-10-04). 끝까지 찬 들여 쓴 마지막 줄은 떼어 다음 줄과 잇는다."""
        full = 78  # 들여 쓴 줄(x=10)의 글자 수: 오른쪽 끝 400
        chars = (
            line("Proof Sketch: We show the proof sketch.", 10, 700)
            + line("From condition one we can prove the following claim for every task in the set".ljust(full, "x"), 10, 688)
            + line("By the above statement and the constraints we can prove that any solution".ljust(full, "y"), 10, 676)
            + line("of IP is also feasible. Thus,", 0, 664)
        )
        blocks = self.blocks(chars)
        assert len(blocks) == 2
        assert blocks[0].startswith("Proof Sketch: We show the proof sketch. From condition one")
        assert blocks[1].startswith("By the above statement") and blocks[1].endswith("of IP is also feasible. Thus,")

    def test_an_indented_list_item_ending_short_does_not_join_the_next_paragraph(self):
        """들여 쓴 항목의 마지막 줄이 짧게 끝나면 그 뒤 왼쪽 끝 줄은 새 문단이다(떼어 잇지 않는다)."""
        chars = (
            line("- first item text that is long enough to wrap".ljust(78, "z"), 10, 700)
            + line("- second item ends short.", 10, 688)
            + line("Next paragraph without indent.", 0, 676)
        )
        assert self.blocks(chars) == [
            "- first item text that is long enough to wrap" + "z" * 33 + " - second item ends short.",
            "Next paragraph without indent.",
        ]

    def test_a_tall_operator_reaching_into_the_next_line_does_not_split_the_paragraph(self):
        """사용자 논문 16쪽: 줄 첫머리의 큰 합 기호(Σ, 본문 줄 높이의 2.5배)가 다음 줄 아래까지 내려와 줄 상자가 겹쳤고, 다음 줄
        "4n + m − 1 constraints …"부터 새 문단이 되었다(2026-10-04). 줄 사이는 큰 기호를 뺀 글자로 잰다."""
        chars = (
            line("Inequality one can be replaced by the sum", 0, 200)
            + [Char("Σ", (0, 174, 8, 198))]
            + line(" of the terms and we have totally n variables", 8, 188)
            + line("and m constraints in the problem.", 0, 176)
        )
        chars = [replace(ch, size=10.0) if ch.box else ch for ch in chars]  # 실제처럼 Σ도 본문과 같은 글꼴 크기
        assert self.blocks(chars) == [
            "Inequality one can be replaced by the sum Σ of the terms and we have totally n variables and m constraints in the problem."
        ]

    def test_a_full_last_line_of_a_list_item_stays_with_its_item(self):
        """사용자 논문 CAAS의 기여 목록 (2026-10-04): 항목 둘째 줄(내어 쓰기)이 끝까지 차고 다음 줄이 왼쪽 글머리표로 시작하면, 그 둘째
        줄을 떼어 다음 항목에 붙였다(들여 쓴 첫 줄로 보았다). 글머리표·번호로 시작하는 줄은 새 항목이다."""
        chars = (
            line("• A model that predicts the most suitable", 0, 700)
            + line("scheduling architecture via reuse distance", 10, 688)
            + line("• An integrated framework that automates it", 0, 676)
            + line("and allocates tasks.", 10, 664)
        )
        assert self.blocks(chars) == [
            "• A model that predicts the most suitable scheduling architecture via reuse distance",
            "• An integrated framework that automates it and allocates tasks.",
        ]

    def test_hanging_indent_item_stays_together(self):
        chars = (
            line("[1] A reference that wraps onto", 0, 700)
            + line("the next indented line.", 12, 688)
            + line("[2] Next reference", 0, 676)
        )
        assert self.blocks(chars) == ["[1] A reference that wraps onto the next indented line.", "[2] Next reference"]

    def test_short_heading_then_indented_paragraph_are_separate(self):
        chars = line("3.1 Model", 0, 700) + line("Indented paragraph text that is long", 12, 688)
        assert self.blocks(chars) == ["3.1 Model", "Indented paragraph text that is long"]

    def test_size_change_and_large_gap_split(self):
        chars = line("Title", 0, 700, 18) + line("body line", 0, 686) + line("after gap", 0, 660)
        assert self.blocks(chars) == ["Title", "body line", "after gap"]


class TestReadingOrder:
    def ordered(self, chars):
        blocks, two_columns = reading_order(build_blocks(build_lines(chars)), PAGE)
        return [block_text(block.lines) for block in blocks], two_columns

    def test_two_columns_read_left_then_right_between_full_width_blocks(self):
        chars = (
            line("Full width heading across the page middle", 200, 760)
            + line("right column first paragraph", 320, 700)
            + line("left column first paragraph", 20, 700)
            + line("left column second paragraph", 20, 640)
            + line("right column second paragraph", 320, 640)
            + line("Footer across the middle line", 230, 40)
        )
        assert self.ordered(chars) == (
            [
                "Full width heading across the page middle",
                "left column first paragraph",
                "left column second paragraph",
                "right column first paragraph",
                "right column second paragraph",
                "Footer across the middle line",
            ],
            True,
        )

    def test_single_column_keeps_pdf_order(self):
        chars = line("Header", 20, 760) + line("Body text in one column across the page", 20, 700) + line("Side note", 400, 720)
        assert self.ordered(chars) == (["Header", "Body text in one column across the page", "Side note"], False)


class TestBlockText:
    @pytest.mark.parametrize(
        ("lines", "expected"),
        [
            (["compo-", "sitional"], "compositional"),  # 줄 끝에서 나뉜 낱말
            (["Noord-", "Holland"], "Noord- Holland"),  # 대문자로 이어지면 하이픈을 둔다
            (["x -", "y"], "x - y"),  # 하이픈 앞이 글자가 아니다
            (["soft­", "hyphen"], "softhyphen"),
            (["ﬁxture  and", "ﬂow"], "fixture and flow"),  # 합자 → NFKC
            (["bad\x01char"], "badchar"),  # 제어 문자는 뺀다
        ],
    )
    def test_join(self, lines, expected):
        built = [build_lines(word(text, 0, 700 - 12 * index))[0] for index, text in enumerate(lines)]
        assert block_text(built) == expected


class TestStatus:
    @pytest.mark.parametrize(
        ("chars", "unmapped", "coverage", "expected"),
        [
            (500, 0, 0.0, ("usable", [])),
            (500, 5, 0.0, ("usable", [])),  # 1% 깨짐은 정상
            (500, 20, 0.0, ("partial", ["unmapped_chars"])),
            (100, 0, 1.0, ("partial", ["mostly_image"])),  # 스캔 쪽 + 내려받기 문구
            (500, 0, 1.0, ("usable", [])),  # 글이 많은 쪽의 배경 이미지
            (3, 0, 1.0, ("image_only", ["no_text"])),
            (0, 0, 0.1, ("unknown", ["no_text"])),  # 빈 쪽, 벡터 그림만 있는 쪽
        ],
    )
    def test_classify_page(self, chars, unmapped, coverage, expected):
        assert classify_page(chars, unmapped, coverage) == expected

    @pytest.mark.parametrize(
        ("pages", "expected"),
        [
            ([("usable", {}), ("unknown", {})], ("INDEXED", None)),  # 빈 쪽은 낮추지 않는다
            ([("usable", {}), ("partial", {})], ("PARTIAL", None)),
            ([("usable", {}), ("image_only", {})], ("PARTIAL", None)),
            ([("usable", {}), ("unknown", {"error": "RESOURCE_LIMIT"})], ("PARTIAL", None)),
            ([("image_only", {}), ("unknown", {})], ("FAILED", "NO_TEXT_LAYER")),
            ([("unknown", {}), ("unknown", {})], ("FAILED", "NO_TEXT_LAYER")),
            ([("unknown", {"error": "RESOURCE_LIMIT"}), ("unknown", {})], ("FAILED", "RESOURCE_LIMIT")),
        ],
    )
    def test_document_status(self, pages, expected):
        assert document_status(pages) == expected


@pytest.mark.parametrize("rotation", [90, 180, 270])
def test_rotated_text_gives_the_same_paragraph(rotation):
    """글줄이 돌아간 쪽(가로 쪽의 표 등)을 돌려 놓고 묶은 뒤 상자를 되돌린다."""
    upright = line("Rotated paragraph first line", 12, 700) + line("and its second line.", 0, 688)

    def turn(box):  # 반시계 rotation만큼 돌린 쪽에 그린 글자의 상자
        left, bottom, right, top = box
        return {
            90: (-top, left, -bottom, right),
            180: (-right, -top, -left, -bottom),
            270: (bottom, -right, top, -left),
        }[rotation]

    turned = [Char(ch.text, turn(ch.box) if ch.box else None) for ch in upright]
    xs = [v for ch in turned if ch.box for v in (ch.box[0], ch.box[2])]
    ys = [v for ch in turned if ch.box for v in (ch.box[1], ch.box[3])]
    view_box = (min(xs) - 10, min(ys) - 10, max(xs) + 10, max(ys) + 10)

    page = layout_page(turned, view_box, image_coverage=0.0, text_rotation=rotation)

    assert [block.text for block in page.blocks] == ["Rotated paragraph first line and its second line."]
    # 줄 상자는 돌리기 전 좌표로 돌아와 그 글자들을 덮는다
    first_line = [ch.box for ch in turned[:28] if ch.box]
    u0, v0, u1, v1 = page.blocks[0].regions[0]
    x0, y0, x1, y1 = view_box
    assert u0 * (x1 - x0) + x0 == pytest.approx(min(b[0] for b in first_line), abs=1e-3)
    assert y1 - v1 * (y1 - y0) == pytest.approx(min(b[1] for b in first_line), abs=1e-3)
