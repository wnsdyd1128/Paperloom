"""글꼴이 유니코드를 주지 않는 수식 기호를 글리프 이름으로 되찾기 (2026-10-04 사용자 요청: 빠지는 수식 기호)."""

import pytest

from paperloom.documents.glyphs import (
    MAC_GLYPHS,
    FontDifferences,
    cmex_text,
    glyph_id_name_agrees,
    glyph_text,
    kind_3b2,
    looks_like_text,
    pua_text,
    standard_text,
    text_3b2,
)


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("prime", "′"),  # 사용자 논문 txsy 코드 12
        ("summationdisplay", "∑"),  # txex 코드 4 (크기 꼬리를 뗀다)
        ("summationtext", "∑"),
        ("parenrightBigg", ")"),
        ("parenleftBig", "("),
        ("braceleftbigg", "{"),
        ("floorrightBigg", "⌋"),
        ("ceilingleftBigg", "⌈"),
        ("nelement", "∉"),  # txsyc
        ("nequal", "≠"),
        ("uni2032", "′"),
    ],
)
def test_known_glyph_names_give_their_symbol(name, expected):
    assert glyph_text(name) == expected


@pytest.mark.parametrize("name", ["braceex", "bracelefttp", "braceleftmid", "unknownglyph", "Bigg", ""])
def test_pieces_of_stretched_symbols_and_unknown_names_give_nothing(name):
    """늘여 쓰는 괄호 조각(…tp·…mid·…ex)은 글자가 아니다. 모르는 이름은 되찾지 않는다."""
    assert glyph_text(name) is None


# 3B2(Arbortext) AdvP 글꼴 (2026-10-14 사용자 논문, IEEE TC): /Differences는 사용자 논문의 글꼴 그대로다(코드 → 이름, 모든 쪽을 합침).
SYMBOL_3B2 = {1: "C15", 3: "C2", 4: "C20", 5: "C0", 6: "C138", 7: "C21", 8: "C3", 32: "space", 41: "parenright", 48: "zero",
              50: "two", 54: "six", 56: "eight", 57: "nine", 79: "O", 91: "bracketleft", 92: "backslash", 94: "asciicircum",
              95: "underscore", 102: "f", 103: "g", 106: "j", 116: "t", 117: "u", 188: "onequarter", 189: "onehalf",
              222: "Thorn", 240: "eth", 254: "thorn"}  # AdvP4C4E74
DELIMITER_3B2 = {2: "C22", 3: "C23", 4: "C16", 5: "C17", 6: "C8", 7: "C9", 8: "C26", 9: "C24", 10: "C25", 32: "space",
                 33: "exclam", 40: "parenleft", 56: "eight", 58: "colon", 60: "less", 62: "greater", 80: "P", 88: "X",
                 106: "j", 107: "k", 108: "l", 109: "m"}  # AdvP4C4E46
ITALIC_3B2 = {2: "C24", 58: "colon", 59: "semicolon", 60: "less", 62: "greater", 65: "A", 66: "B", 67: "C", 97: "a", 98: "b",
              99: "c", 100: "d", 101: "e", 105: "i", 106: "j", 107: "k", 116: "t", 120: "x", 121: "y"}  # AdvP4C4E51(일부)
ROMAN_3B2 = {2: "C22", 46: "period", 48: "zero", 49: "one", 94: "asciicircum", 97: "a", 100: "d", 105: "i", 108: "l",
             109: "m", 110: "n", 111: "o", 120: "x", 160: "Euro"}  # AdvP4C4E59


