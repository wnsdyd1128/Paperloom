"""쪽의 글자를 줄·문단(TextBlock)으로 묶고 쪽의 추출 상태를 정한다 (IMPL §5.3). 순수 함수만 둔다.

입력은 pdfium 텍스트 순서의 글자와 PDF 사용자 공간의 loose box(글꼴 ascent·descent 기준 상자)다.
- 줄: 글자의 세로 가운데가 줄에서 가장 큰 글자의 세로 범위 안이면 같은 줄이다. 그래서 위·아래첨자가 본문 줄에
  남는다. 앞 글자에서 멀리 떨어지면(단 사이, 표 칸) 줄을 나눈다.
- 문단: 글자 높이, 줄 사이 빈 공간, 줄의 시작 위치(첫 줄 들여쓰기)로 나눈다. 문단 텍스트는 줄을 공백으로
  잇고, 줄 끝 하이픈 뒤에 소문자가 오면 하이픈을 빼고 잇는다. 검색을 위해 NFKC로 정규화한다(합자 ﬁ → fi).
- 읽는 순서: 왼쪽·오른쪽 반에만 놓인 문단이 모두 많으면 두 단으로 보고, 쪽 너비 문단 사이마다 왼쪽 단 →
  오른쪽 단 순서로 둔다. 그 밖에는 pdfium 순서를 그대로 쓴다.
글자 방향이 돌아간 쪽(가로 쪽의 표 등)은 글자가 가로로 놓이도록 좌표를 돌려 묶은 뒤 상자를 되돌린다.
상태·순서는 휴리스틱이다. 보정된 확률이나 정답이라고 부르지 않는다.
"""

import hashlib
import json
import re
import statistics
import unicodedata
from dataclasses import dataclass, field

from paperloom.documents.block_kinds import IN_FIGURE, IN_TABLE, MATH, is_display_math
from paperloom.documents.tables import table_blocks

Box = tuple[float, float, float, float]  # left, bottom, right, top (PDF 사용자 공간)

