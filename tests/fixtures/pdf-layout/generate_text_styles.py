"""글꼴 모양 fixture 생성기 (U7 쪽 번역, 2026-10-03 사용자 요청: 레이아웃 유지 번역이 원문 굵게·기울임·글꼴 크기를 따른다).
표준 라이브러리만 쓴다.

text-styles.pdf : 한 쪽
  굵은 제목 한 줄(Helvetica-Bold 12pt). LaTeX PDF처럼 글꼴 크기 1을 글자 행렬로 12배 키운다
  본문 문단 네 줄(10pt, 줄 사이 12pt): 기울임 낱말(Helvetica-Oblique), 굵은 문장(Helvetica-Bold), 굵은 기울임 낱말
  (Helvetica-BoldOblique)이 보통 글(Helvetica) 사이에 섞인다. 마지막 줄은 짧다(번역이 조금 길어도 원문 크기로 들어간다).
  인라인 수식 문단 두 줄(2026-10-04): 첫 줄에 t 뒤 위첨자 "max"(7pt, 올림)와 그 아래로 돌아간 아래첨자 "p"(7pt, 내림 — 위첨자
  폭 13pt만큼 왼쪽으로, 줄 높이보다 멀리)와 C 뒤 아래첨자 "k". 줄이 끊기지 않고 위·아래첨자가 표시되는지 본다.

실행: python tests/fixtures/pdf-layout/generate_text_styles.py
"""

from pathlib import Path

HERE = Path(__file__).resolve().parent
FONTS = {"R": "Helvetica", "B": "Helvetica-Bold", "I": "Helvetica-Oblique", "BI": "Helvetica-BoldOblique"}
BODY = 10
LEADING = 12

HEADING = "3 Styled Section"
# 줄마다 (글꼴, 글) 조각
LINES = [
    [("R", "Styled fixture text keeps the "), ("I", "kappaword"), ("R", " term in italic and the rest of")],
    [("R", "this line plain for the reader. "), ("B", "Bold lead in."), ("R", " The last sentence")],
    [("R", "ends with the "), ("BI", "lambdaword"), ("R", " marker and a short tail of plain")],
    [("R", "words.")],
]


def escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def content() -> str:
    out = f"BT /B 1 Tf 12 0 0 12 72 720 Tm ({escape(HEADING)}) Tj ET\n"
    for index, line in enumerate(LINES):
        runs = " ".join(f"/{font} {BODY} Tf ({escape(text)}) Tj" for font, text in line)
        out += f"BT 72 {690 - index * LEADING} Td {runs} ET\n"
    # 인라인 수식: TJ의 수(1/1000 em)만큼 왼쪽으로 돌아가 위첨자 "max" 아래에 아래첨자 "p"를 둔다(Helvetica 7pt "max" 폭 1,889)
    out += (
        "BT /R 10 Tf 72 620 Td (The bound uses t) Tj /R 7 Tf 4 Ts (max) Tj -2.5 Ts [1889 (p)] TJ"
        " /R 10 Tf 0 Ts ( and C) Tj /R 7 Tf -2.5 Ts (k) Tj /R 10 Tf 0 Ts ( for every task in the set.) Tj ET\n"
        f"BT /R {BODY} Tf 72 {620 - LEADING} Td (The second line ends the paragraph.) Tj ET\n"
    )
    return out


def build_pdf() -> bytes:
    stream = content().encode("latin-1")
    fonts = list(FONTS.items())
    font_refs = " ".join(f"/{key} {5 + index} 0 R" for index, (key, _) in enumerate(fonts))
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << {font_refs} >> >> /Contents 4 0 R >>".encode(),
        b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"endstream",
        *(f"<< /Type /Font /Subtype /Type1 /BaseFont /{name} /Encoding /WinAnsiEncoding >>".encode() for _, name in fonts),
        b"<< /Title (Paperloom text fixture styles \\(synthetic\\)) >>",
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
    (HERE / "text-styles.pdf").write_bytes(build_pdf())


if __name__ == "__main__":
    main()
