"""쪽 범위의 본문을 격리 하위 프로세스에서 추출한다 (IMPL §5.1·§5.3).

pypdfium2(pdfium)로 글자·loose box를 읽고 text_layout으로 문단을 묶는다. 수식 글꼴이 유니코드를 주지 않은 기호는
글꼴 사전의 글리프 이름으로 되찾고, 3B2 조판 PDF의 AdvP 수식 글꼴은 TeX 글꼴 자리로 되돌린다(glyphs, pypdf). 신뢰할 수 없는 PDF이므로
documents.inspect처럼 시간 제한을 두고, POSIX에서는 메모리·CPU도 제한한다(`infrastructure.isolation`).

하위 프로세스: `python -m paperloom.documents.extract <pdf> <first_page> <stop_page> [--plain] [--images <폴더>] [--ocr <폴더>]
[--overrides <파일>]` → stdout에 JSON 한 줄.
--plain(간이 추출, 한 쪽 추출이 실패했을 때 parsing이 다시 해 본다): 글꼴 사전 읽기(pypdf)·그림·표 가로줄·Form 잘라내기·이미지
넓이를 보지 않고 pdfium 글자로만 문단을 묶는다. 쪽에 extract_simplified 표시를 붙인다(그림·표 안 글자를 가리지 못한다).
--images: 쪽마다 레이아웃 모델(documents.layout_model) 입력 그림을 `<폴더>/<page_index>.rgb`에 쓴다. 모델은 서버 프로세스가
돌린다(이 프로세스의 메모리 제한 아래에서는 CUDA를 시작하지 못한다). 간이 추출은 그리지 않는다.
--ocr: 글꼴 정보로 되찾지 못한 글자가 든 글줄을 글줄 인식 모델(documents.ocr_model) 입력으로 그려 `<폴더>/ocr-<쪽>-<n>.rgb`에, 글줄마다
글자 자리(pdfium 글자 차례)·글·못 읽었는지를 `<폴더>/ocr-<쪽>.json`에 쓴다(_write_ocr_lines). parsing이 읽어 채울 글자를 정하고
(documents.ocr_align) 그 쪽을 --overrides로 다시 추출한다: JSON {쪽: {글자 차례: 글}}, ""는 글자가 아니다.
"""

import ctypes
import json
import math
import subprocess
import sys
from collections import Counter
from dataclasses import replace
from pathlib import Path

from paperloom.documents.char_recovery import CharRecovery
from paperloom.documents.fonts import font_style, is_math_font
from paperloom.documents.glyphs import FontDifferences
from paperloom.documents.layout_model import INPUT_SIZE
from paperloom.documents.ocr_model import OCR_HEIGHT
from paperloom.documents.tables import horizontal_rules
from paperloom.documents.text_layout import Char, layout_page
from paperloom.infrastructure.isolation import limit_resources
from paperloom.reading.figures import Graphic, figure_candidates, form_text_clips, page_graphics

PARSER_NAME = "pypdfium2"
SIMPLIFIED = "extract_simplified"  # 쪽 표시: 간이 추출(--plain)로 뽑았다
# 글꼴의 ascent − descent가 글꼴 크기의 이만큼보다 작으면 글꼴 정보가 망가졌다: pdfium의 loose box가 글자 모양 상자가 되어(e는 짧고
# d·p는 길다) 줄 높이가 x 높이쯤이 되고 보통의 줄 사이도 문단 사이로 보였다(2026-10-04 사용자 논문 CAAS, LinLibertineT 0.45·0).
MIN_FONT_SPAN = 0.6
# 그런 본문 글꼴의 글자는 기준선 둘레 보통 글꼴의 아래·위(글꼴 크기 배수)까지 넓힌다(사용자 논문 −0.24·0.71, CBANA −0.22·0.70).
# 수식 글꼴은 넓히지 않는다: 사용자 논문의 rtxmi는 ascent 0인데 넓히면 따로 놓인 수식의 줄이 달라졌다(cases 둘째 줄이 본문 문단으로).
BASELINE_BAND = (-0.22, 0.72)
# 레이아웃 모델 입력은 쪽을 긴 변 이만큼(px)으로 그린 뒤 INPUT_SIZE 정사각형으로 줄인다(모델을 평가한 그림과 같게)
LAYOUT_RENDER_SIDE = 1100
OCR_RENDER_SCALE = 4.0  # 글줄 인식 그림은 쪽을 이 배율(288dpi)로 그려 잘라 높이 OCR_HEIGHT로 줄인다
OCR_PAD = 0.15  # 글줄 상자 둘레 여백(글줄 높이 배수)
OCR_MAX_WIDTH = 3200  # 글줄 그림 너비 상한(px, 모델 설정)
OCR_MAX_LINES = 300  # 한 쪽에서 그릴 글줄 수 상한


