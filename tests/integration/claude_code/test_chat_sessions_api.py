"""사이드바 "Claude와 대화"의 대화 이름 바꾸기·지우기 (2026-10-02 사용자 요청).

대화는 답변(answers)의 대화 ID로 묶인다. 이름은 원문 위에서 옮겨 온 대화면 그 대화 기록(chat_threads)의 제목을,
아니면 chat_titles에 남긴다. 지우면 그 대화의 답을 모두 버리고 대화 기록·이름도 지운다.
"""

import uuid

from test_chat_threads_api import answered_session, client, thread  # noqa: F401 (pytest fixture)


def titles(client) -> dict[str, str]:
    sessions = client.get("/api/v1/chat-sessions", params={"paper_id": client.paper["paper_id"]}).json()["sessions"]
    return {item["session_id"]: item["title"] for item in sessions}


def rename(client, session: str, title: str, paper_id: str | None = None):
    return client.put(f"/api/v1/chat-sessions/{session}/title", json={"paper_id": paper_id or client.paper["paper_id"], "title": title})


def test_a_sidebar_conversation_keeps_its_new_name(client):
    session = answered_session(client)
    assert titles(client) == {}  # 이름을 붙이기 전에는 첫 질문으로 보인다(웹)

    renamed = rename(client, session, "  막대그래프   읽기 ")
    assert (renamed.status_code, renamed.json()) == (200, {"session_id": session, "title": "막대그래프 읽기", "parent_session_id": None, "fork_answer_id": None})
    assert titles(client) == {session: "막대그래프 읽기"}
    assert rename(client, session, "다시 바꾼 이름").status_code == 200
    assert titles(client) == {session: "다시 바꾼 이름"}


def test_renaming_a_conversation_moved_from_the_page_renames_its_thread(client):
    session = answered_session(client)
    thread(client, session)
    assert titles(client) == {session: "막대그래프의 뜻"}

    assert rename(client, session, "새 이름").status_code == 200
    assert titles(client) == {session: "새 이름"}
    [listed] = client.get("/api/v1/chat-threads", params={"paper_id": client.paper["paper_id"]}).json()["threads"]
    assert listed["title"] == "새 이름"  # "선택 설명·질문" 목록도 같은 이름이다


def test_deleting_a_conversation_discards_its_answers_thread_and_name(client):
    session = answered_session(client)
    other = answered_session(client, "다른 질문")
    thread(client, session)
    rename(client, other, "남을 대화")

    assert client.delete(f"/api/v1/chat-sessions/{session}").status_code == 204
    assert client.get("/api/v1/answers", params={"session_id": session}).json()["answers"] == []
    assert client.get("/api/v1/chat-threads", params={"paper_id": client.paper["paper_id"]}).json()["threads"] == []
    assert titles(client) == {other: "남을 대화"}
    assert len(client.get("/api/v1/answers", params={"session_id": other}).json()["answers"]) == 1  # 다른 대화는 그대로
    assert client.delete(f"/api/v1/chat-sessions/{session}").status_code == 404  # 남은 답이 없다

    assert client.delete(f"/api/v1/chat-sessions/{other}").status_code == 204
    assert titles(client) == {}


def test_only_saved_conversations_about_that_paper_can_be_renamed(client):
    session = answered_session(client)
    unknown = str(uuid.uuid4())
    assert (rename(client, unknown, "이름").status_code, client.delete(f"/api/v1/chat-sessions/{unknown}").status_code) == (404, 404)
    assert rename(client, session, "이름", paper_id="no-such-paper").status_code == 404
    for bad in ("", "   ", "가" * 201):
        assert rename(client, session, bad).status_code == 422
    assert client.put(f"/api/v1/chat-sessions/{session}/title", json={"title": "이름"}).status_code == 422  # 논문이 없다


def test_a_fork_remembers_the_conversation_it_came_from(client):
    """갈래 (2026-10-02 사용자 요청): 브리지가 갈래의 첫 답을 저장한 뒤 웹이 원래 대화와 이름을 남긴다."""
    parent = answered_session(client)
    fork = answered_session(client, "갈래 질문")
    body = {"paper_id": client.paper["paper_id"], "parent_session_id": parent, "title": "  막대그래프 (갈래) "}
    recorded = client.put(f"/api/v1/chat-sessions/{fork}/fork", json=body)
    expected = {"session_id": fork, "title": "막대그래프 (갈래)", "parent_session_id": parent, "fork_answer_id": None}
    assert (recorded.status_code, recorded.json()) == (200, expected)
    sessions = client.get("/api/v1/chat-sessions", params={"paper_id": client.paper["paper_id"]}).json()["sessions"]
    assert sessions == [expected]
    assert rename(client, fork, "새 이름").json()["title"] == "새 이름"  # 이름을 바꿔도 원래 대화는 남는다
    assert titles(client) == {fork: "새 이름"}
    sessions = client.get("/api/v1/chat-sessions", params={"paper_id": client.paper["paper_id"]}).json()["sessions"]
    assert sessions[0]["parent_session_id"] == parent

    # 답에서 갈라졌으면 그 답(갈라진 자리)도 남는다
    [point] = client.get("/api/v1/answers", params={"session_id": parent}).json()["answers"]
    at = client.put(f"/api/v1/chat-sessions/{fork}/fork", json={**body, "fork_answer_id": point["answer_id"]}).json()
    assert at["fork_answer_id"] == point["answer_id"]
    sessions = client.get("/api/v1/chat-sessions", params={"paper_id": client.paper["paper_id"]}).json()["sessions"]
    assert sessions[0]["fork_answer_id"] == point["answer_id"]

    unknown = str(uuid.uuid4())
    assert client.put(f"/api/v1/chat-sessions/{fork}/fork", json={**body, "parent_session_id": unknown}).status_code == 404
    assert client.put(f"/api/v1/chat-sessions/{unknown}/fork", json=body).status_code == 404
    assert client.put(f"/api/v1/chat-sessions/{parent}/fork", json={**body, "parent_session_id": parent}).status_code == 422  # 자기 자신
