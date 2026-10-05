"""FastAPI 애플리케이션 조립. 도메인 라우터는 각 작업 패키지에서 여기에 연결한다."""

import logging
import mimetypes
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from paperloom import __version__
from paperloom.annotations.routes import build_router as build_annotations_router
from paperloom.answers.routes import build_router as build_answers_router
from paperloom.answers.service import AnswerService
from paperloom.annotations.service import AnnotationService
from paperloom.api.errors import install_error_handler
from paperloom.api.idempotency import IdempotencyStore
from paperloom.bootstrap.config import Settings
from paperloom.context.routes import build_router as build_context_router
from paperloom.context.service import ContextService
from paperloom.documents.parsing import ParseService
from paperloom.documents.routes import build_router as build_documents_router
from paperloom.documents.service import DocumentService, UploadLimits
from paperloom.infrastructure.database.sqlite import migrate
from paperloom.infrastructure.files.source_store import SourceStore
from paperloom.reading.routes import build_router as build_reading_router
from paperloom.reading.service import AnchorService
from paperloom.retrieval.routes import build_router as build_retrieval_router
from paperloom.retrieval.service import SearchService
from paperloom.preferences.routes import build_router as build_preferences_router
from paperloom.preferences.service import PreferenceService
from paperloom.threads.routes import build_router as build_threads_router
from paperloom.threads.service import ThreadService
from paperloom.translation.routes import build_router as build_translation_router
from paperloom.translation.service import TranslationService

log = logging.getLogger("paperloom")


def create_app(settings: Settings, upload_limits: UploadLimits = UploadLimits()) -> FastAPI:
    data_dir = settings.app.data_dir
    data_dir.mkdir(parents=True, exist_ok=True)
    db_path = data_dir / "paperloom.sqlite3"
    migrate(db_path)
    store = SourceStore(data_dir)
    if removed := store.discard_incomplete_uploads():
        log.warning("이전 실행에서 남은 임시 업로드 %d개를 지웠습니다.", removed)

    parsing = ParseService(db_path, store)

    # 본문 추출 worker는 서버와 함께 시작하고 멈춘다 (IMPL §5.2). 테스트는 app.state.parsing.run_next()로 직접 돌린다.
    @asynccontextmanager
    async def lifespan(_: FastAPI):
        parsing.start()
        try:
            yield
        finally:
            parsing.stop()

    app = FastAPI(title="Paperloom", version=__version__, lifespan=lifespan)
    app.state.parsing = parsing
    install_error_handler(app)

    @app.get("/api/v1/health")
    def health() -> JSONResponse:
        writable = _can_write(data_dir)
        body = {
            "status": "ok" if writable else "degraded",
            "version": __version__,
            "mode": settings.app.mode,
            "cost_policy": settings.cost_policy.mode,
            "data_dir_writable": writable,
            "claude_code_url": settings.app.claude_code_url,
        }
        return JSONResponse(body, status_code=200 if writable else 503)

    app.include_router(build_documents_router(DocumentService(store, db_path, upload_limits, parsing), parsing))
    app.include_router(build_retrieval_router(SearchService(db_path)))
    keys = IdempotencyStore(db_path)
    anchors = AnchorService(db_path, store)
    app.include_router(build_reading_router(anchors, keys))
    app.include_router(build_annotations_router(AnnotationService(db_path, anchors), keys))
    preferences = PreferenceService(db_path)
    app.include_router(build_preferences_router(preferences))
    contexts = ContextService(db_path, anchors, preferences)
    app.include_router(build_context_router(contexts, keys))
    answers = AnswerService(db_path)
    app.include_router(build_answers_router(answers))
    app.include_router(build_threads_router(ThreadService(db_path)))
    app.include_router(build_translation_router(TranslationService(db_path)))

    # API 라우트를 먼저 등록해야 정적 파일 mount가 /api 경로를 가리지 않는다.
    if web_dist_dir := settings.app.web_dist_dir:
        index_html = web_dist_dir / "index.html"

        # 버전 고정 링크(IMPL §4.3)와 답변 화면(U6)을 직접 열거나 새로고침해도 웹앱을 돌려준다. 화면 선택은 웹앱이 한다.
        # index.html은 매번 다시 확인하게 한다(다시 빌드한 뒤 새로고침해도 옛 웹앱이 남지 않게). assets는 이름에 해시가 있다.
        def index_page() -> FileResponse:
            return FileResponse(index_html, headers={"Cache-Control": "no-cache"})

        app.get("/", include_in_schema=False)(index_page)
        app.get("/answers", include_in_schema=False)(index_page)

        @app.get("/reader/{path:path}", include_in_schema=False)
        def reader_page(path: str) -> FileResponse:
            return index_page()

        # StaticFiles는 mimetypes로 형식을 정하는데, Windows에서는 레지스트리 값이 기본값을 덮어쓴다. 스크립트가 JS가 아니면
        # 브라우저가 module(웹앱, PDF.js worker .mjs)을 거부해 PDF가 열리지 않는다(2026-10-05 GitHub Actions Windows E2E).
        mimetypes.add_type("text/javascript", ".js")
        mimetypes.add_type("text/javascript", ".mjs")
        app.mount("/", StaticFiles(directory=web_dist_dir, html=True), name="web")
    return app


def _can_write(directory: Path) -> bool:
    # Windows에서는 os.access가 디렉터리 쓰기 가능 여부를 신뢰성 있게 알려 주지 않는다.
    try:
        with tempfile.TemporaryFile(dir=directory):
            return True
    except OSError:
        return False
