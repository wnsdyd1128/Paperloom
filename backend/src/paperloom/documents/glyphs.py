"""글꼴이 유니코드를 주지 않는 수식 기호를 PDF 글꼴 사전의 /Encoding /Differences 글리프 이름으로 되찾는다.

2026-10-04 사용자 요청(빠지는 수식 기호): 사용자 논문의 newtx 수식 글꼴(txsy·txex)에서 프라임 ′(0x0C)·합 ∑(0x04·0x08)·
큰 괄호·≠ 등이 pdfium에서 제어 문자로 나와 빠졌다(ToUnicode가 그 코드를 빠뜨렸거나, Adobe 글리프 목록에 없는 TeX 이름이다).
pdfium은 글꼴 사전을 주지 않으므로 그 쪽 글꼴의 /Differences를 pypdf로 읽는다(제어 문자가 나온 쪽만, 처음 필요할 때).
수식 글꼴(fonts.is_math_font)만 되찾는다: pdfium은 줄 끝에서 나눈 낱말의 하이픈도 0x02로 주므로 본문 글꼴은 건드리지 않는다.

글리프 번호 글꼴(2026-10-19 사용자 논문 SayCan의 그림, Google 슬라이드에서 만든 듯): Type0 Identity-H 글꼴의 ToUnicode가 비었고 내장
TrueType에 cmap·post 표가 없어 PDF 어디에도 글자가 없다. pdfium은 글리프 번호를 글자로 주어 "+XPDQ"(Human)처럼 29자 밀린 글이
되고 매핑 오류로 쪽이 "일부 쪽만 검색 가능"이 되었다. 원래 글꼴이 매킨토시 표준 글리프 차례(글리프 36 = A)를 따르므로 그 차례로
읽는다(MAC_GLYPHS). 차례가 다른 글꼴이면 엉뚱한 글이 되므로 글꼴마다 읽은 글이 말글처럼 보일 때만 쓴다(looks_like_text).
"""

import re

# Adobe 글리프 목록과 TeX 수식 글꼴(cmsy·cmex·newtx)의 이름. 크기 꼬리(big·Big·bigg·Bigg·display·text)는 떼고 찾는다.
# 늘여 쓰는 조각(…tp·…mid·…bt·…ex)은 글자가 아니라 넣지 않는다(그런 이름은 찾지 못해 빠진다).
GLYPHS = {
    "prime": "′",
    "summation": "∑",
    "product": "∏",
    "coproduct": "∐",
    "integral": "∫",
    "contourintegral": "∮",
    "union": "∪",
    "intersection": "∩",
    "unionsq": "⊔",
    "intersectionsq": "⊓",
    "logicaland": "∧",
    "logicalor": "∨",
    "logicalnot": "¬",
    "circleplus": "⊕",
    "circlemultiply": "⊗",
    "circledot": "⊙",
    "radical": "√",
    "parenleft": "(",
    "parenright": ")",
    "bracketleft": "[",
    "bracketright": "]",
    "braceleft": "{",
    "braceright": "}",
    "angleleft": "⟨",
    "angleright": "⟩",
    "floorleft": "⌊",
    "floorright": "⌋",
    "ceilingleft": "⌈",
    "ceilingright": "⌉",
    "bar": "|",
    "bardbl": "‖",
    "slash": "/",
    "backslash": "\\",
    "arrowright": "→",
    "arrowleft": "←",
    "arrowup": "↑",
    "arrowdown": "↓",
    "arrowboth": "↔",
    "arrowdblright": "⇒",
    "arrowdblleft": "⇐",
    "arrowdblboth": "⇔",
    "mapsto": "↦",
    "element": "∈",
    "nelement": "∉",
    "notelement": "∉",
    "owner": "∋",
    "lessequal": "≤",
    "greaterequal": "≥",
    "nequal": "≠",
    "notequal": "≠",
    "equivalence": "≡",
    "approxequal": "≈",
    "similar": "∼",
    "proportional": "∝",
    "infinity": "∞",
    "partialdiff": "∂",
    "gradient": "∇",
    "emptyset": "∅",
    "universal": "∀",
    "existential": "∃",
    "propersubset": "⊂",
    "propersuperset": "⊃",
    "reflexsubset": "⊆",
    "reflexsuperset": "⊇",
    "asteriskmath": "∗",
    "minus": "−",
    "plusminus": "±",
    "multiply": "×",
    "divide": "÷",
    "periodcentered": "·",
    "dotmath": "⋅",
    "bullet": "•",
    "openbullet": "◦",
    "square": "□",
}
_SIZE = re.compile(r"(?:big|Big|bigg|Bigg|display|text)$")
_UNI = re.compile(r"^uni([0-9A-F]{4})$")
_SUBSET = re.compile(r"^[A-Z]{6}\+")

