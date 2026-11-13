"""PDF로 내보낼 표시 (paperloom.pdf_export.marks): 고른 부분만, 하이라이트의 메모는 그 글로, 설명의 정해진 첫 질문은 빼고."""

from paperloom.annotations.models import AnnotationOut
from paperloom.pdf_export.marks import PARTS, Mark, Thread, Turn, marks_for
from paperloom.reading.models import AnchorOut


def anchor(page_index: int = 0, v: float = 0.1, *, kind: str = "text", quote: str = "worst-case bounds", display_quote: str | None = None) -> AnchorOut:
    return AnchorOut(
        schema_version="anchor.v1", kind=kind, anchor_id=f"a-{page_index}-{v}", version_id="v1", page_index=page_index,
        quads=[[0.1, v, 0.5, v, 0.5, v + 0.02, 0.1, v + 0.02]], quote=quote if kind == "text" else "", display_quote=display_quote,
        prefix="", suffix="", created_at="2026-11-13T00:00:00Z",
    )


def annotation(comment: str = "", color: str | None = None, **where) -> AnnotationOut:
    return AnnotationOut(
        annotation_id="n1", anchor=anchor(**where), comment=comment, color=color, revision=1,
        created_at="2026-11-13T00:00:00Z", updated_at="2026-11-13T00:00:00Z",
    )


def test_a_highlight_with_a_note_becomes_one_highlight_carrying_the_note():
    [mark] = marks_for([annotation("  핵심 가정  ", "c2")], [], PARTS)

    assert mark == Mark(0, "highlight", anchor().quads, "주석", "핵심 가정", "ff9783")


def test_each_part_can_be_left_out():
    colored = annotation("핵심 가정", "c1")

    [highlight] = marks_for([colored], [], {"highlights"})
    assert (highlight.kind, highlight.label, highlight.contents, highlight.rgb) == ("highlight", "하이라이트", "", "ffe0d9")

    # 하이라이트를 빼면 메모만 아이콘으로 남는다. 아이콘은 글을 칠하지 않으므로 첫 줄에 인용을 적는다
    [note] = marks_for([colored], [], {"notes"})
    assert (note.kind, note.label, note.contents) == ("note", "주석", "“worst-case bounds”\n\n핵심 가정")

    assert marks_for([colored], [], {"explanations", "questions"}) == []
    assert marks_for([annotation(" ")], [], PARTS) == []  # 색도 메모도 없으면 넣을 것이 없다


def test_a_note_quotes_the_shown_quote_shortened_or_names_the_region():
    [long] = marks_for([annotation("메모", quote="x " * 300, display_quote=None)], [], PARTS)
    assert long.contents.startswith("“" + "x " * 99 + "x…”\n\n")

    [shown] = marks_for([annotation("메모", quote="f j k", display_quote="f^j_k")], [], PARTS)
    assert shown.contents.startswith("“f^j_k”")

    [region] = marks_for([annotation("그림 메모", kind="figure")], [], PARTS)
    assert region.contents == "[그림]\n\n그림 메모"


def test_an_explanation_hides_its_fixed_first_question_and_shrinks_artifacts():
    turns = [
        Turn("고른 부분을 쉽게 설명해 주세요.", "DDS의 기본 동작입니다.\n"),
        Turn("예를 들면?", '예:\n\n```artifact type="html" title="흐름도"\n<html></html>\n```\n'),
    ]

    [mark] = marks_for([], [Thread("explain", anchor(), turns)], PARTS)

    assert (mark.kind, mark.label, mark.rgb) == ("note", "설명", "ec3013")
    assert mark.contents == "“worst-case bounds”\n\nDDS의 기본 동작입니다.\n\n질문: 예를 들면?\n\n예:\n\n[아티팩트: 흐름도]"


def test_a_question_keeps_every_question():
    turns = [Turn(" 왜 최악인가요? ", "가장 긴 지연이라서."), Turn("그럼 평균은?", "따로 봅니다.")]

    [mark] = marks_for([], [Thread("ask", anchor(), turns)], PARTS)

    assert mark.label == "AI 질문"
    assert mark.contents == "“worst-case bounds”\n\n질문: 왜 최악인가요?\n\n가장 긴 지연이라서.\n\n질문: 그럼 평균은?\n\n따로 봅니다."


def test_threads_follow_their_parts_and_empty_threads_are_skipped():
    explain = Thread("explain", anchor(), [Turn("q", "설명")])
    ask = Thread("ask", anchor(), [Turn("q", "답")])

    assert [mark.label for mark in marks_for([], [explain, ask], {"explanations"})] == ["설명"]
    assert [mark.label for mark in marks_for([], [explain, ask], {"questions"})] == ["AI 질문"]
    assert marks_for([], [Thread("ask", anchor(), [])], PARTS) == []  # 차례를 모두 버린 대화


def test_marks_are_in_reading_order():
    lower = annotation("아래", "c1", page_index=0, v=0.6)
    next_page = annotation("다음 쪽", "c1", page_index=1, v=0.1)
    thread = Thread("ask", anchor(page_index=0, v=0.3), [Turn("q", "답")])

    marks = marks_for([next_page, lower], [thread], PARTS)

    assert [mark.contents.split("\n")[-1] for mark in marks] == ["답", "아래", "다음 쪽"]
