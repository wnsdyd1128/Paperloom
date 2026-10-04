"""그림 후보 묶기 규칙 (그림 클릭 선택, IMPL §10.6)."""

import pytest

from paperloom.reading.figures import Graphic, figure_candidates

PAGE = (0.0, 0.0, 600.0, 800.0)


def path(left, bottom, right, top, filled=True, stroked=False) -> Graphic:
    return Graphic("path", (left, bottom, right, top), filled, stroked)


def pt_boxes(figures, page=PAGE):
    """정본 좌표를 PDF pt(left, bottom, right, top)로 되돌려 비교한다."""
    x0, y0, x1, y1 = page
    return [
        (
            round(x0 + f.box[0] * (x1 - x0), 6),
            round(y1 - f.box[3] * (y1 - y0), 6),
            round(x0 + f.box[2] * (x1 - x0), 6),
            round(y1 - f.box[1] * (y1 - y0), 6),
        )
        for f in figures
    ]


def test_touching_and_nearby_objects_become_one_figure():
    graphics = [path(100, 100, 150, 200), path(150, 100, 200, 160), path(202, 100, 250, 180)]  # 마지막은 2 pt 떨어짐
    assert pt_boxes(figure_candidates(graphics, PAGE)) == [(100, 100, 250, 200)]


def test_objects_further_apart_than_gap_stay_separate_and_sort_top_first():
    graphics = [path(100, 100, 200, 200), path(100, 400, 200, 500)]
    assert pt_boxes(figure_candidates(graphics, PAGE)) == [(100, 400, 200, 500), (100, 100, 200, 200)]


@pytest.mark.parametrize(
    "graphics",
    [
        [path(50, 300, 550, 300.5, filled=False, stroked=True), path(50, 280, 550, 280.5, filled=False, stroked=True)],  # 표 가로줄
        [path(100, 100, 300, 250, filled=False, stroked=True)],  # 획만 있는 선 하나 (대각선)
        [Graphic("image", (100, 100, 120, 120))],  # 20 pt 아이콘
        [path(100, 100, 300, 300, filled=False, stroked=False)],  # 보이지 않는 경로(잘라내기)
        [path(500, -400, 700, 100, filled=False, stroked=True), path(510, -400, 700, 90, filled=False, stroked=True)],  # 대부분 쪽 밖
        [Graphic("image", (0, 0, 600, 800))],  # 쪽 전체 배경
    ],
)
def test_lines_icons_invisible_offpage_and_background_are_not_figures(graphics):
    assert figure_candidates(graphics, PAGE) == []


def test_page_background_does_not_swallow_figures():
    graphics = [path(0, 0, 600, 800), Graphic("image", (100, 500, 300, 700)), path(100, 100, 300, 300), path(300, 100, 400, 200)]
    figures = figure_candidates(graphics, PAGE)
    assert pt_boxes(figures) == [(100, 500, 300, 700), (100, 100, 400, 300)]
    assert [f.source for f in figures] == ["image", "vector"]


def test_single_filled_shape_and_form_count_as_figures():
    figures = figure_candidates([path(100, 100, 200, 200), Graphic("form", (300, 300, 400, 400))], PAGE)
    assert [f.source for f in figures] == ["form", "vector"]


def test_boxes_are_normalized_against_view_box_and_clipped():
    view_box = (36.0, 72.0, 576.0, 756.0)  # CropBox 오프셋
    figures = figure_candidates([Graphic("image", (30, 600, 200, 760))], view_box)  # 왼쪽·위로 조금 넘침
    assert figures[0].box == pytest.approx((0, 0, (200 - 36) / 540, (756 - 600) / 684))
