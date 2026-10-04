"""문맥 Markdown (IMPL §7.3): 논문 본문 범위에서 한도에 걸린 쪽은 그 쪽부터 빠졌다고 적는다."""

from paperloom.context.export import render_markdown
from paperloom.context.models import ContextPacketOut, Evidence, Excluded, Limits, Source


def packet(excluded: list[Excluded]) -> ContextPacketOut:
    evidence = Evidence(
        evidence_id="e1", role="paper_text", source_ref="src_1", version_id="v1", page_index=0, anchor_id="", kind=None,
        text="첫 쪽 본문", display_text=None, truncated=False, regions=[], block_id="b1", image=None, text_status="usable", quality_flags=[],
    )
    return ContextPacketOut(
        intent="ask", question="q", evidence=[evidence], scope="paper", scope_page=None,
        sources=[Source(source_ref="src_1", paper_id="p1", title="T", version_id="v1", sha256="h")],
        limits=Limits(max_text_chars=12_000, used_text_chars=5, max_images=2, used_images=0, truncated=True, excluded=excluded),
        packet_id="k1", created_at="now", content_sha256="c", status="PREPARED",
    )


def test_evidence_is_numbered_apart_from_the_papers_reference_numbers():
    text = render_markdown(packet([]), "http://x/")
    assert "### [근거 1] 논문 본문 · T · 1쪽" in text
    assert "[근거 1]" in text.split("### ")[0] and "참고문헌" in text.split("### ")[0]  # 근거 앞 안내에 표기와 구분을 적는다


def test_paper_text_cut_by_the_budget_is_reported_from_that_page_on():
    text = render_markdown(packet([Excluded(role="paper_text", anchor_id="", page_index=24, reason="text_budget")]), "http://x/")
    assert "- 넣지 않음: 25쪽부터 논문 본문 — 글자 한도를 넘음" in text
    assert "- 범위: 논문 본문" in text


def test_a_page_without_text_is_reported_as_that_page():
    text = render_markdown(packet([Excluded(role="paper_text", anchor_id="", page_index=3, reason="no_extracted_text")]), "http://x/")
    assert "- 넣지 않음: 4쪽 논문 본문 — 그 자리에 추출된 글이 없음" in text


def test_paper_text_paragraphs_are_marked_for_paragraph_citations():
    """문단 근거 (2026-10-02 사용자 요청): 논문 본문 근거의 문단마다 ¶번호를 달고, [근거 n¶m]으로 표시하라고 적는다."""
    item = packet([]).evidence[0].model_copy(update={"text": "첫 문단\n\n둘째 문단", "block_ids": ["b1", "b2"]})
    text = render_markdown(packet([]).model_copy(update={"evidence": [item]}), "http://x/")
    assert "> ¶1 첫 문단\n>\n> ¶2 둘째 문단" in text
    assert "[근거 1¶2]" in text.split("### ")[0]
    # 근거 문단은 본문에서 먼저, 초록은 맨 마지막 (2026-10-04 사용자 요청). 붙여 넣기로 건네는 글도 같은 안내를 받는다.
    assert "초록(Abstract)은 맨 마지막" in text.split("### ")[0]
