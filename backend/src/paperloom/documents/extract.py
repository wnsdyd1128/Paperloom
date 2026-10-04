"""쪽 범위의 본문을 격리 하위 프로세스에서 추출한다 (IMPL §5.1·§5.3).

pypdfium2(pdfium)로 글자·loose box를 읽고 text_layout으로 문단을 묶는다. 수식 글꼴이 유니코드를 주지 않은 기호는
글꼴 사전의 글리프 이름으로 되찾는다(glyphs, pypdf). 신뢰할 수 없는 PDF이므로
documents.inspect처럼 시간 제한을 두고, POSIX에서는 메모리·CPU도 제한한다(`infrastructure.isolation`).

하위 프로세스: `python -m paperloom.documents.extract <pdf> <first_page> <stop_page>` → stdout에 JSON 한 줄.
"""

import ctypes
import json
import math
import subprocess
import sys
from collections import Counter
from pathlib import Path

from paperloom.documents.fonts import font_style, is_math_font
from paperloom.documents.glyphs import FontDifferences
from paperloom.documents.tables import horizontal_rules
from paperloom.documents.text_layout import Char, layout_page
from paperloom.infrastructure.isolation import limit_resources
from paperloom.reading.figures import Graphic, figure_candidates, page_graphics

PARSER_NAME = "pypdfium2"
# 글꼴의 ascent − descent가 글꼴 크기의 이만큼보다 작으면 글꼴 정보가 망가졌다: pdfium의 loose box가 글자 모양 상자가 되어(e는 짧고
# d·p는 길다) 줄 높이가 x 높이쯤이 되고 보통의 줄 사이도 문단 사이로 보였다(2026-10-04 사용자 논문 CAAS, LinLibertineT 0.45·0).
MIN_FONT_SPAN = 0.6
# 그런 본문 글꼴의 글자는 기준선 둘레 보통 글꼴의 아래·위(글꼴 크기 배수)까지 넓힌다(사용자 논문 −0.24·0.71, CBANA −0.22·0.70).
# 수식 글꼴은 넓히지 않는다: 사용자 논문의 rtxmi는 ascent 0인데 넓히면 따로 놓인 수식의 줄이 달라졌다(cases 둘째 줄이 본문 문단으로).
BASELINE_BAND = (-0.22, 0.72)


