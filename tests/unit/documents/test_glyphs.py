"""글꼴이 유니코드를 주지 않는 수식 기호를 글리프 이름으로 되찾기 (2026-10-04 사용자 요청: 빠지는 수식 기호)."""

import pytest

from paperloom.documents.glyphs import glyph_text


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
