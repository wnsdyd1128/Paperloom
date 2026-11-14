"""Wiki로 내보내기 REST (docs/integration/paperloom): 미리보기·생성·기록, 재전송, 한도, outbox 상태, 추출문, 답변, 입력 검사."""

import hashlib
import json
import uuid
from contextlib import closing
from pathlib import Path
from urllib.parse import quote

import pytest
from fastapi.testclient import TestClient

from paperloom.bootstrap.app import create_app
from paperloom.bootstrap.config import AppSettings, Settings, WikiSettings
from paperloom.evidence_bundles import builder
from paperloom.evidence_bundles.outbox import Outbox
from paperloom.infrastructure.database.sqlite import connect
from paperloom.reading import service as reading_service
from paperloom.reading.region_image import RenderFailed, encode_png

FIXTURE_DIR = Path(__file__).resolve().parents[2] / "fixtures" / "pdf-layout"
QUAD = [0.1, 0.1, 0.5, 0.1, 0.5, 0.12, 0.1, 0.12]
SESSION = str(uuid.uuid4())
BASE_URL = "http://127.0.0.1:8000"
PNG = encode_png(1, 1, bytes([255, 255, 255]), 3)
SVG_ANSWER = '그림입니다.\n\n```artifact type="svg" title="합성 그림"\n<svg xmlns="http://www.w3.org/2000/svg"></svg>\n```\n'
ARTIFACTS_ANSWER = (
    "설명 [근거 1].\n\n"
    '```artifact type="markdown" title="요약 문서"\n# 요약\n\n본문\n```\n\n'
    '````artifact type="html" title="표 페이지"\n<!doctype html>\n<pre>\n```\n안의 울타리\n```\n</pre>\n````\n'
)


@pytest.fixture
def outbox(tmp_path: Path) -> Path:
    path = tmp_path / "outbox"
    path.mkdir()
    return path


@pytest.fixture
def app(tmp_path, outbox):
    return create_app(Settings(app=AppSettings(mode="test", data_dir=tmp_path / "data"), wiki=WikiSettings(enabled=True, outbox_path=outbox)))


@pytest.fixture
def client(app) -> TestClient:
    return TestClient(app, base_url=BASE_URL)


def upload(client: TestClient, name: str = "text-digital.pdf") -> dict:
    response = client.post(
        "/api/v1/papers",
        content=(FIXTURE_DIR / name).read_bytes(),
        headers={"Content-Type": "application/pdf", "X-Paperloom-Filename": quote(name)},
    )
    assert response.status_code == 201, response.text
    paper = response.json()
    return {**paper, "version_id": paper["current_version"]["version_id"]}


def extract(app) -> None:
    while app.state.parsing.run_next():
        pass


@pytest.fixture
def paper(app, client) -> dict:
    uploaded = upload(client)
    extract(app)
    return uploaded


def make_anchor(client: TestClient, version_id: str, page_index: int = 1, quad=QUAD, quote_text: str = "인용한 글", kind: str = "text") -> str:
    response = client.post("/api/v1/anchors", json={
        "schema_version": "anchor.v1", "kind": kind, "version_id": version_id, "page_index": page_index, "quads": [quad],
        "quote": quote_text, "display_quote": None, "prefix": "앞", "suffix": "뒤",
    })
    assert response.status_code == 201, response.text
    return response.json()["anchor_id"]


def make_answer(client: TestClient, anchor_ids: list[str], markdown: str, **packet) -> dict:
    body = {"intent": "ask", "question": "질문", "anchors": [{"anchor_id": anchor_id} for anchor_id in anchor_ids], **packet}
    packet_id = client.post("/api/v1/context-packets", json=body).json()["packet_id"]
    client.patch(f"/api/v1/context-packets/{packet_id}", json={"status": "HANDED_OFF", "handoff_method": "claude_code"})
    response = client.post(f"/api/v1/context-packets/{packet_id}/answers", json={"markdown": markdown, "prompt": "차례의 질문", "session_id": SESSION})
    assert response.status_code == 201, response.text
    return response.json()


def create(client: TestClient, body: dict, key: str | None = None):
    return client.post("/api/v1/evidence-bundles", json=body, headers={"Idempotency-Key": key or uuid.uuid4().hex})


def preview(client: TestClient, body: dict):
    return client.post("/api/v1/evidence-bundles/preview", json=body)


def bundles_in(outbox: Path) -> list[Path]:
    return sorted(outbox.iterdir())


def read_json(folder: Path, name: str):
    return json.loads((folder / name).read_text(encoding="utf-8"))


def errors_of(response) -> list[str]:
    assert (response.status_code, response.json()["code"]) == (422, "INVALID_BUNDLE")
    return [item["reason"] for item in response.json()["details"]["errors"]]


