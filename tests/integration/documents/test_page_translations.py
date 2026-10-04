"""U7 쪽 번역 저장 (UI_PLAN U7, IMPL §8): 쪽의 문단·문장마다 번역을 언어별로 둔다. 브리지가 저장하고 웹이 읽는다.

문장은 documents.sentences로 나눈다. 번역은 원문 글과 함께 두어, 다시 추출해 문단 ID가 바뀌어도 글이 같으면 그대로 쓴다.
"""

import sqlite3
from contextlib import closing
from pathlib import Path
from urllib.parse import quote

import pytest
from fastapi.testclient import TestClient

from paperloom.bootstrap.app import create_app
from paperloom.bootstrap.config import AppSettings, Settings
from paperloom.documents.sentences import sentence_spans

FIXTURE_DIR = Path(__file__).resolve().parents[2] / "fixtures" / "pdf-layout"
TWO_SENTENCES = "Navigation fixture text for the outline and the find bar. Section one introduces the cache model."


@pytest.fixture
def data_dir(tmp_path: Path) -> Path:
    return tmp_path / "data"


@pytest.fixture
def app(data_dir):
    return create_app(Settings(app=AppSettings(mode="test", data_dir=data_dir)))


@pytest.fixture
def client(app) -> TestClient:
    return TestClient(app)


def drain(app) -> None:
    while app.state.parsing.run_next():
        pass


@pytest.fixture
def version(app, client) -> str:
    """본문 추출을 마친 text-navigation.pdf의 버전 ID"""
    response = client.post(
        "/api/v1/papers",
        content=(FIXTURE_DIR / "text-navigation.pdf").read_bytes(),
        headers={"Content-Type": "application/pdf", "X-Paperloom-Filename": quote("text-navigation.pdf")},
    )
    drain(app)
    return response.json()["current_version"]["version_id"]


def blocks(client: TestClient, version: str, page: int = 0) -> list[dict]:
    return client.get(f"/api/v1/versions/{version}/pages/{page}").json()["blocks"]


def translated(page_blocks: list[dict], fill=lambda block, index: f"번역 {block['text'][:12]} {index}") -> dict:
    """모든 문단·문장의 번역 (문장 수는 원문을 나눈 대로)"""
    return {
        "model": "sonnet",
        "blocks": [
            {"block_id": block["block_id"], "sentences": [fill(block, index) for index in range(len(sentence_spans(block["text"])))]}
            for block in page_blocks
        ],
    }


def url(version: str, page: int = 0, language: str = "ko") -> str:
    return f"/api/v1/versions/{version}/pages/{page}/translations/{language}"


def test_a_page_translation_is_kept_per_language_with_each_sentence_position(client, version):
    page_blocks = blocks(client, version)
    body = translated(page_blocks)
    saved = client.put(url(version), json=body)
    assert saved.status_code == 200, saved.text
    out = saved.json()
    assert (out["version_id"], out["page_index"], out["language"], out["model"]) == (version, 0, "ko", "sonnet")
    # 문단마다 원문 문장의 글자 위치(그 문단 text 안)와 번역
    two = next(block for block in page_blocks if block["text"] == TWO_SENTENCES)
    two_out = next(block for block in out["blocks"] if block["block_id"] == two["block_id"])
    assert [(item["start"], item["end"]) for item in two_out["sentences"]] == sentence_spans(TWO_SENTENCES)
    assert [TWO_SENTENCES[item["start"]:item["end"]] for item in two_out["sentences"]] == [
        "Navigation fixture text for the outline and the find bar.",
        "Section one introduces the cache model.",
    ]
    assert [item["text"] for item in two_out["sentences"]] == [f"번역 {TWO_SENTENCES[:12]} 0", f"번역 {TWO_SENTENCES[:12]} 1"]
    assert [block["block_id"] for block in out["blocks"]] == [block["block_id"] for block in page_blocks]  # 읽는 차례

    assert client.get(url(version)).json() == out
    missing = client.get(url(version, language="en"))
    assert (missing.status_code, missing.json()["code"]) == (404, "NOT_TRANSLATED")
    assert client.get(url(version, page=1)).json()["code"] == "NOT_TRANSLATED"
    assert client.get(f"/api/v1/versions/{version}/translations/ko").json() == {"version_id": version, "language": "ko", "pages": [0]}
    assert client.get(f"/api/v1/versions/{version}/translations/en").json()["pages"] == []

    # 다시 저장하면(다시 번역) 바뀐다
    again = client.put(url(version), json={**translated(page_blocks, lambda block, index: f"다시 {index}"), "model": "haiku"})
    assert again.json()["model"] == "haiku"
    assert client.get(url(version)).json()["blocks"][0]["sentences"][0]["text"] == "다시 0"