class ExtractFailed(Exception):
    """쪽 범위를 추출하지 못했다. code는 RESOURCE_LIMIT, PARSER_ERROR 등 (IMPL §5.2)."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def extract_pages(
    path: Path,
    first: int,
    stop: int,
    timeout_seconds: float,
    plain: bool = False,
    images: Path | None = None,
    ocr: Path | None = None,
    overrides: Path | None = None,
) -> list[dict]:
    """[first, stop) 쪽의 추출 결과. 실패하면 ExtractFailed. 하위 프로세스를 띄우지 못하면 OSError. plain은 간이 추출이다.
    images가 있으면 그 폴더에 쪽마다 레이아웃 모델 입력 그림(<page_index>.rgb)을 쓴다(간이 추출과 그리지 못한 쪽은 없다).
    ocr가 있으면 그 폴더에 못 읽은 글줄 그림을, overrides(JSON 파일)가 있으면 그 글자를 채워 추출한다(모듈 설명)."""
    options = [*(["--plain"] if plain else []), *(["--images", str(images)] if images is not None else [])]
    options += [*(["--ocr", str(ocr)] if ocr is not None else []), *(["--overrides", str(overrides)] if overrides is not None else [])]
    try:
        result = subprocess.run(
            [sys.executable, "-m", "paperloom.documents.extract", str(path), str(first), str(stop), *options],
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


def _extract(
    path: str, first: int, stop: int, plain: bool = False, images: str | None = None, ocr: str | None = None, overrides: dict | None = None
) -> dict:
    import pypdfium2 as pdfium
    import pypdfium2.raw as pdfium_c

    from paperloom.reading.geometry import page_geometry

    try:
        document = pdfium.PdfDocument(path)
    except pdfium.PdfiumError as error:
        return {"code": "PASSWORD_REQUIRED" if error.err_code == pdfium_c.FPDF_ERR_PASSWORD else "MALFORMED_PDF"}
    try:
        pages = []
        differences = None if plain else FontDifferences(path)
        for index in range(first, stop):
            page = document[index]
            geometry = page_geometry(page)
            if plain:
                chars, rotation = _read_chars(page, pdfium_c, CharRecovery(None, index))
                layout = layout_page(chars, geometry.view_box, 0.0, rotation)
            else:
                fills = {int(position): value for position, value in (overrides or {}).get(str(index), {}).items()}
                chars, rotation = _read_chars(page, pdfium_c, CharRecovery(differences, index), _form_clips(page, pdfium_c), fills)
                graphics = _graphics(page)
                layout = layout_page(
                    chars,
                    geometry.view_box,
                    _image_coverage(page, geometry.view_box, pdfium_c),
                    rotation,
                    [figure.box for figure in figure_candidates(graphics, geometry.view_box)],
                    horizontal_rules(graphics, geometry.view_box),
                )
                if images is not None:
                    _write_layout_image(page, Path(images) / f"{index}.rgb")
                if ocr is not None and rotation == 0 and geometry.rotation == 0:
                    _write_ocr_lines(page, chars, geometry.view_box, Path(ocr), index)
            pages.append(
                {
                    "page_index": index,
                    "page_label": document.get_page_label(index) or None,
                    "view_box": list(geometry.view_box),
                    "rotation": geometry.rotation,
                    "text_status": layout.text_status,
                    "flags": [*layout.flags, SIMPLIFIED] if plain else layout.flags,
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


def _read_chars(page, pdfium_c, recovery: CharRecovery, clips=None, fills: dict[int, str] | None = None) -> tuple[list[Char], int]:
    """pdfium 텍스트 순서의 글자(글자 차례마다 하나)와 가장 많은 글자의 글줄 방향(반시계, 90의 배수). pdfium이 유니코드를 주지 못한
    글자는 recovery(documents.char_recovery)로 되찾는다(늘이는 괄호 조각은 위치 없는 공백). clips(글자 객체 주소 → 쪽 좌표 잘라내기
    상자, reading.figures.form_text_clips)에서 글자 가운데가 상자 밖이면 보이지 않는 글자라 뺀다. fills(글자 차례 → 글)는 OCR로 읽어
    채운 글자다(documents.ocr_align, ""는 글자가 아니다)."""
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
            if clips and (clip := clips.get(ctypes.cast(pdfium_c.FPDFText_GetTextObject(textpage.raw, index), ctypes.c_void_p).value)):
                if not (clip[0] <= (rect.left + rect.right) / 2 <= clip[2] and clip[1] <= (rect.bottom + rect.top) / 2 <= clip[3]):
                    chars.append(Char(" ", None))  # Form 안에서 잘려 보이지 않는 글자
                    continue
            unmapped = bool(pdfium_c.FPDFText_HasUnicodeMapError(textpage.raw, index)) or _is_unmapped(code)
            style, size, math_font = font.read(index)
            box = (rect.left, rect.bottom, rect.right, rect.top)
            band = None if math_font else font.baseline_band(index, size)  # 수식 글꼴은 원래 글꼴 정보가 남다르다(rtxmi ascent 0)
            if band:
                box = (rect.left, min(rect.bottom, band[0]), rect.right, max(rect.top, band[1]))
            found = recovery.char(font.name, code, unmapped, math_font, len(chars))
            if fills and index in fills:
                found = fills[index] or " "
            if found == " ":
                chars.append(Char(" ", None))
                continue
            if found:  # 모르는 사용자 영역 글자는 두어 본문 글에서 뺀다(block_text)
                text, unmapped = found, False
            chars.append(Char(text, box, unmapped, style, size, math_font))
            if text.strip():
                # pdfium의 각도는 시계 방향이다(위로 가는 글줄이 270°). 반시계로 바꾼다. 실패하면 -1.
                angle = pdfium_c.FPDFText_GetCharAngle(textpage.raw, index)
                if angle >= 0:
                    angles[-round(math.degrees(angle) / 90) % 4 * 90] += 1
    finally:
        textpage.close()
    recovery.finish(chars)
    # 3B2 기호 글꼴의 빗금(U+0338)은 긋는 글자보다 먼저 나온다("6¼"가 ≠). 결합 문자는 뒤에 와야 하므로 글만 바꾼다(NFKC에서 "=\u0338"은 ≠)
    index = 0
    while index < len(chars) - 1:
        if chars[index].text == "\u0338" and chars[index + 1].text.strip():
            chars[index], chars[index + 1] = replace(chars[index], text=chars[index + 1].text), replace(chars[index + 1], text="\u0338")
            index += 1  # 옮긴 빗금을 다시 옮기지 않는다
        index += 1
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


def _form_clips(page, pdfium_c) -> dict[int, tuple[float, float, float, float]]:
    """Form 안 글자 객체의 잘라내기 상자. 읽지 못하면 없는 것으로 본다(글자를 빼지 않는다)."""
    try:
        return form_text_clips(page, pdfium_c)
    except Exception:  # noqa: BLE001 - 신뢰할 수 없는 PDF의 객체. 본문 추출은 계속한다
        return {}


def _write_layout_image(page, path: Path) -> None:
    """레이아웃 모델 입력 그림(INPUT_SIZE × INPUT_SIZE RGB 바이트, /Rotate 적용). 그리지 못하면 쓰지 않는다(그 쪽은 규칙만 쓴다)."""
    from PIL import Image

    try:
        width, height = page.get_size()
        image = page.render(scale=LAYOUT_RENDER_SIDE / max(width, height)).to_pil().convert("RGB")
        path.write_bytes(image.resize((INPUT_SIZE, INPUT_SIZE), Image.BICUBIC).tobytes())
    except Exception:  # noqa: BLE001 - 신뢰할 수 없는 PDF의 쪽. 본문 추출은 계속한다
        pass


def _write_ocr_lines(page, chars: list[Char], view_box, folder: Path, page_index: int) -> None:
    """못 읽은 글자가 든 글줄(_text_lines)을 글줄 인식 모델 입력(높이 OCR_HEIGHT RGB 바이트)으로 그려 쓰고, 글줄마다 글자 차례·글·
    못 읽었는지·그림 너비를 JSON으로 쓴다. 그리지 못하면 쓰지 않는다(그 쪽은 못 읽은 채로 둔다)."""
    from PIL import Image

    lines = [line for line in _text_lines(chars) if any(chars[index].unmapped for index in line)][:OCR_MAX_LINES]
    if not lines:
        return
    try:
        image = page.render(scale=OCR_RENDER_SCALE).to_pil().convert("RGB")
        x0, _, _, y1 = view_box
        entries = []
        for number, line in enumerate(lines):
            boxes = [chars[index].box for index in line]
            left, bottom = min(box[0] for box in boxes), min(box[1] for box in boxes)
            right, top = max(box[2] for box in boxes), max(box[3] for box in boxes)
            pad = OCR_PAD * (top - bottom)
            crop = image.crop(tuple(round(value * OCR_RENDER_SCALE) for value in (left - x0 - pad, y1 - top - pad, right - x0 + pad, y1 - bottom + pad)))
            if crop.width < 1 or crop.height < 1:
                continue
            width = max(16, min(OCR_MAX_WIDTH, round(crop.width * OCR_HEIGHT / crop.height)))
            (folder / f"ocr-{page_index}-{number}.rgb").write_bytes(crop.resize((width, OCR_HEIGHT), Image.BICUBIC).tobytes())
            entries.append({"image": f"ocr-{page_index}-{number}.rgb", "width": width, "chars": line,
                            "texts": [chars[index].text for index in line], "unmapped": [chars[index].unmapped for index in line]})
        (folder / f"ocr-{page_index}.json").write_text(json.dumps(entries), encoding="utf-8")
    except Exception:  # noqa: BLE001 - 신뢰할 수 없는 PDF의 쪽. 본문 추출은 계속한다
        pass


def _text_lines(chars: list[Char]) -> list[list[int]]:
    """위치 있는 글자(글자 차례)를 pdfium 차례대로 글줄로 묶는다: 글자 가운데가 줄 첫 글자 높이 띠(위아래로 30% 넓힘) 안에 있고
    앞 글자 오른쪽 끝에서 줄 높이 세 배보다 왼쪽으로 돌아가지 않으면 같은 줄이다. OCR로 읽을 글줄을 고를 때만 쓴다."""
    lines: list[list[int]] = []
    band: tuple[float, float] | None = None
    previous_right = 0.0
    for index, char in enumerate(chars):
        if char.box is None or not (char.text.strip() or char.unmapped):  # 못 읽은 제어 문자(옛 TeX 합자 fi = 0x0C)도 글자다
            continue
        left, bottom, right, top = char.box
        middle = (bottom + top) / 2
        if band and band[0] <= middle <= band[1] and left >= previous_right - 3 * (band[1] - band[0]):
            lines[-1].append(index)
        else:
            slack = 0.3 * (top - bottom)
            band = (bottom - slack, top + slack)
            lines.append([index])
        previous_right = right
    return lines


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
        options = sys.argv[4:]

        def value(name: str) -> str | None:
            return options[options.index(name) + 1] if name in options else None

        overrides = json.loads(Path(value("--overrides")).read_text(encoding="utf-8")) if value("--overrides") else None
        report = _extract(sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), "--plain" in options, value("--images"), value("--ocr"), overrides)
    except MemoryError:
        report = {"code": "RESOURCE_LIMIT"}
    print(json.dumps(report))


if __name__ == "__main__":
    _main()
