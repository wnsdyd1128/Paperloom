"""실제 논문 시험 (로컬 전용, 2026-10-14 사용자 요청: "tests/e2e_papers에 실제 논문 PDF 파일 있는데 이거 기반으로 테스트 진행해줘").

tests/e2e_papers/의 PDF는 저작권 때문에 저장소에 넣지 않는다(.gitignore). 폴더가 없으면 건너뛰고, 있어도 기본 실행·CI에서는
빠진다(pytest.ini). 실행: backend\\.venv\\Scripts\\python.exe -m pytest -m real_papers

모든 논문을 서버 경로(업로드 → 첫 쪽 제목 → 본문 추출)로 한 번 처리한다. 모든 논문에 성립해야 할 성질과, 사용자가 알린 논문
문제의 고침(그 파일이 있을 때만)을 본다. 첫 실행 결과는 docs/gates/evidence/ui/2026-10-14_real-papers.md.
레이아웃 모델(documents.layout_model)이 var/models에 있으면 그것도 쓴다(로컬 서버 설정 ops/config/local.yaml의 자리). 모델에 기대는
시험은 모델이 없으면 건너뛴다.
"""

import re
import statistics
import unicodedata
from pathlib import Path
from urllib.parse import quote

import pytest
from fastapi.testclient import TestClient

from paperloom.bootstrap.app import create_app
from paperloom.bootstrap.config import AppSettings, LayoutSettings, Settings
from paperloom.documents.headings import headings
from paperloom.documents.titles import looks_like_filename

PAPERS = Path(__file__).resolve().parents[1] / "e2e_papers"
NAMES = sorted(path.name for path in PAPERS.glob("*.pdf")) if PAPERS.is_dir() else []
pytestmark = [pytest.mark.real_papers, pytest.mark.skipif(not NAMES, reason="tests/e2e_papers에 실제 논문이 없다")]
MODEL = Path(__file__).resolve().parents[2] / "var" / "models" / "pp-doclayout-plus-l" / "inference.onnx"
needs_model = pytest.mark.skipif(not MODEL.is_file(), reason="var/models에 레이아웃 모델이 없다(python -m paperloom.documents.layout_model download)")

SCHEDULABILITY = "Schedulability Analysis of Global Scheduling for Multicore Systems With Shared Caches.pdf"  # 3B2 수식 글꼴
PREDICTING = "Predicting Inter-Thread Cache Contention on a Chip Multi-Processor Architecture.pdf"  # Word 수식(Type3)
LIU_LAYLAND = "Scheduling Algorithms for Multiprogramming in a Hard-Real-Time Environment.pdf"  # 글꼴에 유니코드가 없다
TCPS = "TCPS a task and cache-aware partitioned scheduler for hard real-time multi-core systems.pdf"
CAAS = "CAAS Cache Affinity Aware Scheduling Framework for RTEMS with Edge Computing Support.pdf"
STACK_DISTANCE = "Efficient_Stack_Distance_Approximation_Based_on_Workload_Characteristics.pdf"
LLVM_REUSE = "LLVM Static Analysis for Program Characterization and Memory Reuse Profile Estimation.pdf"
PARTITIONED = "Partitioned_Scheduling_With_Shared_Resources_on_Imprecise_Mixed-Criticality_Multiprocessor_Systems.pdf"
POWER_OF_10 = "The_power_of_10_rules_for_developing_safety-critical_code.pdf"

KOREAN = "SMP 기반 RTEMS 운영체제 환경에서의 스케줄링 성능 분석.pdf"  # 메타데이터 제목이 HWP 파일 이름
FILE_NAME = re.compile(r"\.(?:pdf|docx?|hwpx?|tex|dvi|ps)$", re.IGNORECASE)


@pytest.fixture(scope="module")
def processed(tmp_path_factory) -> dict[str, dict]:
    """논문 이름 → {paper, pages, blocks(쪽 → 문단)}. 빈 데이터 폴더에 하나씩 올리고 본문 추출을 끝낸다."""
    data_dir = tmp_path_factory.mktemp("real-papers") / "data"
    app = create_app(Settings(app=AppSettings(mode="test", data_dir=data_dir), layout=LayoutSettings(model_path=MODEL)))
    client = TestClient(app)
    result = {}
    for name in NAMES:
        response = client.post(
            "/api/v1/papers",
            content=(PAPERS / name).read_bytes(),
            headers={"Content-Type": "application/pdf", "X-Paperloom-Filename": quote(name)},
        )
        assert response.status_code == 201, (name, response.text)
        while app.state.parsing.run_next():
            pass
        paper = client.get(f"/api/v1/papers/{response.json()['paper_id']}").json()
        version_id = paper["current_version"]["version_id"]
        pages = client.get(f"/api/v1/versions/{version_id}/pages").json()["pages"]
        blocks = {page["page_index"]: client.get(f"/api/v1/versions/{version_id}/pages/{page['page_index']}").json()["blocks"] for page in pages}
        result[name] = {"paper": paper, "pages": pages, "blocks": blocks}
    return result