# 기준값. 바꾸면 저장된 추출의 config_hash가 달라져 다시 추출한다(documents.parsing).
# 2: 글꼴 모양 구간·크기, 그림 안 글자 표시. 3: 수식·표 안·머리글·바닥글 표시(block_kinds·tables·running).
# 4: 수식 글꼴·이음말, 큰 첫 글자 문단, 참고문헌 문단 표시 (U7 쪽 번역, 2026-10-03).
# 5: 넓은 위첨자 아래 아래첨자로 돌아가도 같은 줄, 위·아래첨자 표시 ^·_ (2026-10-04)
# 6: 들여 쓴 줄들 뒤 끝까지 찬 들여 쓴 줄은 떼어 다음 줄과 한 문단(_starts_paragraph, 같은 날)
# 7: 줄 나누기는 줄 오른쪽 끝에서 재고 줄에 겹친 작은 글자(분모의 첨자)는 같은 줄, 줄 사이는 큰 기호를 빼고 잰다(같은 날)
# 8: 수식 글꼴이 유니코드를 주지 않은 기호(프라임·합·큰 괄호)를 글꼴의 글리프 이름으로 되찾는다(extract·glyphs, 같은 날)
# 9: ascent·descent가 망가진 글꼴의 글자 상자를 기준선 둘레로 넓힌다(extract.BASELINE_BAND), 글머리표 줄은 앞 항목의 끝까지 찬
#    마지막 줄을 떼어 가지 않는다(_starts_paragraph, 같은 날 사용자 논문 CAAS)
# 10: 넓은 입력 문단(Input:·Require:)이 든 의사코드 상자도 표 안으로 본다(tables._pseudocode, 2026-10-05 사용자 논문 TCPS·CAAS)
LAYOUT_VERSION = "10"
MIN_FONT_SIZE = 1.5  # pt. 이보다 작은 크기는 글자 행렬이 없는 공백 등이라 크기 셈에서 뺀다
FIGURE_TEXT_SHARE = 0.5  # 문단 상자의 이만큼이 그림 후보 안이면 그림 안 글자다
SCRIPT_BACKSTEP = 1.0  # 줄 높이 배수. 겹친 위·아래첨자처럼 이만큼은 왼쪽으로 돌아가도 같은 줄이다(앞 본 크기 글자까지는 늘 된다)
SCRIPT_SIZE = 0.85  # 글꼴 크기(없으면 글자 높이)가 줄 본 크기의 이 배수 이하면 위·아래첨자 후보다
SCRIPT_SHIFT = 0.15  # 줄 높이 배수. 첨자 후보의 가운데가 본 글자 가운데보다 이만큼 위·아래면 위첨자(^)·아래첨자(_)다
DROP_CAP = 1.8  # 줄 높이 배수. 줄 첫 글자(영문자)가 이만큼 크면 문단 첫 큰 글자다(IEEE 들어가기). 문단 나누기에서 뺀다
DROP_CAP_JOIN = 0.15  # 줄 높이 배수. 큰 글자와 다음 글자 사이가 이보다 좁으면 한 낱말이다(낱말 사이 공백보다 좁다)
BIG_GLYPH = 1.5  # 줄 높이 배수. 이보다 높은 글자(큰 Σ·∫·괄호)는 줄 사이를 잴 때 뺀다: 다음 줄까지 내려온다
LINE_BAND_SLACK = 0.3  # 줄 높이 배수. 가장 큰 글자의 세로 범위를 이만큼 넓혀 같은 줄을 찾는다(기호마다 상자 높이가 다르다)
LINE_SPLIT_GAP = 1.5  # 줄 높이 배수. 이보다 멀리 떨어진 글자는 다른 줄(단 사이, 표 칸)이다
SIZE_CHANGE = 0.25  # 글자 높이가 이 비율보다 달라지면 다른 문단(제목, 각주)
PARAGRAPH_GAP = 0.45  # 줄 사이 빈 공간이 줄 높이의 이 배수보다 크면 다른 문단
INDENT = 0.6  # 줄 시작이 앞 줄과 줄 높이의 이 배수보다 다르면 다른 문단(들여쓰기, 가운데 수식)
SHORT_LINE = 2.0  # 줄 높이 배수. 앞 줄이 이만큼 일찍 끝나고 다음 줄이 들어가 있으면 제목 다음 문단이다
COLUMN_SHARE = 0.25  # 왼쪽 반·오른쪽 반에만 놓인 문단의 글자가 각각 쪽 글자의 이 비율 이상이면 두 단
COLUMN_SLACK = 0.02  # 쪽 너비 비율. 가운데선을 이만큼 넘어도 한쪽 단으로 본다
MIN_TEXT_CHARS = 10  # 글자가 이보다 적으면 글자가 없는 쪽(쪽 번호뿐)으로 본다
UNMAPPED_SHARE = 0.02  # 유니코드로 바꾸지 못한 글자가 이 비율보다 많으면 partial
MOSTLY_IMAGE = 0.8  # 이미지가 쪽의 이 비율 이상을 덮고
MOSTLY_IMAGE_CHARS = 200  # 글자가 이보다 적으면 partial (스캔 쪽에 내려받기 문구만 있는 경우)
IMAGE_ONLY = 0.5  # 글자가 없고 이미지가 쪽의 이 비율 이상을 덮으면 image_only

# 목록 항목의 머리(글머리표, [1]·1.·1)·(a) 번호)
LIST_MARKER = re.compile(r"^(?:[•◦▪▫‣⁃∙*–—-]|\[\d{1,3}\]|\(?\d{1,2}[.)]|\([a-z]\))\s")
HYPHENS = "-‐"
SOFT_HYPHEN = "­"
LINE_END_HYPHEN = "\x02"  # pdfium이 줄 끝에서 단어를 나눈 하이픈을 이 글자로 준다


def config_hash() -> str:
    """추출 결과를 바꾸는 기준값의 해시. ParseRun에 기록한다."""
    names = sorted(name for name, value in globals().items() if name.isupper() and isinstance(value, (int, float, str)))
    values = {name: globals()[name] for name in names}
    return hashlib.sha256(json.dumps(values, sort_keys=True).encode()).hexdigest()[:16]