def test_export_writes_one_bundle_the_receiver_accepts(client, paper, outbox, check_evidence_bundle):
    """AC-01: 논문 1편, Anchor 2개(메모 1개), 제안 1개."""
    version_id, paper_id = paper["version_id"], paper["paper_id"]
    first, second = make_anchor(client, version_id, quote_text="첫째"), make_anchor(client, version_id, 2, quote_text="둘째")
    client.post("/api/v1/annotations", json={"anchor_id": first, "comment": "먼저 쓴 메모"})
    client.post("/api/v1/annotations", json={"anchor_id": first, "comment": "뒤에 쓴 메모"})
    client.post("/api/v1/annotations", json={"anchor_id": first, "comment": "", "color": "c1"})
    body = {
        "papers": [{"version_id": version_id, "anchor_ids": [second, first]}],
        "proposals": [{"version_id": version_id, "title": "  핵심 정의  ", "content_markdown": "# 핵심\n\n내용\n", "anchor_ids": [first]}],
    }

    response = create(client, body)

    assert response.status_code == 201, response.text
    bundle = response.json()
    [folder] = bundles_in(outbox)
    assert folder.name == bundle["directory"] == f"bundle_{bundle['bundle_id']}"
    manifest = check_evidence_bundle(folder)
    assert manifest["schema_version"] == bundle["schema_version"] == "paperloom-bundle.v1.1"  # 기본으로 고른 위치가 있는 쪽의 추출문을 싣는다
    assert bundle["manifest_sha256"] == hashlib.sha256((folder / "manifest.json").read_bytes()).hexdigest()
    assert bundle["status"] == "written"
    assert bundle["file_count"] == 6 and bundle["counts"] == {"anchors": 2, "proposals": 1, "answers": 0, "assets": 0, "texts": 1, "artifacts": 0}
    assert bundle["papers"] == [{"paper_id": paper_id, "version_id": version_id, "title": paper["title"]}]
    assert bundle["size_bytes"] == sum(path.stat().st_size for path in folder.rglob("*") if path.is_file())

    [source] = read_json(folder, "sources.json")
    assert (source["sha256"], source["page_count"]) == (paper["current_version"]["sha256"], paper["current_version"]["page_count"])
    assert source["reader_url"] == f"{BASE_URL}/reader/{paper_id}?version={version_id}"
    anchors = read_json(folder, "anchors.json")
    assert [item["anchor_id"] for item in anchors] == [first, second]  # 읽는 순서
    assert anchors[0]["comment"] == "먼저 쓴 메모\n\n뒤에 쓴 메모" and anchors[1]["comment"] is None
    assert anchors[0]["reader_url"] == f"{BASE_URL}/reader/{paper_id}?version={version_id}&anchor={first}"
    assert (anchors[0]["quads"], anchors[0]["quote"], anchors[0]["prefix"], anchors[0]["suffix"]) == ([QUAD], "첫째", "앞", "뒤")
    [proposal] = [read_json(folder, path.relative_to(folder).as_posix()) for path in (folder / "proposals").iterdir()]
    assert proposal["title"] == "핵심 정의" and proposal["anchor_refs"] == ["anc_1"]
    assert (folder / proposal["content_file"]).read_text(encoding="utf-8") == "# 핵심\n\n내용\n"


def test_anchor_carries_its_section_and_printed_page(app, client, paper, outbox):
    blocks = client.get(f"/api/v1/versions/{paper['version_id']}/pages/1").json()["blocks"]
    block = next(item for item in blocks if item["text"].startswith("The right column"))
    u0, v0, u1, v1 = block["regions"][0]
    anchor_id = make_anchor(client, paper["version_id"], quad=[u0, v0, u1, v0, u1, v1, u0, v1], quote_text="The right column")
    packet = client.post("/api/v1/context-packets", json={"intent": "ask", "question": "q", "anchors": [{"anchor_id": anchor_id}]}).json()

    create(client, {"papers": [{"version_id": paper["version_id"], "anchor_ids": [anchor_id]}]})

    [folder] = bundles_in(outbox)
    [anchor] = read_json(folder, "anchors.json")
    assert anchor["section"] == packet["evidence"][0]["section"]
    pages = client.get(f"/api/v1/versions/{paper['version_id']}/pages").json()["pages"]
    assert anchor["page_label"] == pages[1]["page_label"]


def test_comments_are_left_out_when_not_chosen(client, paper, outbox):
    anchor_id = make_anchor(client, paper["version_id"])
    client.post("/api/v1/annotations", json={"anchor_id": anchor_id, "comment": "메모"})

    create(client, {"papers": [{"version_id": paper["version_id"], "anchor_ids": [anchor_id], "include_comments": False}]})

    [folder] = bundles_in(outbox)
    assert read_json(folder, "anchors.json")[0]["comment"] is None


def test_unchosen_anchors_and_memos_stay_out(client, paper, outbox):
    chosen, other = make_anchor(client, paper["version_id"], quote_text="고른 글"), make_anchor(client, paper["version_id"], quote_text="안 고른 글")
    client.post("/api/v1/annotations", json={"anchor_id": other, "comment": "안 고른 메모"})

    create(client, {"papers": [{"version_id": paper["version_id"], "anchor_ids": [chosen]}]})

    [folder] = bundles_in(outbox)
    text = "".join(path.read_text(encoding="utf-8") for path in folder.rglob("*.json"))
    assert "안 고른" not in text


def test_a_paper_alone_exports_without_anchors_or_proposals(client, paper, outbox, check_evidence_bundle):
    response = create(client, {"papers": [{"version_id": paper["version_id"]}]})

    assert response.status_code == 201
    [folder] = bundles_in(outbox)
    check_evidence_bundle(folder)
    assert read_json(folder, "anchors.json") == []
    assert sorted(path.name for path in folder.iterdir()) == ["anchors.json", "manifest.json", "sources.json"]


def test_several_papers_keep_their_own_anchors_and_proposals(app, client, paper, outbox, check_evidence_bundle):
    other = upload(client, "text-parts.pdf")
    extract(app)
    first, second = make_anchor(client, paper["version_id"]), make_anchor(client, other["version_id"], 0)

    create(client, {
        "papers": [{"version_id": paper["version_id"], "anchor_ids": [first]}, {"version_id": other["version_id"], "anchor_ids": [second]}],
        "proposals": [{"version_id": other["version_id"], "title": "둘째 논문", "content_markdown": "본문", "anchor_ids": [second]}],
    })

    [folder] = bundles_in(outbox)
    check_evidence_bundle(folder)
    assert [item["source_ref"] for item in read_json(folder, "sources.json")] == ["src_1", "src_2"]
    assert [(item["anchor_id"], item["source_ref"]) for item in read_json(folder, "anchors.json")] == [(first, "src_1"), (second, "src_2")]
    [proposal] = (folder / "proposals").iterdir()
    written = json.loads(proposal.read_text(encoding="utf-8"))
    assert written["source_refs"] == ["src_2"] and written["anchor_refs"] == ["anc_2"]


