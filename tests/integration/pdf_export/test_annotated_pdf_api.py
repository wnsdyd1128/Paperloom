"""주석을 넣은 PDF 내려받기 (2026-11-13 사용자 요청): 원본 뒤에 하이라이트·주석·설명·AI 질문을 PDF 표준 주석으로 붙인다.
번역 대화·지운 대화·사이드바 대화는 넣지 않는다."""

import io
import json
import stat
import uuid
from pathlib import Path
from urllib.parse import quote

import pypdf
import pypdfium2 as pdfium
import pytest
from fastapi.testclient import TestClient

from paperloom.bootstrap.app import create_app
from paperloom.bootstrap.config import AppSettings, Settings

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "pdf-layout"
ACCENT_400 = (255, 151, 131)  # 하이라이트 c2


def quad(v: float, u0: float = 0.1, u1: float = 0.4) -> list[float]:
    return [u0, v, u1, v, u1, v + 0.02, u0, v + 0.02]


@pytest.fixture
def client(tmp_path) -> TestClient:
    app = create_app(Settings(app=AppSettings(mode="test", data_dir=tmp_path / "data")))
    client = TestClient(app)
    name = "figures.pdf"
    client.paper = client.post(
        "/api/v1/papers", content=(FIXTURES / name).read_bytes(), headers={"Content-Type": "application/pdf", "X-Paperloom-Filename": quote(name)}
    ).json()
    client.version_id = client.paper["current_version"]["version_id"]
    while app.state.parsing.run_next():
        pass
    return client


def text_anchor(client: TestClient, v: float, text: str = "worst-case bounds") -> str:
    body = {"schema_version": "anchor.v1", "version_id": client.version_id, "page_index": 0, "quads": [quad(v)], "quote": text}
    response = client.post("/api/v1/anchors", json=body)
    assert response.status_code == 201, response.text
    return response.json()["anchor_id"]


def figure_anchor(client: TestClient) -> str:
    vector = next(item for item in json.loads((FIXTURES / "figures.json").read_text())["figures"] if item["name"] == "vector")
    u0, v0, u1, v1 = vector["normalized"]
    body = {"schema_version": "anchor.v1", "kind": "figure", "version_id": client.version_id, "page_index": 0, "quads": [[u0, v0, u1, v0, u1, v1, u0, v1]], "quote": ""}
    return client.post("/api/v1/anchors", json=body).json()["anchor_id"]


def annotate(client: TestClient, anchor_id: str, comment: str = "", color: str | None = None) -> None:
    assert client.post("/api/v1/annotations", json={"anchor_id": anchor_id, "comment": comment, "color": color}).status_code == 201


def conversation(client: TestClient, anchor_id: str, kind: str, turns: list[tuple[str, str]], *, thread: bool = True) -> str:
    """브리지가 차례마다 packet을 보내고 답을 저장한 대화. thread면 원문 위 대화로 남긴다."""
    session = str(uuid.uuid4())
    for prompt, markdown in turns:
        packet_id = client.post("/api/v1/context-packets", json={"intent": "ask" if kind == "chat" else kind, "question": prompt, "anchors": [{"anchor_id": anchor_id}]}).json()["packet_id"]
        client.patch(f"/api/v1/context-packets/{packet_id}", json={"status": "HANDED_OFF", "handoff_method": "claude_code"})
        saved = client.post(f"/api/v1/context-packets/{packet_id}/answers", json={"markdown": markdown, "prompt": prompt, "session_id": session})
        assert saved.status_code == 201, saved.text
    if thread:
        body = {"session_id": session, "paper_id": client.paper["paper_id"], "anchor_id": anchor_id, "kind": kind, "title": "제목"}
        assert client.post("/api/v1/chat-threads", json=body).status_code == 201
    return session


def added_annotations(client: TestClient, pdf: bytes) -> list[dict]:
    """원본에 없던 쪽 1의 주석들."""
    original = pypdf.PdfReader(io.BytesIO(client.get(f"/api/v1/versions/{client.version_id}/pdf").content)).pages[0]
    before = len(original.get("/Annots", []))
    return [item.get_object() for item in pypdf.PdfReader(io.BytesIO(pdf)).pages[0].get("/Annots", [])][before:]


def summary(annotations: list[dict]) -> list[tuple[str, str, str]]:
    return [(item["/Subtype"], item["/T"], item.get("/Contents", "")) for item in annotations]


