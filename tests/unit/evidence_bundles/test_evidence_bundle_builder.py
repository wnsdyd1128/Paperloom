"""bundle 파일 내용 (03-api-spec §5–§8): 수신기 칸 한도, 파일 이름 ID, 답변 머리, 추출문 해시."""

import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

from paperloom.answers.models import Citation
from paperloom.artifacts.blocks import Block as ArtifactBlock
from paperloom.context.builder import Block, VersionText, anchor_section
from paperloom.evidence_bundles import builder
from paperloom.evidence_bundles.builder import (
    AnchorEntry,
    ArtifactEntry,
    BundleContent,
    ProposalEntry,
    SourceEntry,
    block_kind,
    build_files,
    file_kind,
    limit_excess,
    near_limit,
    reader_url,
    text_sha256,
)

FIXTURE_DIR = Path(__file__).resolve().parents[2] / "fixtures" / "evidence-bundles"
BUNDLE = "0f6c2c1e-7a4b-4c8e-9d1a-2b3c4d5e6f70"


def _fixture():
    spec = importlib.util.spec_from_file_location("bundle_generator", FIXTURE_DIR / "generate_bundles.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


fixture = _fixture()


def content(*, anchors=None, proposals=(), answers=(), artifacts=(), paper=None) -> BundleContent:
    paper = paper or fixture._paper()
    version = fixture.VersionOut(**paper.current_version.model_dump(), paper_id=paper.paper_id)
    sources = [SourceEntry(paper, version, anchors or [], None)]
    return BundleContent(BUNDLE, fixture.NOW, "test", "http://127.0.0.1:8000/", sources, list(proposals), list(answers), list(artifacts))


def anchor_entry(anchor_id: str = fixture.TEXT_ANCHOR, **fields) -> AnchorEntry:
    anchor = fixture._anchor(anchor_id, "text", 0, [0, 0, 1, 0, 1, 1, 0, 1], "인용")
    return AnchorEntry(**{"anchor": anchor, "page_label": None, "section": None, "comment": None, "image": None, **fields})


def anchors_json(files: dict[str, bytes]) -> list[dict]:
    return json.loads(files["anchors.json"])


def test_the_manifest_comes_last_and_lists_every_other_file_with_its_hash():
    files = build_files(content(anchors=[anchor_entry()]))

    assert list(files)[-1] == "manifest.json"
    manifest = json.loads(files["manifest.json"])
    assert [item["path"] for item in manifest["files"]] == list(files)[:-1]
    assert all(item["sha256"] == hashlib.sha256(files[item["path"]]).hexdigest() and item["size_bytes"] == len(files[item["path"]]) for item in manifest["files"])
    assert "features" not in manifest and manifest["schema_version"] == "paperloom-bundle.v1"


def test_refs_are_unique_within_the_bundle_and_proposals_use_them():
    proposal = ProposalEntry(fixture.PROPOSAL_ID, fixture.VERSION_ID, "제목", "본문", [fixture.TABLE_ANCHOR])
    files = build_files(content(anchors=[anchor_entry(), anchor_entry(fixture.TABLE_ANCHOR)], proposals=[proposal]))

    assert [item["anchor_ref"] for item in anchors_json(files)] == ["anc_1", "anc_2"]
    written = json.loads(files[f"proposals/{fixture.PROPOSAL_ID}.json"])
    assert written["anchor_refs"] == ["anc_2"] and written["source_refs"] == ["src_1"]
    assert written["content_file"] == f"artifacts/proposal-{fixture.PROPOSAL_ID}.md"
    assert (written["target_note_id"], written["base_content_sha256"], written["requires_user_approval"]) == (None, None, True)
    assert files[written["content_file"]] == "본문".encode()  # 머리말 없이 쓴 그대로


def test_long_values_are_cut_to_the_receiver_limits_instead_of_losing_the_bundle():
    paper = fixture._paper().model_copy(update={"title": "제" * 3000, "authors": ["A"] * 600, "doi": "1" * 600})
    entry = anchor_entry(page_label="1" * 200, section="절" * 3000, comment="메" * 150_000)

    files = build_files(content(anchors=[entry], paper=paper))

    [source], [anchor] = json.loads(files["sources.json"]), anchors_json(files)
    assert (len(source["title"]), len(source["authors"]), len(source["doi"])) == (2000, 500, 500)
    assert (len(anchor["page_label"]), len(anchor["section"]), len(anchor["comment"])) == (100, 2000, 100_000)


def test_an_id_that_is_unsafe_as_a_file_name_is_replaced_and_kept_inside():
    entry = anchor_entry("../evil id", image=b"png")

    files = build_files(content(anchors=[entry]))

    assert "assets/n001.png" in files
    [anchor] = anchors_json(files)
    assert (anchor["anchor_id"], anchor["asset"]) == ("../evil id", "assets/n001.png")


def test_reader_links_follow_the_form_llm_wiki_keeps():
    assert reader_url("http://127.0.0.1:8000/", "p", "v") == "http://127.0.0.1:8000/reader/p?version=v"
    assert reader_url("http://localhost:5173", "p", "v", "a") == "http://localhost:5173/reader/p?version=v&anchor=a"
    assert reader_url("http://127.0.0.1:8000/", "a/b c", "v") == "http://127.0.0.1:8000/reader/a%2Fb%20c?version=v"


def answer_with(citations, unresolved=(), prompt="질문입니다", markdown="답 본문 [근거 1]"):
    return fixture._answer().model_copy(update={"citations": citations, "unresolved_citations": list(unresolved), "prompt": prompt, "markdown": markdown})


def citation(number, anchor_id, page_index=3, paragraph=None):
    return Citation(
        number=number, paragraph=paragraph, evidence_id="e", role="selected_text", page_index=page_index, paper_id=fixture.PAPER_ID,
        version_id=fixture.VERSION_ID, anchor_id=anchor_id, block_id=None,
    )


def test_the_answer_head_maps_citations_to_anchor_refs_and_names_the_unresolved():
    answer = answer_with([citation(1, fixture.TEXT_ANCHOR), citation(2, "", 6, paragraph=3), citation(3, "다른 판본", 8)], unresolved=[9])

    text = build_files(content(anchors=[anchor_entry()], answers=[answer]))[f"artifacts/answer-{answer.answer_id}.md"].decode()

    head, body = text.split("\n\n", 1)
    lines = head.split("\n")
    assert lines[0] == f"> Paperloom 답변 · answer_id {answer.answer_id} · origin claude_code · review unreviewed · {answer.created_at}"
    assert lines[1] == "> 질문: 질문입니다"
    assert lines[2] == "> 근거: [근거 1] = anc_1 (쪽 4) · 풀지 못함: [근거 2¶3] (쪽 7), [근거 3] (쪽 9), [근거 9]"
    assert body == "답 본문 [근거 1]\n"


def test_the_answer_head_stays_on_one_line_each():
    answer = answer_with([], prompt="여러\n줄의\n\n질문 " + "가" * 300)

    head = build_files(content(answers=[answer]))[f"artifacts/answer-{answer.answer_id}.md"].decode().split("\n\n")[0].split("\n")

    assert len(head) == 3 and head[1].startswith("> 질문: 여러 줄의 질문 ") and len(head[1]) == len("> 질문: ") + 200
    assert head[2] == "> 근거: 없음"


def test_a_code_artifact_keeps_its_language_without_breaking_the_fence():
    answer = answer_with([])
    block = ArtifactBlock("code", "여러\n줄의 제목", "py thon`", "print('``')")

    text = build_files(content(artifacts=[ArtifactEntry(answer, 0, block)]))[f"artifacts/artifact-{answer.answer_id}-1.md"].decode()

    head, body = text.split("\n\n", 1)
    assert head.split("\n")[0].endswith(f"· 답변의 1번째 · type code · py thon` · review unreviewed · {answer.created_at}")
    assert head.split("\n")[1] == "> 제목: 여러 줄의 제목"
    assert body == "```python\nprint('``')\n```\n"  # 백틱 울타리의 정보 글에는 백틱이 없어야 한다


def test_an_artifact_of_an_unsafe_answer_id_gets_a_replaced_name():
    answer = answer_with([]).model_copy(update={"answer_id": "../evil id"})
    block = ArtifactBlock("mermaid", "다이어그램", None, "graph TD; A-->B")

    files = build_files(content(artifacts=[ArtifactEntry(answer, 2, block)]))

    assert files["artifacts/artifact-n001-3.md"].decode().endswith("\n\n```mermaid\ngraph TD; A-->B\n```\n")


def test_text_hash_covers_the_pages_in_the_agreed_form():
    pages = [{"b": "글", "a": 1}]

    assert text_sha256(pages) == hashlib.sha256('[{"a":1,"b":"글"}]'.encode()).hexdigest()


@pytest.mark.parametrize(
    ("flags", "text", "headings", "kind"),
    [
        (("reference",), "[1] A.", (), "reference"),
        (("in_table",), "1,200", (), "in_table"),
        (("in_figure",), "x", (), "in_figure"),
        (("math",), "x = y", (), "math"),
        (("page_header",), "Journal", (), "page_header"),
        (("page_footer",), "Vol. 1", (), "page_footer"),
        ((), "3 Method", ("b",), "heading"),
        ((), "Table 1. Results", (), "caption"),
        ((), "Plain paragraph.", (), "body"),
    ],
)
def test_block_kinds_keep_the_marks_paperloom_already_has(flags, text, headings, kind):
    block = Block(block_id="b", page_index=0, text=text, regions=(), quality_flags=flags, line_height=10)

    assert block_kind(block, frozenset(headings)) == kind


def test_an_anchor_finds_its_section_by_paragraph_or_caption():
    paragraph = Block("p", 0, "A paragraph.", ((0.1, 0.1, 0.9, 0.2),), (), 10)
    caption = Block("c", 0, "Figure 1. Bars.", ((0.1, 0.62, 0.9, 0.65),), (), 10)
    text = VersionText(extracted=True, pages={}, blocks=[paragraph, caption], sections={"p": "1 Intro", "c": "2 Results"})
    selected = fixture._anchor("a", "text", 0, [0.1, 0.1, 0.5, 0.1, 0.5, 0.2, 0.1, 0.2], "A")
    region = fixture._anchor("b", "figure", 0, [0.1, 0.3, 0.9, 0.3, 0.9, 0.6, 0.1, 0.6], "")
    elsewhere = fixture._anchor("c", "text", 1, [0.1, 0.1, 0.5, 0.1, 0.5, 0.2, 0.1, 0.2], "A")

    assert (anchor_section(selected, text), anchor_section(region, text), anchor_section(elsewhere, text)) == ("1 Intro", "2 Results", None)


def test_limits(monkeypatch):
    assert limit_excess({"a": b"1"}) is None
    assert limit_excess({str(n): b"" for n in range(65)}) == {"file_count": 65, "total_bytes": 0, "largest_path": "0"}
    assert limit_excess({"big": b"", "a": b""}) is None
    monkeypatch.setattr(builder, "MAX_FILE_BYTES", 2)
    assert limit_excess({"small": b"1", "big": b"123"}) == {"file_count": 2, "total_bytes": 4, "largest_path": "big"}
    monkeypatch.setattr(builder, "MAX_FILE_BYTES", 8 * 1024 * 1024)
    monkeypatch.setattr(builder, "MAX_TOTAL_BYTES", 3)
    assert limit_excess({"a": b"12", "b": b"12"}) == {"file_count": 2, "total_bytes": 4, "largest_path": "a"}
    assert near_limit({"a": b"123"}) and not near_limit({"a": b"12"})
    assert near_limit({str(n): b"" for n in range(52)}) and not near_limit({str(n): b"" for n in range(51)})


@pytest.mark.parametrize(
    ("path", "kind"),
    [
        ("manifest.json", "manifest"),
        ("sources.json", "sources"),
        ("anchors.json", "anchors"),
        ("proposals/a.json", "proposal"),
        ("artifacts/a.md", "artifact"),
        ("assets/a.png", "asset"),
        ("texts/a.json", "text"),
    ],
)
def test_file_kinds(path, kind):
    assert file_kind(path) == kind