class ExtractFailed(Exception):
    """쪽 범위를 추출하지 못했다. code는 RESOURCE_LIMIT, PARSER_ERROR 등 (IMPL §5.2)."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def extract_pages(path: Path, first: int, stop: int, timeout_seconds: float) -> list[dict]:
    """[first, stop) 쪽의 추출 결과. 실패하면 ExtractFailed. 하위 프로세스를 띄우지 못하면 OSError."""
    try:
        result = subprocess.run(
            [sys.executable, "-m", "paperloom.documents.extract", str(path), str(first), str(stop)],
            capture_output=True,
            timeout=timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired:
        raise ExtractFailed("RESOURCE_LIMIT") from None
    try:
        report = json.loads(result.stdout)
    except ValueError:
        raise ExtractFailed("PARSER_ERROR") from None  # 비정상 종료
    if "code" in report:
        raise ExtractFailed(report["code"])
    return report["pages"]


def _extract(path: str, first: int, stop: int) -> dict:
    import pypdfium2 as pdfium
    import pypdfium2.raw as pdfium_c

    from paperloom.reading.geometry import page_geometry

    try:
        document = pdfium.PdfDocument(path)
    except pdfium.PdfiumError as error:
        return {"code": "PASSWORD_REQUIRED" if error.err_code == pdfium_c.FPDF_ERR_PASSWORD else "MALFORMED_PDF"}
    try:
        pages = []
        differences = FontDifferences(path)
        for index in range(first, stop):
            page = document[index]
            geometry = page_geometry(page)
            chars, rotation = _read_chars(page, pdfium_c, lambda font, code, index=index: differences.text(index, font, code))
            graphics = _graphics(page)
            layout = layout_page(
                chars,
                geometry.view_box,
                _image_coverage(page, geometry.view_box, pdfium_c),
                rotation,
                [figure.box for figure in figure_candidates(graphics, geometry.view_box)],
                horizontal_rules(graphics, geometry.view_box),
            )
            pages.append(
                {
                    "page_index": index,
                    "page_label": document.get_page_label(index) or None,
                    "view_box": list(geometry.view_box),
                    "rotation": geometry.rotation,
                    "text_status": layout.text_status,
                    "flags": layout.flags,
                    "quality": layout.quality,
                    "blocks": [
                        {
                            "text": block.text,
                            "regions": block.regions,
                            "quality_flags": block.quality_flags,
                            "styles": block.styles,
                            "font_size": block.font_size,
                        }
                        for block in layout.blocks
                    ],
                }
            )
            page.close()
        return {"pages": pages}
    finally:
        document.close()


def _read_chars(page, pdfium_c, recover=None) -> tuple[list[Char], int]:
    """pdfium 텍스트 순서의 글자와 가장 많은 글자의 글줄 방향(반시계, 90의 배수). recover(글꼴 이름, 코드)는 수식 글꼴이
    유니코드를 주지 않아 제어 문자로 나온 글자를 되찾는다(없으면 None)."""
    textpage = page.get_textpage()
    rect = pdfium_c.FS_RECTF()
    font = _FontReader(textpage.raw, pdfium_c)
    chars = []
    angles: Counter[int] = Counter()
    try:
        for index in range(textpage.count_chars()):
            code = pdfium_c.FPDFText_GetUnicode(textpage.raw, index)
            text = chr(code) if code else "�"
            if pdfium_c.FPDFText_IsGenerated(textpage.raw, index) or text in "\r\n":
                chars.append(Char(" ", None))
                continue
            if not pdfium_c.FPDFText_GetLooseCharBox(textpage.raw, index, ctypes.byref(rect)):
                chars.append(Char(" ", None))
                continue
            unmapped = bool(pdfium_c.FPDFText_HasUnicodeMapError(textpage.raw, index)) or _is_unmapped(code)
            style, size, math_font = font.read(index)
            box = (rect.left, rect.bottom, rect.right, rect.top)
            band = None if math_font else font.baseline_band(index, size)  # 수식 글꼴은 원래 글꼴 정보가 남다르다(rtxmi ascent 0)
            if band:
                box = (rect.left, min(rect.bottom, band[0]), rect.right, max(rect.top, band[1]))
            if 0 < code < 0x20 and math_font and recover is not None:
                # 프라임·합·큰 괄호 등(2026-10-04). 수식 글꼴만: pdfium은 본문 낱말의 줄 끝 하이픈도 0x02로 준다
                found = recover(font.name, code)
                if found:
                    text, unmapped = found, False
            chars.append(Char(text, box, unmapped, style, size, math_font))
            if text.strip():
                # pdfium의 각도는 시계 방향이다(위로 가는 글줄이 270°). 반시계로 바꾼다. 실패하면 -1.
                angle = pdfium_c.FPDFText_GetCharAngle(textpage.raw, index)
                if angle >= 0:
                    angles[-round(math.degrees(angle) / 90) % 4 * 90] += 1
    finally:
        textpage.close()
    return chars, angles.most_common(1)[0][0] if angles else 0


class _FontReader:
    """글자의 글꼴 모양(fonts.font_style)과 크기(pt). 크기는 글꼴 크기 × 글자 행렬의 세로 배율이다(LaTeX PDF는
    글꼴 크기 1에 행렬로 키운다: 사용자 논문 본문 1 × 9.96)."""

    def __init__(self, raw, pdfium_c) -> None:
        self._raw, self._c = raw, pdfium_c
        self._name = ctypes.create_string_buffer(128)
        self._flags = ctypes.c_int()
        self._matrix = pdfium_c.FS_MATRIX()
        self.name = ""  # 마지막으로 읽은 글자의 글꼴 이름(부분 글꼴 접두 없이)
        self._broken: dict[int, bool] = {}  # 글꼴(주소) → ascent·descent가 망가졌는지
        self._ascent, self._descent = ctypes.c_float(), ctypes.c_float()
        self._x, self._y = ctypes.c_double(), ctypes.c_double()

    def read(self, index: int) -> tuple[str, float, bool]:
        """(모양, 크기 pt, 수식 글꼴인지)"""
        c = self._c
        length = c.FPDFText_GetFontInfo(self._raw, index, self._name, len(self._name), ctypes.byref(self._flags))
        name = self.name = self._name.value.decode("latin-1") if 0 < length <= len(self._name) else ""
        style = font_style(name, self._flags.value if length else 0, c.FPDFText_GetFontWeight(self._raw, index))
        size = c.FPDFText_GetFontSize(self._raw, index)
        if c.FPDFText_GetMatrix(self._raw, index, ctypes.byref(self._matrix)):
            size *= math.hypot(self._matrix.c, self._matrix.d)
        return style, round(size, 2), is_math_font(name)


    def baseline_band(self, index: int, size: float) -> tuple[float, float] | None:
        """글꼴 정보가 망가진 글자(MIN_FONT_SPAN)면 기준선 둘레 보통 글꼴의 세로 범위(아래, 위, pt). 아니면 None(loose box 그대로).
        size는 글자 크기(pt, read). 돌린 글자는 다루지 않는다."""
        c = self._c
        font = c.FPDFTextObj_GetFont(c.FPDFText_GetTextObject(self._raw, index))
        key = ctypes.cast(font, ctypes.c_void_p).value
        if not key or size <= 0:
            return None
        broken = self._broken.get(key)
        if broken is None:
            one = ctypes.c_float(1.0)
            measured = c.FPDFFont_GetAscent(font, one, ctypes.byref(self._ascent)) and c.FPDFFont_GetDescent(font, one, ctypes.byref(self._descent))
            broken = self._broken[key] = bool(measured) and self._ascent.value - self._descent.value < MIN_FONT_SPAN
        angle = c.FPDFText_GetCharAngle(self._raw, index)
        if not broken or not (0 <= angle < 0.01 or angle > 2 * math.pi - 0.01):
            return None
        if not c.FPDFText_GetCharOrigin(self._raw, index, ctypes.byref(self._x), ctypes.byref(self._y)):
            return None
        return self._y.value + BASELINE_BAND[0] * size, self._y.value + BASELINE_BAND[1] * size


def _graphics(page) -> list[Graphic]:
    """쪽의 그림 객체(그림 후보·표 가로줄). 그림·표 안 글자를 쪽 번역에서 빼는 데만 쓰므로 실패하면 없는 것으로 본다."""
    try:
        return page_graphics(page)
    except Exception:  # noqa: BLE001 - 신뢰할 수 없는 PDF의 객체. 본문 추출은 계속한다
        return []


def _is_unmapped(code: int) -> bool:
    return code in (0, 0xFFFD) or 0xE000 <= code <= 0xF8FF


def _image_coverage(page, view_box, pdfium_c) -> float:
    """이미지 객체(Form XObject 안 포함)가 덮는 쪽 비율. 겹친 이미지는 더해지므로 1에서 자른다."""
    x0, y0, x1, y1 = view_box
    area = 0.0
    for obj in page.get_objects(filter=[pdfium_c.FPDF_PAGEOBJ_IMAGE]):
        left, bottom, right, top = obj.get_bounds()
        width = min(right, x1) - max(left, x0)
        height = min(top, y1) - max(bottom, y0)
        if width > 0 and height > 0:
            area += width * height
    return min(area / ((x1 - x0) * (y1 - y0)), 1.0)


def _main() -> None:
    limit_resources()
    try:
        report = _extract(sys.argv[1], int(sys.argv[2]), int(sys.argv[3]))
    except MemoryError:
        report = {"code": "RESOURCE_LIMIT"}
    print(json.dumps(report))


if __name__ == "__main__":
    _main()
