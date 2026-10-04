"""글꼴이 유니코드를 주지 않는 수식 기호를 PDF 글꼴 사전의 /Encoding /Differences 글리프 이름으로 되찾는다.

2026-10-04 사용자 요청(빠지는 수식 기호): 사용자 논문의 newtx 수식 글꼴(txsy·txex)에서 프라임 ′(0x0C)·합 ∑(0x04·0x08)·
큰 괄호·≠ 등이 pdfium에서 제어 문자로 나와 빠졌다(ToUnicode가 그 코드를 빠뜨렸거나, Adobe 글리프 목록에 없는 TeX 이름이다).
pdfium은 글꼴 사전을 주지 않으므로 그 쪽 글꼴의 /Differences를 pypdf로 읽는다(제어 문자가 나온 쪽만, 처음 필요할 때).
수식 글꼴(fonts.is_math_font)만 되찾는다: pdfium은 줄 끝에서 나눈 낱말의 하이픈도 0x02로 주므로 본문 글꼴은 건드리지 않는다.
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


def glyph_text(name: str) -> str | None:
    """글리프 이름의 글자. 모르는 이름(늘이는 조각 등)이면 None."""
    if name in GLYPHS:
        return GLYPHS[name]
    unicode = _UNI.match(name)
    if unicode:
        return chr(int(unicode.group(1), 16))
    return GLYPHS.get(_SIZE.sub("", name))


class FontDifferences:
    """쪽 글꼴의 /Differences(글자 코드 → 글리프 이름). PDF는 처음 필요할 때 pypdf로 열고 쪽마다 한 번 읽는다.
    PDF를 읽지 못하면(신뢰할 수 없는 PDF) 되찾지 않는다."""

    def __init__(self, path: str) -> None:
        self._path = path
        self._reader = None
        self._pages: dict[int, dict[str, dict[int, str] | None]] = {}

    def text(self, page_index: int, font: str, code: int) -> str | None:
        """그 쪽 그 글꼴(부분 글꼴 접두 없이)의 글자 코드가 가리키는 글자. 같은 이름의 글꼴이 코드를 다르게 쓰거나 모르면 None."""
        fonts = self._pages.get(page_index)
        if fonts is None:
            fonts = self._pages[page_index] = self._read(page_index)
        names = fonts.get(_SUBSET.sub("", font))
        name = names.get(code) if names else None
        return glyph_text(name) if name else None

    def _read(self, page_index: int) -> dict[str, dict[int, str] | None]:
        try:
            if self._reader is None:
                from pypdf import PdfReader

                self._reader = PdfReader(self._path)
            fonts: dict[str, dict[int, str] | None] = {}
            _collect(self._reader.pages[page_index].get("/Resources"), fonts, depth=0)
            return fonts
        except Exception:  # noqa: BLE001 - 신뢰할 수 없는 PDF. 되찾지 못해도 본문 추출은 계속한다
            return {}


def _collect(resources, fonts: dict[str, dict[int, str] | None], depth: int) -> None:
    """자원의 글꼴(그림 안 Form의 글꼴 포함, 세 겹까지). 같은 이름인데 /Differences가 다르면 None(쓰지 않는다)."""
    if resources is None or depth > 3:
        return
    resources = resources.get_object()
    for ref in (resources.get("/Font") or {}).values():
        font = ref.get_object()
        name = _SUBSET.sub("", str(font.get("/BaseFont", ""))[1:])
        differences = _differences(font)
        fonts[name] = differences if fonts.get(name, differences) == differences else None
    for ref in (resources.get("/XObject") or {}).values():
        form = ref.get_object()
        if form.get("/Subtype") == "/Form":
            _collect(form.get("/Resources"), fonts, depth + 1)


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