def test_preview_writes_nothing_and_matches_what_export_writes(client, paper, outbox):
    anchor_id = make_anchor(client, paper["version_id"])
    body = {
        "papers": [{"version_id": paper["version_id"], "anchor_ids": [anchor_id]}],
        "proposals": [{"version_id": paper["version_id"], "title": "제목", "content_markdown": "본문", "anchor_ids": [anchor_id]}],
    }

    response = preview(client, body)

    assert response.status_code == 200, response.text
    shown = response.json()
    assert bundles_in(outbox) == []
    assert client.get("/api/v1/evidence-bundles").json()["bundles"] == []
    assert shown["files"][0]["path"] == "manifest.json"
    assert [item["kind"] for item in shown["files"]] == ["manifest", "sources", "anchors", "proposal", "artifact", "text"]
    assert shown["limits"] == {"max_files": 64, "max_file_bytes": 8 * 1024 * 1024, "max_total_bytes": 32 * 1024 * 1024}
    assert (shown["file_count"], shown["schema_version"]) == (6, "paperloom-bundle.v1.1")
    assert shown["total_bytes"] == sum(item["size_bytes"] for item in shown["files"])
    assert shown["auto_added_anchors"] == [] and shown["warnings"] == []

    written = create(client, body).json()
    detail = client.get(f"/api/v1/evidence-bundles/{written['bundle_id']}").json()
    sizes = {item["path"].split("/")[0]: item["size_bytes"] for item in detail["files"]}
    assert {item["path"].split("/")[0]: item["size_bytes"] for item in shown["files"]} == sizes


def test_create_uses_values_changed_after_the_preview(client, paper, outbox):
    anchor_id = make_anchor(client, paper["version_id"])
    note = client.post("/api/v1/annotations", json={"anchor_id": anchor_id, "comment": "전"}).json()
    body = {"papers": [{"version_id": paper["version_id"], "anchor_ids": [anchor_id]}]}
    preview(client, body)
    client.patch(f"/api/v1/annotations/{note['annotation_id']}", json={"revision": note["revision"], "comment": "후"})

    create(client, body)

    [folder] = bundles_in(outbox)
    assert read_json(folder, "anchors.json")[0]["comment"] == "후"


def test_same_key_and_body_returns_the_first_answer_and_writes_once(client, paper, outbox):
    """AC-02."""
    body = {"papers": [{"version_id": paper["version_id"]}]}

    first = create(client, body, "same-key")
    again = create(client, body, "same-key")

    assert (first.status_code, again.status_code) == (201, 200)
    assert again.json() == first.json()
    assert len(bundles_in(outbox)) == 1
    other = create(client, {"papers": [{"version_id": paper["version_id"], "include_comments": False}]}, "same-key")
    assert (other.status_code, other.json()["code"]) == (422, "IDEMPOTENCY_KEY_REUSED")


def test_the_key_is_required(client, paper, outbox):
    response = client.post("/api/v1/evidence-bundles", json={"papers": [{"version_id": paper["version_id"]}]})

    assert (response.status_code, response.json()["code"]) == (422, "INVALID_REQUEST")
    assert bundles_in(outbox) == []


def test_the_same_content_exported_again_gets_a_new_bundle(client, paper, outbox):
    body = {"papers": [{"version_id": paper["version_id"]}]}

    assert create(client, body).json()["bundle_id"] != create(client, body).json()["bundle_id"]
    assert len(bundles_in(outbox)) == 2


def test_the_limit_warns_in_preview_and_refuses_on_create(client, paper, outbox, monkeypatch):
    """AC-03."""
    monkeypatch.setattr(builder, "MAX_TOTAL_BYTES", 500)
    body = {"papers": [{"version_id": paper["version_id"]}], "proposals": [{"version_id": paper["version_id"], "title": "큰 제안", "content_markdown": "가" * 1000}]}

    shown = preview(client, body)
    refused = create(client, body)

    assert shown.status_code == 200 and "over_limit" in [item["code"] for item in shown.json()["warnings"]]
    assert (refused.status_code, refused.json()["code"], refused.json()["retryable"]) == (413, "BUNDLE_TOO_LARGE", False)
    details = refused.json()["details"]
    assert details["file_count"] == 5 and details["total_bytes"] > 1000 and details["largest_path"].startswith("artifacts/proposal-")
    assert bundles_in(outbox) == []
    [record] = client.get("/api/v1/evidence-bundles").json()["bundles"]
    assert record["status"] == "failed"
    assert client.get(f"/api/v1/evidence-bundles/{record['bundle_id']}").json()["error_code"] == "BUNDLE_TOO_LARGE"


def test_near_limit_warns_before_the_limit(client, paper, monkeypatch):
    body = {"papers": [{"version_id": paper["version_id"]}], "proposals": [{"version_id": paper["version_id"], "title": "제안", "content_markdown": "a" * 900}]}
    total = preview(client, body).json()["total_bytes"]
    monkeypatch.setattr(builder, "MAX_TOTAL_BYTES", int(total / 0.9))

    codes = [item["code"] for item in preview(client, body).json()["warnings"]]

    assert codes == ["near_limit"]


def test_images_are_not_drawn_when_the_file_limit_is_already_lost(app, client, paper, monkeypatch):
    """영역이 많으면 그리기 전에 알 수 있다. 미리보기가 쓸모없는 이미지를 수십 장 그리느라 멈추면 안 된다."""

    def never(*_):
        raise AssertionError("그리지 않아야 한다")

    monkeypatch.setattr(reading_service, "render_region", never)
    regions = [make_anchor(client, paper["version_id"], quote_text="", kind="figure") for _ in range(70)]
    choice = {"version_id": paper["version_id"], "anchor_ids": regions, "include_region_images": True, "text": {"mode": "none"}}

    response = preview(client, {"papers": [choice]})

    assert "over_limit" in [item["code"] for item in response.json()["warnings"]]
    assert response.json()["file_count"] == 73


