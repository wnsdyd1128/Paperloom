"""번역본 PDF의 번역 쪽 그리기 (2026-11-15 사용자 요청: PDF로 내보낼 때 레이아웃 유지 번역본도 바탕으로 고른다).

번역한 쪽마다 원문 문단 자리를 흰 상자로 덮고 그 위에 번역문을 쓴 덮개 쪽을 pdfium으로 만들어 원문 쪽 위에 합친다
(pypdf merge_page). 원문 쪽의 내용은 고치지 않고 덮기만 하므로(웹의 레이아웃 유지 번역과 같다) 가려진 원문 글도 PDF 안에
남아 검색·복사에 잡힌다. 번역하지 않은 쪽은 그대로 둔다.

웹처럼 화면에 보이는 방향(회전 뒤)에서 조판하고, 그린 글은 /Rotate만큼 돌려 PDF 사용자 공간에 놓는다.
신뢰할 수 없는 PDF를 읽고 pdfium을 쓰므로 내보내기 하위 프로세스(writer)에서만 부른다.
"""

import ctypes
import io
from collections.abc import Sequence
from dataclasses import dataclass

from paperloom.pdf_export.fonts import SYMBOL, Fonts
from paperloom.pdf_export.typeset import BlockLayout, Rect, Run, SourceBlock, layout_block

Box = tuple[float, float, float, float]  # x0, y0, x1, y1 (PDF 사용자 공간)
Quads = dict[tuple[int, str, int], list[list[float]]]  # (쪽, 문단, 문장 묶음) → 그 번역문 줄 조각의 정본 quad

TEXT_RGB = (27, 26, 25)  # 웹 .translated-block 글자색 #1b1a19
ITALIC_SKEW = 0.2  # 기울임 글꼴이 없어 글자를 눕힌다(브라우저가 기울임을 흉내 내는 것과 같다)


@dataclass(frozen=True)
class PageSpace:
    """화면 방향 좌표(회전 뒤, 좌상단 원점, pt)와 정본 좌표(anchor.v1: 회전 전 view box 기준 0~1)·PDF 사용자 공간 사이 변환.
    웹 PDF.js viewport와 같이 /Rotate는 시계 방향이다."""

    view_box: Box
    rotation: int  # 0, 90, 180, 270

    @property
    def _box_size(self) -> tuple[float, float]:
        x0, y0, x1, y1 = self.view_box
        return x1 - x0, y1 - y0

    @property
    def width(self) -> float:
        """화면 방향의 쪽 폭"""
        w, h = self._box_size
        return h if self.rotation in (90, 270) else w

    def to_display(self, u: float, v: float) -> tuple[float, float]:
        w, h = self._box_size
        return {0: (u * w, v * h), 90: ((1 - v) * h, u * w), 180: ((1 - u) * w, (1 - v) * h), 270: (v * h, (1 - u) * w)}[self.rotation]

    def to_norm(self, x: float, y: float) -> tuple[float, float]:
        w, h = self._box_size
        return {0: (x / w, y / h), 90: (y / w, 1 - x / h), 180: (1 - x / w, 1 - y / h), 270: (1 - y / w, x / h)}[self.rotation]

    def to_user(self, x: float, y: float) -> tuple[float, float]:
        u, v = self.to_norm(x, y)
        x0, y0, x1, y1 = self.view_box
        return x0 + u * (x1 - x0), y1 - v * (y1 - y0)

    def axes(self) -> tuple[tuple[float, float], tuple[float, float]]:
        """화면의 오른쪽과 위쪽이 PDF 사용자 공간에서 가리키는 방향"""
        return {0: ((1, 0), (0, 1)), 90: ((0, 1), (-1, 0)), 180: ((-1, 0), (0, -1)), 270: ((0, -1), (1, 0))}[self.rotation]

    def display_rect(self, region: Sequence[float]) -> Rect:
        """정본 상자 [u0, v0, u1, v1]의 화면 방향 상자"""
        points = [self.to_display(u, v) for u in (region[0], region[2]) for v in (region[1], region[3])]
        return Rect(min(x for x, _ in points), min(y for _, y in points), max(x for x, _ in points), max(y for _, y in points))

    def user_rect(self, rect: Rect) -> Box:
        points = [self.to_user(x, y) for x in (rect.left, rect.right) for y in (rect.top, rect.bottom)]
        return min(x for x, _ in points), min(y for _, y in points), max(x for x, _ in points), max(y for _, y in points)

    def quad(self, rect: Rect) -> list[float]:
        """화면 방향 상자의 정본 quad(좌상 → 우상 → 우하 → 좌하, 화면에서 본 차례)"""
        corners = ((rect.left, rect.top), (rect.right, rect.top), (rect.right, rect.bottom), (rect.left, rect.bottom))
        return [value for x, y in corners for value in self.to_norm(x, y)]


def page_space(page) -> PageSpace:
    """reading.geometry.page_geometry와 같은 규칙: CropBox(없으면 MediaBox)와 MediaBox의 교집합, /Rotate."""
    media = _ordered(page.mediabox)
    crop = _ordered(page.cropbox)
    view_box = max(media[0], crop[0]), max(media[1], crop[1]), min(media[2], crop[2]), min(media[3], crop[3])
    return PageSpace(view_box, page.rotation % 360)


