"""공용 fixture. 테스트 PDF는 저작권 문제가 없도록 실행 중에 합성한다 (IMPL §14.1)."""

import io
import struct
import zlib

import pypdf
import pytest


def build_pdf(pages: int = 1, title: str | None = None, user_password: str | None = None) -> bytes:
    writer = pypdf.PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=612, height=792)
    if title is not None:
        writer.add_metadata({"/Title": title})
    if user_password is not None:
        writer.encrypt(user_password=user_password, owner_password="owner")
    buffer = io.BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


@pytest.fixture
def make_pdf():
    return build_pdf


def _decode_png(data: bytes) -> tuple[int, int, list[bytes]]:
    """영역 이미지 PNG(8비트 RGB, 행마다 필터 0)를 (폭, 높이, RGB 행 목록)으로 푼다. CRC도 확인한다."""
    assert data.startswith(b"\x89PNG\r\n\x1a\n")
    offset, chunks = 8, {}
    while offset < len(data):
        (length,) = struct.unpack(">I", data[offset : offset + 4])
        kind = data[offset + 4 : offset + 8]
        body = data[offset + 8 : offset + 8 + length]
        assert struct.unpack(">I", data[offset + 8 + length : offset + 12 + length])[0] == zlib.crc32(kind + body)
        chunks[kind] = chunks.get(kind, b"") + body
        offset += 12 + length
    width, height, depth, color_type = struct.unpack(">IIBB", chunks[b"IHDR"][:10])
    assert (depth, color_type) == (8, 2)
    raw = zlib.decompress(chunks[b"IDAT"])
    rows = [raw[y * (1 + 3 * width) : (y + 1) * (1 + 3 * width)] for y in range(height)]
    assert all(row[0] == 0 for row in rows)
    return width, height, [row[1:] for row in rows]


@pytest.fixture
def decode_png():
    return _decode_png