def one(processed: dict[str, dict], name: str) -> dict:
    if name not in processed:
        pytest.skip(f"{name}이 tests/e2e_papers에 없다")
    return processed[name]


def text_of(item: dict) -> str:
    return "\n".join(block["text"] for blocks in item["blocks"].values() for block in blocks)


@pytest.mark.parametrize("name", NAMES)
def test_every_paper_is_extracted_without_errors(processed, name):
    item = processed[name]
    version = item["paper"]["current_version"]
    # 모두 글자 층이 있는 PDF다. 실패는 글꼴에 문자 정보가 없어 글자를 못 읽는 논문뿐이다
    assert version["status"] in ("INDEXED", "PARTIAL") or (version["status"], version["status_reason"]) == ("FAILED", "UNREADABLE_TEXT")
    assert [page["page_index"] for page in item["pages"] if "extract_failed" in page["flags"]] == []
    assert any(item["blocks"].values())


@pytest.mark.parametrize("name", NAMES)
def test_stored_text_has_no_control_private_use_or_noncharacters(processed, name):
    """제어 문자·사용자 영역(PUA) 글자·비문자(U+FFFE 등)는 검색·근거·번역 글에 남지 않는다(PUA는 첫 실행에서 7편에 남았다)."""
    found = [
        (page, block["text"][:60])
        for page, blocks in processed[name]["blocks"].items()
        for block in blocks
        if any(unicodedata.category(char) in ("Cc", "Co", "Cn") for char in block["text"])
    ]
    assert found == []


@pytest.mark.parametrize("name", NAMES)
def test_titles_are_paper_titles_not_file_names(processed, name):
    title = processed[name]["paper"]["title"]
    assert not looks_like_filename(title)
    assert not FILE_NAME.search(title)


def test_a_hwp_file_name_title_gives_way_to_the_first_page_title(processed):
    """첫 실행에서 찾음: 한글 문서를 바꾼 PDF의 메타데이터 제목이 "10. [25M-05-066M]_725-731_전현수_1차 수정.hwp"였다."""
    assert one(processed, KOREAN)["paper"]["title"] == "SMP 기반 RTEMS 운영체제 환경에서의 스케줄링 성능 분석"


def test_3b2_math_symbols_read_as_the_symbols_they_draw(processed):
    """2026-10-14 사용자 논문(IEEE TC, 3B2 조판): ( ) + =가 ð Þ þ ¼로 깨지고 ∗ ≤ −가 빠져 5·10쪽이 "일부"였다."""
    item = one(processed, SCHEDULABILITY)
    assert item["paper"]["current_version"]["status"] == "INDEXED"
    text = text_of(item)
    assert set("ðÞþ¼") & set(text) == set() and "1⁄4" not in text
    for expected in ("hp(k)", "lp(k)∪{tk}", "Di ≤ Dk", "C∗ i", "update←true"):
        assert expected in text


def test_numbered_chapters_and_sections_of_a_3b2_paper_are_in_the_outline(processed):
    """2026-10-16 사용자 스크린샷: 목차에 ACKNOWLEDGMENTS·REFERENCES만 나왔다. 장 제목 번호 뒤 1 em에 공백 글자가 없어
    "1INTRODUCTION"이 되고, 절 제목 "3.1 Task Model"(본문보다 큰 글꼴)이 바로 아래 문단과 묶였다."""
    item = one(processed, SCHEDULABILITY)
    titles = [entry["title"] for entry in headings([{"page_index": page, "blocks": blocks} for page, blocks in sorted(item["blocks"].items())])]
    for expected in ("1 INTRODUCTION", "2 RELATED WORK", "3 SYSTEM MODEL", "3.1 Task Model", "4 SCHEDULABILITY ANALYSIS", "4.1 Overview"):
        assert expected in titles


def test_paper_whose_equation_symbols_are_unreadable_says_so(processed):
    """2026-10-14 사용자 논문(Word 수식이 Type3 글꼴): 수식 기호만 못 읽은 4·5·6·10쪽 → "검색 가능 · 일부 기호를 읽지 못함"."""
    item = one(processed, PREDICTING)
    version = item["paper"]["current_version"]
    assert (version["status"], version["status_reason"]) == ("PARTIAL", "UNMAPPED_CHARS")
    assert [page["page_index"] for page in item["pages"] if page["text_status"] == "partial"] == [3, 4, 5, 9]


