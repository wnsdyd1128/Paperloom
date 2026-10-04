"""좌표 계약 fixture 생성기 (IMPL §6, PLAN A03). 표준 라이브러리만 쓴다.

geometry-matrix.pdf  : 알려진 PDF 좌표에 표식 문자열과 두 색 사각형을 둔 합성 5쪽 PDF
geometry-matrix.json : 쪽별 기대 view box·회전·UserUnit·표식의 정규화 좌표·사각형 영역

두 색 사각형은 영역 선택(W04a)의 기준이다. 왼쪽 절반은 빨강, 오른쪽 절반은 파랑이라 회전된 쪽에서
잘라 낸 이미지의 방향도 확인할 수 있다.

표식 좌표는 텍스트 기준선의 시작점(Td 위치)이다. 정규화는 IMPL §6.1 계약을 따른다.
실행: python tests/fixtures/pdf-layout/generate_geometry_matrix.py
"""

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
FONT_SIZE = 18
REGION = (300, 400, 120, 60)  # x, y, 폭, 높이 (PDF 사용자 공간). 모든 쪽의 view box 안이다.
REGION_COLORS = {"left": (0.85, 0.1, 0.1), "right": (0.1, 0.1, 0.85)}

# Helvetica AFM 글자 폭(1/1000 em). 표식 문자열의 기대 폭(advance width) 계산용.
HELVETICA_WIDTHS = {
    " ": 278, "A": 667, "B": 667, "C": 722, "D": 722, "E": 667, "F": 611, "G": 778, "H": 722, "I": 278,
    "J": 500, "K": 667, "L": 556, "M": 833, "N": 722, "O": 778, "P": 667, "Q": 778, "R": 722, "S": 667,
    "T": 611, "U": 722, "V": 667, "W": 944, "X": 667, "Y": 667, "Z": 611,
}

PAGES = [
    {"name": "plain", "media_box": [0, 0, 612, 792],
     "markers": [("GEOMETRY LINE ONE", 72, 700), ("GEOMETRY LINE TWO", 72, 676)]},
    {"name": "rotate-90", "media_box": [0, 0, 612, 792], "rotate": 90,
     "markers": [("ROTATED PAGE MARKER", 72, 700)]},
    {"name": "cropbox-offset", "media_box": [0, 0, 612, 792], "crop_box": [36, 72, 576, 756],
     "markers": [("CROPPED PAGE MARKER", 100, 600)]},
    {"name": "negative-origin-user-unit-2", "media_box": [-100, -50, 512, 742], "user_unit": 2,
     "markers": [("USER UNIT MARKER", 0, 600)]},
    # 쪽의 첫 텍스트가 글꼴 크기 0인 경우 (후처리 도구가 넣는 보이지 않는 공백; ACM 논문 1쪽에서 관찰).
    # pdfjs-dist 5.6–6.3은 이때 getTextContent가 예외를 내고 그 쪽의 텍스트를 모두 버린다.
    {"name": "zero-size-first-text", "media_box": [0, 0, 612, 792], "prefix": "BT /F1 0 Tf [( )] TJ ET\n",
     "markers": [("ZERO SIZE FIRST MARKER", 72, 700)]},
]


def view_box(page: dict) -> list[float]:
    media = page["media_box"]
    crop = page.get("crop_box", media)
    return [max(media[0], crop[0]), max(media[1], crop[1]), min(media[2], crop[2]), min(media[3], crop[3])]


def normalize(x: float, y: float, box: list[float]) -> list[float]:
    x0, y0, x1, y1 = box
    return [(x - x0) / (x1 - x0), (y1 - y) / (y1 - y0)]


def advance_width(text: str) -> float:
    """PDF 사용자 공간(pt)에서 문자열의 폭. 회전·확대와 무관한 기대값."""
    return round(sum(HELVETICA_WIDTHS[ch] for ch in text) * FONT_SIZE / 1000, 6)


