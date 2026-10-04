"""본문 추출·검색 fixture 생성기 (W05, IMPL §5.2–5.3·§7.1, G3). 표준 라이브러리만 쓴다.

text-digital.pdf    : 정상 디지털 문서 → INDEXED
  0쪽 한 단: 제목, 소제목, 첫 줄을 들여 쓴 문단 둘(줄 끝 하이픈으로 나뉜 단어, 합자 ﬁ), 쪽 번호
  1쪽 두 단: 위 소제목, 왼쪽 단 문단 둘, 오른쪽 단 문단 둘, 아래 각주. 오른쪽 단을 먼저 그린다(읽는 순서 검사)
  2쪽 첨자: 아래·위첨자가 섞인 한 줄
  3쪽 /Rotate 90, CropBox가 MediaBox보다 작은 쪽의 한 줄 (정본 좌표 검사)
  4쪽 /Rotate 90 쪽에 90° 돌려 그린 두 줄 문단 (화면에서는 바로 선 가로 쪽. 표가 든 가로 쪽처럼)
  5쪽 빈 쪽 (문서 상태를 낮추지 않는다)
text-mixed.pdf      : 일부만 정상 → PARTIAL
  0쪽 정상 문단, 1쪽 쪽 전체 이미지뿐, 2쪽 쪽 전체 이미지 + 짧은 내려받기 문구, 3쪽 글자 일부가 사용자 영역(PUA)으로 매핑됨
text-image-only.pdf : 이미지뿐인 두 쪽 → FAILED (NO_TEXT_LAYER)
text-references.pdf : 참고문헌 쪽 찾기 (2026-10-02). 0쪽 본문(참고문헌 번호 [1]·[2]), 1쪽 본문 뒤 "References" 머리와
  항목, 2쪽 항목만, 3쪽 "A Appendix" 머리와 부록 → 참고문헌 쪽은 1·2쪽. PDF 목차가 없어 본문 제목으로 목차를 만든다(U4)
text-navigation.pdf : 탐색 (U4, 2026-10-02). PDF 목차(outline, 2단계), 0쪽 DOI 줄, 번호 제목 1·2·2.1·2.2와 References.
  outline의 "2.1 Experimental setup"은 본문 제목("2.1 Setup")과 일부러 다르다(화면이 outline을 쓰는지 본다)
text-extraction.json: 문서·쪽 상태, 문단 텍스트와 읽는 순서, 검색어 → 쪽

검색어는 서로 겹치지 않는 그리스 문자 이름(alphaword …)이다.
실행: python tests/fixtures/pdf-layout/generate_text_extraction.py
"""

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
PAGE = [0, 0, 612, 792]
ROTATED_CROP = [36, 36, 576, 756]
BODY = 10  # 본문 글꼴 크기
LEADING = 12

# 문단: (x, 첫 줄 들여쓰기, 줄들). 줄은 위에서 아래로 LEADING 간격.
INTRO_A = [
    "Paperloom keeps the source text of every page so that a later search",
    "finds the alphaword passage on the right page and the compo-",
    "sitional parts of the layout stay attached to their original",
    "coordinates on the page.",
]
INTRO_B = [
    "A second paragraph starts with an indented line and mentions the",
    "\001xture word with a ligature and the betaword marker so the",  # \001 = ﬁ (Differences)
    "search can find both of them.",
]
LEFT_C = [
    "The left column opens with the",
    "gammaword paragraph that runs over",
    "several short lines in a narrow",
    "column of text.",
]
LEFT_D = [
    "Another paragraph in the left",
    "column holds the deltaword term.",
]
RIGHT_E = [
    "The right column is drawn first in",
    "the content stream but it holds the",
    "epsilonword paragraph that a reader",
    "reaches after the left column.",
]
RIGHT_F = [
    "Its second paragraph holds the",
    "zetaword term near the bottom.",
]

DIGITAL_EXPECTED_BLOCKS = {
    0: [
        "Paperloom Extraction Sample",
        "1 Introduction",
        "Paperloom keeps the source text of every page so that a later search finds the alphaword passage on the "
        "right page and the compositional parts of the layout stay attached to their original coordinates on the page.",
        "A second paragraph starts with an indented line and mentions the fixture word with a ligature and the "
        "betaword marker so the search can find both of them.",
        "1",
    ],
    1: [
        "2 Two Column Section",
        " ".join(LEFT_C),
        " ".join(LEFT_D),
        " ".join(RIGHT_E),
        " ".join(RIGHT_F),
        "Footnote with the thetaword marker",
    ],
    4: ["Landscape text with the omicronword marker runs upward on the page."],
}