def test_3b2_fonts_are_told_apart_by_their_glyph_names():
    """3B2가 TeX 수식 기호 글꼴(cmsy)을 다시 인코딩한 글꼴은 3B2가 더한 = ( ) +(onequarter·eth·Thorn·thorn)가 있고, 큰 기호
    글꼴(cmex)은 짝지은 큰 괄호 /Cnn이 둘 이상이고 소문자 한 글자 이름이 /Cnn보다 적다(cmex의 j k l m은 큰 바닥·천장 괄호다).
    둘 다 아니면(cmmi·cmr처럼 /Cnn 하나와 이탤릭 글자들) 모른다."""
    assert kind_3b2(SYMBOL_3B2) == "oms"
    assert kind_3b2(DELIMITER_3B2) == "omx"
    assert kind_3b2(ITALIC_3B2) is None
    assert kind_3b2(ROMAN_3B2) is None
    greek_pairs = {22: "C22", 23: "C23", 24: "C24", 25: "C25", **{97 + n: chr(97 + n) for n in range(8)}}
    assert kind_3b2(greek_pairs) is None  # cmmi의 그리스 문자 짝(μν ξπ)과 이탤릭 글자들
    assert kind_3b2({240: "eth", 254: "thorn", 97: "a"}) is None  # /Cnn이 없으면 본문 글꼴이다(아이슬란드어 글자)


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        (5, "−"),  # /C0: 사용자 논문 "Sk = Dk − Ck"
        (8, "∗"),  # /C3: "C∗i"
        (4, "≤"),  # /C20
        (7, "≥"),  # /C21
        (1, "•"),  # /C15: 글머리표
        (3, "×"),  # /C2
        (0x32, "∈"),  # two: "τk ∈ τ"
        (0x30, "′"),  # zero: "C′k"
        (0x38, "∀"),
        (0x39, "∃"),
        (0x5B, "∪"),
        (0x5C, "∩"),
        (0x5E, "∧"),
        (0x5F, "∨"),
        (0x74, "⊔"),  # t·u: 증명 끝 표시 ⊔⊓
        (0x75, "⊓"),
        (0x66, "{"),
        (0x67, "}"),
        (0x6A, "|"),
        (0x29, "⇒"),  # parenright: "=⇒"
        (0x20, "←"),  # space: 알고리즘의 "I∗ ← empty list"
        (0x36, "\u0338"),  # six: 다음 글자에 긋는 빗금("6¼"는 ≠)
        (0xBC, "="),
        (0xBD, "["),
        (0xF0, "("),
        (0xDE, ")"),
        (0xFE, "+"),
        (6, "]"),  # /C138
        (0x4F, None),  # O: 필기체 글자라 그대로 둔다
    ],
)
def test_3b2_symbol_font_codes_give_the_cmsy_symbol(code, expected):
    assert text_3b2("oms", code, SYMBOL_3B2.get(code)) == expected


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        (2, "⌊"),  # /C22: 사용자 논문 "⌊(Ak + Sk)/Ti⌋"
        (3, "⌋"),
        (4, "("),  # /C16
        (5, ")"),
        (6, "{"),  # /C8
        (7, "}"),
        (8, "{"),  # /C26: 경우 나누기의 큰 중괄호
        (9, "⌈"),  # /C24
        (10, "⌉"),
        (0x20, "("),  # space: parenleftBigg
        (0x21, ")"),  # exclam: parenrightBigg
        (0x28, "{"),  # parenleft: braceleftBigg
        (0x38, " "),  # eight: 늘이는 중괄호 조각은 글자가 아니다
        (0x3A, " "),  # colon
        (0x3E, " "),  # greater: braceex
        (0x50, "∑"),  # P: summationtext
        (0x58, "∑"),  # X: summationdisplay "max ∑"
        (0x6A, "⌊"),  # j·k: floorBig "⌊Ak/Tk⌋"
        (0x6B, "⌋"),
        (0x6C, "⌈"),  # l·m: ceilingBig
        (0x6D, "⌉"),
    ],
)
def test_3b2_delimiter_font_codes_give_the_cmex_symbol(code, expected):
    assert text_3b2("omx", code, DELIMITER_3B2.get(code)) == expected


