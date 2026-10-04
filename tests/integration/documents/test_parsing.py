"""본문 추출 작업과 쪽 REST (W05, IMPL §5.2–5.3, G3).

worker 스레드 대신 app.state.parsing.run_next()로 작업을 하나씩 돌려 결과를 정해진 순서로 확인한다.
스레드 경로는 test_worker_thread_indexes_after_upload가 확인한다.
"""

import json
import sqlite3
import time
from contextlib import closing
from pathlib import Path
from urllib.parse import quote

import pytest
from fastapi.testclient import TestClient

from paperloom.bootstrap.app import create_app
from paperloom.bootstrap.config import AppSettings, Settings
from paperloom.documents import parsing as parsing_module
from paperloom.documents.extract import ExtractFailed, extract_pages
from paperloom.documents.parsing import ParseService, ParseSettings
from paperloom.infrastructure.files.source_store import SourceStore

FIXTURE_DIR = Path(__file__).resolve().parents[2] / "fixtures" / "pdf-layout"
EXPECTED = json.loads((FIXTURE_DIR / "text-extraction.json").read_text(encoding="utf-8"))


@pytest.fixture
def data_dir(tmp_path: Path) -> Path:
    return tmp_path / "data"


def make_app(data_dir: Path):
    return create_app(Settings(app=AppSettings(mode="test", data_dir=data_dir)))


@pytest.fixture
def app(data_dir):
    return make_app(data_dir)


@pytest.fixture
def client(app) -> TestClient:
    return TestClient(app)  # lifespan을 열지 않으므로 worker 스레드는 돌지 않는다


def upload(client: TestClient, name: str) -> dict:
    response = client.post(
        "/api/v1/papers",
        content=(FIXTURE_DIR / name).read_bytes(),
        headers={"Content-Type": "application/pdf", "X-Paperloom-Filename": quote(name)},
    )
    assert response.status_code == 201, response.text
    return response.json()


def drain(service: ParseService) -> None:
    while service.run_next():
        pass


def version_of(client: TestClient, paper: dict) -> dict:
    return client.get(f"/api/v1/papers/{paper['paper_id']}").json()["current_version"]


