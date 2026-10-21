"""차트 Type3 글꼴과 TeX 큰 기호 글꼴 fixture 생성기 (2026-10-21 사용자 논문 Resource-Aware Task Scheduling). 표준 라이브러리만 쓴다.

사용자 논문은 "일부 기호를 읽지 못함"이었다. 두 가지 때문이다.
- 차트(그림마다 Form XObject)의 Type3 글꼴은 글자 코드가 보통 ASCII이고, /Differences 글리프 이름은 유니코드가 아니라 원래 글꼴의
  글리프 번호다(/uni00000024 = 글리프 36 = A, 매킨토시 표준 차례). ToUnicode가 없어 pdfium은 글자 코드를 그대로 주며 매핑 오류로
  표시했다(글은 맞다). 그림마다 같은 글꼴 이름의 다른 부분 글꼴이라 /Differences 전체는 서로 다르다.
- TeX 큰 기호 글꼴(CMEX10)은 /Encoding 없이 글꼴 안 인코딩을 쓰는데 ToUnicode가 늘이는 괄호 조각만 주어, ∑·큰 괄호가 글자 코드
  그대로(X·n·o) 매핑 오류로 나왔다. 여기서는 cmap 표가 없는 최소 TrueType(generate_text_glyph_ids.truetype)을 넣어 같은 매핑 오류를
  낸다(넣지 않은 Type1은 pdfium이 표준 인코딩으로 글자를 주어 매핑 오류가 나지 않는다).
Type3 글리프는 사각형 하나를 그린다(그리는 것이 없으면 글자 하나뿐인 글을 pdfium이 뺀다). 글자 코드는 ASCII만 쓴다(넣지 않은
글꼴의 높은 코드는 Linux pdfium이 뺀다, generate_text_pua.py).

text-chart-fonts.pdf : 두 쪽.
  1쪽: Helvetica 본문, 그림 두 개(같은 이름 BYJABP+TimesNewRomanPSMT의 부분 글꼴 둘: "Number of processors", "Schedulability (%)"),
       수식 줄 "I = ∑{} C"(CMEX10의 X·n·o).
  2쪽: Helvetica 본문과 글리프 이름이 글자와 맞지 않는 Type3 글꼴(/g36 꼴)의 "Response time" → 그대로 매핑 오류로 남는다.
  3쪽(2026-10-21 "Self-recovery 고도화"): matplotlib 차트처럼 표준 글리프 이름(/R /e /space /zero /period)을 쓰는 Type3 글꼴의
       "Reuse Distance 0.5"와, 넣지 않은 Symbol 글꼴(/Encoding 없음)의 =·−가 든 "x = y − z". 둘 다 pdfium이 매핑 오류로 준다.

실행: python tests/fixtures/pdf-layout/generate_text_chart_fonts.py
"""

from pathlib import Path

from generate_text_glyph_ids import truetype

HERE = Path(__file__).resolve().parent
GLYPH = 17  # 모든 Type3 글리프가 쓰는 그림(사각형) 객체 번호


def type3(base: str, text: str, name) -> bytes:
    """text의 글자를 ASCII 코드로 쓰고 name(글자)을 글리프 이름으로 둔 Type3 글꼴"""
    codes = sorted({ord(char) for char in text})
    differences = b" ".join(b"%d /%s" % (code, name(chr(code)).encode()) for code in codes)
    procs = b" ".join(b"/%s %d 0 R" % (name(chr(code)).encode(), GLYPH) for code in codes)
    widths = b" ".join(b"500" for _ in range(codes[0], codes[-1] + 1))
    return (b"<< /Type /Font /Subtype /Type3 /BaseFont /%s /FontBBox [0 0 500 700] /FontMatrix [0.001 0 0 0.001 0 0] "
            b"/CharProcs << %s >> /Encoding << /Type /Encoding /Differences [%s] >> /FirstChar %d /LastChar %d /Widths [%s] "
            b"/Resources << >> >>" % (base.encode(), procs, differences, codes[0], codes[-1], widths))


def glyph_id(char: str) -> str:
    return f"uni{ord(char) - 29:08x}"  # 매킨토시 표준 차례: 공백 3, A 36, a 68


def form(font: int, text: str) -> bytes:
    content = b"0.5 w 0 0 300 60 re S BT /T3 10 Tf 10 25 Td (%s) Tj ET\n" % text.encode().replace(b"(", b"\\(").replace(b")", b"\\)")
    return (b"<< /Type /XObject /Subtype /Form /BBox [0 0 300 60] /Resources << /Font << /T3 %d 0 R >> >> /Length %d >>\nstream\n"
            % (font, len(content)) + content + b"\nendstream")