@dataclass(frozen=True)
class Char:
    text: str
    box: Box | None  # None: pdfium이 넣은 공백·줄바꿈처럼 위치가 없는 글자
    unmapped: bool = False  # 유니코드로 바꾸지 못한 글자(매핑 오류, 사용자 영역, U+FFFD)
    style: str = ""  # 글꼴 모양: "" 보통, "b" 굵게, "i" 기울임, "bi" (fonts.font_style)
    size: float = 0.0  # 글꼴 크기(pt, 글자 행렬 반영). 모르면 0
    math: bool = False  # 수식 글꼴의 글자(fonts.is_math_font)


@dataclass(frozen=True)
class Line:
    text: str
    box: Box
    height: float
    unmapped: int
    marks: tuple[str, ...] = ()  # text의 글자마다 글꼴 모양(fonts.font_style) + 위첨자 "^"·아래첨자 "_"
    size: float = 0.0  # 글자들의 가운데 글꼴 크기(pt). 모르면 0
    glyphs: int = 0  # 위치가 있는 글자 수
    math: int = 0  # 그 가운데 수식 글꼴 글자 수
    body: Box | None = None  # 첫 큰 글자(drop cap)를 뺀 상자. 문단 나누기가 쓴다. None이면 box
    core: tuple[float, float] | None = None  # 첫 큰 글자와 큰 기호(BIG_GLYPH)를 뺀 세로 범위(아래, 위). 줄 사이를 잰다. None이면 flow
    drop_cap: bool = False

    @property
    def flow(self) -> Box:
        return self.body or self.box


@dataclass(eq=False)  # 읽는 순서를 정할 때 같은 내용의 다른 문단과 섞이지 않게 객체로 구분한다
class _Block:
    lines: list[Line] = field(default_factory=list)

    @property
    def height(self) -> float:
        return statistics.median(line.height for line in self.lines)

    @property
    def box(self) -> Box:
        return _union(line.box for line in self.lines)


@dataclass(frozen=True)
class TextBlock:
    text: str
    regions: list[list[float]]  # 줄마다 정본 좌표 상자 [u0, v0, u1, v1] (IMPL §6.1)
    quality_flags: list[str]  # unmapped_chars, 본문이 아닌 문단 표시(block_kinds: in_figure·in_table·math·머리글·바닥글, 쪽 번역에서 뺀다)
    styles: list[list] = field(default_factory=list)  # 굵게·기울임·위아래첨자 구간 [시작, 끝, 모양("b"·"i"·"bi" + "^"·"_")] (text 안)
    font_size: float | None = None  # 가운데 글꼴 크기(pt)


@dataclass(frozen=True)
class PageText:
    blocks: list[TextBlock]
    text_status: str  # usable, partial, image_only, unknown
    flags: list[str]
    quality: dict  # chars, unmapped_chars, image_coverage


