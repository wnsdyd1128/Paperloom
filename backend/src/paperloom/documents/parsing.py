"""본문 추출 작업 (IMPL §5.2–5.3): 대기열, lease, 재시도, 결과 저장, 백그라운드 worker.

업로드가 run을 QUEUED로 넣고, worker 스레드가 하나씩 가져가 격리 하위 프로세스에서 쪽 묶음(chunk_pages)을
추출한다. 묶음이 시간 초과·비정상 종료로 실패하면 그 묶음을 한 쪽씩 다시 추출한다. 그래도 실패한 쪽은 까닭에 맞춰 되살려
본다(_recover: 시간 초과면 더 긴 시간으로, 그래도 안 되거나 하위 프로세스가 죽었으면 간이 추출). 끝내 안 된 쪽만
`extract_failed`로 남긴다. 레이아웃 모델(documents.layout_model)이 있으면 하위 프로세스가 그린 쪽 그림에서 영역을 찾아 문단의
본문 아님 표시를 고친다(layout_regions). 모델이 없거나 실패한 쪽은 규칙 표시 그대로다.

- 버전 상태: READY_TO_READ(추출 전) → PARSING → INDEXED | PARTIAL | FAILED(+ status_reason, PARTIAL은 기호만 못 읽었을 때
  UNMAPPED_CHARS). 어느 상태든 원본은 읽을 수 있다.
- 재시작: 시작할 때 이전 프로세스가 실행 중이던 run을 대기열로 되돌리고, 지금 추출기로 추출한 적 없는 버전을 넣는다.
  같은 데이터를 쓰는 다른 프로세스가 있어도 결과는 lease를 가진 worker만 저장한다.
- 재시도: 하위 프로세스를 띄우지 못하는 등의 I/O 오류는 대기열로 되돌려 한 번 더 한다. run을 max_attempts번
  가져가고도 끝내지 못하면 FAILED(PARSER_ERROR)다. 그 뒤는 사용자가 다시 요청한다(request).
"""

import json
import logging
import sqlite3
import tempfile
import threading
import time
import uuid
from collections.abc import Callable
from contextlib import closing
from dataclasses import dataclass
from importlib.metadata import version as package_version
from pathlib import Path

from paperloom.documents import repository as documents
from paperloom.documents import text_repository as runs
from paperloom.documents.extract import PARSER_NAME, ExtractFailed, extract_pages
from paperloom.documents.metadata import DOI_PAGES, find_doi, paper_doi
from paperloom.documents.block_kinds import NO_BODY_TEXT, NOT_BODY, REFERENCE
from paperloom.documents.inspect import clean_text
from paperloom.documents.layout_model import LayoutModel
from paperloom.documents.layout_regions import apply_layout
from paperloom.documents.references import REFERENCES_FLAG, REFERENCES_VERSION, reference_blocks, reference_pages
from paperloom.documents.running import running_lines
from paperloom.documents.text_layout import LAYOUT_VERSION, config_hash, document_status
from paperloom.documents.titles import looks_like_filename, title_from_blocks
from paperloom.infrastructure.clock import utc_now
from paperloom.infrastructure.database.sqlite import connect
from paperloom.infrastructure.files.source_store import SourceStore

log = logging.getLogger("paperloom.parsing")

# 문서 전체를 열지 못한 오류는 쪽마다 다시 해도 같다.
_DOCUMENT_ERRORS = {"PASSWORD_REQUIRED", "MALFORMED_PDF"}


@dataclass(frozen=True)
class ParseSettings:
    chunk_pages: int = 25
    chunk_timeout_seconds: float = 30
    page_retry_timeout_seconds: float = 90  # 실패한 한 쪽을 되살릴 때(_recover)의 시간 제한. lease보다 짧아야 한다
    lease_seconds: float = 120  # 한 묶음의 시간 제한보다 길어야 한다. 묶음마다 연장한다
    max_attempts: int = 2  # 자동 재시도 1회
    poll_seconds: float = 5


class ParseInProgress(Exception):
    pass


def _stored_block(row: sqlite3.Row) -> dict:
    """저장된 문단(text_repository.page_blocks)을 제목 찾기(titles.title_from_blocks)가 읽는 꼴로"""
    return {"text": row["text"], "regions": json.loads(row["regions_json"]), "font_size": row["font_size"], "quality_flags": json.loads(row["quality_flags_json"])}