def db(data_dir: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(data_dir / "paperloom.sqlite3")
    connection.row_factory = sqlite3.Row
    return connection


def run_rows(data_dir: Path) -> list[sqlite3.Row]:
    with closing(db(data_dir)) as connection:
        return connection.execute("SELECT * FROM parse_runs ORDER BY created_at, parse_run_id").fetchall()


def block_ids(data_dir: Path) -> list[str]:
    with closing(db(data_dir)) as connection:
        return [row[0] for row in connection.execute("SELECT block_id FROM text_blocks ORDER BY id")]


def test_upload_queues_extraction_and_worker_indexes_digital_pdf(app, client, data_dir):
    paper = upload(client, "text-digital.pdf")
    version_id = paper["current_version"]["version_id"]
    assert paper["current_version"]["status"] == "READY_TO_READ"  # 원본은 바로 읽을 수 있다
    assert client.get(f"/api/v1/versions/{version_id}/pages").json() == {
        "version_id": version_id,
        "status": "READY_TO_READ",
        "pages": [],
    }
    not_ready = client.get(f"/api/v1/versions/{version_id}/pages/0")
    assert (not_ready.status_code, not_ready.json()["code"], not_ready.json()["retryable"]) == (409, "TEXT_NOT_READY", True)

    drain(app.state.parsing)

    version = version_of(client, paper)
    assert (version["status"], version["status_reason"]) == ("INDEXED", None)
    pages = client.get(f"/api/v1/versions/{version_id}/pages").json()
    expected_pages = EXPECTED["documents"]["text-digital.pdf"]["pages"]
    assert [(page["page_index"], page["text_status"], page["flags"]) for page in pages["pages"]] == [
        (page["page_index"], page["text_status"], page["flags"]) for page in expected_pages
    ]
    page = client.get(f"/api/v1/versions/{version_id}/pages/1").json()
    assert page["coordinate_space"] == "view-box-unit-top-left"
    assert [block["text"] for block in page["blocks"]] == EXPECTED["documents"]["text-digital.pdf"]["blocks"]["1"]
    assert [block["reading_order"] for block in page["blocks"]] == list(range(len(page["blocks"])))
    assert all(0 <= value <= 1 for block in page["blocks"] for region in block["regions"] for value in region)
    assert client.get(f"/api/v1/versions/{version_id}/pages/99").status_code == 404
    assert client.get("/api/v1/versions/no-such-version/pages").status_code == 404
    assert client.get("/api/v1/versions/no-such-version/pages/0").status_code == 404
    [run] = run_rows(data_dir)
    assert (run["status"], run["attempts"], run["parser_name"]) == ("DONE", 1, "pypdfium2")
    assert run["parser_version"] == app.state.parsing.parser_version and run["config_hash"] == app.state.parsing.config_hash


def test_extraction_marks_the_reference_pages(app, client):
    """업로드 뒤 본문 추출이 문서 전체를 보고 참고문헌 쪽에 "references" 표시를 남긴다 (2026-10-02 사용자 요청)."""
    paper = upload(client, "text-references.pdf")
    drain(app.state.parsing)
    version = version_of(client, paper)
    pages = client.get(f"/api/v1/versions/{version['version_id']}/pages").json()["pages"]
    expected = set(EXPECTED["documents"]["text-references.pdf"]["reference_pages"])
    assert [[flag for flag in page["flags"] if flag == "references"] for page in pages] == [
        ["references"] if page["page_index"] in expected else [] for page in pages
    ]
    assert "+refs" in app.state.parsing.parser_version  # 찾는 방법이 바뀌면 저장된 버전을 다시 추출한다

    # 쪽 번역은 참고문헌 쪽 전체가 아니라 참고문헌 부분(머리부터 부록 앞)의 문단만 뺀다 (2026-10-03 사용자 요청).
    # 참고문헌뿐인 쪽은 no_body_text로 쪽 번역 차례가 건너뛴다
    flags = [
        [(block["text"][:12], block["quality_flags"]) for block in client.get(f"/api/v1/versions/{version['version_id']}/pages/{page}").json()["blocks"]]
        for page in range(4)
    ]
    assert flags[1] == [("2 Method", []), ("The method p", []), ("References", ["reference"]), ("[1] A. Autho", ["reference"])]
    assert flags[2] == [("[3] C. Autho", ["reference"])] and flags[3] == [("A Appendix", []), ("The appendix", [])]
    assert [page["flags"] for page in pages][1:] == [["references"], ["references", "no_body_text"], []]


def test_extraction_marks_text_inside_figures_and_keeps_font_size(app, client):
    """그림 안 글자(벡터 그림의 축 이름, Form 그림의 글자)는 in_figure로 표시해 쪽 번역에서 뺀다. 그림 설명은 아니다.
    문단마다 글꼴 크기(pt)와 굵게·기울임 구간이 있다 (2026-10-03 사용자 요청)."""
    paper = upload(client, "figures.pdf")
    drain(app.state.parsing)
    blocks = client.get(f"/api/v1/versions/{version_of(client, paper)['version_id']}/pages/0").json()["blocks"]
    flags = {block["text"]: block["quality_flags"] for block in blocks}
    assert flags == {
        "A": ["in_figure"],
        "Synthetic values": ["in_figure"],
        "Figure 1. Synthetic bar chart with three bars.": [],
        "BODY TEXT THAT IS NOT A FIGURE": [],
    }
    sizes = {block["text"]: block["font_size"] for block in blocks}
    assert sizes["BODY TEXT THAT IS NOT A FIGURE"] == 12 and sizes["Synthetic values"] == 9
    assert all(block["styles"] == [] for block in blocks)  # Helvetica(보통)뿐


def test_extraction_marks_running_lines_display_equations_and_table_cells(app, client):
    """쪽 번역은 본문만 한다 (2026-10-03 사용자 요청): 쪽마다 되풀이되는 머리글·바닥글, 따로 놓인 수식과 식 번호(번호 없는
    수식, 수식 글꼴로만 쓴 수식 포함), 표 안 칸에 표시를 붙인다. 표 캡션과 본문에는 붙이지 않는다. 큰 첫 글자로 시작하는
    문단은 한 문단이다."""
    paper = upload(client, "text-parts.pdf")
    drain(app.state.parsing)
    version = version_of(client, paper)["version_id"]
    flags = {
        (page, block["text"]): block["quality_flags"]
        for page in range(3)
        for block in client.get(f"/api/v1/versions/{version}/pages/{page}").json()["blocks"]
    }
    for page in range(3):
        assert flags[(page, "Synthetic Parts Journal")] == ["page_header"]
        assert flags[(page, f"7:{page + 1}")] == ["page_header"]
        assert flags[(page, "Synthetic Parts Journal, Vol. 1, Article 7. Publication date: 2026.")] == ["page_footer"]
    assert flags[(0, "x = a + b")] == flags[(0, "(1)")] == flags[(0, "f g h k")] == ["math"]
    assert all(flags[(1, cell)] == ["in_table"] for cell in ("Name", "Value", "alpha", "1,200", "beta", "3,400"))
    body = [
        (0, "Body text before the equation explains the model. It has two sentences on two lines."),
        (0, "The equation above sums two terms. It is used below."),
        (0, "The second equation has no number and only math letters."),
        (1, "Table 1. Synthetic table of values."),
        (1, "The table lists two values. Both are synthetic."),
        (2, "The last page starts with a drop cap like IEEE papers. The first two lines sit beside the large letter and the next lines run under it from the left edge of the column. It is one paragraph."),
    ]
    assert all(flags[key] == [] for key in body)
    assert len(flags) == len(body) + 3 * 3 + 3 + 6


def test_math_symbols_without_unicode_are_recovered_from_the_font_glyph_names(app, client):
    """2026-10-04 사용자 요청(빠지는 수식 기호): 수식 글꼴이 유니코드를 주지 않은 프라임·합·큰 괄호(pdfium은 제어 문자)를
    글꼴 사전의 /Differences 이름으로 되찾는다. 큰 괄호(코드 2)는 줄 끝 하이픈처럼 "-"가 되었다. 본문 글꼴의 줄 끝 하이픈(0x02)은
    그 글꼴의 코드 2 이름(bullet)이 있어도 건드리지 않는다."""
    paper = upload(client, "text-glyphs.pdf")
    drain(app.state.parsing)
    blocks = client.get(f"/api/v1/versions/{version_of(client, paper)['version_id']}/pages/0").json()["blocks"]
    paragraph, equation, hyphenated = blocks
    assert paragraph["text"] == "Recovered math symbols keep their meaning in a paragraph: the bound C′ is small and the sum ∑ of all terms is finite."
    assert "unmapped_chars" not in paragraph["quality_flags"]
    assert equation["text"] == "x = ( ∑ a" and "math" in equation["quality_flags"]
    assert hyphenated["text"] == "The analysis of every single component stays the same in this test."


def test_a_font_with_broken_ascent_and_descent_still_gives_whole_paragraphs(app, client):
    """2026-10-04 사용자 논문 CAAS: 글꼴의 ascent·descent가 망가져(글꼴 크기의 0.45·0) pdfium loose box가 글자 모양 상자였고,
    줄 높이가 x 높이쯤이 되어 문단이 줄마다 나뉘었다(번역이 줄마다 따로 작게 그려졌다). 그런 글꼴의 글자는 기준선 둘레로 넓힌다."""
    paper = upload(client, "text-tight.pdf")
    drain(app.state.parsing)
    blocks = client.get(f"/api/v1/versions/{version_of(client, paper)['version_id']}/pages/0").json()["blocks"]
    assert [(block["text"][:30], len(block["regions"])) for block in blocks] == [
        ("Aerospace and satellite system", 4),
        ("To address this gap we present", 3),
        ("x a e", 1),
    ]
    heights = [region[3] - region[1] for region in blocks[0]["regions"]]
    assert max(heights) / min(heights) < 1.02  # 줄 상자 높이가 글자(아래로 내려가는 글자가 있는지)에 따라 들쭉날쭉하지 않다
    # 수식 글꼴(rtxmi처럼 글꼴 정보가 남다르다)은 넓히지 않는다: 글자 모양 상자 그대로라 본문 줄보다 낮다
    math = blocks[2]["regions"][0]
    assert math[3] - math[1] < 0.8 * min(heights)


def test_extraction_keeps_bold_and_italic_runs_and_font_sizes(app, client):
    """굵게·기울임 구간은 문단 글 안의 [시작, 끝, 모양]이다. 글꼴 이름(Helvetica-Bold·Oblique·BoldOblique)으로 안다."""
    paper = upload(client, "text-styles.pdf")
    drain(app.state.parsing)
    heading, body, inline = client.get(f"/api/v1/versions/{version_of(client, paper)['version_id']}/pages/0").json()["blocks"]
    assert (heading["text"], heading["styles"], heading["font_size"]) == ("3 Styled Section", [[0, 16, "b"]], 12)
    assert body["font_size"] == 10 and len(body["regions"]) == 4
    assert [(body["text"][start:end], mark) for start, end, mark in body["styles"]] == [
        ("kappaword", "i"),
        ("Bold lead in.", "b"),
        ("lambdaword", "bi"),
    ]
    # 인라인 수식: 위첨자 "max" 아래로 줄 높이보다 멀리 돌아간 아래첨자 "p"도 같은 줄이고(문단 하나, 두 줄), 위·아래첨자가 표시된다 (2026-10-04)
    assert inline["text"] == "The bound uses tmax p and Ck for every task in the set. The second line ends the paragraph."
    assert len(inline["regions"]) == 2
    assert [(inline["text"][start:end], mark) for start, end, mark in inline["styles"]] == [("max", "^"), ("p", "_"), ("k", "_")]


@pytest.mark.parametrize("name", ["text-mixed.pdf", "text-image-only.pdf"])
def test_partial_and_image_only_documents(app, client, name):
    paper = upload(client, name)
    drain(app.state.parsing)

    expected = EXPECTED["documents"][name]
    version = version_of(client, paper)
    assert (version["status"], version["status_reason"]) == (expected["status"], expected["status_reason"])
    pages = client.get(f"/api/v1/versions/{version['version_id']}/pages").json()["pages"]
    assert [(page["text_status"], page["flags"]) for page in pages] == [
        (page["text_status"], page["flags"]) for page in expected["pages"]
    ]
    assert all(page["quality"]["image_coverage"] == 1.0 for page in pages if page["text_status"] == "image_only")


def test_restart_requeues_abandoned_run_and_only_the_lease_owner_saves(data_dir):
    first = make_app(data_dir)
    client = TestClient(first)
    paper = upload(client, "text-digital.pdf")
    abandoned = first.state.parsing._claim()  # 작업을 가져간 뒤 프로세스가 멈춘 것과 같다
    assert version_of(client, paper)["status"] == "PARSING"

    restarted = make_app(data_dir)
    restarted.state.parsing.prepare()  # 서버 시작(lifespan)이 부른다
    assert [(row["status"], row["lease_owner"]) for row in run_rows(data_dir)] == [("QUEUED", None)]
    drain(restarted.state.parsing)
    assert version_of(TestClient(restarted), paper)["status"] == "INDEXED"
    saved = block_ids(data_dir)

    # 멈췄던 worker가 뒤늦게 끝나도 lease가 없으므로 저장하지 않는다
    first.state.parsing._execute(abandoned)
    assert block_ids(data_dir) == saved
    assert [(row["status"], row["attempts"]) for row in run_rows(data_dir)] == [("DONE", 2)]


def test_expired_lease_lets_another_worker_take_over(app, client, data_dir, monkeypatch):
    now = [1000.0]
    store = SourceStore(data_dir)
    stalled = ParseService(data_dir / "paperloom.sqlite3", store, clock=lambda: now[0])
    other = ParseService(data_dir / "paperloom.sqlite3", store, clock=lambda: now[0])
    upload(client, "text-digital.pdf")
    run = stalled._claim()

    assert other.run_next() is False  # lease가 살아 있는 동안은 가져가지 않는다
    now[0] += ParseSettings().lease_seconds + 1
    assert other.run_next() is True
    saved = block_ids(data_dir)
    # 멈췄던 worker가 마지막 lease 연장 직후에 lease를 잃었어도, 저장할 때 lease 주인을 다시 확인한다
    monkeypatch.setattr(stalled, "_extend_lease", lambda run: True)
    stalled._execute(run)

    assert block_ids(data_dir) == saved
    [row] = run_rows(data_dir)
    assert (row["status"], row["attempts"]) == ("DONE", 2)


def test_io_error_is_retried_once_then_fails_and_user_can_retry(app, client, data_dir, monkeypatch):
    paper = upload(client, "text-digital.pdf")
    version_id = paper["current_version"]["version_id"]

    def broken(*args, **kwargs):
        raise OSError("하위 프로세스를 띄우지 못함")

    monkeypatch.setattr(parsing_module, "extract_pages", broken)
    assert app.state.parsing.run_next() is False  # 대기열로 되돌린다
    assert [(row["status"], row["attempts"]) for row in run_rows(data_dir)] == [("QUEUED", 1)]
    app.state.parsing.run_next()
    assert [(row["status"], row["attempts"], row["error_code"]) for row in run_rows(data_dir)] == [("FAILED", 2, "PARSER_ERROR")]
    version = version_of(client, paper)
    assert (version["status"], version["status_reason"]) == ("FAILED", "PARSER_ERROR")
    assert app.state.parsing.run_next() is False  # 자동으로 다시 하지 않는다

    monkeypatch.setattr(parsing_module, "extract_pages", extract_pages)
    accepted = client.post(f"/api/v1/versions/{version_id}/parse-runs")
    assert (accepted.status_code, accepted.json()["status"]) == (202, "QUEUED")
    busy = client.post(f"/api/v1/versions/{version_id}/parse-runs")
    assert (busy.status_code, busy.json()["code"]) == (409, "PARSE_IN_PROGRESS")
    assert client.post("/api/v1/versions/no-such-version/parse-runs").status_code == 404
    drain(app.state.parsing)
    assert version_of(client, paper)["status"] == "INDEXED"


def test_transient_io_error_recovers_on_the_automatic_retry(app, client, data_dir, monkeypatch):
    paper = upload(client, "text-digital.pdf")
    calls = []

    def flaky(*args, **kwargs):
        calls.append(args)
        if len(calls) == 1:
            raise OSError("잠깐의 I/O 오류")
        return extract_pages(*args, **kwargs)

    monkeypatch.setattr(parsing_module, "extract_pages", flaky)
    app.state.parsing.run_next()
    app.state.parsing.run_next()

    assert version_of(client, paper)["status"] == "INDEXED"
    assert [(row["status"], row["attempts"]) for row in run_rows(data_dir)] == [("DONE", 2)]


def test_failed_chunk_is_retried_page_by_page(app, client, data_dir, monkeypatch):
    paper = upload(client, "text-digital.pdf")
    bad_page = 2

    def fails_on_bad_page(path, first, stop, timeout_seconds):
        if first <= bad_page < stop:
            raise ExtractFailed("RESOURCE_LIMIT")
        return extract_pages(path, first, stop, timeout_seconds)

    monkeypatch.setattr(parsing_module, "extract_pages", fails_on_bad_page)
    chunked = ParseService(data_dir / "paperloom.sqlite3", SourceStore(data_dir), ParseSettings(chunk_pages=3))
    drain(chunked)

    version = version_of(client, paper)
    assert (version["status"], version["status_reason"]) == ("PARTIAL", None)
    pages = client.get(f"/api/v1/versions/{version['version_id']}/pages").json()["pages"]
    assert [page["text_status"] for page in pages] == ["usable", "usable", "unknown", "usable", "usable", "unknown"]
    assert pages[bad_page]["flags"] == ["extract_failed"] and pages[bad_page]["quality"]["error"] == "RESOURCE_LIMIT"
    # 실패한 묶음의 다른 쪽은 한 쪽씩 다시 추출해 남는다
    assert client.get(f"/api/v1/versions/{version['version_id']}/pages/1").json()["blocks"]


def test_subprocess_timeout_marks_every_page_and_fails_the_document(app, client, data_dir):
    paper = upload(client, "text-mixed.pdf")
    impatient = ParseService(data_dir / "paperloom.sqlite3", SourceStore(data_dir), ParseSettings(chunk_timeout_seconds=0.001))
    drain(impatient)

    version = version_of(client, paper)
    assert (version["status"], version["status_reason"]) == ("FAILED", "RESOURCE_LIMIT")
    pages = client.get(f"/api/v1/versions/{version['version_id']}/pages").json()["pages"]
    assert {(page["text_status"], page["quality"]["error"]) for page in pages} == {("unknown", "RESOURCE_LIMIT")}


def test_extractor_change_reextracts_and_keeps_ids_of_unchanged_paragraphs(app, client, data_dir):
    """추출기가 바뀌면 다시 추출한다. 같은 쪽에 글이 같은 문단은 block ID를 그대로 둔다(2026-10-04: 추출기를 고칠 때마다 모든
    ID가 바뀌어 예전 대화의 문단 근거 링크가 쪽만 열었다). 글이 바뀐 문단은 새 ID다."""
    paper = upload(client, "text-digital.pdf")
    drain(app.state.parsing)
    before = block_ids(data_dir)
    with closing(db(data_dir)) as connection, connection:  # 앞 추출에서는 이 문단의 글이 달랐다(색인도 맞춘다)
        connection.execute("INSERT INTO text_blocks_fts (text_blocks_fts, rowid, text) SELECT 'delete', id, text FROM text_blocks WHERE block_id = ?", (before[0],))
        connection.execute("UPDATE text_blocks SET text = 'an older split of this paragraph' WHERE block_id = ?", (before[0],))
        connection.execute("INSERT INTO text_blocks_fts (rowid, text) SELECT id, text FROM text_blocks WHERE block_id = ?", (before[0],))

    newer = ParseService(data_dir / "paperloom.sqlite3", SourceStore(data_dir))
    newer.prepare()
    assert run_rows(data_dir)[-1]["status"] == "DONE"  # 같은 추출기면 다시 하지 않는다
    newer.config_hash = "changed-thresholds"
    newer.prepare()
    drain(newer)

    after = block_ids(data_dir)
    assert len(after) == len(before) > 1
    assert after[0] not in before and after[1:] == before[1:]
    assert version_of(client, paper)["status"] == "INDEXED"
    with closing(db(data_dir)) as connection:  # 본문 색인(W07 공유 범위 검색용)에 옛 문단이 남지 않는다
        assert connection.execute("SELECT COUNT(*) FROM text_blocks_fts WHERE text_blocks_fts MATCH 'alphaword'").fetchone()[0] == 1


def test_versions_registered_before_extraction_existed_are_queued_on_start(app, client, data_dir):
    paper = upload(client, "text-digital.pdf")
    with closing(db(data_dir)) as connection, connection:  # W05 전에 등록된 버전과 같게 만든다
        connection.execute("DELETE FROM parse_runs")

    restarted = make_app(data_dir)
    restarted.state.parsing.prepare()
    drain(restarted.state.parsing)

    assert version_of(client, paper)["status"] == "INDEXED"


def test_worker_thread_indexes_after_upload(data_dir):
    with TestClient(make_app(data_dir)) as client:  # lifespan이 worker를 시작한다
        paper = upload(client, "text-digital.pdf")
        deadline = time.monotonic() + 30
        while version_of(client, paper)["status"] != "INDEXED":
            assert time.monotonic() < deadline, version_of(client, paper)
            time.sleep(0.1)