def layout_page(
    chars: list[Char],
    view_box: Box,
    image_coverage: float,
    text_rotation: int = 0,
    figures: list[tuple[float, float, float, float]] = (),
    rules: list[tuple[float, float, float, float]] = (),
) -> PageText:
    """한 쪽의 글자(pdfium 순서)를 문단으로 묶는다. text_rotation은 글줄 방향(반시계, 90의 배수)이다.
    figures는 그림 후보 상자, rules는 가로줄 상자(정본 좌표, reading.figures·tables.horizontal_rules)다. 그림 안 문단은 in_figure,
    표·의사코드 안 문단은 in_table, 따로 놓인 수식은 math로 표시한다."""
    framed = [Char(ch.text, _to_frame(ch.box, text_rotation) if ch.box else None, ch.unmapped, ch.style, ch.size, ch.math) for ch in chars]
    lines = build_lines(framed)
    blocks, two_columns = reading_order(build_blocks(lines), _to_frame(view_box, text_rotation))
    back = (360 - text_rotation) % 360
    text_blocks = []
    for block in blocks:
        text = block_text(block.lines)
        regions = [_normalize(_to_frame(line.box, back), view_box) for line in block.lines]
        flags = ["unmapped_chars"] if any(line.unmapped for line in block.lines) else []
        if _in_figure(regions, figures):
            flags.append(IN_FIGURE)
        glyphs = sum(line.glyphs for line in block.lines)
        if is_display_math(text, sum(line.math for line in block.lines) / glyphs if glyphs else 0.0):
            flags.append(MATH)
        sizes = [line.size for line in block.lines if line.size > 0]
        font_size = round(statistics.median(sizes), 2) if sizes else None
        text_blocks.append(TextBlock(text=text, regions=regions, quality_flags=flags, styles=block_styles(block.lines, text), font_size=font_size))
    for index in table_blocks([(block.regions, block.text) for block in text_blocks], rules):
        text_blocks[index].quality_flags.append(IN_TABLE)
    glyphs = sum(1 for ch in chars if ch.box is not None and ch.text.strip())
    unmapped = sum(1 for ch in chars if ch.box is not None and ch.unmapped)
    status, flags = classify_page(glyphs, unmapped, image_coverage)
    if two_columns:
        flags.append("two_columns")
    quality = {"chars": glyphs, "unmapped_chars": unmapped, "image_coverage": round(image_coverage, 4)}
    return PageText(blocks=text_blocks, text_status=status, flags=flags, quality=quality)


def build_lines(chars: list[Char]) -> list[Line]:
    lines: list[Line] = []
    current: list[Char] = []
    tallest: Box | None = None  # 줄에서 가장 큰 글자
    base_left: float | None = None  # 줄의 마지막 본 크기 글자(첨자 아님) 왼쪽 끝: 겹친 위·아래첨자는 여기까지 돌아갈 수 있다
    extent: Box | None = None  # 지금까지 줄에 든 글자들의 상자
    space = False
    for ch in chars:
        if ch.box is None or not ch.text.strip():
            space = space or bool(current)
            continue
        if current and not _same_line(tallest, current[-1].box, ch.box, base_left, extent, _smaller(ch, current, tallest)):
            lines.append(_line(current))
            current, tallest, base_left, extent, space = [], None, None, None, False
        if space and current:
            current.append(Char(" ", None))
        current.append(ch)
        if tallest is None or _height(ch.box) > _height(tallest):
            tallest = ch.box
        if not _smaller(ch, current, tallest):
            base_left = ch.box[0]
        extent = ch.box if extent is None else _union((extent, ch.box))
        space = False
    if current:
        lines.append(_line(current))
    return lines


def _same_line(
    tallest: Box, previous: Box, box: Box, base_left: float | None = None, extent: Box | None = None, small: bool = False
) -> bool:
    """같은 줄인지: 세로로 줄의 가장 큰 글자 범위 안이고, 가로로 앞 글자 바로 뒤(멀지 않게)다. 겹친 위·아래첨자(τ^na_p)는
    위첨자 끝에서 아래첨자로 왼쪽으로 돌아간다: 줄 높이만큼, 또는 앞 본 크기 글자(τ)까지는 돌아가도 같은 줄이다
    (2026-10-04: 위첨자 "na" 아래 p가 9.8pt 돌아가 줄 높이 9.4pt를 넘어 줄이 끊겼다).
    extent는 지금까지 줄에 든 글자들의 상자, small은 이 글자가 줄 본 크기보다 작은지(첨자 후보)다. 작은 글자는 줄에 든 글자와
    세로로 겹치면 같은 줄이다(분모의 아래첨자). 가로 거리는 줄 오른쪽 끝에서 잰다(넓은 위첨자 앞쪽 아래의 아래첨자 뒤 낱말)."""
    height = max(_height(tallest), _height(box))
    slack = LINE_BAND_SLACK * _height(tallest)
    center = (box[1] + box[3]) / 2
    tallest_center = (tallest[1] + tallest[3]) / 2
    vertical = tallest[1] - slack <= center <= tallest[3] + slack or box[1] <= tallest_center <= box[3]
    if not vertical and small and extent is not None:
        vertical = box[1] < extent[3] and extent[1] < box[3]
    back = previous[2] - SCRIPT_BACKSTEP * height <= box[0] or (base_left is not None and base_left <= box[0])
    right = max(previous[2], extent[2]) if extent is not None else previous[2]
    return vertical and back and box[0] <= right + LINE_SPLIT_GAP * height


