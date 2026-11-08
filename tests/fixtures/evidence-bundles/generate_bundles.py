"""Evidence Bundle 계약 fixture 생성기 (NFR-10). LLM Wiki 쪽이 수신기를 시험할 때도 이 폴더를 쓸 수 있다. 값은 모두 합성이다.

v1/   paperloom-bundle.v1: 논문 하나, Anchor 둘(글·표), 메모, 제안 하나, 답변 하나, 영역 이미지 하나
v1.1/ paperloom-bundle.v1.1: 같은 내용에 원문 추출문 texts/ (LLM Wiki 수신기는 2026-11-02부터 이 폴더를 받는다, 03-api-spec §7)

실행: python tests/fixtures/evidence-bundles/generate_bundles.py
"""

from pathlib import Path

from paperloom.answers.models import AnswerOut, Citation
from paperloom.documents.models import PaperOut, SourceVersionOut, VersionOut
from paperloom.evidence_bundles.builder import (
    AnchorEntry,
    BundleContent,
    ProposalEntry,
    SourceEntry,
    TextEntry,
    build_files,
)
from paperloom.reading.models import AnchorOut
from paperloom.reading.region_image import encode_png

HERE = Path(__file__).resolve().parent
NOW = "2026-10-30T00:00:00Z"
PAPER_ID = "11111111-1111-4111-8111-111111111111"
VERSION_ID = "22222222-2222-4222-8222-222222222222"
TEXT_ANCHOR = "33333333-3333-4333-8333-333333333331"
TABLE_ANCHOR = "33333333-3333-4333-8333-333333333332"
PROPOSAL_ID = "3c1a9b2e-1d4f-4a6b-8c7d-9e0f1a2b3c4d"
ANSWER_ID = "44444444-4444-4444-8444-444444444444"
BUNDLES = {
    "v1": "0f6c2c1e-7a4b-4c8e-9d1a-2b3c4d5e6f70",
    "v1.1": "1a7d3d2f-8b5c-4d9f-ae2b-3c4d5e6f7081",
}
PDF_SHA256 = "ab" * 32
BASE_URL = "http://127.0.0.1:8000/"


def _anchor(anchor_id: str, kind: str, page_index: int, quad: list[float], quote: str) -> AnchorOut:
    return AnchorOut(
        schema_version="anchor.v1", kind=kind, anchor_id=anchor_id, version_id=VERSION_ID, page_index=page_index, quads=[quad],
        quote=quote, display_quote=None, prefix="", suffix="", created_at=NOW,
    )


def _paper() -> PaperOut:
    version = SourceVersionOut(
        version_id=VERSION_ID, sha256=PDF_SHA256, size_bytes=1000, page_count=13, status="INDEXED", created_at=NOW,
    )
    return PaperOut(
        paper_id=PAPER_ID, title="Synthetic cache paper", authors=["A. Author"], year=2025, doi=None, created_at=NOW, current_version=version,
        tags=[], last_opened_at=None, annotation_count=1, conversation_count=1,
    )


def _answer() -> AnswerOut:
    citation = Citation(
        number=1, evidence_id="e1", role="selected_text", page_index=3, paper_id=PAPER_ID, version_id=VERSION_ID, anchor_id=TEXT_ANCHOR,
        block_id=None,
    )
    return AnswerOut(
        answer_id=ANSWER_ID, packet_id="packet", origin="claude_code", connection_name=None, prompt="기준선 조건은?", session_id=None,
        markdown="SCP는 WCRT를 18% 줄입니다 [근거 1]. 조건은 다릅니다 [근거 2].", content_sha256=PDF_SHA256, citations=[citation],
        unresolved_citations=[2], review_status="unreviewed", created_at=NOW, discarded_at=None, question="기준선 조건은?",
        paper_titles=["Synthetic cache paper"], source_versions=[VERSION_ID], context=[],
    )


def _text() -> TextEntry:
    block = {
        "block_id": "55555555-5555-4555-8555-555555555555", "order": 1, "kind": "body", "section": "5 Evaluation",
        "text": "SCP reduces WCRT by 18% under the baseline.", "display_text": None,
    }
    pages = [
        {"page_index": 3, "page_label": "4", "text_status": "usable", "flags": ["two_columns"], "blocks": [block]},
        {"page_index": 4, "page_label": None, "text_status": "not_extracted", "flags": [], "blocks": []},
    ]
    extractor = {"name": "paperloom-parse", "version": "fixture", "parse_run_id": "66666666-6666-4666-8666-666666666666", "finished_at": NOW}
    return TextEntry(extractor, pages)


def build(name: str) -> dict[str, bytes]:
    paper = _paper()
    version = VersionOut(**paper.current_version.model_dump(), paper_id=PAPER_ID)
    white_pixel = encode_png(1, 1, bytes([255, 255, 255]), 3)
    anchors = [
        AnchorEntry(_anchor(TEXT_ANCHOR, "text", 3, [0.12, 0.30, 0.88, 0.30, 0.88, 0.33, 0.12, 0.33], "SCP reduces WCRT by 18%"), "4", "5 Evaluation", "기준선 조건 확인 필요", None),
        AnchorEntry(_anchor(TABLE_ANCHOR, "table", 5, [0.1, 0.2, 0.9, 0.2, 0.9, 0.5, 0.1, 0.5], ""), None, None, None, white_pixel),
    ]
    source = SourceEntry(paper, version, anchors, _text() if name == "v1.1" else None)
    proposal = ProposalEntry(PROPOSAL_ID, VERSION_ID, "SCP의 WCRT 개선 조건", "# SCP의 WCRT 개선 조건\n\n기준선에서 18% 줄어든다.\n", [TEXT_ANCHOR])
    return build_files(BundleContent(BUNDLES[name], NOW, "fixture", BASE_URL, [source], [proposal], [_answer()]))


def folder(name: str) -> Path:
    return HERE / name / f"bundle_{BUNDLES[name]}"


def main() -> None:
    for name in BUNDLES:
        for relative, data in build(name).items():
            target = folder(name) / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)


if __name__ == "__main__":
    main()
