"""질문에 쓴 논문 그림 번호 찾기 (2026-11-10 사용자 요청: Claude가 그림 이미지를 받지 못해 축 글자와 본문으로만 답했다).
브리지는 찾은 번호의 원본 그림을 Core에서 잘라 질문과 함께 보낸다."""

import pytest

from paperloom.integrations.claude_code.attachments import MAX_FIGURE_IMAGES, attachment_note, figure_refs


@pytest.mark.parametrize(
    ("question", "labels"),
    [
        ("Figure 3에서 세로선을 그으면 점들이 정렬되는 거지?", ["3"]),
        ("fig. 3과 FIG 4를 비교해 줘", ["3", "4"]),
        ("그림3, 그림 5의 차이는?", ["3", "5"]),
        ("Figures 3 and 4 show what?", ["3", "4"]),
        ("Figs. 2, 7 / 9", ["2", "7", "9"]),
        ("그림 3과 4", ["3", "4"]),
        ("Figure 2–4를 설명해 줘", ["2", "3", "4"]),
        ("Figure S1과 Fig. s2", ["S1", "S2"]),
        ("Figure 3(b)의 범례", ["3"]),
        ("Figure 3을 보고 다시 Figure 3에 대해", ["3"]),  # 한 번씩
        ("Figure 1-100", [str(number) for number in range(1, 2 + MAX_FIGURE_IMAGES)]),  # 범위는 한도까지만 편다
    ],
)
def test_figure_numbers_written_in_the_question_are_found(question, labels):
    assert figure_refs(question) == labels


@pytest.mark.parametrize("question", ["configure 3 nodes", "그림이 무엇을 보여 주나요?", "Table 3은?", "figure out 3 things", "3번 그림"])
def test_other_words_and_numbers_are_not_figure_numbers(question):
    assert figure_refs(question) == []


def test_the_note_says_which_message_image_is_which_figure_or_user_image():
    figures = [{"label": "3", "page_index": 4}, {"label": "S1", "page_index": 10}]
    note = attachment_note(2, figures, 2, [("7", "이 논문의 그림 목록에 없어 붙이지 못했습니다.")])
    assert note.splitlines() == [
        "## 이 질문에 붙인 그림",
        "",
        "- 이 메시지에 붙인 이미지 가운데 2번째: 이 논문의 Figure 3(p.5) 원본 그림. 원문 PDF에서 잘라 낸 그림입니다.",
        "- 이 메시지에 붙인 이미지 가운데 3번째: 이 논문의 Figure S1(p.11) 원본 그림. 원문 PDF에서 잘라 낸 그림입니다.",
        "- 이 메시지에 붙인 이미지 가운데 4번째: 사용자가 붙인 이미지 1",
        "- 이 메시지에 붙인 이미지 가운데 5번째: 사용자가 붙인 이미지 2",
        "- Figure 7: 이 논문의 그림 목록에 없어 붙이지 못했습니다.",
    ]
    assert attachment_note(1, [], 0, []) == ""  # 붙인 것도 뺀 것도 없으면 알리지 않는다