def _smaller(ch: Char, line: list[Char], tallest: Box) -> bool:
    """줄에서 본 크기보다 작은 글자(첨자 후보)인지: 글꼴 크기를 알면 줄의 가장 큰 크기와, 모르면 가장 큰 글자 높이와 견준다."""
    sizes = [other.size for other in line if other.box is not None and other.size > MIN_FONT_SIZE]
    if ch.size > MIN_FONT_SIZE and sizes:
        return ch.size <= SCRIPT_SIZE * max(sizes)
    return _height(ch.box) <= SCRIPT_SIZE * _height(tallest)


def _scripts(glyphs: list[Char]) -> dict[int, str]:
    """줄 글자 가운데 위첨자 "^"·아래첨자 "_"(id(글자) → 표시). 줄 본 크기(글꼴 크기 가운데값, 모르면 높이)보다 작고, 본 글자들
    가운데보다 줄 높이의 SCRIPT_SHIFT배 넘게 위·아래인 글자다. 크기가 고른 줄(작은 대문자 등)은 표시하지 않는다."""
    sized = [ch.size for ch in glyphs if ch.size > MIN_FONT_SIZE]
    if sized:
        body = statistics.median(sized)
        small = [ch.size > MIN_FONT_SIZE and ch.size <= SCRIPT_SIZE * body for ch in glyphs]
    else:
        body_height = statistics.median(_height(ch.box) for ch in glyphs)
        small = [_height(ch.box) <= SCRIPT_SIZE * body_height for ch in glyphs]
    base = [ch for ch, is_small in zip(glyphs, small) if not is_small]
    if not base or len(base) == len(glyphs):
        return {}
    center = statistics.median((ch.box[1] + ch.box[3]) / 2 for ch in base)
    shift = SCRIPT_SHIFT * statistics.median(_height(ch.box) for ch in base)
    marks = {}
    for ch, is_small in zip(glyphs, small):
        offset = (ch.box[1] + ch.box[3]) / 2 - center
        if is_small and abs(offset) > shift:
            marks[id(ch)] = "^" if offset > 0 else "_"
    return marks


def _line(chars: list[Char]) -> Line:
    glyphs = [ch for ch in chars if ch.box is not None]
    rest = [ch for ch in glyphs[1:] if ch.text.strip()]
    rest_height = statistics.median(_height(ch.box) for ch in rest) if rest else 0.0
    # 큰 첫 글자는 영문자다(IEEE). 줄 첫머리의 큰 Σ·Π(그리스 문자)는 아니다
    drop_cap = glyphs[0].text.isascii() and glyphs[0].text.isalpha() and len(rest) >= 3 and _height(glyphs[0].box) >= DROP_CAP * rest_height
    if drop_cap and chars[1].box is None and rest[0].box[0] - glyphs[0].box[2] < DROP_CAP_JOIN * rest_height:
        chars = [chars[0], *chars[2:]]  # 큰 글자에 붙은 낱말의 나머지("T" + "he")에 pdfium이 넣은 공백
    text = "".join("-" if ch.text == LINE_END_HYPHEN else ch.text for ch in chars)
    scripts = _scripts(glyphs)
    pairs = [("-" if ch.text == LINE_END_HYPHEN else ch.text, ch.style + scripts.get(id(ch), "")) for ch in chars]
    marks = tuple(style for _, style in _collapse([(c, style) for text_, style in pairs for c in text_]))
    sizes = [ch.size for ch in glyphs if ch.size > MIN_FONT_SIZE]
    collapsed = " ".join(text.split())
    height = statistics.median(_height(ch.box) for ch in glyphs)
    body_glyphs = glyphs[1:] if drop_cap else glyphs
    core = [ch for ch in body_glyphs if _height(ch.box) <= BIG_GLYPH * height] or body_glyphs
    return Line(
        text=collapsed,
        box=_union(ch.box for ch in glyphs),
        height=height,
        unmapped=sum(ch.unmapped for ch in glyphs),
        marks=marks if len(marks) == len(collapsed) else ("",) * len(collapsed),
        size=statistics.median(sizes) if sizes else 0.0,
        glyphs=sum(1 for ch in glyphs if ch.text.strip()),
        math=sum(1 for ch in glyphs if ch.math and ch.text.strip()),
        body=_union(ch.box for ch in rest) if drop_cap else None,
        drop_cap=drop_cap,
        core=(min(ch.box[1] for ch in core), max(ch.box[3] for ch in core)),
    )