def text_op(font: str, size: float, x: float, y: float, text: str) -> str:
    escaped = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    return f"BT /{font} {size} Tf {x} {y} Td ({escaped}) Tj ET\n"


def paragraph(x: float, top: float, lines: list[str], indent: float = 12, font: str = "F1") -> str:
    return "".join(
        text_op(font, BODY, x + (indent if index == 0 else 0), top - index * LEADING, line) for index, line in enumerate(lines)
    )


FULL_IMAGE = "q 612 0 0 792 0 0 cm /Im1 Do Q\n"

DIGITAL_PAGES = [
    # 0쪽: 한 단
    text_op("F1", 18, 72, 720, "Paperloom Extraction Sample")
    + text_op("F1", 12, 72, 690, "1 Introduction")
    + paragraph(72, 666, INTRO_A)
    + paragraph(72, 666 - 4 * LEADING, INTRO_B, font="F2")
    + text_op("F1", BODY, 303, 40, "1"),
    # 1쪽: 두 단. 오른쪽 단을 먼저 그린다
    text_op("F1", 12, 72, 720, "2 Two Column Section")
    + paragraph(324, 690, RIGHT_E)
    + paragraph(324, 690 - 5 * LEADING, RIGHT_F)
    + paragraph(72, 690, LEFT_C)
    + paragraph(72, 690 - 5 * LEADING, LEFT_D)
    + text_op("F1", 8, 230, 60, "Footnote with the thetaword marker"),
    # 2쪽: 첨자 (아래첨자 7pt, 2pt 내림 / 위첨자 7pt, 4pt 올림)
    "BT /F1 10 Tf 72 700 Td (Each task t) Tj /F1 7 Tf -2 Ts (k) Tj /F1 10 Tf 0 Ts ( has period T) Tj"
    " /F1 7 Tf -2 Ts (k) Tj /F1 10 Tf 0 Ts ( and x) Tj /F1 7 Tf 4 Ts (2) Tj /F1 10 Tf 0 Ts ( term etaword) Tj ET\n",
    # 3쪽: 회전·CropBox
    text_op("F1", BODY, 100, 600, "Rotated page iotaword"),
    # 4쪽: 글줄이 위(+y)로 가도록 돌려 그린 두 줄. 다음 줄은 x가 커지는 쪽이다
    "BT /F1 10 Tf 0 1 -1 0 300 100 Tm (Landscape text with the omicronword marker runs) Tj ET\n"
    "BT /F1 10 Tf 0 1 -1 0 312 100 Tm (upward on the page.) Tj ET\n",
    # 5쪽: 빈 쪽
    "",
]

MIXED_PAGES = [
    paragraph(72, 700, ["A normal paragraph with the kappaword marker", "followed by a second ordinary line."]),
    FULL_IMAGE,
    FULL_IMAGE + text_op("F1", 8, 72, 20, "Downloaded copy lambdaword"),
    paragraph(72, 700, ["Readable text with the nuword marker comes first", "and the next line is also readable."])
    + text_op("F3", BODY, 72, 660, "This line maps to private use codes muword"),
]

IMAGE_ONLY_PAGES = [FULL_IMAGE, FULL_IMAGE]

REFERENCES_PAGES = [
    text_op("F1", 18, 72, 720, "Paperloom References Sample")
    + text_op("F1", 12, 72, 690, "1 Introduction")
    + paragraph(72, 666, ["Prior work [1] measured cache delays and [2] split", "the cache so that the rhoword term stays bounded."]),
    text_op("F1", 12, 72, 720, "2 Method")
    + paragraph(72, 696, ["The method page holds the sigmaword term and", "cites [3] once more."])
    + text_op("F1", 12, 72, 600, "References")
    + paragraph(72, 576, ["[1] A. Author. Cache delay analysis. 2020.", "[2] B. Author. Cache partitioning. 2021."], indent=0),
    paragraph(72, 700, ["[3] C. Author. Shared caches. 2022.", "[4] D. Author. Real-time scheduling. 2023."], indent=0),
    text_op("F1", 12, 72, 720, "A Appendix") + paragraph(72, 696, ["The appendix holds the tauword term."]),
]