# 3B2(Arbortext) 조판 PDF의 AdvP 수식 글꼴 (2026-10-14 사용자 논문, IEEE TC): TeX 수식 글꼴을 다시 인코딩했다.
# 코드 32 이상은 TeX 글꼴의 같은 자리 글자다(글리프 이름은 그 자리의 ASCII 이름이라 "two"가 ∈다). 32보다 작은 코드는
# /Cnn 이름의 nn이 TeX 글꼴의 자리다. 기호 글꼴에는 3B2가 높은 코드에 = [ ( ) +와 ]를 더 넣었다. ToUnicode도 그 이름대로라
# pdfium은 ¼ ½ ð Þ þ와 2 8 [ 등을 준다. 글꼴 이름(AdvP+16진수)으로는 종류를 알 수 없어 /Differences 이름으로 가른다(kind_3b2).
# 근거는 사용자 논문 하나다: 쓰인 자리마다 앞뒤 글과 맞춰 봤다(docs/gates/evidence/ui/2026-10-14_3b2-math-and-labels.md).
OMS = {  # TeX 수식 기호 글꼴(cmsy) 자리 → 글자. A–Z(0x41–0x5A)는 필기체 글자라 그대로 둔다
    0x00: "−", 0x01: "⋅", 0x02: "×", 0x03: "∗", 0x04: "÷", 0x05: "⋄", 0x06: "±", 0x07: "∓",
    0x08: "⊕", 0x09: "⊖", 0x0A: "⊗", 0x0B: "⊘", 0x0C: "⊙", 0x0D: "◯", 0x0E: "∘", 0x0F: "•",
    0x10: "≍", 0x11: "≡", 0x12: "⊆", 0x13: "⊇", 0x14: "≤", 0x15: "≥", 0x16: "⪯", 0x17: "⪰",
    0x18: "∼", 0x19: "≈", 0x1A: "⊂", 0x1B: "⊃", 0x1C: "≪", 0x1D: "≫", 0x1E: "≺", 0x1F: "≻",
    0x20: "←", 0x21: "→", 0x22: "↑", 0x23: "↓", 0x24: "↔", 0x25: "↗", 0x26: "↘", 0x27: "≃",
    0x28: "⇐", 0x29: "⇒", 0x2A: "⇑", 0x2B: "⇓", 0x2C: "⇔", 0x2D: "↖", 0x2E: "↙", 0x2F: "∝",
    0x30: "′", 0x31: "∞", 0x32: "∈", 0x33: "∋", 0x34: "△", 0x35: "▽", 0x36: "\u0338", 0x38: "∀",
    0x39: "∃", 0x3A: "¬", 0x3B: "∅", 0x3C: "ℜ", 0x3D: "ℑ", 0x3E: "⊤", 0x3F: "⊥", 0x40: "ℵ",
    0x5B: "∪", 0x5C: "∩", 0x5D: "⊎", 0x5E: "∧", 0x5F: "∨",
    0x60: "⊢", 0x61: "⊣", 0x62: "⌊", 0x63: "⌋", 0x64: "⌈", 0x65: "⌉", 0x66: "{", 0x67: "}",
    0x68: "⟨", 0x69: "⟩", 0x6A: "|", 0x6B: "‖", 0x6C: "↕", 0x6D: "⇕", 0x6E: "\\", 0x6F: "≀",
    0x70: "√", 0x71: "⨿", 0x72: "∇", 0x73: "∫", 0x74: "⊔", 0x75: "⊓", 0x76: "⊑", 0x77: "⊒",
    0x78: "§", 0x79: "†", 0x7A: "‡", 0x7B: "¶", 0x7C: "♣", 0x7D: "♦", 0x7E: "♥", 0x7F: "♠",
}  # 0x36 빗금은 다음 글자에 긋는다(extract가 순서를 바꿔 "=\u0338"이 ≠가 된다). 0x37(↦의 막대 조각)은 모른다
_PIECE = " "  # 늘여 쓰는 괄호 조각: 글자가 아니다(빈칸으로 둔다)
OMX = {  # TeX 큰 기호 글꼴(cmex) 자리 → 글자
    **dict(zip(range(0x00, 0x0C), "()[]⌊⌋⌈⌉{}⟨⟩", strict=True)),
    0x0C: _PIECE, 0x0D: _PIECE, 0x0E: "/", 0x0F: "\\",  # 0x0C·0x0D는 세로 막대를 늘이는 조각이다
    **dict(zip(range(0x10, 0x20), "()()[]⌊⌋⌈⌉{}⟨⟩/\\", strict=True)),
    **dict(zip(range(0x20, 0x30), "()[]⌊⌋⌈⌉{}⟨⟩/\\/\\", strict=True)),
    **{code: _PIECE for code in range(0x30, 0x44)},
    **dict(zip(range(0x44, 0x62), "⟨⟩⊔⊔∮∮⊙⊙⊕⊕⊗⊗∑∏∫⋃⋂⊎⋀⋁∑∏∫⋃⋂⊎⋀⋁∐∐", strict=True)),
    **dict(zip(range(0x62, 0x70), "^^^~~~[]⌊⌋⌈⌉{}", strict=True)),
    **dict(zip(range(0x70, 0x74), "√√√√", strict=True)),
    **{code: _PIECE for code in range(0x74, 0x80)},
}
_EXTRAS_3B2 = {"onequarter": "=", "onehalf": "[", "eth": "(", "Thorn": ")", "thorn": "+", "C138": "]"}

