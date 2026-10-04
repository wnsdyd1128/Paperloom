"""글자의 글꼴 모양 추정 (U7 쪽 번역: 레이아웃 유지 번역이 원문의 굵게·기울임을 따른다, 2026-10-03 사용자 요청).

PDF에는 "굵게" 표시가 없어 글꼴의 서술자 플래그(ForceBold·Italic), 굵기(FontWeight·StemV에서 pdfium이 계산),
글꼴 이름(…Bold, …TB, CMBX 등)으로 추정한다. 사용자 논문: LinLibertineTB(굵게, ForceBold·650),
LinLibertineTI(기울임, Italic 플래그), LinBiolinumB(굵게, 굵기 0이라 이름으로).
"""

import re

FLAG_ITALIC = 1 << 6  # PDF 32000 표 121: Italic
FLAG_FORCE_BOLD = 1 << 18  # ForceBold
BOLD_WEIGHT = 600

_BOLD_WORDS = re.compile(r"bold|black|heavy|semibold|demi|medi|-bd|cmbx|cmb\d|bx\d", re.IGNORECASE)
_ITALIC_WORDS = re.compile(r"italic|oblique|ital|cmti|cmmi|cmsl|cmbxti|-it$|boldit$", re.IGNORECASE)
# 이름 끝의 짧은 굵기·기울임 표시: LinLibertineTB, LinBiolinumB, LinLibertineTI, …TBI (소문자 뒤에 T?B?I?)
_SUFFIX = re.compile(r"[a-z]T?(B)?(I)?$")
# 수식 글꼴: Computer Modern 수식(CMMI·CMSY·CMEX·CMBSY·CMMIB), AMS(MSAM·MSBM), Euler(EUFM·EUSM·EURM·EUEX), newtx·txfonts·pxfonts
# 수식(txmi·rtxmi·txsy·txex·NewTXMI·pxmi), MathTime(MTMI·MTSY·MTEX·MTExtra), 이름에 Math가 든 것(Latin Modern·STIX·Cambria·XITS
# Math). CMR(본문 로만)·Symbol(본문 그리스 문자에도 쓴다)·newtxmath의 Libertine 글자(LinLibertineI)는 이름으로 가릴 수 없어 뺀다.
_MATH_FONT = re.compile(
    r"^(?:cm(?:mi|sy|ex|bsy|mib)\d|ms[ab]m|eu[fsre][mbx]|r?(?:n?tx|px|zx)(?:mi|sy|ex)|newtx(?:mi|sy|ex)|mt(?:mi|sy|ex))|math",
    re.IGNORECASE,
)


def is_math_font(name: str) -> bool:
    """글꼴 이름(부분 글꼴 접두 ABCDEF+ 포함 가능)이 수식 글꼴인지."""
    return bool(_MATH_FONT.search(name.split("+", 1)[-1]))


def font_style(name: str, flags: int, weight: int) -> str:
    """"" 보통, "b" 굵게, "i" 기울임, "bi" 둘 다. name은 글꼴 이름(부분 글꼴 접두 ABCDEF+ 포함 가능)."""
    base = name.split("+", 1)[-1]
    suffix = _SUFFIX.search(base)
    bold = bool(flags & FLAG_FORCE_BOLD) or weight >= BOLD_WEIGHT or bool(_BOLD_WORDS.search(base)) or bool(suffix and suffix.group(1))
    italic = bool(flags & FLAG_ITALIC) or bool(_ITALIC_WORDS.search(base)) or bool(suffix and suffix.group(2))
    return ("b" if bold else "") + ("i" if italic else "")