NAVIGATION_PAGES = [
    text_op("F1", 18, 72, 720, "Paperloom Navigation Sample")
    + text_op("F1", BODY, 72, 700, "DOI: 10.5555/paperloom.2026.0001")
    + text_op("F1", 12, 72, 670, "1 Introduction")
    + paragraph(72, 646, ["Navigation fixture text for the outline and the", "find bar. Section one introduces the cache model."]),
    text_op("F1", 12, 72, 720, "2 Method")
    + paragraph(72, 696, ["The method section describes how the cache is", "split between the tasks of the system."])
    + text_op("F1", 12, 72, 400, "2.1 Setup")
    + paragraph(72, 376, ["The setup paragraph sits in the middle of the", "page so the outline target is not the page top."]),
    text_op("F1", 12, 72, 720, "2.2 Results") + paragraph(72, 696, ["The results show a smaller cache delay."]),
    text_op("F1", 12, 72, 720, "References") + paragraph(72, 696, ["[1] A. Author. Navigation study. 2024."], indent=0),
]
# PDF 목차: (제목, 쪽, 보기 위쪽 y, 아래 항목[, 배율]). 위쪽은 제목 기준선보다 글자 높이만큼 위다.
# "1 Introduction"은 배율 200%를 정한 목적지다(Reader는 목적지의 배율을 따르지 않는다).
NAVIGATION_OUTLINE = [
    ("1 Introduction", 0, 682, [], 2),
    ("2 Method", 1, 732, [("2.1 Experimental setup", 1, 412, []), ("2.2 Results", 2, 732, [])]),
    ("References", 3, 732, []),
]

TO_UNICODE = b"""/CIDInit /ProcSet findresource begin
12 dict begin
begincmap
/CIDSystemInfo << /Registry (Adobe) /Ordering (UCS) /Supplement 0 >> def
/CMapName /Paperloom-PUA def
/CMapType 2 def
1 begincodespacerange
<00> <FF>
endcodespacerange
1 beginbfrange
<21> <7E> <E021>
endbfrange
endcmap
CMapName currentdict /CMap defineresource pop
end
end
"""
IMAGE_PIXELS = bytes([90, 90, 90, 160, 160, 160, 160, 160, 160, 90, 90, 90])  # 2×2 회색


def outline_objects(items: list, root: int, page_object) -> list[bytes]:
    """PDF 목차 객체들(번호 root부터 이어서). items: (제목, 쪽, 위쪽 y, 아래 항목[, 배율]). 모두 펼친 상태다."""
    bodies: dict[int, str] = {}
    last = [root]

    def level(entries: list, parent: int) -> list[int]:
        numbers = []
        for _ in entries:
            last[0] += 1
            numbers.append(last[0])
        for index, (entry, number) in enumerate(zip(entries, numbers)):
            title, page, top, children, zoom = (*entry, "null")[:5]
            fields = [f"/Title ({title})", f"/Parent {parent} 0 R", f"/Dest [{page_object(page)} 0 R /XYZ 0 {top} {zoom}]"]
            if index > 0:
                fields.append(f"/Prev {numbers[index - 1]} 0 R")
            if index < len(entries) - 1:
                fields.append(f"/Next {numbers[index + 1]} 0 R")
            if children:
                kids = level(children, number)
                fields += [f"/First {kids[0]} 0 R", f"/Last {kids[-1]} 0 R", f"/Count {len(kids)}"]
            bodies[number] = "<< " + " ".join(fields) + " >>"
        return numbers

    top = level(items, root)
    bodies[root] = f"<< /Type /Outlines /First {top[0]} 0 R /Last {top[-1]} 0 R /Count {len(bodies)} >>"
    return [bodies[number].encode() for number in sorted(bodies)]