def test_an_empty_sentence_joins_the_one_before_but_the_first_must_have_text(client, version):
    page_blocks = blocks(client, version)
    joined = translated(page_blocks, lambda block, index: "앞 문장과 합친 번역" if index == 0 else "")
    assert client.put(url(version), json=joined).status_code == 200
    two = next(block for block in client.get(url(version)).json()["blocks"] if len(block["sentences"]) == 2)
    assert [item["text"] for item in two["sentences"]] == ["앞 문장과 합친 번역", ""]

    # 쪽의 첫 문단 첫 문장은 비울 수 없다(합칠 앞 문장이 없다)
    empty_first = translated(page_blocks, lambda block, index: "" if index == 0 else "뒤")
    response = client.put(url(version, page=0), json=empty_first)
    assert (response.status_code, response.json()["code"]) == (422, "INVALID_TRANSLATION")
    # 다른 문단의 첫 문장은 비울 수 있다: PDF에서 문장 가운데서 나뉜 문단을 앞 문단 끝 문장에 합쳐 옮긴 것 (2026-10-03 사용자 논문)
    second = page_blocks[1]["block_id"]
    merged = translated(page_blocks, lambda block, index: "" if block["block_id"] == second and index == 0 else "번역")
    assert client.put(url(version), json=merged).status_code == 200
    assert client.get(url(version)).json()["blocks"][1]["sentences"][0]["text"] == ""


@pytest.mark.parametrize(
    "change",
    ["missing_block", "unknown_block", "duplicate_block", "fewer_sentences", "more_sentences", "too_long"],
)
def test_a_translation_must_cover_every_paragraph_and_sentence_exactly(client, version, change):
    page_blocks = blocks(client, version)
    body = translated(page_blocks)
    two = next(index for index, block in enumerate(page_blocks) if block["text"] == TWO_SENTENCES)
    if change == "missing_block":
        body["blocks"].pop()
    elif change == "unknown_block":
        body["blocks"].append({"block_id": "not-on-this-page", "sentences": ["x"]})
    elif change == "duplicate_block":
        body["blocks"].append(body["blocks"][0])
    elif change == "fewer_sentences":
        body["blocks"][two]["sentences"].pop()
    elif change == "more_sentences":
        body["blocks"][two]["sentences"].append("하나 더")
    else:
        body["blocks"][0]["sentences"][0] = "가" * 5001
    response = client.put(url(version), json=body)
    assert response.status_code == 422
    assert response.json()["code"] in ("INVALID_TRANSLATION", "INVALID_REQUEST")
    assert client.get(url(version)).json()["code"] == "NOT_TRANSLATED"  # 저장하지 않았다


def test_extracting_again_keeps_translations_of_unchanged_text_and_drops_changed_pages(app, client, data_dir, version):
    page_blocks = blocks(client, version)
    assert client.put(url(version), json=translated(page_blocks)).status_code == 200
    assert client.post(f"/api/v1/versions/{version}/parse-runs").status_code == 202
    drain(app)
    new_blocks = blocks(client, version)
    # 글이 같은 문단은 ID도 그대로다(2026-10-04). 번역은 ID가 아니라 원문 글로 짝짓는다
    assert [block["block_id"] for block in new_blocks] == [block["block_id"] for block in page_blocks]
    kept = client.get(url(version))
    assert kept.status_code == 200
    assert [block["block_id"] for block in kept.json()["blocks"]] == [block["block_id"] for block in new_blocks]

    # 글이 바뀐 문단이 있으면(문장 수가 같아도) 그 쪽 번역은 쓰지 않는다(다시 번역)
    two = next(block for block in new_blocks if block["text"] == TWO_SENTENCES)
    with closing(sqlite3.connect(data_dir / "paperloom.sqlite3")) as connection, connection:
        connection.execute("UPDATE text_blocks SET text = replace(text, 'cache model', 'cache modem') WHERE block_id = ?", (two["block_id"],))
    assert client.get(url(version)).json()["code"] == "NOT_TRANSLATED"


