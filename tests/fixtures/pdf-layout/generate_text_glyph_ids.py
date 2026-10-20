"""글리프 번호 글꼴 fixture 생성기 (2026-10-19 사용자 논문 SayCan의 그림). 표준 라이브러리만 쓴다.

사용자 논문 그림(Google 슬라이드에서 만든 듯)의 글꼴은 Type0 Identity-H에 ToUnicode가 비었고(codespace만), 내장 TrueType에 cmap·post
표가 없어 PDF 어디에도 글자가 없다. 글자 코드는 원래 글꼴의 글리프 번호이고 그 글꼴은 매킨토시 표준 글리프 차례를 따른다(글리프
36 = A, 3 = 공백). pdfium은 번호를 글자로 주어 "+XPDQ"(Human)가 되었다. 내장 글꼴은 글리프 모양이 모두 빈 최소 TrueType이다.

text-glyph-ids.pdf : 두 쪽.
  1쪽: Helvetica 본문 한 줄과 그림(Form XObject) 안의 글리프 번호 글꼴 대화 "Human: I spilled my coke, can you bring me a sponge?"
       → 매킨토시 차례로 읽는다.
  2쪽: Helvetica 본문 한 줄과 같은 꼴 글꼴의 글. 매킨토시 차례로 읽으면 자음뿐("Bcd fgh jklm npqr stvw xz")이라 차례가 다른
       글꼴로 보고 그대로 둔다(바꾸지 못한 글자로 남는다).

실행: python tests/fixtures/pdf-layout/generate_text_glyph_ids.py
"""

import struct
from pathlib import Path

HERE = Path(__file__).resolve().parent
GLYPHS = 100  # 내장 글꼴의 글리프 수(매킨토시 차례의 asciitilde 97까지 든다)


def glyph_ids(text: str) -> bytes:
    """매킨토시 표준 글리프 차례의 번호(공백 3 … ~ 97)를 2바이트 Identity-H 코드로"""
    return b"<" + b"".join(b"%04X" % (ord(char) - 29) for char in text) + b">"


def truetype() -> bytes:
    """글리프 모양이 모두 빈 최소 TrueType(glyf·head·hhea·hmtx·loca·maxp, cmap·post 없음)"""
    tables = {
        b"glyf": b"\0\0\0\0",
        b"head": struct.pack(">IIIIHHqqhhhhHHhhh", 0x10000, 0x10000, 0, 0x5F0F3CF5, 0, 1000, 0, 0, 0, -200, 1000, 800, 0, 8, 2, 0, 0),
        b"hhea": struct.pack(">IhhhHhhhhhhhhhhhH", 0x10000, 800, -200, 0, 500, 0, 0, 500, 1, 0, 0, 0, 0, 0, 0, 0, 1),
        b"hmtx": struct.pack(">Hh", 500, 0) + b"\0\0" * (GLYPHS - 1),
        b"loca": b"\0\0" * (GLYPHS + 1),
        b"maxp": struct.pack(">IHHHHHHHHHHHHHH", 0x10000, GLYPHS, 0, 0, 0, 0, 2, 0, 0, 0, 0, 0, 0, 0, 0),
    }
    count = len(tables)
    search = 2 ** (count.bit_length() - 1) * 16
    out = struct.pack(">IHHHH", 0x10000, count, search, search.bit_length() - 5, count * 16 - search)
    offset = 12 + 16 * count
    body = b""
    for tag, data in sorted(tables.items()):
        padded = data + b"\0" * (-len(data) % 4)
        checksum = sum(struct.unpack(f">{len(padded) // 4}I", padded)) & 0xFFFFFFFF
        out += tag + struct.pack(">III", checksum, offset + len(body), len(data))
        body += padded
    return out + body


EMPTY_CMAP = (b"/CIDInit /ProcSet findresource begin 12 dict begin begincmap /CIDSystemInfo << /Registry (Adobe) /Ordering (UCS) "
              b"/Supplement 0 >> def /CMapName /Adobe-Identity-UCS def /CMapType 2 def\n1 begincodespacerange <0000> <FFFF> "
              b"endcodespacerange\nendcmap CMapName currentdict /CMap defineresource pop end end")
FIGURE = b"0.5 w 0 0 450 120 re S BT /G1 12 Tf 10 60 Td " + glyph_ids("Human: I spilled my coke, can you bring me a sponge?") + b" Tj ET\n"
PAGE_1 = b"BT /F1 12 Tf 72 720 Td (Robots follow the plan in the figure below.) Tj ET\nq 1 0 0 1 72 560 cm /Fm1 Do Q\n"
PAGE_2 = (b"BT /F1 12 Tf 72 720 Td (This page has a label in another glyph order.) Tj ET\nBT /F2 12 Tf 72 690 Td "
          + glyph_ids("Bcd fgh jklm npqr stvw xz") + b" Tj ET\n")


def stream(data: bytes, extra: bytes = b"") -> bytes:
    return b"<< /Length %d%s >>\nstream\n" % (len(data), extra) + data + b"\nendstream"


def type0(name: bytes, descendant: int) -> bytes:
    return b"<< /Type /Font /Subtype /Type0 /BaseFont /%s /Encoding /Identity-H /DescendantFonts [%d 0 R] /ToUnicode 13 0 R >>" % (name, descendant)


def cid_font(name: bytes, descriptor: int) -> bytes:
    return (b"<< /Type /Font /Subtype /CIDFontType2 /BaseFont /%s /CIDSystemInfo << /Registry (Adobe) /Ordering (Identity) /Supplement 0 >> "
            b"/FontDescriptor %d 0 R /DW 500 /CIDToGIDMap /Identity >>" % (name, descriptor))


def descriptor(name: bytes) -> bytes:
    return (b"<< /Type /FontDescriptor /FontName /%s /Flags 32 /FontBBox [0 -200 1000 800] /ItalicAngle 0 /Ascent 800 /Descent -200 "
            b"/CapHeight 700 /StemV 80 /FontFile2 8 0 R >>" % name)


def build_pdf() -> bytes:
    figure_font, other_font = b"AAAAAB+font0000000000000001", b"AAAAAC+font0000000000000002"
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R 4 0 R] /Count 2 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 7 0 R >> /XObject << /Fm1 9 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 7 0 R /F2 12 0 R >> >> /Contents 6 0 R >>",
        stream(PAGE_1),
        stream(PAGE_2),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
        stream(truetype(), b" /Length1 %d" % len(truetype())),
        stream(FIGURE, b" /Type /XObject /Subtype /Form /BBox [0 0 450 120] /Resources << /Font << /G1 10 0 R >> >>"),
        type0(figure_font, 11),
        cid_font(figure_font, 14),
        type0(other_font, 15),
        stream(EMPTY_CMAP),
        descriptor(figure_font),
        cid_font(other_font, 16),
        descriptor(other_font),
        b"<< /Title (Paperloom text fixture glyph id fonts \\(synthetic\\)) >>",
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
    (HERE / "text-glyph-ids.pdf").write_bytes(build_pdf())


if __name__ == "__main__":
    main()
