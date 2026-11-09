"""Paperloom이 만든 bundle을 실제 LLM Wiki 수신기로 받아 본다 (AC-01). 로컬 전용: LLM_WIKI_SRC에 llm-wiki의 src 폴더를 줄 때만 돈다.

    LLM_WIKI_SRC="<...>/llm-wiki/src" pytest tests/contract/test_llm_wiki_receiver.py

그 저장소는 읽기만 한다(바이트코드도 남기지 않는다). 수신·후보는 tmp_path의 합성 Vault·상태 폴더에 쌓인다.
"""

import os
import sys
from pathlib import Path
from urllib.parse import quote

import pytest
from fastapi.testclient import TestClient

from paperloom.bootstrap.app import create_app
from paperloom.bootstrap.config import AppSettings, Settings, WikiSettings

SOURCE = os.environ.get("LLM_WIKI_SRC")
pytestmark = pytest.mark.skipif(not SOURCE, reason="LLM_WIKI_SRC가 없다(로컬 전용 시험)")
FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "pdf-layout"
QUAD = [0.1, 0.1, 0.5, 0.1, 0.5, 0.12, 0.1, 0.12]


@pytest.fixture
def receiver(tmp_path, monkeypatch):
    """(수신 서비스, outbox, Vault 폴더)"""
    monkeypatch.setattr(sys, "dont_write_bytecode", True)
    monkeypatch.syspath_prepend(SOURCE)
    from llm_wiki.application.intake import IntakeService
    from llm_wiki.infrastructure.intake import Outbox
    from llm_wiki.infrastructure.storage import WorkspaceStore
    from llm_wiki.infrastructure.vault import Vault

    outbox, vault = tmp_path / "outbox", tmp_path / "위키 공간"
    outbox.mkdir()
    (vault / "Research" / "Papers").mkdir(parents=True)
    return IntakeService(Outbox(outbox), WorkspaceStore(tmp_path / "runtime"), Vault(vault)), outbox, vault


@pytest.fixture
def paperloom(tmp_path, receiver):
    """논문 하나를 올리고 추출한 클라이언트와 그 판본, Anchor 하나."""
    _, outbox, _ = receiver
    app = create_app(Settings(app=AppSettings(mode="test", data_dir=tmp_path / "data"), wiki=WikiSettings(outbox_path=outbox)))
    client = TestClient(app, base_url="http://127.0.0.1:8000")
    paper = client.post(
        "/api/v1/papers",
        content=(FIXTURES / "text-digital.pdf").read_bytes(),
        headers={"Content-Type": "application/pdf", "X-Paperloom-Filename": quote("text-digital.pdf")},
    ).json()
    while app.state.parsing.run_next():
        pass
    version_id = paper["current_version"]["version_id"]
    anchor = client.post("/api/v1/anchors", json={
        "schema_version": "anchor.v1", "kind": "text", "version_id": version_id, "page_index": 1, "quads": [QUAD],
        "quote": "합성 인용", "display_quote": None, "prefix": "", "suffix": "",
    }).json()
    client.post("/api/v1/annotations", json={"anchor_id": anchor["anchor_id"], "comment": "합성 메모"})
    return client, paper, version_id, anchor["anchor_id"]


def export(client: TestClient, body: dict) -> dict:
    response = client.post("/api/v1/evidence-bundles", json=body, headers={"Idempotency-Key": os.urandom(8).hex()})
    assert response.status_code == 201, response.text
    return response.json()