@pytest.mark.parametrize(
    ("font", "code", "expected"),
    [
        # Adobe 글리프 목록이 사용자 영역에 둔 Symbol 글자(2026-10-14 실제 논문 7편): 늘이는 괄호는 윗조각만 괄호, 나머지는 빈칸
        ("Symbol", 0xF8EB, "("),  # parenlefttp
        ("Symbol", 0xF8EC, " "),  # parenleftex
        ("Symbol", 0xF8ED, " "),  # parenleftbt
        ("Symbol", 0xF8F6, ")"),  # parenrighttp
        ("MTEX", 0xF8F1, "{"),  # bracelefttp: 경우 나누기의 큰 중괄호(어느 글꼴이든 같다)
        ("MTEX", 0xF8F4, " "),  # braceex
        ("txexs", 0xF8F3, " "),  # braceleftbt
        ("Symbol", 0xF8E9, "©"),
        # Windows 기호 글꼴은 Symbol 인코딩 코드를 U+F000 + 코드로 준다
        ("SymbolMT", 0xF074, "τ"),
        ("SymbolMT", 0xF067, "γ"),
        ("ABCDEF+SymbolMT", 0xF0D6, "√"),
        ("SymbolMT", 0xF0A3, "≤"),
        ("SymbolMT", 0xF0EC, "{"),  # bracelefttp
        ("SymbolMT", 0xF0EF, " "),  # braceex
        ("Wingdings-Regular", 0xF0E0, None),  # 기호 글꼴이 아니면 모른다(글에서 뺀다)
        ("Symbol", 0xF8FF, None),
        ("Symbol", 0xE000, None),
    ],
)
def test_private_use_symbols_give_the_symbol_they_draw(font, code, expected):
    assert pua_text(font, code) == expected


def test_glyph_ids_in_the_standard_macintosh_order_give_their_letters():
    """유니코드 지도가 빈 글리프 번호 글꼴(2026-10-19 사용자 논문 SayCan 그림)의 글리프 번호는 매킨토시 표준 차례로 읽는다:
    pdfium은 번호를 글자로 주어 "+XPDQ"가 되었다(글리프 43 = H)."""
    assert "".join(MAC_GLYPHS[ord(char)] for char in "+XPDQ") == "Human"
    assert (MAC_GLYPHS[3], MAC_GLYPHS[19], MAC_GLYPHS[36], MAC_GLYPHS[68], MAC_GLYPHS[97]) == (" ", "0", "A", "a", "~")
    assert (MAC_GLYPHS[171], MAC_GLYPHS[178], MAC_GLYPHS[180], MAC_GLYPHS[183], MAC_GLYPHS[257]) == ("…", "–", "“", "’", "đ")
    assert {0, 1, 2, 210}.isdisjoint(MAC_GLYPHS) and max(MAC_GLYPHS) == 257


def test_only_text_that_reads_like_language_is_taken_from_the_glyph_order():
    """차례가 다른 글꼴을 매킨토시 차례로 읽으면 엉뚱한 글이 된다. 한 글꼴의 글이 말글처럼 보일 때만 쓴다."""
    assert looks_like_text("Human: I spilled my coke, can you bring me something?")
    assert not looks_like_text("+XPDQ ,VSLOOHG P\\FRNH")  # 밀린 채(모음 0.06)
    assert not looks_like_text("Bcd fgh jklm npqr")  # 자음뿐
    assert not looks_like_text("Done")  # 영문자가 너무 적다


def test_glyph_id_names_vouch_for_the_character_code():
    """2026-10-21 사용자 논문의 차트 Type3 글꼴: 글리프 이름이 글리프 번호(/uni00000024 = 36 = A)라 pdfium이 글자 코드를 그대로 주며
    매핑 오류로 표시했다. 그 번호의 매킨토시 차례 글자가 글자 코드와 같을 때만 맞는 글자로 본다."""
    assert glyph_id_name_agrees("uni00000024", ord("A")) and glyph_id_name_agrees("uni0000001a", ord("7"))
    assert glyph_id_name_agrees("uni00000003", ord(" "))
    assert not glyph_id_name_agrees("uni00000024", ord("B"))  # 번호와 코드가 다른 글자
    assert not glyph_id_name_agrees("uni0041", ord("A"))  # 유니코드 이름(4자리)은 글리프 번호가 아니다
    assert not glyph_id_name_agrees("g36", ord("A")) and not glyph_id_name_agrees(None, ord("A"))


