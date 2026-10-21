"""흰 배경이 든 Form XObject fixture 생성기 (2026-10-21 사용자 논문 Resource-Aware Task Scheduling 5쪽). 표준 라이브러리만 쓴다.

white-background-forms.pdf : 두 단 한 쪽. 왼쪽 위 그림은 PowerPoint 슬라이드(960×540)째, 오른쪽 위 그림은 A4 쪽(595×842)째로
  넣은 Form이다. 두 Form 모두 첫 객체가 Form 전체를 덮는 흰 채움 사각형이라 pdfium의 객체 상자가 보이는 그림보다 훨씬 크다:
  A4 Form은 오른쪽 단 본문 아래까지 내려가고 왼쪽 Form과 닿아, 두 상자를 합치면 쪽의 79%다(배경 문턱 80% 아래).
  보이는 그림은 슬라이드·쪽 안의 작은 그림(SLIDE_DRAWING·PAGE_DRAWING, 쪽 좌표)뿐이고 그 안에 글자 하나씩 있다. 그림 아래 캡션과
  두 단 본문이 있다.
실행: python tests/fixtures/pdf-layout/generate_white_background_forms.py
"""

from pathlib import Path

HERE = Path(__file__).resolve().parent
PAGE = [0, 0, 612, 792]
SLIDE = (0.414, 10.4, 563.8)  # Form 행렬: 배율, 쪽 x, 쪽 y (실제 논문과 같다)
A4 = (0.76, 167.8, 156.5)
# 쪽 좌표 left, bottom, right, top. 슬라이드 Form 좌표 100..500 × 100..400, A4 Form 좌표 200..500 × 500..800
SLIDE_DRAWING = [10.4 + 0.414 * 100, 563.8 + 0.414 * 100, 10.4 + 0.414 * 500, 563.8 + 0.414 * 400]
PAGE_DRAWING = [167.8 + 0.76 * 200, 156.5 + 0.76 * 500, 167.8 + 0.76 * 500, 156.5 + 0.76 * 800]
LEFT_BODY = [
    "an alternative approach is to reallocate the task to a suitable",
    "core, thereby reducing the impact of parallel resource contention.",
    "Under this new allocation, the local and remote blocking of the",
    "task would differ entirely from the original allocation.",
]
RIGHT_BODY = [
    "If the task still remains unschedulable after reallocation, the",
    "system is deemed unschedulable, leading to the termination of",
    "the algorithm without a feasible scheduling solution being found.",
    "When multiple tasks miss their deadline, our framework sorts them",
    "by priority and optimizes the highest-priority task in each step.",
]


def text(x: float, y: float, value: str, size: float = 9) -> str:
    return f"BT /F1 {size} Tf {x} {y} Td ({value}) Tj ET\n"


CONTENT = (
    f"q {SLIDE[0]} 0 0 {SLIDE[0]} {SLIDE[1]} {SLIDE[2]} cm /Fm1 Do Q\n"
    f"q {A4[0]} 0 0 {A4[0]} {A4[1]} {A4[2]} cm /Fm2 Do Q\n"
    + text(80, 590, "Fig. 2: the overall mechanism.")
    + text(360, 520, "Fig. 3: two priority elevation implementations.")
    + "".join(text(50, 560 - 11 * index, line) for index, line in enumerate(LEFT_BODY))
    + "".join(text(320, 480 - 11 * index, line) for index, line in enumerate(RIGHT_BODY))
)
# 흰 배경 다음에 획 사각형·채운 도형·글자
SLIDE_FORM = (
    "1 g 0 0 960 540 re f\n"
    "0 0 1 RG 4 w 100 100 400 300 re S 0.9 0.8 0.5 rg 150 150 120 80 re f\n"
    "0 g BT /F1 30 Tf 160 300 Td (Initial Setup) Tj ET\n"
)
PAGE_FORM = (
    "1 g 0 0 595 842 re f\n"
    "0.8 0.2 0.2 RG 3 w 200 500 300 300 re S 0.6 0.6 0.9 rg 250 550 100 100 re f\n"
    "0 g BT /F1 14 Tf 250 700 Td (1st adjust) Tj ET\n"
)


def build_pdf() -> bytes:
    content, slide, page = CONTENT.encode(), SLIDE_FORM.encode(), PAGE_FORM.encode()
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [4 0 R] /Count 1 >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        f"<< /Type /Page /Parent 2 0 R /MediaBox {PAGE} /Contents 5 0 R".replace(",", "").encode()
        + b" /Resources << /Font << /F1 3 0 R >> /XObject << /Fm1 6 0 R /Fm2 8 0 R >> >> >>",
        b"<< /Length %d >>\nstream\n" % len(content) + content + b"endstream",
        b"<< /Type /XObject /Subtype /Form /BBox [0 0 960 540] /Resources << /Font << /F1 3 0 R >> >>"
        b" /Length %d >>\nstream\n" % len(slide) + slide + b"endstream",
        b"<< /Title (Paperloom white background form fixture \\(synthetic\\)) >>",
        b"<< /Type /XObject /Subtype /Form /BBox [0 0 595 842] /Resources << /Font << /F1 3 0 R >> >>"
        b" /Length %d >>\nstream\n" % len(page) + page + b"endstream",
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
    (HERE / "white-background-forms.pdf").write_bytes(build_pdf())
    print("wrote white-background-forms.pdf")