@pytest.mark.parametrize("config", ["없음", "없는 폴더"])
def test_export_is_blocked_without_an_outbox_but_the_server_runs(tmp_path, config):
    """AC-04."""
    path = None if config == "없음" else tmp_path / config
    app = create_app(Settings(app=AppSettings(mode="test", data_dir=tmp_path / "data"), wiki=WikiSettings(enabled=True, outbox_path=path)))
    client = TestClient(app, base_url=BASE_URL)
    uploaded = upload(client)
    body = {"papers": [{"version_id": uploaded["version_id"]}]}

    health = client.get("/api/v1/health")

    assert (health.status_code, health.json()["status"], health.json()["wiki_outbox"]["status"]) == (200, "ok", "not_configured")
    for response in (preview(client, body), create(client, body)):
        assert (response.status_code, response.json()["code"], response.json()["retryable"]) == (503, "OUTBOX_UNAVAILABLE", True)


def test_health_reports_a_writable_outbox(client, outbox):
    assert client.get("/api/v1/health").json()["wiki_outbox"] == {"status": "ready", "path": Outbox(outbox).shown_path()}


def test_unfinished_text_warns_in_preview_and_refuses_on_create(app, client, outbox):
    """AC-05: 추출 전 판본의 추출문."""
    uploaded = upload(client)
    body = {"papers": [{"version_id": uploaded["version_id"], "text": {"mode": "ranges", "ranges": [{"from": 0, "to": 1}]}}]}

    shown = preview(client, body)
    refused = create(client, body)

    assert shown.status_code == 200
    assert shown.json()["warnings"] == [{"code": "pages_not_extracted", "detail": f"{uploaded['version_id']}: 1, 2"}]
    assert (refused.status_code, refused.json()["code"], refused.json()["retryable"]) == (409, "TEXT_NOT_READY", True)
    assert bundles_in(outbox) == []


