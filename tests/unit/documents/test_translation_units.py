"""쪽 번역 요청의 문장 (브리지 page_translation, 2026-10-03 사용자 요청): 그림 안 글자는 빼고, 원문의 굵게·기울임은
<b>·<i> 표시로 감싸 보낸다(번역에서도 그 말을 같은 표시로 감싸게 한다)."""

import json

import pytest

from paperloom.integrations.claude_code.page_translation import (
    TRANSLATION_PROMPT,
    BadTranslation,
    continued_blocks,
    parse_translation,
    repair_request,
    split_units,
    translation_request,
    translation_units,
)

TEXT = "Real-time Scheduling. To run deg2rad tasks we use both cores."


def test_units_mark_bold_and_italic_runs_per_sentence_and_skip_text_inside_figures():
    blocks = [
        {"block_id": "b1", "text": TEXT, "styles": [[0, 21, "b"], [29, 36, "i"], [50, 54, "bi"]], "quality_flags": []},
        {"block_id": "fig", "text": "Axis label.", "styles": [], "quality_flags": ["in_figure"]},
        {"block_id": "b2", "text": "Plain one. Bold across the end. Next", "styles": [[11, 36, "b"]], "quality_flags": []},
    ]
    assert translation_units(blocks) == [
        ("b1", ["<b>Real-time Scheduling.</b>", "To run <i>deg2rad</i> tasks we use <b><i>both</i></b> cores."]),
        ("b2", ["Plain one.", "<b>Bold across the end.</b>", "<b>Next</b>"]),  # 문장 경계에서 나눠 감싼다
    ]


def test_superscripts_and_subscripts_are_sent_as_sup_and_sub_marks():
    """위·아래첨자는 <sup>·<sub>로 감싸 보낸다(기울임과 겹치면 <i><sup>…</sup></i>). 2026-10-04 사용자 확인."""
    blocks = [{"block_id": "m", "text": "Let Ck and τnap hold.", "styles": [[5, 6, "_"], [11, 12, "i"], [12, 14, "i^"], [14, 15, "i_"]], "quality_flags": []}]
    assert translation_units(blocks) == [("m", ["Let C<sub>k</sub> and <i>τ</i><i><sup>na</sup></i><i><sub>p</sub></i> hold."])]


def test_blocks_without_styles_from_older_extractions_are_plain():
    assert translation_units([{"block_id": "x", "text": "Old block.", "quality_flags": []}]) == [("x", ["Old block."])]


def test_the_prompt_asks_to_keep_the_marks():
    assert "<b>" in TRANSLATION_PROMPT and "<i>" in TRANSLATION_PROMPT
    assert "<sub>" in TRANSLATION_PROMPT and "<sup>" in TRANSLATION_PROMPT
    assert "<b>Real-time</b>" in translation_request([("b1", ["<b>Real-time</b> work."])])


def test_a_paragraph_that_starts_mid_sentence_may_be_merged_into_the_paragraph_before():
    """PDF에서 문단이 문장 가운데서 나뉘면("… if it can be assigned" / "to a core. …") 모델은 앞 문단 끝 문장에 합쳐 옮기고
    뒤 문단 첫 id를 비운다(2026-10-03 사용자 논문 13쪽). 묶음의 첫 id는 비울 수 없다(합칠 앞 문장이 없다). 이어지는 문단
    (continued_blocks)이 아닌 문단의 첫 id도 비울 수 없다: 비우면 그 글이 번역에서 빠진다(2026-11-20 사용자 논문 AXLE)."""
    units = [("a", ["We assign it if it can be assigned"]), ("b", ["to a core.", "Then we repeat."])]
    answer = '{"1.1": "코어에 할당할 수 있으면 할당한다.", "2.1": "", "2.2": "그다음 반복한다."}'
    blocks = parse_translation(answer, units, {"b"})
    assert [block["sentences"] for block in blocks] == [["코어에 할당할 수 있으면 할당한다."], ["", "그다음 반복한다."]]
    with pytest.raises(BadTranslation):
        parse_translation('{"1.1": "", "2.1": "코어에.", "2.2": "그다음 반복한다."}', units, {"b"})
    with pytest.raises(BadTranslation) as emptied:
        parse_translation(answer, units)
    assert str(emptied.value).startswith('"continues": true가 없는 문단의 첫 문장을 비운 id: 2.1.')
    assert "앞 문단" in TRANSLATION_PROMPT and '"continues": true' in TRANSLATION_PROMPT


def body(block_id: str, text: str, flags=()) -> dict:
    return {"block_id": block_id, "text": text, "styles": [], "quality_flags": list(flags)}


