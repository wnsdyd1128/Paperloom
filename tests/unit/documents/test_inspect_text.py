"""PDF 메타데이터·파일명에서 온 글 정리 (논문 제목). 2026-10-03 사용자 확인: IEEE PDF의 Title에 출판사 표시
(<underline>C</underline>ache …)가 들어 있어 제목에 태그가 그대로 보였다."""

from paperloom.documents.inspect import clean_text


def test_markup_tags_in_metadata_titles_are_removed():
    title = "CBANA: A Lightweight, Efficient, and Flexible <underline>C</underline>ache <underline>B</underline>ehavior <underline>Ana</underline>lysis Framework"
    assert clean_text(title) == "CBANA: A Lightweight, Efficient, and Flexible Cache Behavior Analysis Framework"
    assert clean_text("On <italic>k</italic>-Means and x<sub>i</sub> <inline-formula><tex-math notation=\"LaTeX\">$O(n)$</tex-math></inline-formula>") == "On k-Means and xi $O(n)$"


def test_comparisons_and_plain_angle_brackets_stay():
    assert clean_text("Bounds for a < b and c > d") == "Bounds for a < b and c > d"
    assert clean_text("  Spaced\ttitle  ") == "Spaced title"
    assert clean_text("<underline></underline>") is None
