"""3B2(Arbortext) 조판 PDF의 수식 글꼴 fixture 생성기 (2026-10-14 사용자 논문 IEEE TC). 표준 라이브러리만 쓴다.

3B2는 TeX 수식 글꼴을 AdvP+16진수 이름의 글꼴로 다시 인코딩했다. /Differences는 사용자 논문의 두 글꼴 그대로다: 코드 32 이상은
TeX 글꼴의 같은 자리 글자인데 이름은 그 자리의 ASCII 이름이고("two"가 ∈), 32보다 작은 코드는 /Cnn(nn이 TeX 자리), 기호
글꼴의 높은 코드에는 3B2가 더한 = [ ( ) +(onequarter·onehalf·eth·Thorn·thorn)가 있다. 글꼴은 넣지 않는다(pdfium은 이름으로
2·ð·¼ 등을 주고 /Cnn은 제어 문자로 준다 — 사용자 논문의 ToUnicode도 이름대로였다). 넣지 않은 글꼴의 빈칸(코드 32)은 글자 상자가
없을 때가 있어 기호 글꼴의 ←(코드 32)는 단위 시험이 본다. 제어 문자 하나뿐인 글 객체는 pdfium이 버리므로 제어 문자는 둘씩 쓴다.

text-3b2.pdf : 한 쪽, 글줄마다 문단 하나.
  - 기호 글꼴(ABCDEF+AdvP4C4E74, cmsy): 집합 hp(k)=lp(k)∪{t}, i≠k(빗금 6과 = ¼), 제어 문자 ∗ ≤ − ≥
  - 큰 기호 글꼴(ABCDEG+AdvP4C4E46, cmex): ⌊A/T⌋(코드 j·k, 사용자 논문 "⌊Ak/Tk⌋")와 늘이는 중괄호 조각(글자가 아니다)
  - cmmi처럼 /Cnn이 하나뿐인 AdvP 글꼴(ABCDEH+AdvP4C4E59): 모르는 글꼴이라 그대로 둔다(제어 문자는 바꾸지 못한 글자로 남는다)
  - 본문 글꼴(Helvetica)의 ð: 3B2 글꼴이 아니므로 그대로("Guðmundsson")

실행: python tests/fixtures/pdf-layout/generate_text_3b2.py
"""

from pathlib import Path

HERE = Path(__file__).resolve().parent


def line(y: float, *runs: tuple[str, bytes]) -> bytes:
    """한 글줄: 글꼴을 바꿔 가며 이어 쓴다(글자 사이가 벌어지지 않게 한 BT 안에서)."""
    shown = b"".join(b"/%s 10 Tf (%s) Tj " % (font.encode(), _escape(value)) for font, value in runs)
    return b"BT 72 %g Td %sET\n" % (y, shown)


def _escape(value: bytes) -> bytes:
    return b"".join(b"\\%03o" % byte if byte < 0x20 or byte > 0x7E or byte in b"()\\" else bytes([byte]) for byte in value)


CONTENT = (
    line(700, ("F1", b"Sets hp"), ("F2", b"\xf0"), ("F1", b"k"), ("F2", b"\xde\xbc"), ("F1", b"lp"), ("F2", b"\xf0"), ("F1", b"k"),
         ("F2", b"\xde[f"), ("F1", b"t"), ("F2", b"g"), ("F1", b" hold for all i"), ("F2", b"6\xbc"), ("F1", b"k."))
    + line(660, ("F1", b"The bound C"), ("F2", b"\x08\x04"), ("F1", b"D holds and x"), ("F2", b"\x05\x07"), ("F1", b"y as well."))
    + line(580, ("F1", b"The workload is W = "), ("F3", b"j"), ("F1", b"A/T"), ("F3", b"k"), ("F1", b" in this case"), ("F3", b"8:"), ("F1", b"."))
    + line(540, ("F1", b"An unknown font keeps its letters "), ("F4", b"a\x03d"), ("F1", b" as they are."))
    + line(500, ("F1", b"Written by Gu\xf0mundsson in Reykjavik."))
)

SYMBOL = (b"[1 /C15 3 /C2 /C20 /C0 /C138 /C21 /C3 32 /space 41 /parenright 48 /zero 50 /two 54 /six 56 /eight /nine 79 /O"
          b" 91 /bracketleft 94 /asciicircum 102 /f /g 106 /j 188 /onequarter /onehalf 222 /Thorn 240 /eth 254 /thorn]")
DELIMITER = (b"[2 /C22 /C23 /C16 /C17 /C8 /C9 /C26 /C24 /C25 32 /space /exclam 40 /parenleft 56 /eight 58 /colon 60 /less 62 /greater"
             b" 80 /P 88 /X 106 /j /k /l /m]")
ITALIC = b"[3 /C22 97 /a 100 /d]"


def font(base: bytes, differences: bytes) -> bytes:
    return b"<< /Type /Font /Subtype /Type1 /BaseFont /%s /Encoding << /Type /Encoding /Differences %s >> >>" % (base, differences)


def build_pdf() -> bytes:
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 5 0 R /F2 6 0 R /F3 7 0 R /F4 8 0 R >> >> /Contents 4 0 R >>",
        b"<< /Length %d >>\nstream\n" % len(CONTENT) + CONTENT + b"endstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
        font(b"ABCDEF+AdvP4C4E74", SYMBOL),
        font(b"ABCDEG+AdvP4C4E46", DELIMITER),
        font(b"ABCDEH+AdvP4C4E59", ITALIC),
        b"<< /Title (Paperloom text fixture 3B2 math fonts \\(synthetic\\)) >>",
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
    (HERE / "text-3b2.pdf").write_bytes(build_pdf())


if __name__ == "__main__":
    main()
