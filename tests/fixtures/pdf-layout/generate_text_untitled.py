"""메타데이터 제목이 없는 논문 첫 쪽 fixture 생성기 (2026-10-05 사용자 요청: arXiv 논문이 파일 이름 1706.03762v7로 등록되었다).
표준 라이브러리만 쓴다.

text-untitled.pdf : 한 쪽, /Info에 /Title이 없다.
  - 맨 위 작은 줄(8pt) "Preprint. Under review."
  - 제목(18pt) 두 줄 "A Synthetic Study of Woven Paper Titles" / "for Readers Without Metadata"
  - 저자(11pt), "Abstract"(11pt), 본문(10pt) 여섯 줄
  - 왼쪽 여백에 90도 돌린 arXiv 도장(20pt, 제목보다 크다) "arXiv:2401.01234v2 [cs.DL] 5 Oct 2026"

실행: python tests/fixtures/pdf-layout/generate_text_untitled.py
"""

from pathlib import Path

HERE = Path(__file__).resolve().parent


def text(size: float, x: float, y: float, value: str) -> bytes:
    return b"BT /F1 %g Tf %g %g Td (%s) Tj ET\n" % (size, x, y, value.encode("latin-1"))


BODY = [
    "Readers often register papers whose files carry no title metadata at all.",
    "The library then shows the file name, such as an archive number, instead",
    "of the title printed on the first page. We show that the largest text in",
    "the upper half of that page is the title in the papers we examined, and",
    "that stamps in the margin are narrow enough to set aside. A short check",
    "against the body size keeps ordinary pages from producing false titles.",
]
CONTENT = b"".join([
    text(8, 72, 760, "Preprint. Under review."),
    text(18, 110, 700, "A Synthetic Study of Woven Paper Titles"),
    text(18, 160, 678, "for Readers Without Metadata"),
    text(11, 220, 640, "Ada Example and Ben Sample"),
    text(11, 72, 600, "Abstract"),
    *(text(10, 72, 582 - 13 * index, line) for index, line in enumerate(BODY)),
    b"BT /F1 20 Tf 0 1 -1 0 40 250 Tm (arXiv:2401.01234v2 [cs.DL] 5 Oct 2026) Tj ET\n",
])


def build_pdf() -> bytes:
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
        b"<< /Length %d >>\nstream\n" % len(CONTENT) + CONTENT + b"endstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
        b"<< /Producer (Paperloom synthetic fixture) >>",  # 제목이 없는 /Info
    ]
    info = 6
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


if __name__ == "__main__":
    (HERE / "text-untitled.pdf").write_bytes(build_pdf())
    print("wrote", HERE / "text-untitled.pdf")