@pytest.mark.parametrize(
    ("font", "code", "expected"),
    [
        ("IJNTRM+CMEX10", 0x58, "∑"),  # summationdisplay
        ("CMEX10", 0x18, "⌈"),  # ceilingleftbigg
        ("CMEX7", 0x6E, "{"),  # braceleftBig
        ("cmex10", 0x21, ")"),  # parenrightBigg
        ("CMEX10", 0x3F, " "),  # 늘이는 조각
        ("CMEX10", 0xC4, None),  # 모르는 자리
        ("CMMI10", 0x58, None),  # 큰 기호 글꼴이 아니다
    ],
)
def test_tex_extension_font_codes_give_the_symbol_at_that_position(font, code, expected):
    """CMEX10의 ToUnicode가 늘이는 괄호 조각만 주어 ∑·큰 괄호가 X·n·o로 나왔다(2026-10-21 사용자 논문). 자리는 TeX가 정해 두었다."""
    assert cmex_text(font, code) == expected


def test_tex_extension_positions_apply_only_to_fonts_with_their_built_in_encoding(monkeypatch):
    """/Differences로 다시 인코딩한 CMEX는 자리가 다르다(실제 논문 PARDA: 코드 2가 큰 중괄호인데 TeX 자리로는 [). 그런 글꼴은 글리프
    이름으로 되찾고(FontDifferences.text) TeX 자리표를 쓰지 않는다."""
    differences = FontDifferences("unused.pdf")
    monkeypatch.setattr(differences, "_names", lambda page_index, font: {} if font == "IJNTRM+CMEX10" else {2: "braceleftbigg"})
    assert differences.cmex_text(0, "IJNTRM+CMEX10", 0x58) == "∑"
    assert differences.cmex_text(0, "BDNPMO+CMEX10", 0x02) is None


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("zero", "0"), ("A", "A"), ("space", " "), ("quoteright", "’"), ("endash", "–"), ("fi", "ﬁ"), ("minus", "−"),
        ("alpha", "α"), ("Omega", "Ω"), ("theta1", "ϑ"), ("uni2212", "−"), ("uni00410042", "AB"), ("u1D400", "𝐀"),
        ("summationdisplay", "∑"),  # 수식 글꼴 이름(glyph_text)
        ("uni00000024", None),  # 글리프 번호 이름: 제어 문자가 되는 uni 이름은 모른다
        ("BP", None), ("CG", None), ("a0", None), ("g36", None),  # dvips·Word 수식 Type3의 뜻 없는 이름
    ],
)
def test_standard_glyph_names_give_their_character(name, expected):
    """2026-10-21 "Self-recovery 고도화": matplotlib 차트의 Type3 글꼴은 /zero·/A 같은 표준 이름을 쓰는데 pdfium이 글자 코드를
    매핑 오류로 준다. 표준 이름(ASCII·매킨토시 표준 258개·그리스 문자·uni/u 이름·수식 이름)은 그 글자로 읽는다."""
    assert standard_text(name) == expected


def test_glyph_names_are_used_only_when_the_font_names_its_glyphs_in_the_standard_way(monkeypatch):
    """dvips 비트맵 Type3 글꼴의 이름(/A1 /AB /AE /BP …)에는 표준 이름 /AE(Æ)가 우연히 섞인다. 이름 대부분이 표준 이름인 글꼴만
    이름으로 읽는다(STANDARD_SHARE)."""
    differences = FontDifferences("unused.pdf")
    names = {
        "DejaVuSans": {48: "zero", 65: "A", 82: "R", 32: "space"},
        "": {1: "A1", 11: "AB", 12: "AC", 13: "AD", 14: "AE", 34: "AY"},
    }
    monkeypatch.setattr(differences, "_read_page", lambda page_index: ({}, {}, names))
    assert [differences.name_text(0, "ABCDEF+DejaVuSans", code) for code in (48, 65, 32, 66)] == ["0", "A", " ", None]
    assert differences.name_text(0, "", 14) is None  # /AE지만 이 글꼴의 이름은 표준 이름이 아니다