def stream(data: bytes, extra: bytes = b"") -> bytes:
    return b"<< /Length %d%s >>\nstream\n" % (len(data), extra) + data + b"\nendstream"


AXIS, LABEL, OTHER = "Number of processors", "Schedulability (%)", "Response time"
PAGE_1 = (b"BT /F1 12 Tf 72 720 Td (Schedulability results are shown in the figures below.) Tj ET\n"
          b"q 1 0 0 1 72 600 cm /Fm1 Do Q\nq 1 0 0 1 72 500 cm /Fm2 Do Q\n"
          b"BT /F1 12 Tf 72 420 Td (I = ) Tj /F2 12 Tf (Xno) Tj /F1 12 Tf ( C) Tj ET\n")
PAGE_2 = b"BT /F1 12 Tf 72 720 Td (This page has a label in an unnamed font.) Tj ET\nBT /F3 12 Tf 72 690 Td (Response time) Tj ET\n"
NAMED = "Reuse Distance 0.5"
STANDARD = {" ": "space", ".": "period", "0": "zero", "5": "five"}  # 나머지는 글자 이름 그대로(/R /e …)
PAGE_3 = (b"BT /F5 12 Tf 72 720 Td (Reuse Distance 0.5) Tj ET\n"
          b"BT /F1 12 Tf 72 690 Td (x ) Tj /F4 12 Tf (=) Tj /F1 12 Tf ( y ) Tj /F4 12 Tf (-) Tj /F1 12 Tf ( z) Tj ET\n")
CMEX_TO_UNICODE = (b"/CIDInit /ProcSet findresource begin 12 dict begin begincmap /CMapName /SynthCmex def\n"
                   b"1 begincodespacerange <00> <FF> endcodespacerange\n1 beginbfchar\n<30> <F8EB>\nendbfchar\n"
                   b"endcmap CMapName currentdict /CMap defineresource pop end end")


def build_pdf() -> bytes:
    program = truetype()
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R 4 0 R 19 0 R] /Count 3 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 7 0 R /F2 8 0 R >> "
        b"/XObject << /Fm1 9 0 R /Fm2 10 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 7 0 R /F3 13 0 R >> >> /Contents 6 0 R >>",
        stream(PAGE_1),
        stream(PAGE_2),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
        b"<< /Type /Font /Subtype /TrueType /BaseFont /IJNTRM+CMEX10 /FirstChar 88 /LastChar 111 /Widths [%s] /FontDescriptor 15 0 R "
        b"/ToUnicode 14 0 R >>" % b" ".join(b"500" for _ in range(88, 112)),
        form(11, AXIS),
        form(12, LABEL),
        type3("BYJABP+TimesNewRomanPSMT", AXIS, glyph_id),
        type3("BYJABP+TimesNewRomanPSMT", LABEL, glyph_id),
        type3("CDEFGH+ArialMT", OTHER, lambda char: f"g{ord(char) - 29}"),
        stream(CMEX_TO_UNICODE),
        b"<< /Type /FontDescriptor /FontName /IJNTRM+CMEX10 /Flags 4 /FontBBox [0 -200 1000 800] /ItalicAngle 0 /Ascent 800 "
        b"/Descent -200 /CapHeight 700 /StemV 80 /FontFile2 16 0 R >>",
        stream(program, b" /Length1 %d" % len(program)),
        stream(b"500 0 0 0 450 650 d1 50 0 400 650 re f"),
        b"<< /Title (Paperloom text fixture chart Type3 and CMEX fonts \\(synthetic\\)) >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 7 0 R /F4 21 0 R /F5 23 0 R >> >> /Contents 20 0 R >>",
        stream(PAGE_3),
        b"<< /Type /Font /Subtype /TrueType /BaseFont /Symbol /FirstChar 32 /LastChar 126 /Widths [%s] /FontDescriptor 22 0 R >>"
        % b" ".join(b"500" for _ in range(32, 127)),
        b"<< /Type /FontDescriptor /FontName /Symbol /Flags 4 /FontBBox [0 -200 1000 800] /ItalicAngle 0 /Ascent 800 /Descent -200 "
        b"/CapHeight 700 /StemV 80 >>",
        type3("ABCDEF+DejaVuSans", NAMED, lambda char: STANDARD.get(char, char)),
    ]
    info = 18
    out = bytearray(b"%PDF-1.7\n")
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % number + body + b"\nendobj\n"
    xref_at = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    out += b"".join(b"%010d 00000 n \n" % offset for offset in offsets)
    out += b"trailer\n<< /Size %d /Root 1 0 R /Info %d 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objects) + 1, info, xref_at)
    return bytes(out)


def main() -> None:
    (HERE / "text-chart-fonts.pdf").write_bytes(build_pdf())


if __name__ == "__main__":
    main()