def test_paper_whose_text_cannot_be_read_is_not_called_searchable(processed):
    """첫 실행에서 찾음: 1973년 논문은 글꼴에 유니코드가 없어 쪽마다 글자 96–100%를 못 읽는다(스캔과 같다). 기호 일부가 아니다."""
    item = one(processed, LIU_LAYLAND)
    version = item["paper"]["current_version"]
    assert (version["status"], version["status_reason"]) == ("FAILED", "UNREADABLE_TEXT")
    assert {page["text_status"] for page in item["pages"]} == {"unreadable"}


def test_pseudocode_stays_out_of_translation(processed):
    """2026-10-05 사용자 논문 TCPS: 알고리즘 의사코드(Input: 문단이 든 상자)는 표 안 글로 보아 번역하지 않는다."""
    item = one(processed, TCPS)
    inputs = [block for blocks in item["blocks"].values() for block in blocks if block["text"].startswith("Input: Task parameters")]
    assert inputs and all("in_table" in block["quality_flags"] for block in inputs)


@pytest.mark.parametrize(("name", "page"), [(STACK_DISTANCE, 5), (LLVM_REUSE, 3)])
def test_pseudocode_taller_than_half_the_page_stays_out_of_translation(processed, name, page):
    """2026-10-16 사용자 논문(IEEE TIM 6쪽 Algorithm 1): 쪽 높이 절반이 넘는 의사코드 상자를 머리글·바닥글 줄 사이로 보고 넘겨
    번역에 들어갔다. 이 폴더의 두 논문도 같은 모양이었다(상자 높이 0.62). 같은 쪽 본문은 그대로 번역한다."""
    blocks = one(processed, name)["blocks"][page]
    starts = [block for block in blocks if block["text"].startswith("1: procedure")]
    assert starts and all("in_table" in block["quality_flags"] for block in starts)
    assert any(not block["quality_flags"] and len(block["text"]) > 200 for block in blocks)


def test_body_text_under_a_clipped_form_figure_is_not_figure_text(processed):
    """2026-10-17 사용자 요청: LLVM 4쪽 그림 5(Form 안에서 잘린 CFG)의 객체 상자가 쪽 가운데 아래까지 잡혀 그 아래 본문 17줄이
    그림 안 글자로 번역에서 빠졌다."""
    blocks = one(processed, LLVM_REUSE)["blocks"][3]
    [body] = [block for block in blocks if block["text"].startswith("Once we have the CFG")]
    assert "in_figure" not in body["quality_flags"]


def test_paragraphs_are_not_split_line_by_line(processed):
    """2026-10-04 사용자 논문 CAAS: 글꼴의 ascent·descent가 망가져 문단이 줄마다 나뉘었다(본문 쪽의 문단 길이 가운데값 > 100자)."""
    item = one(processed, CAAS)
    for page in (1, 2, 3, 5, 6):
        body = [len(block["text"]) for block in item["blocks"][page] if not block["quality_flags"]]
        assert statistics.median(body) > 100, page


@needs_model
def test_an_algorithm_the_rules_missed_stays_out_of_translation(processed):
    """2026-10-19 사용자 요청("알고리즘이나 표 이런 게 자꾸 번역되네"): 상자 줄이 없는 알고리즘(8쪽 Algorithm 1)은 규칙이 본문으로
    보아 번역했다. 레이아웃 모델이 알고리즘으로 본다. 캡션과 그 아래 본문은 번역한다."""
    blocks = one(processed, PARTITIONED)["blocks"][7]
    ties = [block for block in blocks if block["text"].startswith("In case of a tie")]
    assert len(ties) == 2 and all("in_table" in block["quality_flags"] for block in ties)
    [caption] = [block for block in blocks if block["text"].startswith("Algorithm 1: RA-CU-WFD")]
    [body] = [block for block in blocks if block["text"].startswith("Algorithm 1 presents the RA-CU-WFD algorithm")]
    assert not caption["quality_flags"] and not body["quality_flags"]


@needs_model
def test_body_text_the_rules_took_for_figure_text_is_translated(processed):
    """규칙의 그림 후보 상자가 본문 단을 덮어 The Power of 10 1–3쪽 본문이 그림 안 글자로 빠졌다(2026-10-19 평가). 모델이 본문으로
    확신하면 그림 표시를 뗀다."""
    item = one(processed, POWER_OF_10)
    for page, start in ((0, "Among the many coding guidelines"), (1, "Rule 5: The code’s assertion density"), (2, "If these rules seem draconian")):
        [block] = [block for block in item["blocks"][page] if block["text"].startswith(start)]
        assert "in_figure" not in block["quality_flags"], (page, start)