# 사용자 영역(PUA) 글자 (2026-10-14 실제 논문 36편 중 7편): Adobe 글리프 목록은 Symbol 글꼴의 늘이는 괄호 조각 등을 U+F6D9–F8FE에
# 둔다(어느 글꼴이든 같은 뜻). 큰 괄호는 윗조각만 괄호로 두고 나머지 조각은 빈칸이다(조각마다 괄호를 두면 "(((")
ADOBE_PUA = {
    0xF6D9: "©", 0xF6DA: "®", 0xF6DB: "™", 0xF8E8: "®", 0xF8E9: "©", 0xF8EA: "™",
    0xF8EB: "(", 0xF8EE: "[", 0xF8F1: "{", 0xF8F6: ")", 0xF8F9: "]", 0xF8FC: "}",
    **{code: _PIECE for code in (0xF8E5, 0xF8E6, 0xF8E7, 0xF8EC, 0xF8ED, 0xF8EF, 0xF8F0, 0xF8F2, 0xF8F3, 0xF8F4, 0xF8F5, 0xF8F7,
                                 0xF8F8, 0xF8FA, 0xF8FB, 0xF8FD, 0xF8FE)},
}
# Adobe Symbol 인코딩(코드 → 글자). Windows 기호 글꼴(SymbolMT 등)은 이 코드를 U+F000 + 코드(사용자 영역)로 준다.
# 늘이는 조각(0x60·0xBD·0xBE·0xE6–0xEF·0xF4–0xFE)은 큰 괄호 윗조각만 괄호, 나머지는 빈칸이다. 0xF0(쓰지 않는 자리)은 없다
SYMBOL = {
    **dict(zip(range(0x20, 0x7F), " !∀#∃%&∋()∗+,−./0123456789:;<=>?≅ΑΒΧΔΕΦΓΗΙϑΚΛΜΝΟΠΘΡΣΤΥςΩΞΨΖ[∴]⊥_ αβχδεφγηιϕκλμνοπθρστυϖωξψζ{|}∼", strict=True)),
    **dict(zip(range(0xA0, 0xF0), "€ϒ′≤⁄∞ƒ♣♦♥♠↔←↑→↓°±″≥×∝∂•÷≠≡≈…  ↵ℵℑℜ℘⊗⊕∅∩∪⊃⊇⊄⊂⊆∈∉∠∇®©™∏√⋅¬∧∨⇔⇐⇑⇒⇓◊⟨®©™∑(  [  {   ", strict=True)),
    **dict(zip(range(0xF1, 0xFF), "⟩∫∫  )  ]  }  ", strict=True)),
}
# TrueType 매킨토시 표준 글리프 차례(post 표 형식 1의 258개) → 글자. 0–2(.notdef·.null·nonmarkingreturn)와 210(apple)은 없다
MAC_GLYPHS = {
    **dict(zip(range(3, 98), map(chr, range(0x20, 0x7F)), strict=True)),  # space … asciitilde
    **dict(zip(range(98, 210), "ÄÅÇÉÑÖÜáàâäãåçéèêëíìîïñóòôöõúùûü†°¢£§•¶ß®©™´¨≠ÆØ∞±≤≥¥µ∂∑∏π∫ªºΩæø¿¡¬√ƒ≈∆«»… ÀÃÕŒœ–—“”‘’÷◊ÿŸ⁄¤‹›ﬁﬂ‡·‚„‰ÂÊÁËÈÍÎÏÌÓÔ", strict=True)),
    **dict(zip(range(211, 258), "ÒÚÛÙıˆ˜¯˘˙˚¸˝˛ˇŁłŠšŽž¦ÐðÝýÞþ−×¹²³½¼¾₣ĞğİŞşĆćČčđ", strict=True)),
}
# 글리프 차례로 읽은 한 글꼴의 글이 말글이려면: 영문자가 이만큼 이상이고 그 가운데 모음(aeiou)이 이 비율 이상(영어 약 0.38,
# 사용자 논문 그림 글 0.39–0.44, 밀린 채로는 0.06–0.14, 차례가 다른 글꼴을 잘못 읽으면 고른 글자라 약 0.19)
GLYPH_ORDER_LETTERS = 8
GLYPH_ORDER_VOWELS = 0.3
_TEX_NAME = re.compile(r"^C(\d+)$")
_DELIMITER_PAIRS = ((0, 1), (2, 3), (4, 5), (6, 7), (8, 9), (16, 17), (18, 19), (22, 23), (24, 25), (26, 27))