def test_the_receiver_takes_a_paperloom_bundle_and_makes_one_unapproved_candidate(paperloom, receiver):
    service, _, vault = receiver
    client, paper, version_id, anchor_id = paperloom
    bundle = export(client, {
        "papers": [{"version_id": version_id, "anchor_ids": [anchor_id]}],
        "proposals": [{"version_id": version_id, "title": "합성 후보", "content_markdown": "# 합성 후보\n\n내용\n", "anchor_ids": [anchor_id]}],
    })

    listed = {entry.bundle_id: entry for entry in service.bundles()}
    assert (listed[bundle["bundle_id"]].status, listed[bundle["bundle_id"]].reason) == ("new", None)
    record, created = service.receive(bundle["bundle_id"])

    assert created and record.manifest_hash == bundle["manifest_sha256"]
    assert [outcome.outcome for outcome in record.proposals] == ["created"]
    detail = service.record(record.id)
    assert [source.sha256 for source in detail.sources] == [paper["current_version"]["sha256"]]
    assert detail.sources[0].reader_url == f"http://127.0.0.1:8000/reader/{paper['paper_id']}?version={version_id}"
    [evidence] = detail.evidence
    assert (evidence.anchor_id, evidence.page, evidence.quote, evidence.comment) == (anchor_id, 2, "합성 인용", "합성 메모")
    assert evidence.reader_url == f"http://127.0.0.1:8000/reader/{paper['paper_id']}?version={version_id}&anchor={anchor_id}"
    [change] = detail.changes
    assert (change.status, change.operation, change.origin) == ("pending", "create_note", "paperloom")
    assert not list(vault.rglob("*.md"))  # 승인 전에는 Vault에 쓰지 않는다
    assert service.receive(bundle["bundle_id"]) == (record, False)  # 같은 bundle을 또 받아도 한 번이다

    # AC-10의 나머지: 승인 → Vault 반영. 노트에 인용과 Reader 복귀 링크가 남는다
    from llm_wiki.application.apply import ApplyService

    applying = ApplyService(service.store, service.vault, "ready")
    approved = applying.approve(change.id, change.candidate_raw_sha256, change.base_raw_sha256)
    applying.apply(approved.id)
    assert service.store.get_changeset(change.id).status == "applied"
    note = (vault / change.target_path).read_text(encoding="utf-8")
    assert "합성 인용" in note and "합성 메모" not in note  # 메모는 근거 기록에 남고 노트에는 인용과 링크만 들어간다
    assert f"<http://127.0.0.1:8000/reader/{paper['paper_id']}?version={version_id}&anchor={anchor_id}>" in note
    assert "내용" in note


def test_evidence_only_bundle_is_kept_without_a_candidate(paperloom, receiver):
    service, _, _ = receiver
    client, _, version_id, anchor_id = paperloom
    bundle = export(client, {"papers": [{"version_id": version_id, "anchor_ids": [anchor_id]}]})

    record, _ = service.receive(bundle["bundle_id"])

    assert record.proposals == [] and len(service.record(record.id).evidence) == 1


def test_the_receiver_keeps_an_artifact_exported_without_its_answer(paperloom, receiver):
    """2026-11-09 사용자 요청: 아티팩트만 따로 내보낸다. 수신기는 artifacts/에 Markdown만 받으므로 .md 한 파일로 넣는다."""
    service, _, _ = receiver
    client, _, version_id, anchor_id = paperloom
    packet = client.post("/api/v1/context-packets", json={"intent": "ask", "question": "질문", "anchors": [{"anchor_id": anchor_id}]}).json()
    client.patch(f"/api/v1/context-packets/{packet['packet_id']}", json={"status": "HANDED_OFF", "handoff_method": "claude_code"})
    markdown = '그림입니다.\n\n```artifact type="html" title="합성 페이지"\n<!doctype html>\n<p>합성</p>\n```\n'
    answer = client.post(f"/api/v1/context-packets/{packet['packet_id']}/answers", json={"markdown": markdown, "prompt": "질문", "session_id": "0f6c2c1e-7a4b-4c8e-9d1a-2b3c4d5e6f70"}).json()
    bundle = export(client, {"papers": [{"version_id": version_id}], "artifacts": [{"answer_id": answer["answer_id"], "index": 0}]})

    [entry] = service.bundles()
    record, _ = service.receive(bundle["bundle_id"])

    assert (entry.status, entry.reason) == ("new", None)
    assert f"artifacts/artifact-{answer['answer_id']}-1.md" in [item.path for item in record.files]


def test_the_receiver_keeps_the_text_that_the_default_carries(paperloom, receiver):
    """03-api-spec §7·요구사항 Q3: 수신기가 texts/를 받으므로(2026-11-02) 기본은 고른 위치가 있는 쪽의 추출문을 싣는다."""
    service, _, _ = receiver
    client, _, version_id, anchor_id = paperloom
    bundle = export(client, {"papers": [{"version_id": version_id, "anchor_ids": [anchor_id]}]})

    [entry] = service.bundles()
    record, _ = service.receive(bundle["bundle_id"])

    assert (bundle["schema_version"], bundle["counts"]["texts"]) == ("paperloom-bundle.v1.1", 1)
    assert (entry.status, entry.reason) == ("new", None)
    assert len(record.text_sources) == 1
