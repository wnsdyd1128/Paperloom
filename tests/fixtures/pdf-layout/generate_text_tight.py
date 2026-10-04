"""글꼴 정보(ascent·descent)가 망가진 글꼴 fixture 생성기 (2026-10-04 사용자 논문 CAAS: 문단이 줄마다 나뉘어 번역이 줄마다 따로
작게 그려졌다). 표준 라이브러리만 쓴다.

사용자 논문의 LinLibertineT는 ascent가 글꼴 크기의 0.45, descent가 0이라 pdfium의 loose box가 글자 모양 상자가 되었다(e는 짧고
d·p는 길다). 그래서 줄 높이(글자 높이 가운데값)가 x 높이쯤이 되고 보통의 줄 사이도 문단 사이로 보였다.

text-tight.pdf : 한 쪽. 같은 글꼴(SynthTight, FontDescriptor /Ascent 455 /Descent -2)로 쓴 두 문단(첫 줄 들여쓰기, 9pt, 줄 사이 11pt).
  아래로 내려가는 글자(p·g·y)가 없는 줄도 있다(그런 줄 아래 틈은 더 넓어 보인다).
  그 아래 따로 놓인 수식 한 줄(수식 글꼴 ABCDEF+rtxmi, /Ascent 0 /Descent -210: 사용자 논문의 rtxmi처럼 글꼴 정보가 남다르다).
  수식 글꼴은 넓히지 않는다(넓히면 사용자 논문의 따로 놓인 수식 줄이 달라졌다).

실행: python tests/fixtures/pdf-layout/generate_text_tight.py
"""

from pathlib import Path

HERE = Path(__file__).resolve().parent


def text(x: float, y: float, value: str) -> bytes:
    return b"BT /F1 9 Tf %g %g Td (%s) Tj ET\n" % (x, y, value.encode("latin-1"))


LINES = [
    (82, "Aerospace and satellite systems increasingly adopt multiprocessor"),
    (72, "architectures to support real time missions such as autonomous"),
    (72, "control. These modern schedulers manage the tasks at once"),
    (72, "within the same RTEMS kernel on the chosen hardware."),
    (82, "To address this gap we present a framework that characterizes"),
    (72, "workloads via reuse distance analysis and selects the most suitable"),
    (72, "scheduler for each mission in the end."),
]
CONTENT = b"".join(text(x, 700 - 11 * index, line) for index, (x, line) in enumerate(LINES)) + b"BT /F2 9 Tf 260 600 Td (x a e) Tj ET\n"
WIDTHS = b"/FirstChar 32 /LastChar 126 /Widths [" + b" ".join([b"480"] * 95) + b"]"


def build_pdf() -> bytes:
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 5 0 R /F2 8 0 R >> >> /Contents 4 0 R >>",
        b"<< /Length %d >>\nstream\n" % len(CONTENT) + CONTENT + b"endstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /SynthTight /Encoding /WinAnsiEncoding " + WIDTHS + b" /FontDescriptor 6 0 R >>",
        b"<< /Type /FontDescriptor /FontName /SynthTight /Flags 32 /FontBBox [-200 -250 1000 900] /ItalicAngle 0 /Ascent 455 /Descent -2"
        b" /CapHeight 650 /StemV 80 >>",
        b"<< /Title (Paperloom text fixture tight font metrics \\(synthetic\\)) >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /ABCDEF+rtxmi /Encoding /WinAnsiEncoding " + WIDTHS + b" /FontDescriptor 9 0 R >>",
        b"<< /Type /FontDescriptor /FontName /ABCDEF+rtxmi /Flags 32 /FontBBox [-200 -250 1000 900] /ItalicAngle 0 /Ascent 0 /Descent -210"
        b" /CapHeight 650 /StemV 80 >>",
    ]
    info = 7  # /Info는 일곱째 객체
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
    (HERE / "text-tight.pdf").write_bytes(build_pdf())


if __name__ == "__main__":
    main()
