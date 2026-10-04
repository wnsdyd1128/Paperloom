"""Anchor 영역 이미지 (IMPL §5.4, §10.6). pypdfium2로 영역만 그려 PNG로 돌려준다.

좌표는 anchor.v1 정본 좌표(회전 전 view box 기준, 좌상단 원점, 0~1)다. 이미지는 화면에 보이는 방향
(쪽의 /Rotate 적용)으로 그린다. pdfium은 view box(CropBox ∩ MediaBox)를 /Rotate를 적용해 그리고
UserUnit은 쓰지 않는다(1 canvas unit = 1 pt).

신뢰할 수 없는 PDF를 다루므로 문서 검사(documents.inspect)처럼 시간 제한이 있는 하위 프로세스에서 그린다.
하위 프로세스: `python -m paperloom.reading.region_image <pdf> <page_index> <u0> <v0> <u1> <v1> <scale>`
→ stdout에 PNG.
"""

import math
import struct
import subprocess
import sys
import zlib
from pathlib import Path

from paperloom.infrastructure.isolation import limit_resources

Box = tuple[float, float, float, float]  # u0, v0, u1, v1

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
# 큰 영역·높은 배율 요청에 메모리를 쓰지 않도록 배율을 줄여 맞춘다.
MAX_SIDE_PX = 4000
MAX_PIXELS = 12_000_000


class RenderFailed(Exception):
    """code: RESOURCE_LIMIT(시간 초과), RENDER_FAILED(그 밖의 실패)."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def render_region(path: Path, page_index: int, box: Box, scale: float, timeout_seconds: float) -> bytes:
    command = [sys.executable, "-m", "paperloom.reading.region_image", str(path), str(page_index)]
    try:
        result = subprocess.run(
            [*command, *(repr(value) for value in (*box, scale))],
            capture_output=True,
            timeout=timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired:
        raise RenderFailed("RESOURCE_LIMIT") from None
    if result.returncode != 0 or not result.stdout.startswith(PNG_SIGNATURE):
        raise RenderFailed("RENDER_FAILED")
    return result.stdout


def displayed_box(box: Box, rotation: int) -> Box:
    """회전 전 정규화 상자를 /Rotate(시계 방향)를 적용한 화면 쪽의 정규화 상자로 바꾼다."""
    u0, v0, u1, v1 = box
    if rotation == 90:
        return 1 - v1, u0, 1 - v0, u1
    if rotation == 180:
        return 1 - u1, 1 - v1, 1 - u0, 1 - v0
    if rotation == 270:
        return v0, 1 - u1, v1, 1 - u0
    return box


def encode_png(width: int, height: int, rgb: bytes, stride: int) -> bytes:
    """8비트 RGB PNG. 행마다 필터 0(없음)을 쓴다."""
    raw = b"".join(b"\x00" + rgb[row * stride : row * stride + width * 3] for row in range(height))

    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))

    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return PNG_SIGNATURE + chunk(b"IHDR", header) + chunk(b"IDAT", zlib.compress(raw, 6)) + chunk(b"IEND", b"")


def _render(path: str, page_index: int, box: Box, scale: float) -> bytes:
    import pypdfium2 as pdfium
    import pypdfium2.raw as pdfium_c

    document = pdfium.PdfDocument(path)
    try:
        page = document[page_index]
        width, height = page.get_size()  # /Rotate를 적용한 크기 (pt)
        u0, v0, u1, v1 = displayed_box(box, page.get_rotation())
        region_width, region_height = (u1 - u0) * width, (v1 - v0) * height
        scale = min(scale, MAX_SIDE_PX / max(region_width, region_height), (MAX_PIXELS / (region_width * region_height)) ** 0.5)
        crop = (u0 * width, (1 - v1) * height, (1 - u1) * width, v0 * height)  # 왼쪽, 아래, 오른쪽, 위에서 잘라 낼 양
        # pypdfium2는 잘라 낼 양을 픽셀로 올림(ceil)해 영역이 1 px까지 깎인다. 바깥쪽으로 맞추도록 픽셀 단위로
        # 내림한다. 회전 변환의 부동소수 오차(400 → 399.9999…)로 한 픽셀 더 붙지 않게 1e-6 px 안은 정수로 본다.
        crop = tuple(max(0.0, (math.floor(amount * scale + 1e-6) - 1e-6) / scale) for amount in crop)
        bitmap = page.render(scale=scale, crop=crop, force_bitmap_format=pdfium_c.FPDFBitmap_BGR, rev_byteorder=True)
        return encode_png(bitmap.width, bitmap.height, bytes(bitmap.buffer), bitmap.stride)
    finally:
        document.close()


def _main() -> None:
    limit_resources()
    path, page_index, *numbers = sys.argv[1:]
    u0, v0, u1, v1, scale = map(float, numbers)
    sys.stdout.buffer.write(_render(path, int(page_index), (u0, v0, u1, v1), scale))


if __name__ == "__main__":
    _main()
