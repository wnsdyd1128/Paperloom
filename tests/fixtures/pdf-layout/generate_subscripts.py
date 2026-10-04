"""첨자·분수 추정 fixture 생성기 (IMPL §5.4, G2 R14). 표준 라이브러리만 쓴다.

subscripts.pdf  : 첨자·문장 속 분수가 섞인 줄과 그렇지 않은 줄을 둔 합성 1쪽 PDF
subscripts.json : 줄별 조각(본문·위첨자·아래첨자·분자·분모)과 기대하는 추정 표기(display_quote)

TeX처럼 첨자는 0.7배 크기의 별도 텍스트로 그린다. 위첨자는 기준선을 0.4 em 올리고 아래첨자는
0.25 em 내린다. 위·아래첨자가 겹치면(f_k^j) 같은 x에서 시작한다. 문장 속 분수는 분자를 0.4 em 올리고
분모를 0.45 em 내린 0.7배 크기 글자로 가운데 맞춰 그리고, 분수선을 긋고, 앞뒤에 간격을 둔다
(TeX의 관계 기호 간격 0.28 em, \\nulldelimiterspace 0.1 em). 분자·분모 속 첨자는 0.55배 크기다.
PDF에는 첨자·분수 구조가 없으므로 PDF.js는 이 조각들을 순서대로 이어 붙인다(원문 인용 quote).
추정 표기는 웹이 글자 크기와 위치로 만든다.
실행: python tests/fixtures/pdf-layout/generate_subscripts.py
"""

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
PAGE = [0, 0, 612, 792]
FONT_SIZE = 18
SCRIPT_SIZE = 12.6  # 0.7 em
SCRIPTSCRIPT_SIZE = 9.9  # 0.55 em
RISE = {"main": 0, "sup": 0.4 * FONT_SIZE, "sub": -0.25 * FONT_SIZE}
NUMERATOR_RISE = 0.4 * FONT_SIZE
DENOMINATOR_RISE = -0.45 * FONT_SIZE
NESTED_SUB_RISE = -0.1 * FONT_SIZE  # 분자·분모 속 아래첨자
AXIS = 0.25 * FONT_SIZE  # 분수선 높이

# Helvetica AFM 글자 폭(1/1000 em). 조각의 x 위치 계산용.
WIDTHS = {
    " ": 278, "+": 584, "=": 584, ",": 278, ".": 278, "2": 556,
    "c": 500, "d": 556, "e": 556, "f": 278, "i": 222, "j": 222, "k": 500, "m": 833, "r": 333, "t": 278,
    "x": 500, "y": 500,
    "C": 722, "E": 667, "H": 722, "I": 278, "N": 722, "O": 778, "P": 667, "R": 722, "S": 667, "T": 611, "U": 722,
}

# 조각: (텍스트, 역할). 역할 뒤 "@"는 앞 첨자와 같은 x에서, "+"는 바로 앞 조각 끝에서 시작한다.
# ("GAP", em)은 간격, ("FRAC", 분자 조각들, 분모 조각들)은 문장 속 분수다(조각 역할은 main 또는 sub).
LINES = [
    {"name": "stacked", "y": 700, "display_quote": "f^j_k = d^j_k + r_k",
     "segments": [("f", "main"), ("j", "sup"), ("k", "sub@"), (" = d", "main"), ("j", "sup"), ("k", "sub@"),
                  (" + r", "main"), ("k", "sub")]},
    {"name": "multi-letter", "y": 640, "display_quote": "x_{ij} + y^2",
     "segments": [("x", "main"), ("ij", "sub"), (" + y", "main"), ("2", "sup")]},
    {"name": "fraction", "y": 580, "display_quote": "U_i = \\frac{C_i}{T_i}.",
     "segments": [("U", "main"), ("i", "sub"), ("GAP", 0.28), ("=", "main"), ("GAP", 0.38),
                  ("FRAC", [("C", "main"), ("i", "sub")], [("T", "main"), ("i", "sub")]), ("GAP", 0.1), (".", "main")]},
    {"name": "split-subscript", "y": 520, "display_quote": "I^c_{i,k} term",
     "segments": [("I", "main"), ("c", "sup"), ("i", "sub@"), (",", "sub+"), ("k", "sub+"), (" term", "main")]},
    {"name": "plain", "y": 460, "display_quote": None, "segments": [("NO SCRIPTS HERE", "main")]},
]
X0 = 72


def width(text: str, size: float) -> float:
    return sum(WIDTHS[ch] for ch in text) * size / 1000


