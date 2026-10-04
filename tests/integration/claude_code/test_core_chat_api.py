"""Claude Code 대화를 위한 Core REST (ADR 0003): 대화 답변 저장, 전달 방법 claude_code, 이미지를 붙이는 글, 브리지 주소."""

import json
import sqlite3
import uuid
from contextlib import closing
from pathlib import Path
from urllib.parse import quote

import pytest
from fastapi.testclient import TestClient

from paperloom.bootstrap.app import create_app
from paperloom.bootstrap.config import AppSettings, Settings

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "pdf-layout"


@pytest.fixture
def client(tmp_path) -> TestClient:
    app = create_app(Settings(app=AppSettings(mode="test", data_dir=tmp_path / "data", claude_code_url="http://127.0.0.1:8794")))
    client = TestClient(app)
    paper = client.post(
        "/api/v1/papers",
        content=(FIXTURES / "figures.pdf").read_bytes(),
        headers={"Content-Type": "application/pdf", "X-Paperloom-Filename": quote("figures.pdf")},
    ).json()
    while app.state.parsing.run_next():
        pass
    vector = next(item for item in json.loads((FIXTURES / "figures.json").read_text())["figures"] if item["name"] == "vector")
    u0, v0, u1, v1 = vector["normalized"]
    anchor_id = client.post("/api/v1/anchors", json={
        "schema_version": "anchor.v1", "kind": "figure", "version_id": paper["current_version"]["version_id"], "page_index": 0,
        "quads": [[u0, v0, u1, v0, u1, v1, u0, v1]], "quote": "", "display_quote": None, "prefix": "", "suffix": "",
    }).json()["anchor_id"]
    client.packet_id = client.post("/api/v1/context-packets", json={
        "intent": "explain", "question": "그림을 설명해 주세요.", "anchors": [{"anchor_id": anchor_id}],
    }).json()["packet_id"]
    return client


def save(client: TestClient, packet_id: str, **body):
    return client.post(f"/api/v1/context-packets/{packet_id}/answers", json=body)


SESSION = str(uuid.uuid4())


def test_health_tells_the_web_where_the_bridge_is(client):
    assert client.get("/api/v1/health").json()["claude_code_url"] == "http://127.0.0.1:8794"


def test_text_for_the_bridge_says_images_are_attached(client):
    text = client.get(f"/api/v1/context-packets/{client.packet_id}/export.md", params={"images": "attached"}).text
    assert "이 영역의 이미지는 이 메시지에 붙인 이미지 가운데 1번째입니다." in text and "따로 붙여 넣으세요" not in text
    assert "따로 붙여 넣으세요" in client.get(f"/api/v1/context-packets/{client.packet_id}/export.md").text
    assert client.get(f"/api/v1/context-packets/{client.packet_id}/export.md", params={"images": "tool"}).status_code == 422


def test_chat_answers_are_saved_per_turn_with_question_and_session(client):
    packet_id = client.packet_id
    refused = save(client, packet_id, markdown="답 [1]", prompt="질문", session_id=SESSION)
    assert (refused.status_code, refused.json()["code"]) == (409, "INVALID_TRANSITION")  # 아직 보내지 않은 문맥
    handed = client.patch(f"/api/v1/context-packets/{packet_id}", json={"status": "HANDED_OFF", "handoff_method": "claude_code"}).json()
    assert (handed["status"], handed["handoff_method"]) == ("HANDED_OFF", "claude_code")

    first = save(client, packet_id, markdown="그림은 막대 세 개입니다 [근거 1], [근거 2].", prompt="그림을 설명해 주세요.", session_id=SESSION)
    assert first.status_code == 201
    answer = first.json()
    assert (answer["origin"], answer["prompt"], answer["session_id"], answer["connection_name"]) == ("claude_code", "그림을 설명해 주세요.", SESSION, None)
    assert [(item["number"], item["role"]) for item in answer["citations"]] == [(1, "selected_region"), (2, "caption")]
    assert client.get(f"/api/v1/context-packets/{packet_id}").json()["status"] == "IMPORTED"

    assert save(client, packet_id, markdown="그림은 막대 세 개입니다 [근거 1], [근거 2].", prompt="그림을 설명해 주세요.", session_id=SESSION).status_code == 200
    assert save(client, packet_id, markdown="그림은 막대 세 개입니다 [근거 1], [근거 2].", prompt="다시 말해 주세요.", session_id=SESSION).status_code == 201
    listed = client.get("/api/v1/answers", params={"packet_id": packet_id}).json()["answers"]
    assert [item["prompt"] for item in listed] == ["다시 말해 주세요.", "그림을 설명해 주세요."]