def test_all_text_carries_every_page_with_flags_and_hash(client, paper, outbox, check_evidence_bundle):
    """AC-06."""
    version_id = paper["version_id"]
    response = create(client, {"papers": [{"version_id": version_id, "text": {"mode": "all"}}]})

    assert response.status_code == 201, response.text
    assert response.json()["schema_version"] == "paperloom-bundle.v1.1" and response.json()["counts"]["texts"] == 1
    [folder] = bundles_in(outbox)
    manifest = check_evidence_bundle(folder)
    assert manifest["features"] == ["texts"]
    document = read_json(folder, f"texts/{version_id}.json")
    assert document["schema_version"] == "paperloom-text.v1"
    assert (document["source_ref"], document["version_id"], document["sha256"]) == ("src_1", version_id, paper["current_version"]["sha256"])
    assert document["extractor"]["name"] == "paperloom-parse"
    assert document["extractor"]["version"] and document["extractor"]["parse_run_id"] and document["extractor"]["finished_at"]
    pages = client.get(f"/api/v1/versions/{version_id}/pages").json()["pages"]
    assert [page["page_index"] for page in document["pages"]] == [page["page_index"] for page in pages]
    assert [page["flags"] for page in document["pages"]] == [page["flags"] for page in pages]
    assert [page["text_status"] for page in document["pages"]] == [page["text_status"] for page in pages]
    blocks = client.get(f"/api/v1/versions/{version_id}/pages/1").json()["blocks"]
    written = document["pages"][1]["blocks"]
    assert [(item["block_id"], item["text"]) for item in written] == [(item["block_id"], item["text"]) for item in blocks]
    assert [item["order"] for item in written] == list(range(1, len(blocks) + 1))
    canonical = json.dumps(document["pages"], sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
    assert document["text_sha256"] == hashlib.sha256(canonical).hexdigest()


def test_text_marks_what_is_not_body_and_keeps_it(app, client, outbox):
    uploaded = upload(client, "text-parts.pdf")
    extract(app)

    create(client, {"papers": [{"version_id": uploaded["version_id"], "text": {"mode": "all"}}]})

    [folder] = bundles_in(outbox)
    kinds = {block["kind"] for page in read_json(folder, f"texts/{uploaded['version_id']}.json")["pages"] for block in page["blocks"]}
    assert {"body", "page_header", "page_footer", "math", "in_table", "caption"} <= kinds


def test_text_of_anchor_pages_follows_the_anchors_in_the_bundle(client, paper, outbox):
    first, second = make_anchor(client, paper["version_id"], 2), make_anchor(client, paper["version_id"], 1)
    version_id = paper["version_id"]

    create(client, {
        "papers": [{"version_id": version_id, "anchor_ids": [first], "text": {"mode": "anchor_pages"}}],
        "proposals": [{"version_id": version_id, "title": "제목", "content_markdown": "본문", "anchor_ids": [second]}],
    })

    [folder] = bundles_in(outbox)
    assert [page["page_index"] for page in read_json(folder, f"texts/{version_id}.json")["pages"]] == [1, 2]


def test_text_ranges_count_from_zero_and_include_both_ends(client, paper, outbox):
    version_id = paper["version_id"]

    create(client, {"papers": [{"version_id": version_id, "text": {"mode": "ranges", "ranges": [{"from": 1, "to": 2}, {"from": 2, "to": 2}]}}]})

    [folder] = bundles_in(outbox)
    assert [page["page_index"] for page in read_json(folder, f"texts/{version_id}.json")["pages"]] == [1, 2]


def test_text_of_anchor_pages_is_carried_by_default(client, paper, outbox):
    """요구사항 Q3: LLM Wiki 수신기가 texts/를 받으므로 기본은 고른 위치가 있는 쪽이다."""
    version_id = paper["version_id"]
    anchor_id = make_anchor(client, version_id, 1)

    bundle = create(client, {"papers": [{"version_id": version_id, "anchor_ids": [anchor_id]}]}).json()

    assert (bundle["schema_version"], bundle["counts"]["texts"]) == ("paperloom-bundle.v1.1", 1)
    [folder] = bundles_in(outbox)
    assert [page["page_index"] for page in read_json(folder, f"texts/{version_id}.json")["pages"]] == [1]


def test_ranges_are_ignored_unless_the_mode_asks_for_them(client, paper, outbox):
    body = {"papers": [{"version_id": paper["version_id"], "text": {"mode": "none", "ranges": [{"from": 0, "to": 1}]}}]}

    assert create(client, body).json()["counts"]["texts"] == 0


def test_a_page_that_failed_extraction_is_named_and_carried_without_text(tmp_path, client, paper, outbox):
    version_id = paper["version_id"]
    with closing(connect(tmp_path / "data" / "paperloom.sqlite3")) as connection, connection:
        connection.execute("UPDATE pages SET text_status = 'unknown', flags_json = ? WHERE version_id = ? AND page_index = 1", ('["extract_failed"]', version_id))
        connection.execute("DELETE FROM text_blocks WHERE version_id = ? AND page_index = 1", (version_id,))
    body = {"papers": [{"version_id": version_id, "text": {"mode": "ranges", "ranges": [{"from": 0, "to": 1}]}}]}

    assert preview(client, body).json()["warnings"] == [{"code": "pages_not_extracted", "detail": f"{version_id}: 2"}]
    assert create(client, body).status_code == 201  # 고른 쪽 가운데 하나는 추출됐다
    [folder] = bundles_in(outbox)
    failed = read_json(folder, f"texts/{version_id}.json")["pages"][1]
    assert (failed["text_status"], failed["flags"], failed["blocks"]) == ("unknown", ["extract_failed"], [])


def test_anchor_pages_with_no_anchor_carry_no_text(client, paper, outbox):
    bundle = create(client, {"papers": [{"version_id": paper["version_id"], "text": {"mode": "anchor_pages"}}]}).json()

    assert (bundle["schema_version"], bundle["counts"]["texts"]) == ("paperloom-bundle.v1", 0)


def test_ranges_need_a_range(client, paper):
    response = preview(client, {"papers": [{"version_id": paper["version_id"], "text": {"mode": "ranges"}}]})

    assert (response.status_code, response.json()["code"]) == (422, "INVALID_REQUEST")


@pytest.mark.parametrize("bad", [{"from": 2, "to": 1}, {"from": 0, "to": 999}, {"from": -1, "to": 0}])
def test_bad_ranges_are_refused(client, paper, bad):
    response = preview(client, {"papers": [{"version_id": paper["version_id"], "text": {"mode": "ranges", "ranges": [bad]}}]})

    assert errors_of(response) == ["invalid_range"]


def test_region_images_are_written_when_chosen(app, client, outbox, check_evidence_bundle, decode_png):
    uploaded = upload(client, "figures.pdf")
    extract(app)
    anchor_id = make_anchor(client, uploaded["version_id"], 0, [0.1, 0.1, 0.5, 0.1, 0.5, 0.4, 0.1, 0.4], "", "figure")
    text_anchor = make_anchor(client, uploaded["version_id"], 0)

    bundle = create(client, {"papers": [{"version_id": uploaded["version_id"], "anchor_ids": [anchor_id, text_anchor], "include_region_images": True}]}).json()

    [folder] = bundles_in(outbox)
    check_evidence_bundle(folder)
    assert bundle["counts"]["assets"] == 1
    entries = {item["anchor_id"]: item for item in read_json(folder, "anchors.json")}
    assert entries[anchor_id]["asset"] == f"assets/{anchor_id}.png" and entries[text_anchor]["asset"] is None
    assert decode_png((folder / entries[anchor_id]["asset"]).read_bytes())[0] > 0


def test_a_region_without_an_image_is_named(client, paper, outbox):
    anchor_id = make_anchor(client, paper["version_id"], quote_text="", kind="figure")
    body = {"papers": [{"version_id": paper["version_id"], "anchor_ids": [anchor_id]}]}

    warnings = preview(client, body).json()["warnings"]

    assert warnings == [{"code": "region_without_image", "detail": f"{paper['version_id']}: 1개"}]


def test_a_region_that_cannot_be_drawn_does_not_stop_the_export(client, paper, outbox, monkeypatch):
    def fail(*_):
        raise RenderFailed("RENDER_FAILED")

    monkeypatch.setattr(reading_service, "render_region", fail)
    anchor_id = make_anchor(client, paper["version_id"], quote_text="", kind="table")
    body = {"papers": [{"version_id": paper["version_id"], "anchor_ids": [anchor_id], "include_region_images": True}]}

    assert [item["code"] for item in preview(client, body).json()["warnings"]] == ["region_without_image"]
    assert create(client, body).status_code == 201
    [folder] = bundles_in(outbox)
    assert read_json(folder, "anchors.json")[0]["asset"] is None


def test_an_answer_is_written_as_is_with_its_cited_anchor_added(client, paper, outbox, check_evidence_bundle):
    version_id = paper["version_id"]
    cited = make_anchor(client, version_id, quote_text="답변이 인용한 글")
    answer = make_answer(client, [cited], "<b>본문</b> 그대로 [근거 1], 없는 근거 [근거 99].")
    body = {"papers": [{"version_id": version_id}], "answer_ids": [answer["answer_id"]]}

    shown = preview(client, body).json()

    assert shown["auto_added_anchors"] == [{"version_id": version_id, "anchor_id": cited, "reason": "cited_by_answer"}]
    assert shown["warnings"] == [{"code": "unresolved_answer_citation", "detail": f"{answer['answer_id']}: 근거 99"}]
    bundle = create(client, body).json()
    assert bundle["counts"]["anchors"] == 1 and bundle["counts"]["answers"] == 1
    [folder] = bundles_in(outbox)
    check_evidence_bundle(folder)
    text = (folder / f"artifacts/answer-{answer['answer_id']}.md").read_text(encoding="utf-8")
    assert f"> Paperloom 답변 · answer_id {answer['answer_id']} · origin claude_code · review unreviewed · {answer['created_at']}\n" in text
    assert "> 질문: 차례의 질문\n" in text
    assert "> 근거: [근거 1] = anc_1 (쪽 2) · 풀지 못함: [근거 99]\n" in text
    assert text.endswith("\n\n<b>본문</b> 그대로 [근거 1], 없는 근거 [근거 99].\n")


def test_a_citation_of_the_paper_text_has_no_anchor_and_stays_unresolved_with_its_page(client, paper, outbox):
    """대화 범위 '논문 본문'의 근거는 Anchor가 없다(anchor_id가 빈 글)."""
    version_id = paper["version_id"]
    answer = make_answer(client, [], "본문 근거 [근거 2].", scope="paper", version_id=version_id)
    [citation] = answer["citations"]
    assert citation["anchor_id"] == ""
    body = {"papers": [{"version_id": version_id}], "answer_ids": [answer["answer_id"]]}

    shown = preview(client, body).json()

    assert shown["auto_added_anchors"] == []
    assert shown["warnings"] == [{"code": "unresolved_answer_citation", "detail": f"{answer['answer_id']}: 근거 2"}]
    create(client, body)
    [folder] = bundles_in(outbox)
    text = (folder / f"artifacts/answer-{answer['answer_id']}.md").read_text(encoding="utf-8")
    assert f"> 근거: 풀지 못함: [근거 2] (쪽 {citation['page_index'] + 1})\n" in text


def test_discarded_and_unknown_answers_are_not_found(client, paper):
    anchor_id = make_anchor(client, paper["version_id"])
    answer = make_answer(client, [anchor_id], "답")
    client.delete(f"/api/v1/answers/{answer['answer_id']}")

    for answer_id in (answer["answer_id"], "no-such"):
        response = preview(client, {"papers": [{"version_id": paper["version_id"]}], "answer_ids": [answer_id]})
        assert (response.status_code, response.json()["code"], response.json()["details"]) == (404, "NOT_FOUND", {"field": "answer_ids[0]"})


def test_an_answer_needs_its_paper_in_the_bundle(app, client, paper):
    other = upload(client, "text-parts.pdf")
    extract(app)
    answer = make_answer(client, [make_anchor(client, paper["version_id"])], "답")

    response = preview(client, {"papers": [{"version_id": other["version_id"]}], "answer_ids": [answer["answer_id"]]})

    assert errors_of(response) == ["answer_version_not_selected"]


def test_an_artifact_is_written_alone_without_its_answer(client, paper, outbox, check_evidence_bundle):
    version_id = paper["version_id"]
    answer = make_answer(client, [make_anchor(client, version_id)], ARTIFACTS_ANSWER)
    answer_id = answer["answer_id"]
    body = {"papers": [{"version_id": version_id}], "artifacts": [{"answer_id": answer_id, "index": 1}, {"answer_id": answer_id, "index": 0}]}

    shown = preview(client, body).json()

    assert sorted(file["path"] for file in shown["files"] if file["kind"] == "artifact") == [f"artifacts/artifact-{answer_id}-1.md", f"artifacts/artifact-{answer_id}-2.md"]
    assert shown["auto_added_anchors"] == []  # 답변 글을 넣지 않으므로 그 근거도 더하지 않는다
    bundle = create(client, body).json()
    assert (bundle["counts"]["artifacts"], bundle["counts"]["answers"], bundle["counts"]["anchors"]) == (2, 0, 0)
    [folder] = bundles_in(outbox)
    check_evidence_bundle(folder)
    assert not (folder / f"artifacts/answer-{answer_id}.md").exists()
    page = (folder / f"artifacts/artifact-{answer_id}-2.md").read_text(encoding="utf-8")
    assert page.startswith(
        f"> Paperloom 아티팩트 · answer_id {answer_id} · 답변의 2번째 · type html · review unreviewed · {answer['created_at']}\n"
        "> 제목: 표 페이지\n> 질문: 차례의 질문\n\n````html\n<!doctype html>\n"
    )
    assert page.endswith("\n```\n안의 울타리\n```\n</pre>\n````\n")  # 안의 울타리보다 긴 울타리로 감싼다
    document = (folder / f"artifacts/artifact-{answer_id}-1.md").read_text(encoding="utf-8")
    assert document.endswith("> 제목: 요약 문서\n> 질문: 차례의 질문\n\n# 요약\n\n본문\n")  # 문서는 감싸지 않는다


def test_an_artifact_needs_its_answer_its_place_and_its_paper(app, client, paper):
    answer = make_answer(client, [make_anchor(client, paper["version_id"])], SVG_ANSWER)

    def chosen(choice: dict, version_id: str = paper["version_id"]):
        return preview(client, {"papers": [{"version_id": version_id}], "artifacts": [choice]})

    for choice, field in (({"answer_id": "no-such", "index": 0}, "artifacts[0].answer_id"), ({"answer_id": answer["answer_id"], "index": 1}, "artifacts[0].index")):
        response = chosen(choice)
        assert (response.status_code, response.json()["code"], response.json()["details"]) == (404, "NOT_FOUND", {"field": field})
    other = upload(client, "text-parts.pdf")
    extract(app)
    assert errors_of(chosen({"answer_id": answer["answer_id"], "index": 0}, other["version_id"])) == ["artifact_version_not_selected"]


def test_repeated_ids_count_once(client, paper, outbox, check_evidence_bundle):
    anchor_id = make_anchor(client, paper["version_id"])
    answer = make_answer(client, [anchor_id], "답 [근거 1]")
    artifact_answer = make_answer(client, [anchor_id], SVG_ANSWER)

    bundle = create(client, {
        "papers": [{"version_id": paper["version_id"], "anchor_ids": [anchor_id, anchor_id]}],
        "answer_ids": [answer["answer_id"], answer["answer_id"]],
        "artifacts": [{"answer_id": artifact_answer["answer_id"], "index": 0}] * 2,
        "proposals": [{"version_id": paper["version_id"], "title": "제목", "content_markdown": "본문", "anchor_ids": [anchor_id, anchor_id]}],
    }).json()

    assert bundle["counts"] == {"anchors": 1, "proposals": 1, "answers": 1, "assets": 0, "texts": 1, "artifacts": 1}
    [folder] = bundles_in(outbox)
    check_evidence_bundle(folder)
    [path] = (folder / "proposals").iterdir()
    assert json.loads(path.read_text(encoding="utf-8"))["anchor_refs"] == ["anc_1"]


def test_a_proposal_anchor_joins_the_chosen_anchors(client, paper, outbox):
    anchor_id = make_anchor(client, paper["version_id"])
    body = {
        "papers": [{"version_id": paper["version_id"]}],
        "proposals": [{"version_id": paper["version_id"], "title": "제목", "content_markdown": "본문", "anchor_ids": [anchor_id]}],
    }

    assert preview(client, body).json()["auto_added_anchors"] == [{"version_id": paper["version_id"], "anchor_id": anchor_id, "reason": "linked_by_proposal"}]
    create(client, body)
    [folder] = bundles_in(outbox)
    assert [item["anchor_id"] for item in read_json(folder, "anchors.json")] == [anchor_id]


def test_mismatched_choices_are_refused_with_reasons_not_values(app, client, paper, outbox):
    other = upload(client, "text-parts.pdf")
    extract(app)
    mine, theirs = make_anchor(client, paper["version_id"]), make_anchor(client, other["version_id"], 0)
    secret = "비밀 제목"

    response = create(client, {
        "papers": [{"version_id": paper["version_id"], "anchor_ids": [mine, theirs]}, {"version_id": paper["version_id"]}],
        "proposals": [
            {"version_id": other["version_id"], "title": secret, "content_markdown": "본문"},
            {"version_id": paper["version_id"], "title": secret, "content_markdown": "본문", "anchor_ids": [theirs]},
        ],
    })

    assert sorted(errors_of(response)) == ["anchor_other_version", "anchor_other_version", "duplicate_version", "proposal_version_not_selected"]
    assert secret not in response.text
    assert bundles_in(outbox) == [] and client.get("/api/v1/evidence-bundles").json()["bundles"] == []  # 입력 오류는 기록하지 않는다


@pytest.mark.parametrize(
    ("change", "field"),
    [
        ({"papers": [{"version_id": "no-such"}]}, "papers[0].version_id"),
        ({"anchor_ids": ["no-such"]}, "papers[0].anchor_ids[0]"),
        ({"proposal_anchor_ids": ["no-such"]}, "proposals[0].anchor_ids[0]"),
    ],
)
def test_unknown_ids_are_not_found_and_name_the_field(client, paper, change, field):
    choice = {"version_id": paper["version_id"], "anchor_ids": change.get("anchor_ids", [])}
    body = {"papers": change.get("papers", [choice])}
    if "proposal_anchor_ids" in change:
        body["proposals"] = [{"version_id": paper["version_id"], "title": "제목", "content_markdown": "본문", "anchor_ids": change["proposal_anchor_ids"]}]

    response = preview(client, body)

    assert (response.status_code, response.json()["code"], response.json()["details"]) == (404, "NOT_FOUND", {"field": field})


@pytest.mark.parametrize(
    "body",
    [
        {"papers": []},
        {"papers": [{"version_id": "v"}] * 21},
        {"papers": [{"version_id": "v", "anchor_ids": ["a"] * 201}]},
        {"papers": [{"version_id": "v", "unknown": 1}]},
        {"papers": [{"version_id": "v", "text": {"mode": "other"}}]},
        {"papers": [{"version_id": "v", "text": {"mode": "ranges", "ranges": [{"from": 0, "to": 0}] * 21}}]},
        {"papers": [{"version_id": "v"}], "answer_ids": ["a"] * 21},
        {"papers": [{"version_id": "v"}], "artifacts": [{"answer_id": "a", "index": 0}] * 21},
        {"papers": [{"version_id": "v"}], "artifacts": [{"answer_id": "a", "index": -1}]},
        {"papers": [{"version_id": "v"}], "artifacts": [{"answer_id": "a", "index": "0"}]},
        {"papers": [{"version_id": "v"}], "proposals": [{"version_id": "v", "title": "   ", "content_markdown": "본문"}]},
        {"papers": [{"version_id": "v"}], "proposals": [{"version_id": "v", "title": "제목", "content_markdown": "  \n "}]},
        {"papers": [{"version_id": "v"}], "proposals": [{"version_id": "v", "title": "가" * 501, "content_markdown": "본문"}]},
        {"papers": [{"version_id": "v"}], "proposals": [{"version_id": "v", "title": "제목", "content_markdown": "가" * 200_001}]},
        {"papers": [{"version_id": "v"}], "proposals": [{"version_id": "v", "title": "제목", "content_markdown": "본문"}] * 21},
    ],
)
def test_malformed_bodies_are_refused(client, body):
    response = preview(client, body)

    assert (response.status_code, response.json()["code"]) == (422, "INVALID_REQUEST")


def test_a_write_failure_leaves_nothing_and_is_recorded(client, paper, outbox, monkeypatch):
    def fail(*_):
        raise OSError("디스크가 찼습니다")

    body = {"papers": [{"version_id": paper["version_id"]}]}
    monkeypatch.setattr("paperloom.evidence_bundles.outbox.os.rename", fail)

    response = create(client, body, "retry-key")

    assert (response.status_code, response.json()["code"], response.json()["retryable"]) == (500, "BUNDLE_WRITE_FAILED", True)
    assert bundles_in(outbox) == []
    [record] = client.get("/api/v1/evidence-bundles").json()["bundles"]
    assert (record["status"], record["file_count"], record["present_in_outbox"]) == ("failed", 0, False)
    assert client.get(f"/api/v1/evidence-bundles/{record['bundle_id']}").json()["error_code"] == "BUNDLE_WRITE_FAILED"
    monkeypatch.undo()
    assert create(client, body, "retry-key").status_code == 201  # 실패한 키로 다시 시도할 수 있다


def test_history_lists_recent_first_with_details(client, paper, outbox):
    body = {"papers": [{"version_id": paper["version_id"]}]}
    first, second = create(client, body).json(), create(client, body).json()

    listed = client.get("/api/v1/evidence-bundles").json()["bundles"]
    assert [item["bundle_id"] for item in listed] == [second["bundle_id"], first["bundle_id"]]
    assert listed[0] == {
        "bundle_id": second["bundle_id"], "status": "written", "created_at": second["created_at"], "file_count": 3,
        "size_bytes": second["size_bytes"], "papers": second["papers"], "present_in_outbox": True,
    }
    assert len(client.get("/api/v1/evidence-bundles", params={"limit": 1}).json()["bundles"]) == 1
    assert client.get("/api/v1/evidence-bundles", params={"limit": 0}).status_code == 422
    assert client.get("/api/v1/evidence-bundles", params={"limit": 201}).status_code == 422

    detail = client.get(f"/api/v1/evidence-bundles/{second['bundle_id']}").json()
    assert {key: detail[key] for key in second} == second
    assert detail["error_code"] is None and detail["present_in_outbox"] is True
    folder = outbox / second["directory"]
    assert {item["path"]: item["size_bytes"] for item in detail["files"]} == {path.name: path.stat().st_size for path in folder.iterdir()}
    assert {item["path"]: item["sha256"] for item in detail["files"]}["manifest.json"] == second["manifest_sha256"]


def test_history_notices_a_bundle_the_user_removed(client, paper, outbox):
    bundle = create(client, {"papers": [{"version_id": paper["version_id"]}]}).json()
    for path in (outbox / bundle["directory"]).iterdir():
        path.unlink()
    (outbox / bundle["directory"]).rmdir()

    assert client.get(f"/api/v1/evidence-bundles/{bundle['bundle_id']}").json()["present_in_outbox"] is False
    assert client.get("/api/v1/evidence-bundles").json()["bundles"][0]["present_in_outbox"] is False


def test_history_survives_deleting_the_paper(client, paper, outbox):
    bundle = create(client, {"papers": [{"version_id": paper["version_id"]}]}).json()

    assert client.delete(f"/api/v1/papers/{paper['paper_id']}").status_code in (200, 204)

    assert client.get(f"/api/v1/evidence-bundles/{bundle['bundle_id']}").json()["papers"] == bundle["papers"]
    assert (outbox / bundle["directory"]).is_dir()  # 지우기는 사용자 몫이다


def test_unknown_bundle_is_not_found(client):
    response = client.get("/api/v1/evidence-bundles/no-such")

    assert (response.status_code, response.json()["code"], response.json()["details"]) == (404, "NOT_FOUND", {"field": "bundle_id"})


def test_starting_up_discards_what_an_interrupted_write_left(tmp_path, outbox):
    """AC-09."""
    leftover = outbox / ".tmp-0f6c2c1e-7a4b-4c8e-9d1a-2b3c4d5e6f70"
    leftover.mkdir()
    (leftover / "sources.json").write_bytes(b"[]")

    create_app(Settings(app=AppSettings(mode="test", data_dir=tmp_path / "data"), wiki=WikiSettings(enabled=True, outbox_path=outbox)))

    assert bundles_in(outbox) == []


def test_the_bundle_never_holds_the_source_pdf(app, client, outbox):
    """AC-08."""
    uploaded = upload(client, "figures.pdf")
    extract(app)
    anchor_id = make_anchor(client, uploaded["version_id"], 0, quote_text="", kind="figure")

    create(client, {"papers": [{"version_id": uploaded["version_id"], "anchor_ids": [anchor_id], "include_region_images": True, "text": {"mode": "all"}}]})

    [folder] = bundles_in(outbox)
    pdf = (FIXTURE_DIR / "figures.pdf").read_bytes()
    assert all(path.suffix != ".pdf" and path.read_bytes() != pdf for path in folder.rglob("*") if path.is_file())


def test_all_anchors_of_a_version_are_listed_in_reading_order(client, paper):
    version_id = paper["version_id"]
    later, earlier = make_anchor(client, version_id, 2), make_anchor(client, version_id, 1)

    listed = client.get(f"/api/v1/versions/{version_id}/anchors").json()["anchors"]

    assert [item["anchor_id"] for item in listed] == [earlier, later]
    assert client.get("/api/v1/versions/no-such/anchors").status_code == 404


def test_the_web_app_answers_on_the_bundle_history_address(tmp_path):
    web = tmp_path / "web"
    web.mkdir()
    (web / "index.html").write_text("<!doctype html>", encoding="utf-8")
    client = TestClient(create_app(Settings(app=AppSettings(mode="test", data_dir=tmp_path / "data", web_dist_dir=web))))

    assert client.get("/bundles").status_code == 200


def test_near_limit_is_counted_with_rendered_images(client, paper, monkeypatch):
    monkeypatch.setattr(reading_service, "render_region", lambda *_: PNG)
    regions = [make_anchor(client, paper["version_id"], quote_text="", kind="figure") for _ in range(50)]
    choice = {"version_id": paper["version_id"], "anchor_ids": regions, "include_region_images": True, "text": {"mode": "none"}}

    response = preview(client, {"papers": [choice]})

    assert response.json()["file_count"] == 53
    assert [item["code"] for item in response.json()["warnings"]] == ["near_limit"]


def test_export_is_off_unless_enabled_even_with_a_ready_folder(tmp_path):
    """Wiki로 내보내기는 개발 중이라 설정 wiki.enabled를 켜야 쓴다(2026-11-13 사용자 결정). 끄면 health가 disabled라
    화면이 진입점을 숨기고, 서버도 bundle을 쓰지 않는다."""
    outbox = tmp_path / "outbox"
    outbox.mkdir()
    app = create_app(Settings(app=AppSettings(mode="test", data_dir=tmp_path / "data"), wiki=WikiSettings(outbox_path=outbox)))
    client = TestClient(app, base_url=BASE_URL)
    body = {"papers": [{"version_id": upload(client)["version_id"]}]}

    assert client.get("/api/v1/health").json()["wiki_outbox"]["status"] == "disabled"
    for response in (preview(client, body), create(client, body)):
        assert (response.status_code, response.json()["code"]) == (503, "OUTBOX_UNAVAILABLE")
    assert list(outbox.iterdir()) == []