def _marked(page: dict, marks: dict[tuple[int, int], list[str]]) -> dict:
    """쪽의 문단에 표시를 더하고(레이아웃 모델이 이미 붙인 표시는 겹치지 않게), 글은 있지만 모두 본문이 아닌 쪽에 no_body_text를 붙인다."""
    blocks = [
        {**block, "quality_flags": [*block["quality_flags"], *(flag for flag in marks.get((page["page_index"], index), []) if flag not in block["quality_flags"])]}
        for index, block in enumerate(page["blocks"])
    ]
    no_body = bool(blocks) and all(NOT_BODY.intersection(block["quality_flags"]) for block in blocks)
    return {**page, "blocks": blocks, "flags": [*page["flags"], NO_BODY_TEXT] if no_body else page["flags"]}


class ParseService:
    def __init__(
        self,
        db_path: Path,
        store: SourceStore,
        settings: ParseSettings = ParseSettings(),
        clock: Callable[[], float] = time.time,
        layout: LayoutModel | None = None,
    ) -> None:
        self._db_path = db_path
        self._store = store
        self._settings = settings
        self._clock = clock
        self._layout = layout
        self._worker_id = f"worker-{uuid.uuid4()}"
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.parser_version = f"{package_version('pypdfium2')}+layout{LAYOUT_VERSION}+refs{REFERENCES_VERSION}"
        if layout is not None:
            self.parser_version += f"+dla-{layout.identity()}"  # 모델을 켜거나 끄거나 바꾸면 다시 추출한다
        self.config_hash = config_hash()

    # 대기열 -----------------------------------------------------------------

    def enqueue(self, connection: sqlite3.Connection, version_id: str) -> str:
        """호출자의 트랜잭션 안에서 run을 넣는다. commit 뒤에 notify()를 부른다."""
        return runs.insert_run(connection, version_id, PARSER_NAME, self.parser_version, self.config_hash, utc_now())

    def notify(self) -> None:
        self._wake.set()

    def request(self, version_id: str) -> str | None:
        """사용자가 다시 추출을 요청한다. 버전이 없으면 None, 이미 대기·실행 중이면 ParseInProgress."""
        with closing(connect(self._db_path)) as connection:
            if documents.get_version(connection, version_id) is None:
                return None
            with connection:
                if runs.active_run(connection, version_id):
                    raise ParseInProgress()
                run_id = self.enqueue(connection, version_id)
        self.notify()
        return run_id

    def prepare(self) -> None:
        """시작할 때 한 번: 멈춘 run을 되돌리고, 지금 추출기로 추출하지 않은 버전을 넣는다."""
        with closing(connect(self._db_path)) as connection, connection:
            if released := runs.release_abandoned(connection, self._worker_id):
                log.warning("이전 실행에서 끝나지 않은 본문 추출 %d개를 다시 대기열에 넣었습니다.", released)
            for version_id in runs.versions_without_run(connection, self.parser_version, self.config_hash):
                self.enqueue(connection, version_id)
            # DOI 찾기(D5) 전에 추출한 논문은 저장된 앞쪽 문단에서 찾는다. 다시 추출하면 문단 ID가 바뀌어 저장된 답의
            # 문단 근거가 끊기므로 추출기 버전을 올리지 않았다.
            # 메타데이터 제목의 표시 태그를 빼기 전에 올린 논문(2026-10-03): 제목에서 태그를 뺀다(검색 색인은 트리거가 맞춘다)
            for paper_id, title in documents.titles_with_markup(connection):
                if (cleaned := clean_text(title)) and cleaned != title:
                    documents.fix_title(connection, paper_id, cleaned)
            # 첫 쪽에서 제목을 찾기 전(2026-10-05)에 파일 이름(1706.03762v7)으로 등록한 논문: 저장된 첫 쪽에서 제목을 찾는다
            for paper_id, version_id in documents.filename_titles(connection):
                if title := title_from_blocks([_stored_block(row) for row in runs.page_blocks(connection, version_id, 0)]):
                    documents.fix_title(connection, paper_id, title)
            for paper_id, version_id in documents.papers_without_doi(connection):
                rows = runs.blocks_on_pages(connection, version_id, list(range(DOI_PAGES)))
                if doi := find_doi([row["text"] for row in rows]):
                    documents.fill_doi(connection, paper_id, doi)

    # worker -----------------------------------------------------------------

    def start(self) -> None:
        self.prepare()
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="paperloom-parse", daemon=True)
        self._thread.start()

    def stop(self, timeout_seconds: float = 5) -> None:
        """다음 작업을 가져가지 않게 한다. 실행 중인 하위 프로세스는 기다리지 않는다(lease가 끝나면 다시 한다)."""
        self._stop.set()
        self._wake.set()
        if self._thread is not None:
            self._thread.join(timeout_seconds)

    def _loop(self) -> None:
        if self._layout is not None:
            try:
                self._layout.load()  # 첫 추출이 모델 열기를 기다리지 않게, health가 장치를 보이게
            except Exception:  # noqa: BLE001 - 쪽마다 다시 해 보고, 안 되면 규칙 표시만 쓴다(_with_layout)
                log.warning("레이아웃 모델을 열지 못했습니다.", exc_info=True)
        while not self._stop.is_set():
            try:
                worked = self.run_next()
            except Exception:
                log.exception("본문 추출 작업을 처리하지 못했습니다.")
                worked = False
            if not worked:
                self._wake.wait(self._settings.poll_seconds)
                self._wake.clear()

    def run_next(self) -> bool:
        """대기 중인 run 하나를 처리한다. 처리할 것이 없거나 재시도로 되돌렸으면 False."""
        run = self._claim()
        if run is None:
            return False
        return self._execute(run)

    def _claim(self) -> runs.ParseRun | None:
        with closing(connect(self._db_path)) as connection:
            while True:
                with connection:
                    run = runs.next_claimable(connection, self._clock())
                    if run is None:
                        return None
                    if run.attempts >= self._settings.max_attempts:
                        self._fail(connection, run, owner=None)
                        continue
                    if runs.claim(connection, run, self._worker_id, self._clock() + self._settings.lease_seconds, utc_now()):
                        runs.set_version_status(connection, run.version_id, "PARSING")
                        return runs.ParseRun(run.parse_run_id, run.version_id, "RUNNING", run.attempts + 1, None)

    def _execute(self, run: runs.ParseRun) -> bool:
        started = time.monotonic()
        with closing(connect(self._db_path)) as connection:
            version = documents.get_version(connection, run.version_id)
            storage_ref = documents.get_storage_ref(connection, run.version_id)
        try:
            if version is None or storage_ref is None or not (path := self._store.path_for(storage_ref)).is_file():
                raise FileNotFoundError(run.version_id)
            pages: list[dict] = []
            with tempfile.TemporaryDirectory(prefix="paperloom-layout-") as images:
                for first in range(0, version.page_count, self._settings.chunk_pages):
                    stop = min(first + self._settings.chunk_pages, version.page_count)
                    pages += self._extract_range(path, first, stop, run, Path(images) if self._layout else None)
                    if not self._extend_lease(run):
                        log.warning("본문 추출 %s의 lease를 잃어 결과를 버립니다.", run.parse_run_id)
                        return True
        except OSError:
            log.warning("본문 추출 %s가 I/O 오류로 멈췄습니다 (시도 %d).", run.parse_run_id, run.attempts, exc_info=True)
            self._retry_or_fail(run)
            return False
        status, reason = document_status([(page["text_status"], page["quality"]) for page in pages])
        # 참고문헌 쪽은 문서 전체의 문단을 본 뒤에 정한다(쪽 묶음별 추출로는 알 수 없다).
        references = set(reference_pages(pages))
        pages = [{**page, "flags": [*page["flags"], REFERENCES_FLAG]} if page["page_index"] in references else page for page in pages]
        # 쪽마다 되풀이되는 머리글·바닥글과 참고문헌 부분 문단도 문서 전체를 본 뒤 표시한다(쪽 번역에서 뺀다)
        marks = {key: [flag] for key, flag in running_lines(pages).items()}
        for key in reference_blocks(pages):
            marks.setdefault(key, []).append(REFERENCE)
        pages = [_marked(page, marks) for page in pages]
        doi = paper_doi(pages)
        with closing(connect(self._db_path)) as connection, connection:
            if not runs.finish_run(connection, run.parse_run_id, self._worker_id, "DONE", utc_now()):
                log.warning("본문 추출 %s의 lease를 잃어 결과를 버립니다.", run.parse_run_id)
                return True
            runs.replace_extraction(connection, run.version_id, run.parse_run_id, pages)
            if doi:
                documents.fill_doi(connection, version.paper_id, doi)
            # 등록 때 첫 쪽을 읽지 못해 파일 이름이 제목이 된 논문은 추출한 첫 쪽에서 제목을 찾는다
            paper = documents.get_paper(connection, version.paper_id)
            first = next((page for page in pages if page["page_index"] == 0), None)
            if paper and first and looks_like_filename(paper.title) and (title := title_from_blocks(first["blocks"])):
                documents.fix_title(connection, version.paper_id, title)
            runs.set_version_status(connection, run.version_id, status, reason)
        log.info(
            "본문 추출 %s 끝: version=%s status=%s reason=%s pages=%d parser=%s %.2fs",
            run.parse_run_id, run.version_id, status, reason, len(pages), self.parser_version, time.monotonic() - started,
        )
        return True

    def _extract_range(self, path: Path, first: int, stop: int, run: runs.ParseRun, images: Path | None) -> list[dict]:
        """images는 레이아웃 모델 입력 그림을 둘 폴더다(모델이 없으면 None)."""
        try:
            return self._with_layout(extract_pages(path, first, stop, self._settings.chunk_timeout_seconds, images=images), images)
        except ExtractFailed as failed:
            if failed.code in _DOCUMENT_ERRORS:
                return [_failed_page(index, failed.code) for index in range(first, stop)]
            if stop - first == 1:
                return [self._recover(path, first, failed.code, run, images)]
            return [page for index in range(first, stop) for page in self._extract_range(path, index, index + 1, run, images)]

    def _with_layout(self, pages: list[dict], images: Path | None) -> list[dict]:
        """레이아웃 모델로 문단 표시를 고친다. 쪽 그림이 없거나(간이 추출, 그리지 못한 쪽) 모델이 실패한 쪽은 규칙 표시 그대로다."""
        if images is None:
            return pages
        result = []
        for page in pages:
            image = images / f"{page['page_index']}.rgb"
            if image.is_file():
                try:
                    page = apply_layout(page, self._layout.detect(image.read_bytes()))
                except Exception:  # noqa: BLE001 - 모델 실패는 규칙 표시로 둔다
                    log.warning("레이아웃 모델이 %d쪽을 보지 못해 규칙 표시만 씁니다.", page["page_index"] + 1, exc_info=True)
                finally:
                    image.unlink()
            result.append(page)
        return result

    def _recover(self, path: Path, index: int, code: str, run: runs.ParseRun, images: Path | None) -> dict:
        """한 쪽 추출이 실패하면 까닭에 맞춰 다시 해 본다(2026-10-17 사용자 요청: 쪽 번역이 읽지 못한 답을 고쳐 받는 것처럼).
        시간이 모자랐으면(RESOURCE_LIMIT) 더 긴 시간으로 한 번, 그래도 안 되거나 하위 프로세스가 죽었으면(PARSER_ERROR 등 — 같은
        추출을 다시 해도 같다) 글꼴 사전·그림 분석 없이 글자만 뽑는다(간이 추출, extract_simplified). 끝내 안 되면 extract_failed."""
        attempts = [False, True] if code == "RESOURCE_LIMIT" else [True]
        for plain in attempts:
            self._extend_lease(run)  # 한 쪽에 오래 걸려도 다른 worker가 run을 가져가지 않게
            try:
                pages = extract_pages(path, index, index + 1, self._settings.page_retry_timeout_seconds, plain=plain, images=None if plain else images)
            except ExtractFailed as failed:
                code = failed.code
                continue
            log.info("본문 추출 %s의 %d쪽을 %s 되살렸습니다.", run.parse_run_id, index + 1, "간이 추출로" if plain else "더 긴 시간으로")
            [page] = self._with_layout(pages, images)
            return page
        log.warning("본문 추출 %s의 %d쪽을 되살리지 못했습니다(%s).", run.parse_run_id, index + 1, code)
        return _failed_page(index, code)

    def _extend_lease(self, run: runs.ParseRun) -> bool:
        with closing(connect(self._db_path)) as connection, connection:
            return runs.extend_lease(connection, run.parse_run_id, self._worker_id, self._clock() + self._settings.lease_seconds)

    def _retry_or_fail(self, run: runs.ParseRun) -> None:
        with closing(connect(self._db_path)) as connection, connection:
            if run.attempts < self._settings.max_attempts:
                runs.release(connection, run.parse_run_id, self._worker_id)
            else:
                self._fail(connection, run, owner=self._worker_id)

    def _fail(self, connection: sqlite3.Connection, run: runs.ParseRun, owner: str | None) -> None:
        """끝내지 못한 run. owner가 None이면 시도 횟수를 다 쓰고 대기 중이거나 lease가 끝난 run이다.
        옛 추출 결과도 지워, 검색되는 내용과 버전 상태가 어긋나지 않게 한다."""
        if owner is None:
            failed = runs.give_up(connection, run, utc_now(), "PARSER_ERROR")
        else:
            failed = runs.finish_run(connection, run.parse_run_id, owner, "FAILED", utc_now(), "PARSER_ERROR")
        if failed:
            runs.clear_extraction(connection, run.version_id)
            runs.set_version_status(connection, run.version_id, "FAILED", "PARSER_ERROR")
            log.warning("본문 추출 %s를 %d번 시도하고 멈췄습니다.", run.parse_run_id, run.attempts)


def _failed_page(page_index: int, code: str) -> dict:
    return {
        "page_index": page_index,
        "page_label": None,
        "view_box": None,
        "rotation": 0,
        "text_status": "unknown",
        "flags": ["extract_failed"],
        "quality": {"chars": 0, "unmapped_chars": 0, "image_coverage": 0.0, "error": code},
        "blocks": [],
    }
