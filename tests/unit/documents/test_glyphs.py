"""글꼴이 유니코드를 주지 않는 수식 기호를 글리프 이름으로 되찾기 (2026-10-04 사용자 요청: 빠지는 수식 기호)."""

import pytest

from paperloom.documents.glyphs import glyph_text, kind_3b2, text_3b2


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