def test_a_page_is_not_ready_while_its_version_is_extracted_again(app, client, version):
    """다시 추출하는 동안(시작할 때 추출기 버전이 바뀐 논문 등)은 문단이 곧 바뀌므로 번역을 읽거나 저장하지 않는다.
    브리지는 번역 전에 읽어 보므로 Claude를 실행하지 않는다(문단이 바뀐 뒤 저장이 거부되어 사용량만 쓰지 않게)."""
    page_blocks = blocks(client, version)
    assert client.put(url(version), json=translated(page_blocks)).status_code == 200
    assert client.post(f"/api/v1/versions/{version}/parse-runs").status_code == 202
    for response in (client.get(url(version)), client.put(url(version), json=translated(page_blocks))):
        assert (response.status_code, response.json()["code"]) == (409, "TEXT_NOT_READY")
    drain(app)
    assert client.get(url(version)).status_code == 200  # 글이 같으면 그대로


def test_text_inside_figures_is_not_part_of_a_page_translation(app, client):
    """그림 안 글자(in_figure)는 번역하지 않는다 (2026-10-03 사용자 요청). 저장에 그 문단이 없어도 되고, 있으면 거부한다."""
    response = client.post(
        "/api/v1/papers",
        content=(FIXTURE_DIR / "figures.pdf").read_bytes(),
        headers={"Content-Type": "application/pdf", "X-Paperloom-Filename": quote("figures.pdf")},
    )
    drain(app)
    figures = response.json()["current_version"]["version_id"]
    page_blocks = blocks(client, figures)
    outside = [block for block in page_blocks if "in_figure" not in block["quality_flags"]]
    assert {block["text"] for block in outside} == {"Figure 1. Synthetic bar chart with three bars.", "BODY TEXT THAT IS NOT A FIGURE"}
    saved = client.put(url(figures), json=translated(outside))
    assert saved.status_code == 200, saved.text
    assert {block["block_id"] for block in saved.json()["blocks"]} == {block["block_id"] for block in outside}
    with_figure = client.put(url(figures), json=translated(page_blocks))
    assert (with_figure.status_code, with_figure.json()["code"]) == (422, "INVALID_TRANSLATION")


def test_only_body_paragraphs_are_part_of_a_page_translation(app, client):
    """머리글·바닥글, 따로 놓인 수식, 표 안 칸은 번역하지 않는다. 표 캡션은 번역한다 (2026-10-03 사용자 요청)."""
    response = client.post(
        "/api/v1/papers",
        content=(FIXTURE_DIR / "text-parts.pdf").read_bytes(),
        headers={"Content-Type": "application/pdf", "X-Paperloom-Filename": quote("text-parts.pdf")},
    )
    drain(app)
    parts = response.json()["current_version"]["version_id"]
    for page, texts in [
        (0, {
            "Body text before the equation explains the model. It has two sentences on two lines.",
            "The equation above sums two terms. It is used below.",
            "The second equation has no number and only math letters.",
        }),
        (1, {"Table 1. Synthetic table of values.", "The table lists two values. Both are synthetic."}),
    ]:
        page_blocks = blocks(client, parts, page)
        body = [block for block in page_blocks if not block["quality_flags"]]
        assert {block["text"] for block in body} == texts
        assert client.put(url(parts, page), json=translated(body)).status_code == 200
        assert client.put(url(parts, page), json=translated(page_blocks)).json()["code"] == "INVALID_TRANSLATION"


def test_deleting_a_language_drops_every_page_of_that_version_only(client, version):
    page_blocks = blocks(client, version)
    for language in ("ko", "en"):
        assert client.put(url(version, language=language), json=translated(page_blocks)).status_code == 200
    assert client.delete(f"/api/v1/versions/{version}/translations/ko").status_code == 204
    assert client.get(f"/api/v1/versions/{version}/translations/ko").json()["pages"] == []
    assert client.get(url(version, language="en")).status_code == 200  # 다른 언어는 그대로
    assert client.delete("/api/v1/versions/no-such-version/translations/ko").status_code == 404


def test_unknown_versions_pages_languages_and_text_not_extracted_yet(app, client, version):
    assert client.get(url("no-such-version")).json()["code"] == "NOT_FOUND"
    assert client.get(url(version, page=99)).json()["code"] == "NOT_FOUND"
    assert client.get(url(version, language="ja")).status_code == 422
    assert client.put(url("no-such-version"), json={"model": None, "blocks": [{"block_id": "x", "sentences": ["y"]}]}).status_code == 404
    assert client.get("/api/v1/versions/no-such-version/translations/ko").json()["code"] == "NOT_FOUND"

    pending = client.post(
        "/api/v1/papers",
        content=(FIXTURE_DIR / "text-digital.pdf").read_bytes(),
        headers={"Content-Type": "application/pdf", "X-Paperloom-Filename": quote("text-digital.pdf")},
    ).json()["current_version"]["version_id"]
    response = client.get(url(pending))
    assert (response.status_code, response.json()["code"]) == (409, "TEXT_NOT_READY")