def glyph_text(name: str) -> str | None:
    """글리프 이름의 글자. 모르는 이름(늘이는 조각 등)이면 None."""
    if name in GLYPHS:
        return GLYPHS[name]
    unicode = _UNI.match(name)
    if unicode:
        return chr(int(unicode.group(1), 16))
    return GLYPHS.get(_SIZE.sub("", name))


def looks_like_text(text: str) -> bool:
    """글리프 차례(MAC_GLYPHS)로 읽은 한 글꼴의 글이 말글처럼 보이는지(GLYPH_ORDER_LETTERS·GLYPH_ORDER_VOWELS)."""
    letters = [char.lower() for char in text if char.isascii() and char.isalpha()]
    return len(letters) >= GLYPH_ORDER_LETTERS and sum(char in "aeiou" for char in letters) >= GLYPH_ORDER_VOWELS * len(letters)


def kind_3b2(names: dict[int, str]) -> str | None:
    """AdvP 글꼴의 /Differences(코드 → 글리프 이름)로 3B2가 다시 인코딩한 TeX 글꼴: "oms"(cmsy), "omx"(cmex), 모르면 None.

    둘 다 /Cnn 이름이 있다. 기호 글꼴은 3B2가 더한 = ( ) +(onequarter·eth·Thorn·thorn·onehalf)가 있다. 큰 기호 글꼴은
    짝지은 큰 괄호가 둘 이상이고 소문자 한 글자 이름이 /Cnn보다 적다(cmex의 j k l m은 큰 바닥·천장 괄호다). cmmi·cmr은 /Cnn이
    적고(그리스 문자 몇 개) 이탤릭 글자가 많아 이것으로 가른다. 근거는 사용자 논문 하나의 네 글꼴이다."""
    tex = {int(match.group(1)) for name in names.values() if (match := _TEX_NAME.match(name))}
    if not tex:
        return None
    if any(name in _EXTRAS_3B2 for name in names.values() if not _TEX_NAME.match(name)):
        return "oms"
    lowercase = sum(1 for name in names.values() if len(name) == 1 and name.islower())
    pairs = sum(1 for left, right in _DELIMITER_PAIRS if left in tex and right in tex)
    return "omx" if pairs >= 2 and lowercase < len(tex) else None


