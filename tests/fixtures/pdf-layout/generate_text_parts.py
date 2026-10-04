"""본문이 아닌 문단 fixture 생성기 (U7 쪽 번역, 2026-10-03 사용자 요청: 쪽 번역은 본문만 — 머리글·바닥글, 따로 놓인 수식,
표 안 글은 빼고 캡션은 번역). 표준 라이브러리만 쓴다.

text-parts.pdf : 세 쪽. 쪽마다 머리글(저널 이름 + 쪽 번호 "7:n")과 바닥글(저널·호·날짜)이 되풀이된다.
  1쪽: 본문 문단, 가운데 수식 "x = a + b"와 오른쪽 식 번호 "(1)", 본문 문단, 수식 글꼴(CMMI10)로만 쓴 번호 없는 수식
       "f g h k"(유니코드 수학 기호 없음), 본문 문단
  2쪽: 표 캡션 "Table 1. …", 가로줄 셋(위·머리 아래·아래) 사이의 표 칸, 본문 문단
  3쪽: IEEE 들어가기처럼 큰 첫 글자(28pt "T")로 시작하는 문단 하나(큰 글자 옆 두 줄, 그 아래 두 줄)

실행: python tests/fixtures/pdf-layout/generate_text_parts.py
"""

from pathlib import Path

HERE = Path(__file__).resolve().parent
JOURNAL = "Synthetic Parts Journal"
FOOTER = "Synthetic Parts Journal, Vol. 1, Article 7. Publication date: 2026."


def text(x: float, y: float, value: str, size: float = 10, font: str = "F1") -> str:
    escaped = value.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    return f"BT /{font} {size} Tf {x} {y} Td ({escaped}) Tj ET\n"


def paragraph(y: float, lines: list[str]) -> str:
    return paragraph_at(72, y, lines)


def paragraph_at(x: float, y: float, lines: list[str]) -> str:
    return "".join(text(x, y - index * 12, line) for index, line in enumerate(lines))


def rule(y: float) -> str:
    return f"0.8 w 72 {y} m 540 {y} l S\n"


def page(number: int, body: str) -> str:
    return text(72, 760, JOURNAL, 9) + text(500, 760, f"7:{number}", 9) + body + text(72, 40, FOOTER, 8)


PAGES = [
    page(
        1,
        paragraph(700, ["Body text before the equation explains the model. It has two", "sentences on two lines."])
        + text(270, 640, "x = a + b")
        + text(520, 640, "(1)")
        + paragraph(600, ["The equation above sums two terms. It is used below."])
        + text(280, 570, "f g h k", font="F2")
        + paragraph(540, ["The second equation has no number and only math letters."]),
    ),
    page(
        2,
        text(220, 720, "Table 1. Synthetic table of values.", 9)
        + rule(708)
        + text(90, 697, "Name", 9)
        + text(300, 697, "Value", 9)
        + rule(692)
        + text(90, 678, "alpha", 9)
        + text(300, 678, "1,200", 9)
        + text(90, 662, "beta", 9)
        + text(300, 662, "3,400", 9)
        + rule(650)
        + paragraph(620, ["The table lists two values. Both are synthetic."]),
    ),
    page(
        3,
        text(72, 688, "T", 28)
        + paragraph_at(90, 700, ["he last page starts with a drop cap like IEEE papers. The first", "two lines sit beside the large letter and the next lines"])
        + paragraph(676, ["run under it from the left edge of the column. It is one", "paragraph."]),
    ),
]


def build_pdf() -> bytes:
    count = len(PAGES)
    kids = " ".join(f"{5 + 2 * index} 0 R" for index in range(count))
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        f"<< /Type /Pages /Kids [{kids}] /Count {count} >>".encode(),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /CMMI10 /Encoding /WinAnsiEncoding >>",
    ]
    for index, content in enumerate(PAGES):
        stream = content.encode("latin-1")
        objects.append(f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 3 0 R /F2 4 0 R >> >> /Contents {6 + 2 * index} 0 R >>".encode())
        objects.append(b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"endstream")
    objects.append(b"<< /Title (Paperloom text fixture parts \\(synthetic\\)) >>")
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
    (HERE / "text-parts.pdf").write_bytes(build_pdf())


if __name__ == "__main__":
    main()