@pytest.mark.parametrize(
    "body",
    [
        {"markdown": "답", "prompt": "질문", "session_id": "not-a-uuid"},
        {"markdown": "답", "prompt": "질문", "session_id": r"C:\Users\x\.claude\projects\p\s.jsonl"},
        {"markdown": "답", "prompt": "", "session_id": SESSION},
        {"markdown": "답", "session_id": SESSION},
        {"markdown": "  ", "prompt": "질문", "session_id": SESSION},
        {"markdown": "답", "prompt": "질문", "session_id": SESSION, "origin": "host_mcp"},
    ],
)
def test_bad_chat_answers_are_refused(client, body):
    client.patch(f"/api/v1/context-packets/{client.packet_id}", json={"status": "HANDED_OFF", "handoff_method": "claude_code"})
    assert save(client, client.packet_id, **body).status_code == 422


def test_chat_answer_needs_an_existing_handed_off_packet(client):
    assert save(client, "no-such", markdown="답", prompt="질문", session_id=SESSION).status_code == 404
    client.patch(f"/api/v1/context-packets/{client.packet_id}", json={"status": "CANCELLED"})
    assert save(client, client.packet_id, markdown="답", prompt="질문", session_id=SESSION).status_code == 409


def test_answers_tell_which_scope_their_packet_sent(client):
    """대화 패널은 그 대화에 이미 보낸 범위(논문 본문·그 쪽)를 보고 본문을 다시 보낼지 정한다 (docs/UI_PLAN.md U3)."""
    version_id = client.get(f"/api/v1/context-packets/{client.packet_id}").json()["sources"][0]["version_id"]
    page = client.post("/api/v1/context-packets", json={"intent": "ask", "question": "q", "scope": "page", "version_id": version_id, "page_index": 0}).json()
    for packet_id in (client.packet_id, page["packet_id"]):
        client.patch(f"/api/v1/context-packets/{packet_id}", json={"status": "HANDED_OFF", "handoff_method": "claude_code"})
    selection = save(client, client.packet_id, markdown="그림 답", prompt="그림?", session_id=SESSION).json()
    on_page = save(client, page["packet_id"], markdown="쪽 답", prompt="이 쪽?", session_id=SESSION).json()
    assert (selection["scope"], selection["scope_page"]) == ("selection", None)
    assert (on_page["scope"], on_page["scope_page"]) == ("page", 0)


def test_answers_by_paper_and_session_carry_the_chosen_passage(client):
    packet_id = client.packet_id
    client.patch(f"/api/v1/context-packets/{packet_id}", json={"status": "HANDED_OFF", "handoff_method": "claude_code"})
    other_session = str(uuid.uuid4())
    save(client, packet_id, markdown="첫 답 [1]", prompt="첫 질문", session_id=SESSION)
    save(client, packet_id, markdown="다른 대화의 답", prompt="다른 질문", session_id=other_session)
    paper_id = client.get(f"/api/v1/context-packets/{packet_id}").json()["sources"][0]["paper_id"]

    by_paper = client.get("/api/v1/answers", params={"paper_id": paper_id, "origin": "claude_code"}).json()["answers"]
    assert [item["prompt"] for item in by_paper] == ["다른 질문", "첫 질문"]
    assert client.get("/api/v1/answers", params={"paper_id": "no-such"}).json()["answers"] == []
    assert client.get("/api/v1/answers", params={"paper_id": paper_id, "origin": "host_mcp"}).json()["answers"] == []
    [one] = client.get("/api/v1/answers", params={"session_id": SESSION}).json()["answers"]
    assert one["prompt"] == "첫 질문"
    # 고른 위치(그림 영역과 그 이미지)가 인용으로 함께 온다. 캡션·영역 글자는 고른 것이 아니라 빠진다
    [context] = one["context"]
    assert (context["kind"], context["page_index"], context["text"]) == ("figure", 0, "")
    assert context["image_url"].startswith("/api/v1/anchors/") and context["anchor_id"]
    assert client.get("/api/v1/answers", params={"origin": "other"}).status_code == 422


