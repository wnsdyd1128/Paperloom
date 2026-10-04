"""그림 후보 fixture 생성기 (그림 클릭 선택, IMPL §10.6). 표준 라이브러리만 쓴다.

figures.pdf  : 그림이 되어야 할 객체와 되면 안 되는 객체를 한 쪽에 모은 합성 PDF
figures.json : 기대하는 그림 후보 (PDF 사용자 공간 상자, 출처)

그림이 되어야 할 것: 이미지 XObject, Form XObject(안에 사각형과 글자), 막대·축으로 된 벡터 그림.
그림이 되면 안 되는 것: 쪽 전체를 덮는 흰 배경, 표의 가로줄 두 개, 대각선 하나, 쪽 밖으로 대부분 나간 선,
20 pt 아이콘 이미지, 본문 글자.
문맥의 캡션·영역 안 글자(IMPL §7.2)용으로 벡터 그림 안에 작은 글자 한 줄과, 그림 바로 아래에 9 pt 캡션을 둔다.
본문(12 pt)과 글자 크기가 달라 본문의 앞뒤 문단으로는 골라지지 않는다.
실행: python tests/fixtures/pdf-layout/generate_figures.py
"""

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
PAGE = [0, 0, 612, 792]
IMAGE_PIXELS = bytes([200, 40, 40] * 4 + [40, 40, 200] * 4)  # 4×2 RGB: 위 빨강, 아래 파랑

CONTENT = """1 1 1 rg 0 0 612 792 re f
q 120 0 0 60 72 600 cm /Im1 Do Q
q 1 0 0 1 300 590 cm /Fm1 Do Q
0 0 0 RG 1 w 72 300 m 72 420 l S 72 300 m 252 300 l S
0.3 0.4 0.8 rg 90 300 30 60 re f 140 300 30 90 re f 190 300 30 40 re f
0.5 w 72 250 m 540 250 l S 72 230 m 540 230 l S
1 w 400 120 m 520 200 l S
560 -100 m 700 100 l S
q 20 0 0 20 500 700 cm /Im1 Do Q
0 g BT /F1 12 Tf 72 180 Td (BODY TEXT THAT IS NOT A FIGURE) Tj ET
0 g BT /F1 9 Tf 150 400 Td (Synthetic values) Tj ET
0 g BT /F1 9 Tf 72 286 Td (Figure 1. Synthetic bar chart with three bars.) Tj ET
"""
FORM = "0 0 1 RG 2 w 5 5 90 70 re S BT /F1 10 Tf 40 35 Td (A) Tj ET\n"

# 그림 후보 (PDF 사용자 공간 left, bottom, right, top). 선 두께·Form 경계 계산 차이로 2 pt까지 허용한다.
EXPECTED = [
    {"name": "form", "source": "form", "pdf_box": [304, 594, 396, 666]},
    {"name": "image", "source": "image", "pdf_box": [72, 600, 192, 660]},
    {"name": "vector", "source": "vector", "pdf_box": [72, 300, 252, 420]},
]
TOLERANCE_PT = 2


def build_pdf() -> bytes:
    content = CONTENT.encode()
    form = FORM.encode()
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [4 0 R] /Count 1 >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        f"<< /Type /Page /Parent 2 0 R /MediaBox {PAGE} /Contents 5 0 R".replace(",", "").encode()
        + b" /Resources << /Font << /F1 3 0 R >> /XObject << /Im1 6 0 R /Fm1 7 0 R >> >> >>",
        b"<< /Length %d >>\nstream\n" % len(content) + content + b"endstream",
        b"<< /Type /XObject /Subtype /Image /Width 4 /Height 2 /ColorSpace /DeviceRGB /BitsPerComponent 8"
        b" /Length %d >>\nstream\n" % len(IMAGE_PIXELS) + IMAGE_PIXELS + b"\nendstream",
        b"<< /Type /XObject /Subtype /Form /BBox [0 0 100 80] /Resources << /Font << /F1 3 0 R >> >>"
        b" /Length %d >>\nstream\n" % len(form) + form + b"endstream",
        b"<< /Title (Paperloom figure fixture \\(synthetic\\)) >>",
    ]
    out = bytearray(b"%PDF-1.7\n")
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % number + body + b"\nendobj\n"
    xref_at = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    out += b"".join(b"%010d 00000 n \n" % offset for offset in offsets)
    out += b"trailer\n<< /Size %d /Root 1 0 R /Info 8 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objects) + 1, xref_at)
    return bytes(out)


def expected() -> dict:
    x0, y0, x1, y1 = PAGE
    return {
        "schema_version": "figure-fixture.v1",
        "page": PAGE,
        "tolerance_pt": TOLERANCE_PT,
        "figures": [
            {
                **figure,
                "normalized": [
                    (figure["pdf_box"][0] - x0) / (x1 - x0),
                    (y1 - figure["pdf_box"][3]) / (y1 - y0),
                    (figure["pdf_box"][2] - x0) / (x1 - x0),
                    (y1 - figure["pdf_box"][1]) / (y1 - y0),
                ],
            }
            for figure in EXPECTED
        ],
    }


if __name__ == "__main__":
    (HERE / "figures.pdf").write_bytes(build_pdf())
    (HERE / "figures.json").write_text(json.dumps(expected(), indent=2) + "\n", encoding="utf-8")
    print("wrote figures.pdf, figures.json")
