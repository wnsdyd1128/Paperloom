"""번역본 PDF의 글꼴 (2026-11-15 사용자 결정: 앱 화면과 같은 Wanted Sans를, 쓴 글자만 담아 PDF에 넣는다).

번역문은 Wanted Sans(OFL, fonts/OFL.txt) 보통·굵게로 쓴다. Wanted Sans에 없는 그리스 문자·수학 기호는 PDF 표준 Symbol
글꼴로 쓴다(뷰어에 들어 있어 PDF에 넣지 않는다). 둘 다 없는 글자는 NFKC로 바꿔 쓸 수 있으면 바꾸고(𝐿 → L, ℝ → R),
그래도 없으면 Wanted Sans의 빈 글자(.notdef)로 둔다.

Symbol 글자 폭은 pdfium에서 읽는다. pdfium은 여러 스레드에서 함께 부르면 안 되므로 내보내기 하위 프로세스(writer)에서만 쓴다.
"""

import ctypes
import io
import unicodedata
from pathlib import Path

FONT_DIR = Path(__file__).resolve().parent / "fonts"
WANTED = "wanted"
SYMBOL = "symbol"
# Symbol은 그리스 대문자 오메가·델타와 뮤를 모양이 같은 다른 코드 포인트(옴 기호·증분·마이크로 기호)로 가진다
_ALIASES = {0x03A9: 0x2126, 0x0394: 0x2206, 0x03BC: 0x00B5, 0x03F5: 0x03B5, 0x22C5: 0x00B7}
_NOT_IN_SYMBOL = "가"  # Symbol에 없는 글자. pdfium은 없는 글자에도 폭(기본 폭)을 준다


class Fonts:
    """글자마다 쓸 글꼴과 폭(typeset.Metrics), PDF에 넣을 글꼴. with 블록 안에서 쓴다(pdfium 문서를 닫는다)."""

    def __init__(self) -> None:
        import pypdfium2 as pdfium
        import pypdfium2.raw as raw
        from fontTools.ttLib import TTFont

        self._faces = {bold: TTFont(_path(bold), lazy=True) for bold in (False, True)}
        self._cmaps = {bold: face.getBestCmap() for bold, face in self._faces.items()}
        self._widths = {bold: face["hmtx"] for bold, face in self._faces.items()}
        regular = self._faces[False]
        units = regular["head"].unitsPerEm
        self._units = units
        self.ascent = regular["hhea"].ascent / units
        self.descent = -regular["hhea"].descent / units
        self._raw = raw
        self._document = pdfium.PdfDocument.new()
        self._symbol = raw.FPDFText_LoadStandardFont(self._document.raw, b"Symbol")
        self._symbol_widths: dict[str, float | None] = {}
        self._missing_width = self._symbol_width(_NOT_IN_SYMBOL)

    def __enter__(self) -> "Fonts":
        return self

    def __exit__(self, *_) -> None:
        self._raw.FPDFFont_Close(self._symbol)
        self._document.close()

    def resolve(self, text: str) -> str:
        """두 글꼴에 없는 글자를 같은 모양의 글자(Symbol의 다른 코드 포인트, NFKC)로 바꾼다."""
        return "".join(self._resolve(char) for char in text)

    def font_of(self, char: str) -> str:
        return SYMBOL if ord(char) not in self._cmaps[False] and self._in_symbol(char) else WANTED

    def advance(self, char: str, bold: bool) -> float:
        if self.font_of(char) == SYMBOL:
            return self._symbol_widths[char]  # type: ignore[return-value]
        glyph = self._cmaps[bold].get(ord(char), ".notdef")
        return self._widths[bold][glyph][0] / self._units

    def subset(self, bold: bool, chars: set[str]) -> bytes:
        """그 굵기의 Wanted Sans에서 chars만 담은 TrueType 글꼴. 글자 모양 바꾸기(GSUB·GPOS)와 힌팅은 쓰지 않아 뺀다."""
        from fontTools import subset
        from fontTools.ttLib import TTFont

        options = subset.Options()
        options.layout_features = []
        options.hinting = False
        options.name_IDs = ["*"]  # 저작권·라이선스 이름을 남긴다(OFL)
        font = TTFont(_path(bold))
        subsetter = subset.Subsetter(options)
        subsetter.populate(text="".join(chars))
        subsetter.subset(font)
        output = io.BytesIO()
        font.save(output)
        return output.getvalue()

    def _resolve(self, char: str) -> str:
        if ord(char) in self._cmaps[False]:
            return char
        alias = chr(_ALIASES.get(ord(char), ord(char)))
        if ord(alias) in self._cmaps[False] or self._in_symbol(alias):
            return alias
        folded = unicodedata.normalize("NFKC", char)
        if folded != char and all(ord(item) in self._cmaps[False] or self._in_symbol(item) for item in folded):
            return folded
        return char

    def _in_symbol(self, char: str) -> bool:
        width = self._symbol_width(char)
        return width is not None and width != self._missing_width

    def _symbol_width(self, char: str) -> float | None:
        if char not in self._symbol_widths:
            width = ctypes.c_float()
            found = self._raw.FPDFFont_GetGlyphWidth(self._symbol, ord(char), 1.0, ctypes.byref(width))
            self._symbol_widths[char] = width.value if found else None
        return self._symbol_widths[char]


def _path(bold: bool) -> Path:
    return FONT_DIR / ("WantedSans-Bold.ttf" if bold else "WantedSans-Regular.ttf")
