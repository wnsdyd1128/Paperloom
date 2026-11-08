"""논문 대화의 아티팩트 목록 (2026-11-09 사용자 요청: 대화에서 만든 아티팩트를 모아 두는 보관함). 저장된 답에서 읽는다."""

import json
import uuid
from pathlib import Path
from urllib.parse import quote

import pytest
from fastapi.testclient import TestClient

from paperloom.bootstrap.app import create_app
from paperloom.bootstrap.config import AppSettings, Settings

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "pdf-layout"
PAGE = '<!doctype html><html><head><title>발표 예상 질문</title></head><body></body></html>'


@pytest.fixture
def client(tmp_path) -> TestClient:
    app = create_app(Settings(app=AppSettings(mode="test", data_dir=tmp_path / "data")))
    client = TestClient(app)
    client.paper = client.post(
        "/api/v1/papers",
        content=(FIXTURES / "figures.pdf").read_bytes(),
        headers={"Content-Type": "application/pdf", "X-Paperloom-Filename": quote("figures.pdf")},
    ).json()
    while app.state.parsing.run_next():
        pass
    vector = next(item for item in json.loads((FIXTURES / "figures.json").read_text())["figures"] if item["name"] == "vector")
    u0, v0, u1, v1 = vector["normalized"]
    client.anchor_id = client.post("/api/v1/anchors", json={
        "schema_version": "anchor.v1", "kind": "figure", "version_id": client.paper["current_version"]["version_id"],
        "page_index": 0, "quads": [[u0, v0, u1, v0, u1, v1, u0, v1]], "quote": "", "display_quote": None, "prefix": "", "suffix": "",
    }).json()["anchor_id"]
    return client


def answer(client: TestClient, markdown: str, prompt: str, session: str | None = None) -> dict:
    """브리지가 한 차례를 끝낸 것처럼 packet을 보내고 답을 저장한다."""
    packet_id = client.post("/api/v1/context-packets", json={
        "intent": "ask", "question": prompt, "anchors": [{"anchor_id": client.anchor_id}],
    }).json()["packet_id"]
    client.patch(f"/api/v1/context-packets/{packet_id}", json={"status": "HANDED_OFF", "handoff_method": "claude_code"})
    saved = client.post(
        f"/api/v1/context-packets/{packet_id}/answers", json={"markdown": markdown, "prompt": prompt, "session_id": session or str(uuid.uuid4())}
    )
    assert saved.status_code == 201
    return saved.json()


def listed(client: TestClient, paper_id: str | None = None) -> list[dict]:
    response = client.get(f"/api/v1/papers/{paper_id or client.paper['paper_id']}/artifacts")
    assert response.status_code == 200
    return response.json()["artifacts"]


def test_artifacts_of_the_papers_conversations_are_listed_newest_answer_first(client):
    first = answer(client, f'두 개를 만들었습니다.\n\n```artifact type="svg" title="막대 그림"\n<svg/>\n```\n\n```html\n{PAGE}\n```', "그려 주세요")
    answer(client, "아티팩트 없는 답 [근거 1]", "설명해 주세요")
    second = answer(client, '```artifact type="code" language="python" title="합 계산"\nprint(1)\n```', "코드로 주세요", session=first["session_id"])

    artifacts = listed(client)

    assert [(item["answer_id"], item["index"], item["type"], item["title"]) for item in artifacts] == [
        (second["answer_id"], 0, "code", "합 계산"),
        (first["answer_id"], 0, "svg", "막대 그림"),
        (first["answer_id"], 1, "html", "발표 예상 질문"),  # 형식 없이 온 HTML 문서도 아티팩트다
    ]
    code = artifacts[0]
    assert (code["session_id"], code["prompt"], code["created_at"]) == (first["session_id"], "코드로 주세요", second["created_at"])
    assert (code["language"], code["content"]) == ("python", "print(1)")
    assert artifacts[1]["language"] is None and artifacts[2]["content"] == PAGE


def test_a_discarded_answer_takes_its_artifacts_away(client):
    kept = answer(client, '```artifact type="svg"\n<svg/>\n```', "남길 그림")
    dropped = answer(client, '```artifact type="mermaid" title="흐름"\nflowchart LR\n  A --> B\n```', "버릴 그림")
    assert len(listed(client)) == 2

    client.delete(f"/api/v1/answers/{dropped['answer_id']}")

    assert [item["answer_id"] for item in listed(client)] == [kept["answer_id"]]


def test_an_unknown_paper_has_none(client):
    answer(client, '```artifact type="svg"\n<svg/>\n```', "그림")

    assert listed(client, "no-such-paper") == []