def build_pdf(pages: list[str], title: str, page_boxes: dict[int, str] | None = None, outline: list | None = None) -> bytes:
    """pages: 쪽마다 content stream. 글꼴 F1(Helvetica), F2(ﬁ 합자를 \\001에 둔 Helvetica), F3(PUA ToUnicode), 이미지 Im1.
    outline이 있으면 쪽 뒤에 PDF 목차 객체를 둔다."""
    page_count = len(pages)
    first_page = 9  # 1 catalog, 2 pages, 3–5 글꼴, 6 ToUnicode, 7 이미지, 8 info
    kids = " ".join(f"{first_page + 2 * index} 0 R" for index in range(page_count))
    outline_root = first_page + 2 * page_count
    catalog = f"<< /Type /Catalog /Pages 2 0 R /Outlines {outline_root} 0 R >>" if outline else "<< /Type /Catalog /Pages 2 0 R >>"
    objects = [
        catalog.encode(),
        f"<< /Type /Pages /Kids [{kids}] /Count {page_count} >>".encode(),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica"
        b" /Encoding << /Type /Encoding /BaseEncoding /WinAnsiEncoding /Differences [1 /fi] >> >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding /ToUnicode 6 0 R >>",
        b"<< /Length %d >>\nstream\n" % len(TO_UNICODE) + TO_UNICODE + b"endstream",
        b"<< /Type /XObject /Subtype /Image /Width 2 /Height 2 /ColorSpace /DeviceRGB /BitsPerComponent 8"
        b" /Length %d >>\nstream\n" % len(IMAGE_PIXELS) + IMAGE_PIXELS + b"\nendstream",
        f"<< /Title ({title}) >>".encode(),
    ]
    resources = "/Resources << /Font << /F1 3 0 R /F2 4 0 R /F3 5 0 R >> /XObject << /Im1 7 0 R >> >>"
    for index, content in enumerate(pages):
        extra = (page_boxes or {}).get(index, "")
        objects.append(
            f"<< /Type /Page /Parent 2 0 R /MediaBox {PAGE}{extra} {resources} /Contents {first_page + 2 * index + 1} 0 R >>".replace(
                ",", ""
            ).encode()
        )
        data = content.encode("latin-1")
        objects.append(b"<< /Length %d >>\nstream\n" % len(data) + data + b"endstream")
    if outline:
        objects += outline_objects(outline, outline_root, lambda page: first_page + 2 * page)
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


DOCUMENTS = {
    "text-digital.pdf": lambda: build_pdf(
        DIGITAL_PAGES,
        "Paperloom text fixture digital \\(synthetic\\)",
        {3: f" /CropBox {ROTATED_CROP} /Rotate 90".replace(",", ""), 4: " /Rotate 90"},
    ),
    "text-mixed.pdf": lambda: build_pdf(MIXED_PAGES, "Paperloom text fixture mixed \\(synthetic\\)"),
    "text-image-only.pdf": lambda: build_pdf(IMAGE_ONLY_PAGES, "Paperloom text fixture image only \\(synthetic\\)"),
    "text-references.pdf": lambda: build_pdf(REFERENCES_PAGES, "Paperloom text fixture references \\(synthetic\\)"),
    "text-navigation.pdf": lambda: build_pdf(
        NAVIGATION_PAGES, "Paperloom text fixture navigation \\(synthetic\\)", outline=NAVIGATION_OUTLINE
    ),
}


def _flatten_outline(items: list, depth: int = 1) -> list:
    return [
        entry
        for title, page, top, children, *_ in items
        for entry in [(depth, (title, page, top)), *_flatten_outline(children, depth + 1)]
    ]


