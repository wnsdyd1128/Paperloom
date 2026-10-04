"""유니코드를 주지 않는 수식 기호 fixture 생성기 (2026-10-04 사용자 요청: 빠지는 수식 기호). 표준 라이브러리만 쓴다.

사용자 논문의 newtx 수식 글꼴처럼 글꼴 사전의 /Encoding /Differences에만 글리프 이름이 있고 pdfium은 제어 문자를 준다.
(제어 문자 하나뿐인 글 객체는 pdfium이 버리므로 수식 기호 뒤에 빈칸을 둔다. 내장 글꼴인 실제 논문에서는 하나여도 나온다.)

text-glyphs.pdf : 한 쪽.
  - 본문 문단(Helvetica) 안의 프라임(수식 기호 글꼴 ABCDEF+txsy, 코드 12 /prime, ToUnicode에는 없음)과 합(수식 큰 기호 글꼴
    ABCDEG+txex, 코드 8 /summationtext, ToUnicode 없음)
  - 따로 놓인 수식: 큰 괄호(코드 2 /parenleftBigg — 되찾지 않으면 줄 끝 하이픈처럼 "-"가 되었다)와 큰 합(코드 4 /summationdisplay)
  - 본문 글꼴(ABCDEH+SynthSerif, 코드 2 /bullet)로 쓴 문단의 줄 끝 하이픈 "compo-"(pdfium이 0x02로 준다): 수식 글꼴이 아니므로
    되찾지 않고 "component"로 잇는다

실행: python tests/fixtures/pdf-layout/generate_text_glyphs.py
"""

from pathlib import Path

HERE = Path(__file__).resolve().parent


def text(x: float, y: float, value: bytes, size: float = 10, font: str = "F1") -> bytes:
    escaped = value.replace(b"\\", b"\\\\").replace(b"(", b"\\(").replace(b")", b"\\)")
    return b"BT /%s %g Tf %g %g Td (%s) Tj ET\n" % (font.encode(), size, x, y, escaped)


CONTENT = (
    text(72, 700, b"Recovered math symbols keep their meaning in a paragraph:")
    + text(72, 688, b"the bound C")
    + text(126.5, 692, b"\x0c ", 7, "F2")
    + text(134, 688, b"is small and the sum")
    + text(240, 688, b"\x08 ", 10, "F3")
    + text(250, 688, b"of all terms is finite.")
    + text(250, 640, b"x =")
    + text(270, 632, b"\x02 ", 10, "F3")
    + text(278, 632, b"\x04 ", 10, "F3")
    + text(296, 640, b"a")
    + text(72, 590, b"The analysis of every single compo-", font="F4")
    + text(72, 578, b"nent stays the same in this test.", font="F4")
)

# ToUnicode에 프라임(코드 12)이 없다: 사용자 논문의 txsy도 그랬다
CMAP = b"""/CIDInit /ProcSet findresource begin 12 dict begin begincmap /CMapName /SynthSy def
1 begincodespacerange <00> <FF> endcodespacerange
1 beginbfchar <03> <2208> endbfchar
endcmap CMapName currentdict /CMap defineresource pop end end"""


def build_pdf() -> bytes:
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 5 0 R /F2 6 0 R /F3 7 0 R /F4 8 0 R >> >> /Contents 4 0 R >>",
        b"<< /Length %d >>\nstream\n" % len(CONTENT) + CONTENT + b"endstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /ABCDEF+txsy /Encoding << /Type /Encoding /Differences [2 /arrowright /element 12 /prime] >> /ToUnicode 9 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /ABCDEG+txex"
        b" /Encoding << /Type /Encoding /Differences [2 /parenleftBigg /parenrightBigg /summationdisplay 8 /summationtext] >> >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /ABCDEH+SynthSerif /Encoding << /Type /Encoding /BaseEncoding /WinAnsiEncoding /Differences [2 /bullet] >> >>",
        b"<< /Length %d >>\nstream\n" % len(CMAP) + CMAP + b"\nendstream",
        b"<< /Title (Paperloom text fixture glyphs \\(synthetic\\)) >>",
    ]
    info = len(objects)
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
    (HERE / "text-glyphs.pdf").write_bytes(build_pdf())


if __name__ == "__main__":
    main()
