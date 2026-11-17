"""서지 조회 worker (documents.bibliography, 2026-11-16 사용자 결정): 본문 추출이 끝났고 아직 묻지 않은 논문의 비어 있는 저자·연도를 채운다.

시작할 때와 본문 추출이 끝날 때마다(ParseService의 after_extract → notify) 묻는다. 네트워크를 기다리는 동안 추출을 막지 않게
따로 스레드에서 돈다. 네트워크·서버 오류면 그 논문을 묻지 않은 채 두고 그 차례를 멈췄다가, RETRY_SECONDS 뒤나 다음 추출 뒤에
다시 묻는다. 한 차례 안의 요청 사이는 PAUSE_SECONDS 쉰다(arXiv API의 요청 간격 안내가 3초다).
사용자가 논문 정보를 고친 논문은 묻지 않고, 물은 뒤에도 사용자가 채운 값은 덮지 않는다(repository.fill_bibliography).
"""

import json
import logging
import threading
import xml.etree.ElementTree as ElementTree
from collections.abc import Callable
from contextlib import closing
from pathlib import Path

from paperloom.documents import bibliography
from paperloom.documents import repository as documents
from paperloom.documents import text_repository as runs
from paperloom.infrastructure.database.sqlite import connect

log = logging.getLogger("paperloom.bibliography")

PAUSE_SECONDS = 3.0
RETRY_SECONDS = 3600.0

Fetch = Callable[[str, str], bibliography.Record | None]


class BibliographyService:
    def __init__(self, db_path: Path, fetch: Fetch | None = None, pause_seconds: float = PAUSE_SECONDS) -> None:
        self._db_path = db_path
        self._fetch = fetch
        self._pause_seconds = pause_seconds
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def notify(self) -> None:
        self._wake.set()

    def start(self) -> None:
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="paperloom-bibliography", daemon=True)
        self._thread.start()

    def stop(self, timeout_seconds: float = 5) -> None:
        """기다리던 요청은 끝까지 기다리지 않는다(묻지 않은 논문은 다음 시작 때 다시 묻는다)."""
        self._stop.set()
        self._wake.set()
        if self._thread is not None:
            self._thread.join(timeout_seconds)

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                self.run_pending()
            except Exception:
                log.exception("서지 조회를 처리하지 못했습니다.")
            self._wake.wait(RETRY_SECONDS)
            self._wake.clear()

    def run_pending(self) -> int:
        """아직 묻지 않은 논문을 차례로 묻고, 채우거나 묻지 않아도 된다고 적은 논문 수를 돌려준다. 네트워크 오류면 거기서 멈춘다."""
        with closing(connect(self._db_path)) as connection:
            pending = documents.papers_to_look_up(connection)
        done = 0
        asked = False
        for paper in pending:
            with closing(connect(self._db_path)) as connection:
                blocks = [
                    {"text": row["text"], "regions": json.loads(row["regions_json"]), "quality_flags": json.loads(row["quality_flags_json"])}
                    for row in runs.page_blocks(connection, paper["current_version_id"], 0)
                ]
            record, looked_up = None, "none"
            for kind, value in bibliography.identifiers(paper["doi"], blocks):
                if asked and self._stop.wait(self._pause_seconds):
                    return done
                asked = True
                try:
                    record = (self._fetch or bibliography.fetch)(kind, value)
                except (OSError, ValueError, ElementTree.ParseError):
                    log.warning("논문 %s의 서지를 %s:%s로 묻지 못했습니다. 나중에 다시 묻습니다.", paper["paper_id"], kind, value, exc_info=True)
                    return done
                looked_up = f"{kind}:{value}"
                if record is not None:
                    break
            with closing(connect(self._db_path)) as connection, connection:
                documents.fill_bibliography(connection, paper["paper_id"], looked_up, record.authors if record else [], record.year if record else None)
            log.info("논문 %s의 서지를 %s로 %s.", paper["paper_id"], looked_up, "채웠습니다" if record else "찾지 못했습니다")
            done += 1
        return done