def test_only_a_short_lowercase_rest_of_an_unfinished_paragraph_may_be_merged_into_it():
    """앞 문단 끝 문장에 합쳐 옮겨도 되는 문단(2026-11-20 사용자 논문): 앞 본문 문단이 문장 가운데서 끝나고(단이 바뀜) 그림·표
    제목이 아니며, 이 문단이 소문자로 시작하고 이어지는 첫 문장이 앞 문단 글의 절반까지일 때다. 한 줄 문단에 문장 전체 번역을
    합치면 그 자리에 맞추느라 글자가 아주 작아졌고(EdgePace), 끝난 제목·표 제목 뒤의 조각은 비워져 글이 빠졌다(AXLE·Capuchin)."""
    long = "Fig. 1 provides an overview of the communication process. A message is passed through threads as follows: the thread on the side"
    blocks = [
        body("a", long),
        body("b", "generates a message. It stores it."),  # 이어진다
        body("fig", "Axis label", ["in_figure"]),  # 본문이 아닌 문단은 건너뛴다
        body("c", "Then the DDS thread runs."),  # 대문자로 시작: 새 문장
        body("d", "BACK-STREAMING IN LEVERAGING THE STRENGTHS OF BOTH MODES."),
        body("e", "ing hardware still fall short. Instead we simulate."),  # 앞 문단이 끝난 문장
        body("f", "Figure 1. Synchronization Overhead of vDNN on Vgg16"),
        body("g", "scale. We profile execution."),  # 앞 문단이 그림 제목
        body("h", "Monitoring overhead. On Orin Nano Super,"),
        body("i", "median reads take 80.9 and 130.8 us at the two sampling intervals, respectively (Table 2). These consume 4%."),  # 앞보다 길다
        body("j", "The weights of the graph layer are computed for every node of the graph as follows, for unweighted graphs, as:"),
        body("eq", "h = sigma(W x)", ["math"]),
        body("k", "with W the trainable weight matrix. It is learned."),  # 사이에 따로 놓인 수식
    ]
    assert continued_blocks(blocks) == {"b"}
    request = translation_request(translation_units(blocks[:2]), continued={"a", "b"})
    paragraphs = json.loads(request.split("```json")[1].split("```")[0])["paragraphs"]
    assert ["continues" in paragraph for paragraph in paragraphs] == [False, True]  # 묶음의 첫 문단은 합칠 앞 문단이 없다


def test_an_unreadable_answer_says_what_is_wrong_so_it_can_be_asked_again():
    """읽지 못한 답의 까닭은 모델에게 고쳐 달라고 그대로 보낸다(repair_request, 2026-10-16 사용자 요청). JSON 문법 오류는 틀린
    곳 부근을, id 빠짐은 빠진 id를 모두 말한다."""
    units = [("a", ["One.", "Two."]), ("b", ["Three."]), ("c", ["Four.", "Five."])]
    with pytest.raises(BadTranslation) as stutter:
        parse_translation('{"1.1": "하나.", "1.2", "1.2": "둘.", "2.1": "셋."}', units)  # 2026-10-16 사용자 논문 6쪽의 모양
    assert str(stutter.value).startswith("JSON 문법이 틀렸습니다(Expecting ':' delimiter)") and '"1.2", "1.2"' in str(stutter.value)
    with pytest.raises(BadTranslation) as missing:
        parse_translation('{"1.1": "하나.", "2.1": "셋.", "3.1": "넷."}', units)
    assert str(missing.value) == "번역이 없는 id: 1.2, 3.2"
    with pytest.raises(BadTranslation, match="JSON 객체가 없습니다"):
        parse_translation("번역했습니다.", units)
    request = repair_request(str(missing.value))
    assert request.startswith("## 앞 답을 읽지 못했습니다") and "번역이 없는 id: 1.2, 3.2" in request and '빈 글("")' in request


def group_sizes(groups) -> list[int]:
    return [sum(len(text) for _, sentences in group for text in sentences) for group in groups]


def test_the_viewed_page_is_split_into_up_to_four_consecutive_groups_without_splitting_paragraphs():
    """보는 쪽은 문단 묶음 넷까지 나눠 동시에 번역한다 (2026-10-03 사용자 결정 D12, 2026-10-04 셋 → 넷). 묶음은 이어진 문단이고
    겹치지 않는다. 600자마다 한 묶음이다(2026-10-04 1,200 → 600)."""
    units = [(f"b{index}", ["x" * 300, "y" * 200]) for index in range(10)]  # 5,000자
    groups = split_units(units)
    assert len(groups) == 4
    assert [unit for group in groups for unit in group] == units  # 차례 그대로, 빠짐·겹침 없음
    assert max(group_sizes(groups)) == 1500  # 문단 셋(가장 고르게)
    assert len(split_units(units[:5])) == 4  # 2,500자
    assert len(split_units(units[:3])) == 2  # 1,500자
    assert split_units(units[:1]) == [units[:1]]  # 짧은 쪽은 나누지 않는다
    assert len(split_units([("only", ["z" * 9000])])) == 1  # 문단 하나는 나누지 않는다


def test_groups_are_balanced_so_the_slowest_group_is_as_short_as_possible():
    """쪽은 가장 늦게 끝나는 묶음에 맞춰 끝나므로 가장 큰 묶음이 가장 작게 자른다 (2026-10-04 사용자 확인: 나눈 뒤 약 2배였다.
    사용자 논문 한 쪽의 문단 글자 수: 앞 방식은 2,073 / 2,229 / 992자로 나눠 가장 큰 묶음이 9.5초 걸렸다)."""
    sizes = [178, 854, 565, 41, 435, 281, 923, 1025, 234, 28, 156, 574]  # 5,294자 → 넷
    units = [(f"b{index}", ["w" * size]) for index, size in enumerate(sizes)]
    groups = split_units(units)
    assert group_sizes(groups) == [1638, 1639, 1025, 992]  # 넷으로 나눌 수 있는 가장 고른 것(가장 큰 묶음 1,639자)
    assert [unit for group in groups for unit in group] == units


def test_a_group_after_the_first_carries_the_paragraph_before_as_context_only():
    """묶음 경계에서 이어 읽히게 바로 앞 문단을 참고로 함께 보낸다. 번역할 JSON에는 들지 않는다."""
    request = translation_request([("b5", ["Next part."])], context="The paragraph before ends here.")
    head, body = request.split("```json")
    assert "## 앞 문맥" in head and "The paragraph before ends here." in head
    assert "The paragraph before" not in body
    assert "## 앞 문맥" not in translation_request([("b1", ["First."])])
    assert "앞 문맥" in TRANSLATION_PROMPT