def pua_text(font: str, code: int) -> str | None:
    """사용자 영역 글자가 그리는 글자: Adobe 글리프 목록의 Symbol 글자(ADOBE_PUA), 기호 글꼴의 U+F000 + Symbol 코드(SYMBOL).
    늘이는 괄호 조각은 " ", 모르면 None(본문 글에서 뺀다, text_layout.block_text)."""
    if code in ADOBE_PUA:
        return ADOBE_PUA[code]
    if 0xF020 <= code <= 0xF0FF and "Symbol" in font:
        return SYMBOL.get(code - 0xF000)
    return None


def text_3b2(kind: str, code: int, name: str | None) -> str | None:
    """kind_3b2 글꼴의 글자 코드(그 자리의 글리프 이름 name)가 그리는 글자. 늘이는 괄호 조각은 " ", 모르면 None(그대로 둔다)."""
    if kind == "oms" and name in _EXTRAS_3B2:
        return _EXTRAS_3B2[name]
    match = _TEX_NAME.match(name) if name else None
    return (OMS if kind == "oms" else OMX).get(int(match.group(1)) if match else code)


class FontDifferences:
    """쪽 글꼴의 /Differences(글자 코드 → 글리프 이름)와 글리프 번호 글꼴. PDF는 처음 필요할 때 pypdf로 열고 쪽마다 한 번 읽는다.
    PDF를 읽지 못하면(신뢰할 수 없는 PDF) 되찾지 않는다."""

    def __init__(self, path: str) -> None:
        self._path = path
        self._reader = None
        self._pages: dict[int, tuple[dict[str, dict[int, str] | None], dict[str, bool]]] = {}

    def text(self, page_index: int, font: str, code: int) -> str | None:
        """그 쪽 그 글꼴(부분 글꼴 접두 없이)의 글자 코드가 가리키는 글자. 같은 이름의 글꼴이 코드를 다르게 쓰거나 모르면 None."""
        names = self._names(page_index, font)
        name = names.get(code) if names else None
        return glyph_text(name) if name else None

    def text_3b2(self, page_index: int, font: str, code: int) -> str | None:
        """3B2 AdvP 수식 글꼴(kind_3b2)이면 그 글꼴의 글자 코드가 그리는 글자. 다른 글꼴이거나 모르면 None."""
        names = self._names(page_index, font)
        kind = kind_3b2(names) if names else None
        return text_3b2(kind, code, names.get(code)) if kind else None

    def glyph_ids(self, page_index: int, font: str) -> bool:
        """그 쪽 그 글꼴이 글리프 번호 글꼴(_glyph_ids)인지. 같은 이름의 글꼴이 모두 그래야 한다."""
        return self._read_page(page_index)[1].get(_SUBSET.sub("", font), False)

    def _names(self, page_index: int, font: str) -> dict[int, str] | None:
        return self._read_page(page_index)[0].get(_SUBSET.sub("", font))

    def _read_page(self, page_index: int) -> tuple[dict[str, dict[int, str] | None], dict[str, bool]]:
        if page_index not in self._pages:
            self._pages[page_index] = self._read(page_index)
        return self._pages[page_index]

    def _read(self, page_index: int) -> tuple[dict[str, dict[int, str] | None], dict[str, bool]]:
        try:
            if self._reader is None:
                from pypdf import PdfReader

                self._reader = PdfReader(self._path)
            fonts: dict[str, dict[int, str] | None] = {}
            glyph_ids: dict[str, bool] = {}
            _collect(self._reader.pages[page_index].get("/Resources"), fonts, glyph_ids, depth=0)
            return fonts, glyph_ids
        except Exception:  # noqa: BLE001 - 신뢰할 수 없는 PDF. 되찾지 못해도 본문 추출은 계속한다
            return {}, {}


