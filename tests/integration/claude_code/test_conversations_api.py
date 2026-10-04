"""U6 답변 화면 (사용자 결정 D8): 모든 논문의 Claude Code 대화 목록. 사이드바 대화와 선택 설명·질문·번역을 최근 순으로."""

import json
import time
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
    client.papers = [upload(client, "figures.pdf"), upload(client, "text-references.pdf")]
    while app.state.parsing.run_next():
        pass
    client.anchors = []
    for paper, page in zip(client.papers, (0, 1)):
        client.anchors.append(client.post("/api/v1/anchors", json={
            "schema_version": "anchor.v1", "kind": "text", "version_id": paper["current_version"]["version_id"], "page_index": page,
            "quads": [[0.1, 0.1, 0.5, 0.1, 0.5, 0.12, 0.1, 0.12]], "quote": "q", "display_quote": None, "prefix": "", "suffix": "",
        }).json()["anchor_id"])
    return client


def answer(client: TestClient, paper_index: int, session: str, prompt: str) -> dict:
    """브리지가 한 차례를 끝낸 것처럼 packet을 보내고 답을 저장한다."""
    packet_id = client.post("/api/v1/context-packets", json={
        "intent": "ask", "question": prompt, "anchors": [{"anchor_id": client.anchors[paper_index]}],
    }).json()["packet_id"]
    client.patch(f"/api/v1/context-packets/{packet_id}", json={"status": "HANDED_OFF", "handoff_method": "claude_code"})
    saved = client.post(f"/api/v1/context-packets/{packet_id}/answers", json={"markdown": "답", "prompt": prompt, "session_id": session})
    assert saved.status_code == 201, saved.text
    time.sleep(0.01)  # 저장 시각이 차례대로 다르게
    return saved.json()


def test_conversations_of_every_paper_newest_first_with_kind_title_and_place(client):
    first_paper, second_paper = client.papers
    chat, untitled, thread, moved, other = (str(uuid.uuid4()) for _ in range(5))
    answer(client, 0, chat, "첫 질문")
    answer(client, 0, chat, "이어 묻기")
    renamed = client.put(f"/api/v1/chat-sessions/{chat}/title", json={"paper_id": first_paper["paper_id"], "title": "캐시 분할 정리"})
    assert renamed.status_code == 200, renamed.text
    answer(client, 0, untitled, "제목 없는 대화의 첫 질문입니다")
    answer(client, 1, thread, "이 문장을 설명해 주세요.")
    client.post("/api/v1/chat-threads", json={
        "session_id": thread, "paper_id": second_paper["paper_id"], "anchor_id": client.anchors[1], "kind": "explain", "title": "설명 제목",
    })
    answer(client, 1, moved, "번역해 주세요.")
    client.post("/api/v1/chat-threads", json={
        "session_id": moved, "paper_id": second_paper["paper_id"], "anchor_id": client.anchors[1], "kind": "translate", "title": "번역 제목",
    })
    client.patch(f"/api/v1/chat-threads/{moved}", json={"placement": "sidebar"})
    gone = answer(client, 0, other, "버린 대화")
    client.delete(f"/api/v1/answers/{gone['answer_id']}")

    items = client.get("/api/v1/conversations").json()["conversations"]

    def shape(item):
        return (item["session_id"], item["kind"], item["title"], item["paper_id"], item["placement"], item["page_index"], item["answer_count"])

    assert [shape(item) for item in items] == [
        (moved, "translate", "번역 제목", second_paper["paper_id"], "sidebar", 1, 1),
        (thread, "explain", "설명 제목", second_paper["paper_id"], "inline", 1, 1),
        (untitled, "chat", "제목 없는 대화의 첫 질문입니다", first_paper["paper_id"], None, None, 1),
        (chat, "chat", "캐시 분할 정리", first_paper["paper_id"], None, None, 2),
    ]
    assert items[1]["anchor_id"] == client.anchors[1] and items[3]["anchor_id"] is None
    assert items[0]["paper_title"] == second_paper["title"]
    assert items[0]["version_id"] == second_paper["current_version"]["version_id"]
    assert all(items[n]["last_answer_at"] >= items[n + 1]["last_answer_at"] for n in range(len(items) - 1))
    assert json.dumps(items).count(other) == 0  # 답을 모두 버린 대화는 없다


def test_a_deleted_thread_is_not_listed_and_the_list_has_a_limit(client):
    thread = str(uuid.uuid4())
    answer(client, 1, thread, "설명해 주세요.")
    client.post("/api/v1/chat-threads", json={
        "session_id": thread, "paper_id": client.papers[1]["paper_id"], "anchor_id": client.anchors[1], "kind": "ask", "title": "질문",
    })
    for _ in range(2):
        answer(client, 0, str(uuid.uuid4()), "다른 대화")
    assert len(client.get("/api/v1/conversations").json()["conversations"]) == 3
    assert len(client.get("/api/v1/conversations", params={"limit": 2}).json()["conversations"]) == 2
    client.delete(f"/api/v1/chat-sessions/{thread}")
    assert thread not in json.dumps(client.get("/api/v1/conversations").json())
    assert client.get("/api/v1/conversations", params={"limit": 0}).status_code == 422