def region_ops() -> str:
    x, y, w, h = REGION
    left, right = REGION_COLORS["left"], REGION_COLORS["right"]
    return (
        f"{left[0]} {left[1]} {left[2]} rg {x} {y} {w / 2} {h} re f\n"
        f"{right[0]} {right[1]} {right[2]} rg {x + w / 2} {y} {w / 2} {h} re f\n"
    )


def region(box: list[float]) -> dict:
    x, y, w, h = REGION
    u0, v0 = normalize(x, y + h, box)  # 왼쪽 위
    u1, v1 = normalize(x + w, y, box)  # 오른쪽 아래
    return {
        "pdf_rect": [x, y, w, h],
        "normalized": [u0, v0, u1, v1],
        "colors": {name: [round(c * 255) for c in rgb] for name, rgb in REGION_COLORS.items()},
    }


def build_pdf() -> bytes:
    objects: list[bytes] = []  # objects[i]는 객체 번호 i+1

    def add(body: bytes) -> int:
        objects.append(body)
        return len(objects)

    catalog = add(b"")  # 페이지 목록을 만든 뒤 채운다
    pages_obj = add(b"")
    font = add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    kids = []
    for page in PAGES:
        markers = "".join(f"BT /F1 {FONT_SIZE} Tf {x} {y} Td ({s}) Tj ET\n" for s, x, y in page["markers"])
        text = (page.get("prefix", "") + markers + region_ops()).encode()
        contents = add(b"<< /Length %d >>\nstream\n" % len(text) + text + b"endstream")
        entries = [f"/Type /Page /Parent {pages_obj} 0 R", f"/MediaBox {page['media_box']}".replace(",", "")]
        if "crop_box" in page:
            entries.append(f"/CropBox {page['crop_box']}".replace(",", ""))
        if "rotate" in page:
            entries.append(f"/Rotate {page['rotate']}")
        if "user_unit" in page:
            entries.append(f"/UserUnit {page['user_unit']}")
        entries.append(f"/Resources << /Font << /F1 {font} 0 R >> >> /Contents {contents} 0 R")
        kids.append(add(("<< " + " ".join(entries) + " >>").encode()))
    objects[pages_obj - 1] = f"<< /Type /Pages /Kids [{' '.join(f'{k} 0 R' for k in kids)}] /Count {len(kids)} >>".encode()
    info = add(b"<< /Title (Paperloom geometry matrix \\(synthetic\\)) >>")
    objects[catalog - 1] = f"<< /Type /Catalog /Pages {pages_obj} 0 R >>".encode()

    out = bytearray(b"%PDF-1.7\n")
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % number + body + b"\nendobj\n"
    xref_at = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    out += b"".join(b"%010d 00000 n \n" % offset for offset in offsets)
    out += b"trailer\n<< /Size %d /Root %d 0 R /Info %d 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (
        len(objects) + 1, catalog, info, xref_at)
    return bytes(out)


def expected() -> dict:
    pages = []
    for index, page in enumerate(PAGES):
        box = view_box(page)
        pages.append({
            "page_index": index,
            "name": page["name"],
            "view_box": box,
            "rotation": page.get("rotate", 0),
            "user_unit": page.get("user_unit", 1),
            "markers": [
                {"text": s, "pdf_point": [x, y], "normalized": normalize(x, y, box), "advance_width": advance_width(s)}
                for s, x, y in page["markers"]
            ],
            "region": region(box),
        })
    return {"schema_version": "geometry-fixture.v1", "title": "Paperloom geometry matrix (synthetic)",
            "font_size": FONT_SIZE, "pages": pages}


if __name__ == "__main__":
    (HERE / "geometry-matrix.pdf").write_bytes(build_pdf())
    (HERE / "geometry-matrix.json").write_text(json.dumps(expected(), indent=2) + "\n", encoding="utf-8")
    print("wrote geometry-matrix.pdf, geometry-matrix.json")
