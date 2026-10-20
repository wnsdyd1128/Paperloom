"""잘라내기(clip)가 든 Form XObject fixture 생성기 (2026-10-17 실제 논문 LLVM Static Analysis 4쪽). 표준 라이브러리만 쓴다.

clipped-form.pdf : 한 쪽. 0.5배로 줄여 놓은 Form이 안에서 `re W n`으로 잘린다. Form 안 그림은 잘라내기 상자보다 훨씬
  위아래로 나가 있어(pdfium의 객체 상자는 잘라내기를 무시하고 이 부분까지 덮는다) 보이는 부분은 쪽 (100, 500)–(300, 650)뿐이다.
  보이는 그림 바로 아래 캡션, 그 아래 Form이 잘려 보이지 않는 자리에 본문 문단(여러 줄)이 있다. Form 안에는 잘라내기 밖에
  놓여 보이지 않는 글자 "HIDDEN"도 있다(pdfium은 이 글자도 글자 목록에 준다).
  오른쪽 Form 하나 더(그래프 모양): 축·축 글자는 잘라내기 없이 그리고 안쪽 채움만 작게 잘린다. 그림은 축 글자까지다.
실행: python tests/fixtures/pdf-layout/generate_clipped_form.py
"""

from pathlib import Path

HERE = Path(__file__).resolve().parent
PAGE = [0, 0, 612, 792]
VISIBLE = [100, 500, 300, 650]  # 쪽 좌표 left, bottom, right, top: Form 행렬 0.5배 + (100, 500), 잘라내기 0 0 400 300
BODY = [
    "Once we have the graph with block execution counts and branch",
    "probabilities, we make a virtual trace of the memory accesses from",
    "it. We use a Python library to read the graph, stored in the dot",
    "format. Each node represents a basic block of the target function,",
    "and the edges represent the direction from one node to another.",
]


def text(x: float, y: float, value: str, size: float = 10) -> str:
    return f"BT /F1 {size} Tf {x} {y} Td ({value}) Tj ET\n"


CONTENT = (
    "q 0.5 0 0 0.5 100 500 cm /Fm1 Do Q\n"
    "q 1 0 0 1 350 500 cm /Fm2 Do Q\n"
    + text(100, 488, "Figure 1. A clipped drawing of a graph.", 9)
    + "".join(text(100, 450 - 12 * index, line) for index, line in enumerate(BODY))
)
# Form 좌표: 잘라내기 0..400 × 0..300. 세로로 긴 그림(−500..500)과 보이는 자리의 채운 마디 둘, 글자 하나
FORM = (
    "0 0 400 300 re W n\n"
    "0 0 1 RG 2 w 10 -500 380 1000 re S 200 -500 m 200 500 l S\n"
    "0.9 0.8 0.5 rg 60 160 120 80 re f 220 40 120 80 re f\n"
    "0 g BT /F1 20 Tf 90 190 Td (BB3) Tj ET\n"
    "BT /F1 20 Tf 90 420 Td (HIDDEN) Tj ET\n"
)
# 그래프 모양 Form(쪽 (350, 500)에 1배): 잘라내기 없는 축과 축 아래 글자, 작게(30×30) 잘린 채움
CHART = (
    "0 0 0 RG 1 w 0 0 m 200 0 l S 0 0 m 0 100 l S\n"
    "0 g BT /F1 10 Tf 80 -15 Td (axis label) Tj ET\n"
    "q 10 10 30 30 re W n 0.2 0.6 0.2 rg 0 0 200 100 re f Q\n"
)


def build_pdf() -> bytes:
    content, form, chart = CONTENT.encode(), FORM.encode(), CHART.encode()
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [4 0 R] /Count 1 >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        f"<< /Type /Page /Parent 2 0 R /MediaBox {PAGE} /Contents 5 0 R".replace(",", "").encode()
        + b" /Resources << /Font << /F1 3 0 R >> /XObject << /Fm1 6 0 R /Fm2 8 0 R >> >> >>",
        b"<< /Length %d >>\nstream\n" % len(content) + content + b"endstream",
        b"<< /Type /XObject /Subtype /Form /BBox [-100 -600 500 600] /Resources << /Font << /F1 3 0 R >> >>"
        b" /Length %d >>\nstream\n" % len(form) + form + b"endstream",
        b"<< /Title (Paperloom clipped form fixture \\(synthetic\\)) >>",
        b"<< /Type /XObject /Subtype /Form /BBox [-50 -50 250 150] /Resources << /Font << /F1 3 0 R >> >>"
        b" /Length %d >>\nstream\n" % len(chart) + chart + b"endstream",
    ]
    out = bytearray(b"%PDF-1.7\n")
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % number + body + b"\nendobj\n"
    xref_at = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    out += b"".join(b"%010d 00000 n \n" % offset for offset in offsets)
    out += b"trailer\n<< /Size %d /Root 1 0 R /Info 7 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objects) + 1, xref_at)
    return bytes(out)


if __name__ == "__main__":
    (HERE / "clipped-form.pdf").write_bytes(build_pdf())
    print("wrote clipped-form.pdf")