@pytest.fixture
def marked(client) -> TestClient:
    annotate(client, text_anchor(client, 0.05, "the default mechanism"), "핵심 가정", "c2")
    annotate(client, text_anchor(client, 0.08, "communication delays"), "따로 메모")
    colored = text_anchor(client, 0.95)
    annotate(client, colored, color="c2")
    figure = figure_anchor(client)
    conversation(client, figure, "explain", [("그림을 설명해 주세요.", "막대 셋입니다."), ("더 자세히?", "높이가 다릅니다.")])
    asked = text_anchor(client, 0.7, "priority misalignment")
    conversation(client, asked, "ask", [("왜 어긋나나요?", "층마다 우선순위가 달라서입니다.")])
    conversation(client, colored, "translate", [("번역해 주세요.", "최악의 경우")])  # 번역은 넣지 않는다
    conversation(client, asked, "chat", [("사이드바 질문", "사이드바 답")], thread=False)  # 사이드바 대화도
    deleted = conversation(client, asked, "ask", [("지운 질문", "지운 답")])
    assert client.delete(f"/api/v1/chat-threads/{deleted}").status_code == 204
    return client


def test_everything_is_added_in_reading_order_after_the_untouched_original(marked):
    response = marked.get(f"/api/v1/versions/{marked.version_id}/annotated-pdf")

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.headers["content-disposition"] == f'attachment; filename="paperloom-{marked.version_id[:8]}.pdf"'
    assert response.content.startswith(marked.get(f"/api/v1/versions/{marked.version_id}/pdf").content)
    assert summary(added_annotations(marked, response.content)) == [
        ("/Highlight", "주석", "핵심 가정"),
        ("/Text", "주석", "“communication delays”\n\n따로 메모"),
        ("/Text", "설명", "[그림]\n\n막대 셋입니다.\n\n질문: 더 자세히?\n\n높이가 다릅니다."),
        ("/Text", "AI 질문", "“priority misalignment”\n\n질문: 왜 어긋나나요?\n\n층마다 우선순위가 달라서입니다."),
        ("/Highlight", "하이라이트", ""),
    ]


def test_only_the_chosen_parts_are_added(marked):
    response = marked.get(f"/api/v1/versions/{marked.version_id}/annotated-pdf", params=[("include", "highlights"), ("include", "questions")])

    assert summary(added_annotations(marked, response.content)) == [
        ("/Highlight", "하이라이트", ""),  # 메모를 고르지 않으면 하이라이트에 글이 없다
        ("/Text", "AI 질문", "“priority misalignment”\n\n질문: 왜 어긋나나요?\n\n층마다 우선순위가 달라서입니다."),
        ("/Highlight", "하이라이트", ""),
    ]


def test_a_highlight_is_drawn_by_pdfium_in_its_colour(marked):
    """Edge·Chrome의 PDF 보기(pdfium)가 그리는 모양. 주석에 모양 스트림이 없어도 하이라이트 색이 보인다."""

    def share_of_accent(pdf: bytes) -> float:
        page = pdfium.PdfDocument(pdf)[0]
        width, height = page.get_size()
        image = page.render(scale=1, draw_annots=True).to_pil().convert("RGB")
        box = (int(0.1 * width) + 2, int(0.95 * height) + 2, int(0.4 * width) - 2, int(0.97 * height) - 2)
        pixels = list(image.crop(box).get_flattened_data())
        return sum(all(abs(a - b) <= 8 for a, b in zip(pixel, ACCENT_400, strict=True)) for pixel in pixels) / len(pixels)

    original = marked.get(f"/api/v1/versions/{marked.version_id}/pdf").content
    exported = marked.get(f"/api/v1/versions/{marked.version_id}/annotated-pdf", params={"include": "highlights"}).content

    assert share_of_accent(original) == 0
    assert share_of_accent(exported) > 0.9


def test_a_paper_without_marks_comes_back_as_the_original_bytes(client):
    response = client.get(f"/api/v1/versions/{client.version_id}/annotated-pdf")

    assert response.content.startswith(client.get(f"/api/v1/versions/{client.version_id}/pdf").content)
    assert added_annotations(client, response.content) == []


def test_unknown_versions_parts_and_broken_sources_are_refused(client, tmp_path):
    assert client.get("/api/v1/versions/no-such/annotated-pdf").json()["code"] == "NOT_FOUND"
    wrong = client.get(f"/api/v1/versions/{client.version_id}/annotated-pdf", params={"include": "translations"})
    assert (wrong.status_code, wrong.json()["code"]) == (422, "INVALID_REQUEST")

    for path in (tmp_path / "data").rglob("*.pdf"):
        path.chmod(stat.S_IWRITE)  # 원본은 읽기 전용으로 저장된다
        path.write_bytes(b"%PDF-1.7\nbroken")
    broken = client.get(f"/api/v1/versions/{client.version_id}/annotated-pdf")
    assert (broken.status_code, broken.json()["code"]) == (500, "EXPORT_FAILED")