def part(text: str, role: str, x: float, y: float, size: float) -> dict:
    return {"text": text, "role": role, "x": round(x, 3), "y": round(y, 3), "size": size}


def layout_fraction_side(pieces: list, x: float, baseline: float, role: str) -> tuple[list[dict], float]:
    """분자 또는 분모: main은 0.7배, sub는 0.55배로 내려 바로 뒤에 붙인다. (조각들, 폭)"""
    out = []
    pen = x
    for text, kind in pieces:
        size = SCRIPT_SIZE if kind == "main" else SCRIPTSCRIPT_SIZE
        rise = 0 if kind == "main" else NESTED_SUB_RISE
        out.append(part(text, f"{role}-{kind}", pen, baseline + rise, size))
        pen += width(text, size)
    return out, pen - x


def layout(line: dict) -> tuple[list[dict], list[tuple[float, float, float]]]:
    """각 조각의 기준선 시작점과 크기, 분수선(x0, x1, y)."""
    out, rules = [], []
    pen = script_x = X0  # 다음 조각이 시작할 x, 마지막 첨자가 시작한 x
    previous_end = X0
    for segment in line["segments"]:
        if segment[0] == "GAP":
            pen += segment[1] * FONT_SIZE
            continue
        if segment[0] == "FRAC":
            numerator, width_n = layout_fraction_side(segment[1], 0, line["y"] + NUMERATOR_RISE, "numerator")
            denominator, width_d = layout_fraction_side(segment[2], 0, line["y"] + DENOMINATOR_RISE, "denominator")
            total = max(width_n, width_d)
            for pieces, side_width in ((numerator, width_n), (denominator, width_d)):
                shift = pen + (total - side_width) / 2  # 가운데 맞춤
                out.extend({**piece, "x": round(piece["x"] + shift, 3)} for piece in pieces)
            rules.append((round(pen, 3), round(pen + total, 3), line["y"] + AXIS))
            pen += total
            previous_end = pen
            continue
        text, role = segment
        kind = role.rstrip("@+")
        size = FONT_SIZE if kind == "main" else SCRIPT_SIZE
        start = script_x if role.endswith("@") else previous_end if role.endswith("+") else pen
        if not role.endswith("+"):
            script_x = start
        previous_end = start + width(text, size)
        pen = max(pen, previous_end)
        out.append(part(text, kind, start, line["y"] + RISE[kind], size))
    return out, rules


def build_pdf() -> bytes:
    ops = []
    for line in LINES:
        parts, rules = layout(line)
        for piece in parts:
            ops.append(f"BT /F1 {piece['size']} Tf {piece['x']} {piece['y']} Td ({piece['text']}) Tj ET\n")
        for x0, x1, y in rules:
            ops.append(f"0.72 w {x0} {y} m {x1} {y} l S\n")
    text = "".join(ops).encode()
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [4 0 R] /Count 1 >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        f"<< /Type /Page /Parent 2 0 R /MediaBox {PAGE} /Resources << /Font << /F1 3 0 R >> >> /Contents 5 0 R >>"
        .replace(",", "").encode(),
        b"<< /Length %d >>\nstream\n" % len(text) + text + b"endstream",
        b"<< /Title (Paperloom subscript fixture \\(synthetic\\)) >>",
    ]
    out = bytearray(b"%PDF-1.7\n")
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % number + body + b"\nendobj\n"
    xref_at = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    out += b"".join(b"%010d 00000 n \n" % offset for offset in offsets)
    out += b"trailer\n<< /Size %d /Root 1 0 R /Info 6 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objects) + 1, xref_at)
    return bytes(out)


def expected() -> dict:
    x0, y0, x1, y1 = PAGE
    lines = []
    for line in LINES:
        parts, _ = layout(line)
        lines.append({
            "name": line["name"],
            # 줄의 세로 범위(정규화 v): 위첨자·분자 윗변부터 아래첨자·분모 아랫변까지 넉넉히
            "v_range": [(y1 - (line["y"] + FONT_SIZE)) / (y1 - y0), (y1 - (line["y"] - 0.6 * FONT_SIZE)) / (y1 - y0)],
            "text": "".join(piece["text"] for piece in parts),
            "display_quote": line["display_quote"],
            "segments": parts,
        })
    return {
        "schema_version": "subscript-fixture.v1",
        "title": "Paperloom subscript fixture (synthetic)",
        "font_size": FONT_SIZE,
        "lines": lines,
    }


if __name__ == "__main__":
    (HERE / "subscripts.pdf").write_bytes(build_pdf())
    (HERE / "subscripts.json").write_text(json.dumps(expected(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print("wrote subscripts.pdf, subscripts.json")