def expected() -> dict:
    x0, y0, x1, y1 = ROTATED_CROP
    return {
        "schema_version": "text-extraction-fixture.v1",
        "documents": {
            "text-digital.pdf": {
                "status": "INDEXED",
                "status_reason": None,
                "pages": [
                    {"page_index": 0, "text_status": "usable", "flags": []},
                    {"page_index": 1, "text_status": "usable", "flags": ["two_columns"]},
                    {"page_index": 2, "text_status": "usable", "flags": []},
                    {"page_index": 3, "text_status": "usable", "flags": []},
                    {"page_index": 4, "text_status": "usable", "flags": []},
                    {"page_index": 5, "text_status": "unknown", "flags": ["no_text"]},
                ],
                # 쪽별 문단 텍스트(읽는 순서). 하이픈으로 나뉜 단어는 잇고, 합자는 풀어 쓴다. 4쪽은 돌려 그린 글줄.
                "blocks": {str(page): texts for page, texts in DIGITAL_EXPECTED_BLOCKS.items()},
                # 본문 제목: [제목, 쪽, 단계]. 쪽 번호 "1"은 제목이 아니다.
                "headings": [["1 Introduction", 0, 1], ["2 Two Column Section", 1, 1]],
                # 첨자 줄은 한 줄짜리 문단 하나다.
                "script_line": {"page_index": 2, "contains": ["Each task t", "etaword"], "regions": 1},
                # 회전·CropBox 쪽의 줄: 기준선 시작점 (100, 600)을 정본 좌표로 바꾼 값. 줄 상자가 이 점을 포함한다.
                "rotated_line": {
                    "page_index": 3,
                    "text": "Rotated page iotaword",
                    "baseline_start": [(100 - x0) / (x1 - x0), (y1 - 600) / (y1 - y0)],
                    "font_size_v": BODY / (y1 - y0),
                },
            },
            "text-mixed.pdf": {
                "status": "PARTIAL",
                "status_reason": None,
                "pages": [
                    {"page_index": 0, "text_status": "usable", "flags": []},
                    {"page_index": 1, "text_status": "image_only", "flags": ["no_text"]},
                    {"page_index": 2, "text_status": "partial", "flags": ["mostly_image"]},
                    {"page_index": 3, "text_status": "partial", "flags": ["unmapped_chars"]},
                ],
            },
            "text-image-only.pdf": {
                "status": "FAILED",
                "status_reason": "NO_TEXT_LAYER",
                "pages": [
                    {"page_index": 0, "text_status": "image_only", "flags": ["no_text"]},
                    {"page_index": 1, "text_status": "image_only", "flags": ["no_text"]},
                ],
            },
            "text-references.pdf": {
                "status": "INDEXED",
                "status_reason": None,
                "pages": [{"page_index": page, "text_status": "usable", "flags": []} for page in range(4)],
                # 문서 전체를 본 뒤 정하는 참고문헌 쪽 (documents.references). 본문 추출이 끝나면 그 쪽에 "references" 표시를 붙인다.
                "reference_pages": [1, 2],
                # 본문 제목 (documents.headings): [제목, 쪽, 단계]
                "headings": [["1 Introduction", 0, 1], ["2 Method", 1, 1], ["References", 1, 1], ["A Appendix", 3, 1]],
            },
            "text-navigation.pdf": {
                "status": "INDEXED",
                "status_reason": None,
                "pages": [{"page_index": page, "text_status": "usable", "flags": []} for page in range(4)],
                "reference_pages": [3],
                "headings": [
                    ["1 Introduction", 0, 1],
                    ["2 Method", 1, 1],
                    ["2.1 Setup", 1, 2],
                    ["2.2 Results", 2, 2],
                    ["References", 3, 1],
                ],
                # 0쪽 글에서 찾는 DOI (documents.metadata)
                "doi": "10.5555/paperloom.2026.0001",
                # PDF 목차: [제목, 쪽, 단계, 보기 위쪽 y(PDF 좌표)]
                "outline": [
                    [title, page, depth, top]
                    for depth, (title, page, top) in _flatten_outline(NAVIGATION_OUTLINE)
                ],
            },
        },
        # 검색어 → (문서, 쪽). 검색되지 않아야 하는 것은 null.
        "search": {
            "alphaword": ["text-digital.pdf", 0],
            "compositional": ["text-digital.pdf", 0],
            "fixture": ["text-digital.pdf", 0],
            "betaword": ["text-digital.pdf", 0],
            "gammaword": ["text-digital.pdf", 1],
            "deltaword": ["text-digital.pdf", 1],
            "epsilonword": ["text-digital.pdf", 1],
            "zetaword": ["text-digital.pdf", 1],
            "thetaword": ["text-digital.pdf", 1],
            "etaword": ["text-digital.pdf", 2],
            "iotaword": ["text-digital.pdf", 3],
            "omicronword": ["text-digital.pdf", 4],
            "kappaword": ["text-mixed.pdf", 0],
            "lambdaword": ["text-mixed.pdf", 2],
            "nuword": ["text-mixed.pdf", 3],
            "muword": None,
        },
    }


def main() -> None:
    for name, build in DOCUMENTS.items():
        (HERE / name).write_bytes(build())
    (HERE / "text-extraction.json").write_text(json.dumps(expected(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
