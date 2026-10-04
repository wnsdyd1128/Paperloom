"""anchor.v1 quad 모양 검사 (IMPL §6.2): 넓이 없음·자기 교차를 거부한다."""

import pytest

from paperloom.reading.geometry import quad_shape_problem


@pytest.mark.parametrize(
    "quad",
    [
        [0.1, 0.1, 0.5, 0.1, 0.5, 0.2, 0.1, 0.2],  # 축 정렬 사각형 (웹이 만드는 모양)
        [0.1, 0.1, 0.5, 0.15, 0.45, 0.25, 0.05, 0.2],  # 기울어진 볼록 사각형
        [0, 0, 1, 0, 1, 1, 0, 1],  # 쪽 전체
        [0.2, 0.2, 0.2003, 0.2, 0.2003, 0.2004, 0.2, 0.2004],  # 아주 작지만 넓이가 있다
    ],
)
def test_accepts_simple_quads(quad):
    assert quad_shape_problem(quad) is None


@pytest.mark.parametrize(
    ("quad", "message"),
    [
        ([0.1, 0.1, 0.5, 0.1, 0.1, 0.2, 0.5, 0.2], "자기 교차"),  # 아래 두 점이 뒤바뀐 나비 모양
        ([0.1, 0.1, 0.1, 0.2, 0.5, 0.1, 0.5, 0.2], "자기 교차"),
        ([0.1, 0.1, 0.5, 0.1, 0.5, 0.1, 0.1, 0.1], "넓이"),  # 높이 0
        ([0.3, 0.3, 0.3, 0.3, 0.3, 0.3, 0.3, 0.3], "넓이"),  # 한 점
        ([0.1, 0.1, 0.2, 0.2, 0.3, 0.3, 0.4, 0.4], "넓이"),  # 한 직선 위
    ],
)
def test_rejects_degenerate_or_self_intersecting_quads(quad, message):
    assert message in quad_shape_problem(quad)
