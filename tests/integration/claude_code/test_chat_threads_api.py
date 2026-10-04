"""선택 설명·질문 대화 (docs/UI_PLAN.md U2·A4): 원문 위 창으로 이어지는 Claude Code 대화를 위치·종류·자리와 함께 남긴다."""

import json
import uuid
from pathlib import Path
from urllib.parse import quote

import pytest
from fastapi.testclient import TestClient

from paperloom.bootstrap.app import create_app
from paperloom.bootstrap.config import AppSettings, Settings

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "pdf-layout"


def upload(client: TestClient, name: str) -> dict:
    return client.post(
        "/api/v1/papers",
        content=(FIXTURES / name).read_bytes(),
        headers={"Content-Type": "application/pdf", "X-Paperloom-Filename": quote(name)},
    ).json()


@pytest.fixture
def client(tmp_path) -> TestClient:
    app = create_app(Settings(app=AppSettings(mode="test", data_dir=tmp_path / "data")))
    client = TestClient(app)
    client.paper = upload(client, "figures.pdf")
    while app.state.parsing.run_next():
        pass
    vector = next(item for item in json.loads((FIXTURES / "figures.json").read_text())["figures"] if item["name"] == "vector")
    u0, v0, u1, v1 = vector["normalized"]
    client.anchor_id = client.post("/api/v1/anchors", json={
        "schema_version": "anchor.v1", "kind": "figure", "version_id": client.paper["current_version"]["version_id"],
        "page_index": 0, "quads": [[u0, v0, u1, v0, u1, v1, u0, v1]], "quote": "", "display_quote": None, "prefix": "", "suffix": "",
    }).json()["anchor_id"]
    return client


def answered_session(client: TestClient, prompt: str = "그림을 설명해 주세요.") -> str:
    """브리지가 한 차례를 끝낸 것처럼 packet을 보내고 답을 저장한 대화 ID."""
    packet_id = client.post("/api/v1/context-packets", json={
        "intent": "explain", "question": prompt, "anchors": [{"anchor_id": client.anchor_id}],
    }).json()["packet_id"]
    client.patch(f"/api/v1/context-packets/{packet_id}", json={"status": "HANDED_OFF", "handoff_method": "claude_code"})
    session = str(uuid.uuid4())
    saved = client.post(f"/api/v1/context-packets/{packet_id}/answers", json={"markdown": "막대 셋 [1]", "prompt": prompt, "session_id": session})
    assert saved.status_code == 201
    return session


def thread(client: TestClient, session: str, **overrides):
    body = {"session_id": session, "paper_id": client.paper["paper_id"], "anchor_id": client.anchor_id, "kind": "explain", "title": "막대그래프의 뜻"}
    return client.post("/api/v1/chat-threads", json={**body, **overrides})


def test_a_thread_keeps_its_place_kind_and_title_and_is_listed_per_paper(client):
    session = answered_session(client)

    created = thread(client, session)
    assert created.status_code == 201
    body = created.json()
    assert (body["session_id"], body["kind"], body["title"], body["placement"]) == (session, "explain", "막대그래프의 뜻", "inline")
    assert (body["anchor"]["anchor_id"], body["anchor"]["page_index"], body["anchor"]["kind"]) == (client.anchor_id, 0, "figure")
    assert body["answer_count"] == 1

    again = thread(client, session, title="다른 제목")  # 같은 대화를 다시 보내면 앞의 것을 준다
    assert (again.status_code, again.json()["title"]) == (200, "막대그래프의 뜻")

    listed = client.get("/api/v1/chat-threads", params={"paper_id": client.paper["paper_id"]}).json()["threads"]
    assert [item["session_id"] for item in listed] == [session]
    assert client.get("/api/v1/chat-threads", params={"paper_id": "no-such"}).json()["threads"] == []


def test_moving_a_thread_to_the_sidebar_changes_only_its_placement(client):
    session = answered_session(client)
    thread(client, session)

    moved = client.patch(f"/api/v1/chat-threads/{session}", json={"placement": "sidebar"})
    assert (moved.status_code, moved.json()["placement"], moved.json()["title"]) == (200, "sidebar", "막대그래프의 뜻")
    assert client.patch(f"/api/v1/chat-threads/{session}", json={"placement": "floating"}).status_code == 422
    assert client.patch(f"/api/v1/chat-threads/{uuid.uuid4()}", json={"placement": "sidebar"}).status_code == 404


def test_deleting_a_thread_discards_its_answers(client):
    session = answered_session(client)
    other = answered_session(client, "다른 질문")
    thread(client, session)

    assert client.delete(f"/api/v1/chat-threads/{session}").status_code == 204
    assert client.get("/api/v1/chat-threads", params={"paper_id": client.paper["paper_id"]}).json()["threads"] == []
    assert client.get("/api/v1/answers", params={"session_id": session}).json()["answers"] == []
    assert len(client.get("/api/v1/answers", params={"session_id": other}).json()["answers"]) == 1  # 다른 대화는 그대로
    assert client.delete(f"/api/v1/chat-threads/{session}").status_code == 404


def test_a_thread_whose_answers_were_all_discarded_is_not_listed(client):
    """2026-10-02 사용자 확인: 사이드바 대화에서 답을 버리면 "선택 설명·질문"에 "답변 0"인 대화가 남았다."""
    session = answered_session(client)
    kept = answered_session(client, "남길 질문")
    thread(client, session)
    thread(client, kept)
    [answer] = client.get("/api/v1/answers", params={"session_id": session}).json()["answers"]
    assert client.delete(f"/api/v1/answers/{answer['answer_id']}").status_code == 200  # 사이드바 대화의 "버리기"

    listed = client.get("/api/v1/chat-threads", params={"paper_id": client.paper["paper_id"]}).json()["threads"]
    assert [item["session_id"] for item in listed] == [kept]


def test_a_thread_needs_a_saved_conversation_about_that_paper(client):
    # 이 브리지가 답을 저장하지 않은 대화 ID로는 만들 수 없다(다른 Claude Code 세션을 가리키지 못한다).
    refused = thread(client, str(uuid.uuid4()))
    assert (refused.status_code, refused.json()["code"]) == (409, "UNKNOWN_SESSION")

    session = answered_session(client)
    other_paper = upload(client, "subscripts.pdf")
    other_anchor = client.post("/api/v1/anchors", json={
        "schema_version": "anchor.v1", "kind": "generic", "version_id": other_paper["current_version"]["version_id"],
        "page_index": 0, "quads": [[0.1, 0.1, 0.3, 0.1, 0.3, 0.2, 0.1, 0.2]], "quote": "", "display_quote": None, "prefix": "", "suffix": "",
    }).json()["anchor_id"]
    refused = thread(client, session, paper_id=other_paper["paper_id"], anchor_id=other_anchor)  # 그 논문에 대한 대화가 아니다
    assert (refused.status_code, refused.json()["code"]) == (409, "UNKNOWN_SESSION")
    assert thread(client, session, paper_id=other_paper["paper_id"]).status_code == 404  # 위치가 그 논문에 없다
    assert thread(client, session, anchor_id="no-such").status_code == 404


@pytest.mark.parametrize(
    "overrides",
    [
        {"kind": "chat"},
        {"title": ""},
        {"title": "x" * 201},
        {"session_id": "not-a-uuid"},
        {"placement": "sidebar"},
    ],
)
def test_bad_threads_are_refused(client, overrides):
    session = answered_session(client)
    assert thread(client, session, **overrides).status_code == 422