def test_a_turn_keeps_the_context_length_the_bridge_reported(client):
    """사이드바 대화가 그 대화의 컨텍스트 길이를 보인다 (2026-10-02 사용자 요청). 브리지가 차례 끝의 토큰 수를 준다."""
    client.patch(f"/api/v1/context-packets/{client.packet_id}", json={"status": "HANDED_OFF", "handoff_method": "claude_code"})
    measured = save(client, client.packet_id, markdown="답", prompt="질문", session_id=SESSION, context_tokens=45_210, context_window=200_000).json()
    assert (measured["context_tokens"], measured["context_window"]) == (45_210, 200_000)
    unknown = save(client, client.packet_id, markdown="다른 답", prompt="질문", session_id=SESSION).json()
    assert (unknown["context_tokens"], unknown["context_window"]) == (None, None)  # 모르면 비워 둔다
    assert save(client, client.packet_id, markdown="답 3", prompt="질문", session_id=SESSION, context_tokens=-1).status_code == 422


def test_a_turn_keeps_the_claude_code_message_id_for_forking_there(client):
    """답마다 갈래 (2026-10-02): 브리지가 차례 끝 메시지 ID를 준다. 없으면 null."""
    client.patch(f"/api/v1/context-packets/{client.packet_id}", json={"status": "HANDED_OFF", "handoff_method": "claude_code"})
    message = str(uuid.uuid4())
    kept = save(client, client.packet_id, markdown="답", prompt="질문", session_id=SESSION, message_id=message).json()
    assert kept["message_id"] == message
    assert save(client, client.packet_id, markdown="다른 답", prompt="질문", session_id=SESSION).json()["message_id"] is None


def test_a_paragraph_citation_points_at_that_paragraph(client):
    """[근거 1¶2]는 논문 본문 근거 1의 둘째 문단 블록을 가리킨다. 문단이 없으면 근거(쪽 첫 문단)로 본다."""
    version_id = client.get(f"/api/v1/context-packets/{client.packet_id}").json()["sources"][0]["version_id"]
    paper = client.post("/api/v1/context-packets", json={"intent": "ask", "question": "q", "scope": "paper", "version_id": version_id}).json()
    blocks = paper["evidence"][0]["block_ids"]
    assert len(blocks) >= 2
    client.patch(f"/api/v1/context-packets/{paper['packet_id']}", json={"status": "HANDED_OFF", "handoff_method": "claude_code"})
    answer = save(client, paper["packet_id"], markdown="둘째 문단 [근거 1¶2], 없는 문단 [근거 1¶99], 쪽 [근거 1]", prompt="q", session_id=SESSION).json()
    assert [(item["number"], item["paragraph"], item["block_id"]) for item in answer["citations"]] == [
        (1, 2, blocks[1]),
        (1, None, paper["evidence"][0]["block_id"]),
    ]


def test_citation_forms_read_after_saving_still_become_links(client, tmp_path):
    """2026-10-02 사용자 확인: 문단 범위 [근거 1¶1–2]를 쓴 답은 저장할 때 근거로 읽지 못해 링크가 없었다.
    답을 줄 때 글을 다시 읽어 저장된 근거에 더하므로, 이미 저장한 답도 링크가 된다."""
    version_id = client.get(f"/api/v1/context-packets/{client.packet_id}").json()["sources"][0]["version_id"]
    paper = client.post("/api/v1/context-packets", json={"intent": "ask", "question": "q", "scope": "paper", "version_id": version_id}).json()
    blocks = paper["evidence"][0]["block_ids"]
    client.patch(f"/api/v1/context-packets/{paper['packet_id']}", json={"status": "HANDED_OFF", "handoff_method": "claude_code"})
    session = str(uuid.uuid4())
    answer = save(client, paper["packet_id"], markdown="범위 [근거 1¶1–2], 없는 [근거 9]", prompt="q", session_id=session).json()
    assert [(item["number"], item["paragraph"], item["block_id"]) for item in answer["citations"]] == [(1, 1, blocks[0])]
    assert answer["unresolved_citations"] == [9]

    with closing(sqlite3.connect(tmp_path / "data" / "paperloom.sqlite3")) as connection, connection:  # 범위를 읽기 전에 저장한 답
        connection.execute("UPDATE answers SET citations_json = ? WHERE answer_id = ?", ('{"resolved": [], "unresolved": []}', answer["answer_id"]))
    [listed] = client.get("/api/v1/answers", params={"session_id": session}).json()["answers"]
    assert [(item["number"], item["paragraph"], item["block_id"]) for item in listed["citations"]] == [(1, 1, blocks[0])]
    assert listed["unresolved_citations"] == [9]
