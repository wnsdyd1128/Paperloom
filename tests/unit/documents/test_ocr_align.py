"""OCR이 읽은 글줄로 못 읽은 글자 채우기 (documents.ocr_align, 2026-10-21 "Self-recovery 고도화" ③)."""

from paperloom.documents.ocr_align import NO_TEXT, OCR_SCORE, fill


def line(text: str, unreadable: str = "") -> list[tuple[str, bool]]:
    """글줄 글자들. unreadable에 든 글자는 못 읽은 글자다(글은 pdfium이 준 그대로)."""
    return [(char, char in unreadable) for char in text if not char.isspace()]


def test_old_tex_bitmap_text_is_confirmed_and_ligatures_and_quotes_are_filled():
    """옛 TeX 비트맵 글꼴(Liu & Layland 1973): pdfium 글은 맞는데 글꼴이 글자를 알려 주지 않는다. 합자 fi(0x0C)와 따옴표(OT1의 \\)는
    OCR 글자로 채운다."""
    chars = [(char, True) for char in "con\x0cguration \\hard\""]
    chars = [char for char in chars if char[0] != " "]
    found = fill(chars, 'configuration "hard"', 0.99)
    assert "".join(found[index] for index in range(len(chars))) == 'configuration"hard"'
    assert found[3] == "fi"


def test_a_garbled_formula_run_takes_the_ocr_text_spread_over_its_glyphs():
    """Word 수식 Type3(Predicting): 글 자체가 깨졌다. 못 읽은 구간을 OCR 글로 채우되 글자 수가 다르면 구간 글자들이 차례로 나눠
    받는다(한 글자에 몰면 나머지 글자 상자가 없어져 글줄이 끊긴다). OCR 글자가 모자라면 남는 글리프는 위치만 남는다(NO_TEXT)."""
    chars = line("To obtain") + [("-", True), ("\x01", True), ("\x03", True)] + line(", an off-line")
    first = len(line("To obtain"))
    assert fill(chars, "To obtain N (cseqx), an off-line", 0.98) == {first: "N (c", first + 1: "seq", first + 2: "x)"}
    assert fill(chars, "To obtain ∑, an off-line", 0.98) == {first: "∑", first + 1: NO_TEXT, first + 2: NO_TEXT}  # 조각 셋으로 그린 기호


def test_known_characters_are_never_changed():
    chars = line("Ri = Ci + X", unreadable="X")
    found = fill(chars, "Ri = Ci + ∑", 0.97)
    assert found == {len(chars) - 1: "∑"}


def test_an_epsilon_the_model_reads_as_a_euro_sign_is_an_epsilon():
    """논문 40편에서 모델이 수식의 ε을 €로 읽었다(Efficient and Precise 4쪽 "an error estimate ε", Liu & Layland 13쪽 "T − T′ − ε")."""
    chars = line("an error estimate X.", unreadable="X")
    assert fill(chars, "an error estimate €.", 0.95) == {len(chars) - 2: "ε"}


def test_a_line_the_ocr_read_differently_from_the_known_characters_is_dropped():
    """이미 읽은 글자와 많이 다르게 읽은 줄(여기서는 모음을 모두 빠뜨렸다)은 OCR이 그 줄을 잘못 읽었다고 보고 쓰지 않는다."""
    chars = line("Multiset approaches to account for the [ highest", unreadable="[")
    assert fill(chars, "Mltst pprchs t ccnt fr th - hghst", 0.9) == {}


def test_low_confidence_reads_are_not_used():
    assert fill(line("Ri = X", unreadable="X"), "Ri = ∑", OCR_SCORE - 0.01) == {}


def test_glyphs_that_draw_figures_are_not_characters():
    """옛 LaTeX는 그림의 빗금 상자·화살표·선을 글꼴 글리프로 그렸다(Liu & Layland 3·9쪽 그림 1). OCR이 글자를 찾지 못하거나, pdfium이
    글자 정보를 하나도 주지 않았고(U+FFFD) OCR도 확신하지 못하면 글자가 아니다."""
    assert fill([("\x01", True), ("\x02", True)], "", 0.0) == {0: "", 1: ""}
    assert fill([("\ufffd", True)] * 3, "==", 0.6) == {0: "", 1: "", 2: ""}
    assert fill([("\x01", True)] * 3, "==", 0.6) == {}  # 글자 정보가 있으면(Word 수식 꼴) 지우지 않는다
    assert fill(line("x = ") + [("\ufffd", True)], "", 0.0) == {}  # 읽은 글자가 섞인 줄은 그림이 아니다


def test_an_unreadable_space_stays_a_space_only_where_the_ocr_also_saw_one():
    """차트 Type3 글꼴은 공백도 글리프다. OCR은 공백을 글자로 읽지 않으므로 그 자리를 띄어 읽었을 때만 공백으로 둔다."""
    chars = [(char, True) for char in "Response time"]
    assert fill(chars, "Response time", 0.97) == dict(enumerate("Response time"))
    assert 8 not in fill(chars, "Responsetime", 0.97)


def test_chinese_characters_the_model_makes_up_from_lines_and_boxes_are_not_used():
    """모델 글자 사전 대부분이 한자라, 그림의 선·상자를 目·十으로, 식의 근호를 立로 읽었다(Liu & Layland). 한자·가나가 없는 글줄에서는
    OCR의 한자·가나를 쓰지 않는다: 줄 전체가 못 읽은 글자면 그림이고, 섞인 줄의 그 글자는 못 읽은 채로 둔다."""
    assert fill([("\x0e", True), ("\x0f", True)], "目目", 0.95) == {0: "", 1: ""}
    chars = line("f = 2") + [("\x0c", True)] + line("- 1")
    assert fill(chars, "f = 2 立 - 1", 0.95) == {}
    assert fill([("可", True), ("乐", True)], "可乐", 0.95) == {0: "可", 1: "乐"}  # 한자 글줄은 한자로 읽는다


def test_lines_without_unreadable_characters_are_left_alone():
    assert fill(line("plain text"), "plain text", 0.99) == {}
