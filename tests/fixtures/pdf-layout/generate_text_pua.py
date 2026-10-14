"""사용자 영역(PUA) 글자 fixture 생성기 (2026-10-14 실제 논문 시험에서 찾음). 표준 라이브러리만 쓴다.

실제 논문 7편이 사용자 영역 글자를 그대로 저장했다: Windows 기호 글꼴(SymbolMT)은 Symbol 인코딩 코드를 U+F000 + 코드로 주고,
수식 글꼴(MTEX·txexs·Symbol)의 늘이는 괄호 조각은 Adobe 글리프 목록의 U+F8EB–F8FE다. 글꼴은 넣지 않고 ToUnicode로 그 코드를 준다.
기호 글꼴 이름은 MTSymbol(MathType)로 둔다: 넣지 않은 SymbolMT는 pdfium이 표준 Symbol 글꼴로 다루어 그 글자를 버린다.

text-pua.pdf : 한 쪽, 글줄마다 문단 하나.
  - 기호 글꼴(ABCDEF+MTSymbol): t·g → U+F074·F067 → τ·γ
  - 수식 글꼴(ABCDEG+MTEX): 큰 중괄호 조각 U+F8F1(윗조각)·F8F4·F8F3 → "{"와 빈칸
  - 기호 글꼴이 아닌 Wingdings(ABCDEH+Wingdings-Regular)의 U+F0E0: 모르는 글자라 문단 글에서 뺀다(바꾸지 못한 글자로 남는다)

실행: python tests/fixtures/pdf-layout/generate_text_pua.py
"""

from pathlib import Path

HERE = Path(__file__).resolve().parent


def line(y: float, *runs: tuple[str, bytes]) -> bytes:
    shown = b"".join(b"/%s 10 Tf (%s) Tj " % (font.encode(), _escape(value)) for font, value in runs)
    return b"BT 72 %g Td %sET\n" % (y, shown)


def _escape(value: bytes) -> bytes:
    return b"".join(b"\\%03o" % byte if byte < 0x20 or byte > 0x7E or byte in b"()\\" else bytes([byte]) for byte in value)


CONTENT = (
    line(700, ("F1", b"Tasks "), ("F2", b"t"), ("F1", b"1 and "), ("F2", b"g"), ("F1", b"a are released."))
    + line(660, ("F1", b"The value is "), ("F3", b"\x01\x02\x03"), ("F1", b"one case."))
    + line(620, ("F1", b"Then e "), ("F4", b"\xe0"), ("F1", b" L2 evicts a."))
)


def cmap(name: bytes, pairs: list[tuple[int, int]]) -> bytes:
    chars = b"".join(b"<%02X> <%04X>\n" % pair for pair in pairs)
    return (b"/CIDInit /ProcSet findresource begin 12 dict begin begincmap /CMapName /%s def\n1 begincodespacerange <00> <FF> endcodespacerange\n"
            b"%d beginbfchar\n%sendbfchar\nendcmap CMapName currentdict /CMap defineresource pop end end" % (name, len(pairs), chars))


CMAPS = [
    cmap(b"SynthSymbol", [(0x74, 0xF074), (0x67, 0xF067)]),
    cmap(b"SynthMtex", [(0x01, 0xF8F1), (0x02, 0xF8F4), (0x03, 0xF8F3)]),
    cmap(b"SynthWingdings", [(0xE0, 0xF0E0)]),
]


def build_pdf() -> bytes:
    font = b"<< /Type /Font /Subtype /Type1 /BaseFont /%s /ToUnicode %d 0 R >>"
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 5 0 R /F2 6 0 R /F3 7 0 R /F4 8 0 R >> >> /Contents 4 0 R >>",
        b"<< /Length %d >>\nstream\n" % len(CONTENT) + CONTENT + b"endstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
        font % (b"ABCDEF+MTSymbol", 9),
        font % (b"ABCDEG+MTEX", 10),
        font % (b"ABCDEH+Wingdings-Regular", 11),
        *(b"<< /Length %d >>\nstream\n" % len(body) + body + b"\nendstream" for body in CMAPS),
        b"<< /Title (Paperloom text fixture private use characters \\(synthetic\\)) >>",
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
    (HERE / "text-pua.pdf").write_bytes(build_pdf())


if __name__ == "__main__":
    main()