def draw_translations(writer, pages: Sequence[dict], scale: float) -> Quads:
    """writer(pypdf.PdfWriter)의 번역한 쪽(pages: translated.TranslatedPage를 dict로)에 번역문을 덮어 쓴다."""
    import pypdf

    with Fonts() as fonts:
        laid: list[tuple[int, PageSpace, list[BlockLayout]]] = []
        for page in pages:
            index = page["page_index"]
            space = page_space(writer.pages[index])
            layouts = [
                layout_block(
                    SourceBlock(
                        block["block_id"],
                        [space.display_rect(region) for region in block["regions"]],
                        block["font_size"],
                        block["mark"],
                        [fonts.resolve(text) for text in block["groups"]],
                    ),
                    space.width,
                    scale,
                    fonts,
                )
                for block in page["blocks"]
                if block["regions"]
            ]
            laid.append((index, space, layouts))
        overlay = pypdf.PdfReader(io.BytesIO(_overlay(laid, fonts)))
    quads: Quads = {}
    for (index, space, layouts), cover in zip(laid, overlay.pages, strict=True):
        writer.pages[index].merge_page(cover)
        for layout in layouts:
            for group, rects in layout.groups.items():
                quads[(index, layout.block_id, group)] = [space.quad(rect) for rect in rects]
    return quads


def _overlay(laid: list[tuple[int, PageSpace, list[BlockLayout]]], fonts: Fonts) -> bytes:
    """번역한 쪽마다 한 쪽: 흰 상자를 모두 깐 뒤 번역문을 쓴다(뒤 문단 상자가 앞 문단 번역을 가리지 않게)."""
    import pypdfium2 as pdfium
    import pypdfium2.raw as raw

    document = pdfium.PdfDocument.new()
    used: dict[bool, set[str]] = {False: set(), True: set()}
    for _, _, layouts in laid:
        for layout in layouts:
            for run in layout.runs:
                used[run.bold].update(char for char in run.text if fonts.font_of(char) != SYMBOL)
    buffers = []  # pdfium이 글꼴을 쓰는 동안 붙잡아 둔다
    handles = {}
    for bold, chars in used.items():
        if chars:
            data = fonts.subset(bold, chars)
            buffers.append((ctypes.c_uint8 * len(data)).from_buffer_copy(data))
            handles[bold] = raw.FPDFText_LoadFont(document.raw, buffers[-1], len(data), raw.FPDF_FONT_TRUETYPE, True)
    handles[SYMBOL] = raw.FPDFText_LoadStandardFont(document.raw, b"Symbol")
    try:
        for _, space, layouts in laid:
            x0, y0, x1, y1 = space.view_box
            page = document.new_page(x1 - x0, y1 - y0)
            raw.FPDFPage_SetMediaBox(page.raw, x0, y0, x1, y1)  # merge_page는 덮개 쪽을 그 쪽 상자로 자른다
            for layout in layouts:
                _mask(raw, page, space.user_rect(layout.mask))
            for layout in layouts:
                for run in layout.runs:
                    _write(raw, document, page, space, run, fonts, handles)
            raw.FPDFPage_GenerateContent(page.raw)
            page.close()
        output = io.BytesIO()
        document.save(output)
        return output.getvalue()
    finally:
        for handle in handles.values():
            raw.FPDFFont_Close(handle)
        document.close()


def _mask(raw, page, box: Box) -> None:
    x0, y0, x1, y1 = box
    rect = raw.FPDFPageObj_CreateNewRect(x0, y0, x1 - x0, y1 - y0)
    raw.FPDFPageObj_SetFillColor(rect, 255, 255, 255, 255)
    raw.FPDFPath_SetDrawMode(rect, raw.FPDF_FILLMODE_WINDING, False)
    raw.FPDFPage_InsertObject(page.raw, rect)


def _write(raw, document, page, space: PageSpace, run: Run, fonts: Fonts, handles: dict) -> None:
    """글자를 글꼴(Wanted Sans·Symbol)마다 나눠 쓴다. 자리는 조판에서 잰 폭으로 정한다."""
    (dx, dy), (ux, uy) = space.axes()
    skew = ITALIC_SKEW if run.italic else 0.0
    offset = 0.0
    for font, text in _by_font(run.text, fonts):
        handle = handles[SYMBOL] if font == SYMBOL else handles[run.bold]
        item = raw.FPDFPageObj_CreateTextObj(document.raw, handle, run.size)
        encoded = text.encode("utf-16-le") + bytes(2)
        raw.FPDFText_SetText(item, ctypes.cast(ctypes.c_char_p(encoded), ctypes.POINTER(ctypes.c_ushort)))
        raw.FPDFPageObj_SetFillColor(item, *TEXT_RGB, 255)
        x, y = space.to_user(run.x + offset, run.baseline)
        raw.FPDFPageObj_Transform(item, dx, dy, skew * dx + ux, skew * dy + uy, x, y)
        raw.FPDFPage_InsertObject(page.raw, item)
        offset += sum(fonts.advance(char, run.bold) for char in text) * run.size


def _by_font(text: str, fonts: Fonts) -> list[tuple[str, str]]:
    pieces: list[tuple[str, str]] = []
    for char in text:
        font = fonts.font_of(char)
        if pieces and pieces[-1][0] == font:
            pieces[-1] = (font, pieces[-1][1] + char)
        else:
            pieces.append((font, char))
    return pieces


def _ordered(box) -> Box:
    x0, y0, x1, y1 = (float(value) for value in box)
    return min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1)
