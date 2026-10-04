"""영역 이미지의 좌표 변환과 PNG 인코딩 (IMPL §10.6)."""

import pytest

from paperloom.reading.region_image import displayed_box, encode_png

BOX = (0.1, 0.2, 0.4, 0.3)  # u0, v0, u1, v1 (회전 전)


@pytest.mark.parametrize(
    ("rotation", "expected"),
    [
        (0, (0.1, 0.2, 0.4, 0.3)),
        (90, (0.7, 0.1, 0.8, 0.4)),  # 시계 방향 90°: (u, v) → (1 − v, u)
        (180, (0.6, 0.7, 0.9, 0.8)),
        (270, (0.2, 0.6, 0.3, 0.9)),  # (u, v) → (v, 1 − u)
    ],
)
def test_displayed_box_follows_clockwise_rotation(rotation, expected):
    assert displayed_box(BOX, rotation) == pytest.approx(expected)


def test_displayed_box_rotations_compose():
    # 90°를 네 번 돌리면 제자리, 90° 두 번은 180°
    box = BOX
    for _ in range(4):
        box = displayed_box(box, 90)
    assert box == pytest.approx(BOX)
    assert displayed_box(displayed_box(BOX, 90), 90) == pytest.approx(displayed_box(BOX, 180))


def test_encode_png_round_trip_with_row_padding(decode_png):
    width, height, stride = 3, 2, 12  # pdfium bitmap처럼 행 끝에 여분 바이트가 있다
    pixels = [[(255, 0, 0), (0, 255, 0), (0, 0, 255)], [(10, 20, 30), (40, 50, 60), (70, 80, 90)]]
    buffer = b"".join(bytes(sum(row, ())) + b"\xee" * (stride - 3 * width) for row in pixels)

    decoded_width, decoded_height, rows = decode_png(encode_png(width, height, buffer, stride))

    assert (decoded_width, decoded_height) == (width, height)
    assert rows == [bytes(sum(row, ())) for row in pixels]