def _collapse(pairs: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """글자·모양 쌍에 " ".join(text.split())과 같은 공백 정리를 한다. 공백은 모양이 없다."""
    out: list[tuple[str, str]] = []
    space = False
    for char, style in pairs:
        if char.isspace():
            space = bool(out)
            continue
        if space:
            out.append((" ", ""))
            space = False
        out.append((char, style))
    return out


def block_styles(lines: list[Line], text: str) -> list[list]:
    """문단 글(block_text)의 굵게·기울임 구간 [시작, 끝, 모양]. 같은 모양 사이의 공백은 그 구간에 넣는다.
    block_text와 같은 규칙으로 이어 붙인 결과가 text와 다르면(정규화로 글자 수가 바뀜 등) 구간 없이 둔다."""
    pairs: list[tuple[str, str]] = []
    for line in lines:
        current = list(zip(line.text, line.marks or ("",) * len(line.text)))
        if not pairs:
            pairs = current
        elif pairs[-1][0] == SOFT_HYPHEN:
            pairs = pairs[:-1] + current
        elif pairs[-1][0] in HYPHENS and len(pairs) > 1 and pairs[-2][0].isalpha() and line.text[:1].islower():
            pairs = pairs[:-1] + current
        else:
            pairs += [(" ", "")] + current
    normalized = [(c, style) for char, style in pairs for c in unicodedata.normalize("NFKC", char) if unicodedata.category(c) != "Cc"]
    collapsed = _collapse(normalized)
    if "".join(c for c, _ in collapsed) != text:
        return []
    marks = [style for _, style in collapsed]
    for index, (char, style) in enumerate(collapsed):  # 같은 모양 낱말 사이의 공백
        if char == " " and 0 < index < len(marks) - 1 and marks[index - 1] and marks[index - 1] == marks[index + 1]:
            marks[index] = marks[index - 1]
    runs: list[list] = []
    for index, style in enumerate(marks):
        if not style:
            continue
        if runs and runs[-1][1] == index and runs[-1][2] == style:
            runs[-1][1] = index + 1
        else:
            runs.append([index, index + 1, style])
    return runs


def _in_figure(regions: list[list[float]], figures) -> bool:
    """문단 상자의 반 이상이 한 그림 후보 안에 있는지"""
    u0, v0 = min(region[0] for region in regions), min(region[1] for region in regions)
    u1, v1 = max(region[2] for region in regions), max(region[3] for region in regions)
    area = max(u1 - u0, 1e-9) * max(v1 - v0, 1e-9)
    for f0, g0, f1, g1 in figures:
        overlap = max(0.0, min(u1, f1) - max(u0, f0)) * max(0.0, min(v1, g1) - max(v0, g0))
        if overlap >= FIGURE_TEXT_SHARE * area:
            return True
    return False


def build_blocks(lines: list[Line]) -> list[_Block]:
    blocks: list[_Block] = []
    for line in lines:
        if blocks and _continues(blocks[-1], line):
            blocks[-1].lines.append(line)
        elif blocks and _starts_paragraph(blocks[-1], line):
            # 마지막 줄은 이 줄로 이어지는 문단의 들여 쓴 첫 줄이다(앞 줄들과 들여쓰기가 같아 함께 묶였다)
            blocks.append(_Block([blocks[-1].lines.pop(), line]))
        else:
            blocks.append(_Block([line]))
    return blocks


def _starts_paragraph(block: _Block, line: Line) -> bool:
    """블록의 마지막 줄이 이 줄(왼쪽 끝으로 나온 줄)로 이어지는 문단의 들여 쓴 첫 줄인지. 들여 쓴 짧은 문단들 뒤에 들여 쓴 첫 줄이
    오면 들여쓰기가 같아 앞 문단과 묶이고, 왼쪽 끝으로 나온 다음 줄만 따로 떨어졌다(2026-10-04 사용자 논문 16쪽 "By the above … /
    of IP(…) is also feasible …"). 마지막 줄이 블록의 가장 긴 줄만큼 끝까지 차야 한다(짧게 끝난 항목 줄 뒤는 새 문단이다).
    이 줄이 글머리표·번호로 시작하면 새 목록 항목이다(앞 항목의 끝까지 찬 둘째 줄을 떼어 가지 않는다, 2026-10-04 사용자 논문 CAAS)."""
    if len(block.lines) < 2 or LIST_MARKER.match(line.text):
        return False
    last, height = block.lines[-1], block.height
    if line.flow[0] > last.flow[0] - INDENT * height:
        return False  # 왼쪽으로 나오지 않았다
    if last.flow[2] < max(other.flow[2] for other in block.lines) - INDENT * height:
        return False  # 짧게 끝났다
    return _continues(_Block([last]), line)


def _continues(block: _Block, line: Line) -> bool:
    """줄 사이·들여쓰기는 첫 큰 글자(drop cap)를 뺀 상자로 잰다: 큰 글자는 둘째 줄까지 내려오고, 그 옆 줄들은 큰 글자만큼
    들어가 있다가 그 아래 줄부터 큰 글자 왼쪽 끝에서 시작한다. 줄 사이는 큰 기호(Σ·∫)도 뺀다: 다음 줄까지 내려온다(2026-10-04)."""
    previous = block.lines[-1].flow
    current = line.flow
    height = block.height
    if abs(line.height - height) > SIZE_CHANGE * height:
        return False
    below = block.lines[-1].core[0] if block.lines[-1].core else previous[1]
    above = line.core[1] if line.core else current[3]
    gap = below - above  # 앞 줄 아래와 이 줄 위 사이. 음수면 겹치거나 위로 올라갔다(새 단)
    if not -0.5 * height <= gap <= PARAGRAPH_GAP * height:
        return False
    if current[0] >= previous[2] or current[2] <= previous[0]:
        return False  # 가로로 겹치지 않는다
    shift = current[0] - previous[0]
    if len(block.lines) == 1:
        # 첫 줄을 들여 쓴 문단(다음 줄이 왼쪽으로 나옴)과 내어 쓴 항목(다음 줄이 들어감)은 이어진다.
        # 짧은 줄(제목) 다음에 들어간 줄은 새 문단이다.
        return not (shift > INDENT * height and previous[2] < current[2] - SHORT_LINE * height)
    first = block.lines[0]
    if first.drop_cap and abs(current[0] - first.box[0]) <= INDENT * height:
        return True  # 큰 글자 아래로 내려와 큰 글자 왼쪽 끝에서 시작하는 줄
    return abs(shift) <= INDENT * height  # 문단 안의 줄은 같은 곳에서 시작한다


def reading_order(blocks: list[_Block], view_box: Box) -> tuple[list[_Block], bool]:
    """(읽는 순서의 문단, 두 단 여부)"""
    middle = (view_box[0] + view_box[2]) / 2
    slack = COLUMN_SLACK * (view_box[2] - view_box[0])

    def side(block: _Block) -> str:
        left, _, right, _ = block.box
        return "left" if right <= middle + slack else "right" if left >= middle - slack else "full"

    def chars(selected: list[_Block]) -> int:
        return sum(len(line.text) for block in selected for line in block.lines)

    total = chars(blocks)
    lefts = [block for block in blocks if side(block) == "left"]
    rights = [block for block in blocks if side(block) == "right"]
    if total == 0 or chars(lefts) < COLUMN_SHARE * total or chars(rights) < COLUMN_SHARE * total:
        return blocks, False

    def top_down(selected: list[_Block]) -> list[_Block]:
        return sorted(selected, key=lambda block: -block.box[3])

    def center(block: _Block) -> float:
        return (block.box[1] + block.box[3]) / 2

    ordered: list[_Block] = []
    remaining = [block for block in blocks if side(block) != "full"]
    for full in [*top_down([block for block in blocks if side(block) == "full"]), None]:
        above = [block for block in remaining if full is None or center(block) > center(full)]
        ordered += top_down([block for block in above if side(block) == "left"])
        ordered += top_down([block for block in above if side(block) == "right"])
        remaining = [block for block in remaining if block not in above]
        if full is not None:
            ordered.append(full)
    return ordered, True


def block_text(lines: list[Line]) -> str:
    text = ""
    for line in lines:
        if not text:
            text = line.text
        elif text[-1] == SOFT_HYPHEN:
            text = text[:-1] + line.text
        elif text[-1] in HYPHENS and len(text) > 1 and text[-2].isalpha() and line.text[:1].islower():
            text = text[:-1] + line.text  # 줄 끝에서 나뉜 단어
        else:
            text += " " + line.text
    normalized = unicodedata.normalize("NFKC", text)
    return " ".join("".join(ch for ch in normalized if unicodedata.category(ch) != "Cc").split())


def classify_page(chars: int, unmapped: int, image_coverage: float) -> tuple[str, list[str]]:
    """(text_status, flags). chars는 공백이 아닌 글자 수, image_coverage는 이미지가 덮는 쪽 비율이다."""
    if chars < MIN_TEXT_CHARS:
        return ("image_only" if image_coverage >= IMAGE_ONLY else "unknown"), ["no_text"]
    if unmapped > UNMAPPED_SHARE * chars:
        return "partial", ["unmapped_chars"]
    if image_coverage >= MOSTLY_IMAGE and chars < MOSTLY_IMAGE_CHARS:
        return "partial", ["mostly_image"]
    return "usable", []


def document_status(pages: list[tuple[str, dict]]) -> tuple[str, str | None]:
    """쪽들의 (text_status, quality)로 문서 상태 (IMPL §5.2): INDEXED, PARTIAL, FAILED와 실패 이유.

    글자가 없는 빈 쪽(unknown, no_text)은 문서 상태를 낮추지 않는다. 추출에 실패한 쪽은 quality에 error가 있다.
    """
    errors = [quality["error"] for _, quality in pages if quality.get("error")]
    if not any(status in ("usable", "partial") for status, _ in pages):
        if errors and not any(status == "image_only" for status, _ in pages):
            return "FAILED", errors[0]
        return "FAILED", "NO_TEXT_LAYER"
    if errors or any(status in ("partial", "image_only") for status, _ in pages):
        return "PARTIAL", None
    return "INDEXED", None


def _to_frame(box: Box, rotation: int) -> Box:
    """글줄 방향이 rotation(반시계)인 좌표를 글줄이 오른쪽으로 가는 좌표로 돌린다. 되돌릴 때는 360 - rotation."""
    left, bottom, right, top = box
    if rotation == 90:  # (x, y) → (y, -x)
        return bottom, -right, top, -left
    if rotation == 180:  # (x, y) → (-x, -y)
        return -right, -top, -left, -bottom
    if rotation == 270:  # (x, y) → (-y, x)
        return -top, left, -bottom, right
    return box


def _normalize(box: Box, view_box: Box) -> list[float]:
    x0, y0, x1, y1 = view_box
    left, bottom, right, top = box
    values = ((left - x0) / (x1 - x0), (y1 - top) / (y1 - y0), (right - x0) / (x1 - x0), (y1 - bottom) / (y1 - y0))
    return [round(min(max(value, 0.0), 1.0), 6) for value in values]


def _union(boxes) -> Box:
    boxes = list(boxes)
    return min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes)


def _height(box: Box) -> float:
    return box[3] - box[1]