def _collect(resources, fonts: dict[str, dict[int, str] | None], glyph_ids: dict[str, bool], depth: int) -> None:
    """자원의 글꼴(그림 안 Form의 글꼴 포함, 세 겹까지). 같은 이름인데 /Differences가 다르면 None(쓰지 않는다)."""
    if resources is None or depth > 3:
        return
    resources = resources.get_object()
    for ref in (resources.get("/Font") or {}).values():
        font = ref.get_object()
        name = _SUBSET.sub("", str(font.get("/BaseFont", ""))[1:])
        differences = _differences(font)
        fonts[name] = differences if fonts.get(name, differences) == differences else None
        glyph_ids[name] = glyph_ids.get(name, True) and _glyph_ids(font)
    for ref in (resources.get("/XObject") or {}).values():
        form = ref.get_object()
        if form.get("/Subtype") == "/Form":
            _collect(form.get("/Resources"), fonts, glyph_ids, depth + 1)


def _glyph_ids(font) -> bool:
    """글리프 번호를 글자 코드로 쓰고(Type0 Identity-H, CIDToGIDMap Identity) 글자를 알려 주지 않는(ToUnicode가 없거나 비었고
    내장 TrueType에 cmap 표가 없는) 글꼴. pdfium은 글리프 번호를 글자로 주고 매핑 오류로 표시한다."""
    try:
        if font.get("/Subtype") != "/Type0" or font.get("/Encoding") != "/Identity-H":
            return False
        to_unicode = font.get("/ToUnicode")
        if to_unicode is not None and re.search(rb"begin(?:bfchar|bfrange)", to_unicode.get_object().get_data()):
            return False
        descendant = font["/DescendantFonts"].get_object()[0].get_object()
        if descendant.get("/CIDToGIDMap", "/Identity") != "/Identity":
            return False
        program = descendant["/FontDescriptor"].get_object().get("/FontFile2")
        if program is None:
            return False
        data = program.get_object().get_data()
        tags = {data[12 + 16 * index : 16 + 16 * index] for index in range(int.from_bytes(data[4:6], "big"))}
        return b"cmap" not in tags
    except Exception:  # noqa: BLE001 - 신뢰할 수 없는 PDF의 글꼴. 모르면 글리프 번호 글꼴로 보지 않는다
        return False


def _differences(font) -> dict[int, str]:
    encoding = font.get("/Encoding")
    encoding = encoding.get_object() if encoding is not None else None
    found: dict[int, str] = {}
    if encoding is None or not hasattr(encoding, "get"):
        return found  # 이름만 있는 인코딩(/WinAnsiEncoding 등)
    code = 0
    for item in encoding.get("/Differences", []):
        if isinstance(item, int):
            code = item
        else:
            found[code] = str(item)[1:]
            code += 1
    return found
