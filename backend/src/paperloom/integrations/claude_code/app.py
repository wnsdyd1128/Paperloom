"""Reader의 "Claude와 대화" 탭이 부르는 이 PC의 브리지 HTTP 앱 (ADR 0003).

- 127.0.0.1에서만 열고, Host가 이 주소가 아니면 거부한다(DNS rebinding 방지).
- Paperloom 웹 주소(origins)에서 온 요청만 받는다. 다른 웹 페이지가 사용자의 구독 사용량을 쓰지 못하게 한다.
- 받는 것은 packet ID와 질문뿐이다. 근거 글·이미지는 브리지가 Core에서 직접 읽는다(임의의 글을 모델에 보내는 통로가 아니다).
- 대화는 논문마다 이어질 수 있다. 이어 묻기는 이 브리지가 답을 저장한 대화 ID로만 한다(다른 Claude Code 세션을
  열지 못한다). 그 대화에 처음 보내는 packet이면 그 근거 글·이미지를 함께 보내고, 이미 보낸 packet이면 질문만 보낸다.
- 한 번에 한 차례만 실행한다(일반적인 개인 사용). 브라우저가 끊겨도 차례를 끝까지 실행해 답을 저장한다.
  첫 사건(start)의 실행 ID로 중단(/cancel)하면 Claude Code를 끝내고 답을 저장하지 않는다(2026-10-02 사용자 요청).
- 갈래(fork): 저장된 대화를 이어받은 새 대화로 묻는다(Claude Code --fork-session). 원래 대화는 그대로다.
- 쪽 번역(U7, `POST /translate-page`): 받는 것은 버전 ID와 쪽 번호뿐이다. 문단은 Core에서 읽어 문장으로 나누고, 문장마다
  번역을 JSON으로 받아 검사한 뒤 Core에 저장한다. 저장된 쪽은 다시 실행하지 않는다(다시 번역은 force). 대화와 같은
  자물쇠로 한 번에 한 차례다(UI_PLAN D3·D10, ADR 0003).
- 로그에는 packet ID·결과·시간만 남기고 질문·답은 남기지 않는다(IMPL §15).
"""

import base64
import json
import logging
import queue
import threading
import time
import uuid
from collections.abc import Iterator
from concurrent.futures import FIRST_EXCEPTION, ThreadPoolExecutor, wait
from typing import Literal

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from paperloom.answers.models import MAX_PROMPT_CHARS, UUID_PATTERN
from paperloom.integrations.claude_code.cli import RUN_TIMEOUT_SECONDS, ClaudeCli, ClaudeNotReady
from paperloom.integrations.claude_code.core import CoreClient, CoreRefused, CoreUnavailable
from paperloom.integrations.claude_code.page_translation import (
    TRANSLATION_PROMPT,
    BadTranslation,
    group_context,
    parse_translation,
    split_units,
    translation_request,
    translation_units,
)
from paperloom.integrations.claude_code.personalization import personalization

# 설정을 읽지 못했을 때(설정 REST가 없는 예전 Core)의 기본 모델. 설정의 처음 값과 같다(사용자 결정 D7).
DEFAULT_MODEL = "sonnet"
# 생각의 깊이(--effort, 2026-10-04 사용자 요청): 대화는 깊게, 쪽 번역은 빠르게. 넘기지 않으면 medium이었다
CHAT_EFFORT = "high"
TRANSLATION_EFFORT = "low"

log = logging.getLogger("paperloom.claude_code")


class ChatIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    packet_id: str = Field(min_length=1, max_length=100)
    question: str = Field(max_length=MAX_PROMPT_CHARS)
    session_id: str | None = Field(default=None, pattern=UUID_PATTERN)  # 없으면 새 대화
    model: Literal["sonnet", "opus", "haiku"] | None = None  # 없으면 Claude Code 계정 기본값
    fork: bool = False  # session_id 대화를 이어받은 새 대화(갈래)로 묻는다
    fork_at: str | None = Field(default=None, min_length=1, max_length=100)  # 갈래가 이 답까지만 이어받는다(답 ID)

    @field_validator("question")
    @classmethod
    def _question_has_text(cls, question: str) -> str:
        question = question.strip()
        if not question:
            raise ValueError("질문이 비어 있습니다.")
        return question

    @model_validator(mode="after")
    def _fork_needs_a_conversation(self) -> "ChatIn":
        if self.fork and self.session_id is None:
            raise ValueError("갈래는 이어받을 대화(session_id)가 있어야 합니다.")
        if self.fork_at is not None and not self.fork:
            raise ValueError("갈라질 답(fork_at)은 갈래에만 줍니다.")
        return self


class TranslatePageIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version_id: str = Field(min_length=1, max_length=100)
    page_index: int = Field(ge=0, le=100_000)
    force: bool = False  # 저장된 번역이 있어도 다시 번역한다(다시 번역 단추)
    split: bool = False  # 보는 쪽: 문단 묶음으로 나눠 동시에 번역한다(2026-10-03 사용자 결정). 모든 쪽 번역의 다른 쪽은 통째로


class CancelIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str = Field(min_length=1, max_length=100)


def build_app(cli: ClaudeCli, core: CoreClient, origins: set[str], port: int) -> FastAPI:
    app = FastAPI(title="Paperloom Claude Code bridge", docs_url=None, redoc_url=None, openapi_url=None)
    hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}
    # 대화와 쪽 번역은 따로 한 차례씩이다(2026-10-03 사용자 결정: 번역 중에도 대화는 바로 답한다)
    busy = threading.Lock()  # 대화
    translating = threading.Lock()  # 쪽 번역
    running = _Running()  # 지금 실행 중인 차례들(중단용)

    @app.middleware("http")
    async def guard(request: Request, call_next):
        if request.headers.get("host") not in hosts:
            return _error(403, "FORBIDDEN_HOST", "이 브리지는 127.0.0.1에서만 받습니다.")
        origin = request.headers.get("origin")
        if (origin is not None or request.method == "POST") and origin not in origins:
            return _error(403, "FORBIDDEN_ORIGIN", "Paperloom 웹에서 온 요청만 받습니다.")
        return await call_next(request)

    # 나중에 더한 CORS가 바깥이다. preflight(OPTIONS)는 CORS가 직접 답하고(허락한 origin만), 실제 요청은 guard를 거친다.
    app.add_middleware(CORSMiddleware, allow_origins=sorted(origins), allow_methods=["GET", "POST"], allow_headers=["Content-Type"])

    @app.get("/health")
    def health() -> dict:
        status = cli.status()
        try:
            cli.check_ready()
            error = None
        except ClaudeNotReady as not_ready:
            error = {"code": not_ready.code, "message": not_ready.message}
        return {"bridge": "paperloom-claude-code", "ready": error is None, "claude": status, "error": error, "paperloom_url": core.base_url}

    @app.post("/chat")
    def chat(body: ChatIn):
        try:
            cli.check_ready()
        except ClaudeNotReady as not_ready:
            return _error(503, not_ready.code, not_ready.message)
        if not busy.acquire(blocking=False):
            return _error(409, "BUSY", "앞 질문의 답을 만드는 중입니다. 끝난 뒤 다시 보내세요.")
        try:
            content, resume_at, intent = _content(core, body)
            preferences = _preferences(core)
            core.hand_off(body.packet_id)
        except CoreUnavailable:
            busy.release()
            return _error(503, "PAPERLOOM_NOT_RUNNING", "이 컴퓨터의 Paperloom에 연결할 수 없습니다.")
        except CoreRefused as refused:
            busy.release()
            return _error(refused.status, refused.code, refused.message)
        except _Refused as refused:
            busy.release()
            return _error(refused.status, refused.code, refused.message)
        events: queue.Queue = queue.Queue()
        run_id, cancel = running.begin()
        # 대화창에서 모델을 고르지 않으면 설정의 기본 모델(D7). 답 언어·개인화는 기본 규칙 뒤에 붙인다(A3).
        model = body.model or preferences.get("default_model") or DEFAULT_MODEL
        turn = (cli, core, body, content, resume_at, events, busy, running, run_id, cancel, model, personalization(preferences, intent))
        threading.Thread(target=_turn, args=turn, daemon=True).start()
        return StreamingResponse(_stream(events), media_type="application/x-ndjson")

    @app.post("/translate-page")
    def translate_page(body: TranslatePageIn):
        """쪽 하나를 번역해 Core에 저장하고 그 번역을 돌려준다({translation, cached}). 이미 저장된 쪽이면 실행하지 않는다."""
        try:
            cli.check_ready()
        except ClaudeNotReady as not_ready:
            return _error(503, not_ready.code, not_ready.message)
        try:
            preferences = _preferences(core)
            language = preferences.get("answer_language") or "ko"
            if not body.force and (saved := core.page_translation(body.version_id, body.page_index, language)) is not None:
                return {"translation": saved, "cached": True}
        except CoreUnavailable:
            return _error(503, "PAPERLOOM_NOT_RUNNING", "이 컴퓨터의 Paperloom에 연결할 수 없습니다.")
        except CoreRefused as refused:
            return _error(refused.status, refused.code, refused.message)
        if not translating.acquire(blocking=False):
            return _error(409, "BUSY", "다른 쪽을 번역하는 중입니다. 끝난 뒤 다시 번역합니다.")
        run_id, cancel = running.begin()
        started, outcome, groups = time.monotonic(), "error", 0
        try:
            units = translation_units(core.page_text(body.version_id, body.page_index)["blocks"])
            if not units:
                outcome = "no_text"
                return _error(422, "NO_TEXT", "이 쪽에는 번역할 글이 없습니다(그림·이미지뿐인 쪽).")
            model = preferences.get("default_model") or DEFAULT_MODEL  # D9: 설정의 기본 모델
            parts = split_units(units) if body.split else [units]
            groups = len(parts)
            blocks = _translate_groups(cli, parts, model, cancel, personalization(preferences, "translate"))
            translation = core.save_page_translation(body.version_id, body.page_index, language, model, blocks)
            outcome = "ok"
            return {"translation": translation, "cached": False}
        except _ClaudeFailed as failed:
            return _error(502, "CLAUDE_FAILED", failed.message or "Claude Code가 번역하지 못했습니다.")
        except BadTranslation:
            outcome = "bad_translation"
            return _error(502, "BAD_TRANSLATION", "Claude의 번역 응답을 읽지 못했습니다(문장 빠짐·JSON 아님). 다시 번역하세요.")
        except CoreUnavailable:
            return _error(503, "PAPERLOOM_NOT_RUNNING", "이 컴퓨터의 Paperloom에 연결할 수 없습니다.")
        except CoreRefused as refused:
            return _error(refused.status, refused.code, refused.message)
        finally:
            running.end(run_id)
            translating.release()
            log.info(
                "쪽 번역 version=%s page=%d 다시=%s 묶음=%d 결과=%s %.1f초",
                body.version_id, body.page_index, body.force, groups, outcome, time.monotonic() - started,
            )

    @app.post("/cancel")
    def cancel(body: CancelIn):
        """실행 ID가 지금 실행 중인 차례면 중단한다. 다른 실행·끝난 실행은 404다."""
        if not running.cancel(body.run_id):
            return _error(404, "NO_SUCH_RUN", "지금 실행 중인 그 차례가 없습니다.")
        return {"cancelled": True}

    return app


class _ClaudeFailed(Exception):
    def __init__(self, message: str | None) -> None:
        super().__init__(message)
        self.message = message


def _translate_groups(cli: ClaudeCli, groups: list, model: str, cancel: threading.Event, system_extra: str) -> list[dict]:
    """문단 묶음마다 Claude Code를 동시에 실행해(묶음 하나면 하나) 번역을 받아 쪽 차례대로 잇는다. 둘째 묶음부터는 앞 문단을
    참고로 붙인다. 묶음 하나라도 실패하면 나머지를 멈추고 그 실패를 낸다(쪽 전체를 저장하지 않는다)."""

    def translate(index: int) -> list[dict]:
        context = group_context(groups[index - 1][-1]) if index else None
        content = [{"type": "text", "text": translation_request(groups[index], context)}]
        run = cli.run(content, model=model, cancel=cancel, system_prompt=TRANSLATION_PROMPT, system_extra=system_extra, effort=TRANSLATION_EFFORT)
        result = [event for event in run if event["type"] == "result"][-1]
        if result["is_error"]:
            raise _ClaudeFailed(result["error"])
        return parse_translation(result["text"], groups[index])

    with ThreadPoolExecutor(max_workers=len(groups)) as pool:
        futures = [pool.submit(translate, index) for index in range(len(groups))]
        wait(futures, return_when=FIRST_EXCEPTION)
        failed = next((future.exception() for future in futures if future.done() and future.exception()), None)
        if failed is not None:
            cancel.set()  # 아직 도는 묶음을 멈춘다
            raise failed
        return [block for future in futures for block in future.result()]


class _Running:
    """지금 실행 중인 차례들의 ID와 중단 신호(대화 한 차례와 쪽 번역 한 차례가 함께 돌 수 있다)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._runs: dict[str, threading.Event] = {}

    def begin(self) -> tuple[str, threading.Event]:
        run_id, event = str(uuid.uuid4()), threading.Event()
        with self._lock:
            self._runs[run_id] = event
        return run_id, event

    def end(self, run_id: str) -> None:
        with self._lock:
            self._runs.pop(run_id, None)

    def cancel(self, run_id: str) -> bool:
        with self._lock:
            event = self._runs.get(run_id)
        if event is None:
            return False
        event.set()
        return True


class _Refused(Exception):
    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status, self.code, self.message = status, code, message


def _preferences(core: CoreClient) -> dict:
    """사용자 설정. 설정 REST가 없는 예전 Core면 기본값({})으로 묻는다."""
    try:
        return core.preferences()
    except CoreRefused:
        return {}


def _content(core: CoreClient, body: ChatIn) -> tuple[list[dict], str | None, str | None]:
    """(모델에 보낼 메시지, 갈래가 이어받을 마지막 메시지 ID, packet 요청 종류). 그 대화(갈래면 이어받는 차례)에 처음
    보내는 packet이면 근거 글과 영역 이미지를 붙이고, 아니면 질문만."""
    packet = core.packet(body.packet_id)
    if packet is None:
        raise _Refused(404, "PACKET_NOT_FOUND", "문맥을 찾을 수 없습니다.")
    resume_at = None
    if body.session_id is not None:
        turns = core.session_answers(body.session_id)  # 최근 것부터
        if not turns:
            raise _Refused(409, "UNKNOWN_SESSION", "이어 갈 수 없는 대화입니다. 새 대화로 물어 주세요.")
        if body.fork_at is not None:
            index = next((index for index, item in enumerate(turns) if item["answer_id"] == body.fork_at), None)
            if index is None:
                raise _Refused(409, "UNKNOWN_TURN", "그 대화의 답이 아닙니다.")
            resume_at = turns[index].get("message_id")
            if not resume_at:
                raise _Refused(409, "NO_FORK_POINT", "이 답은 갈라질 자리를 모릅니다(이 기능 전에 저장한 답). 대화 전체를 이어받는 갈래를 쓰세요.")
            turns = turns[index:]  # 갈래가 이어받는 차례(그 답과 그 전)
        if any(item["packet_id"] == body.packet_id for item in turns):
            return [{"type": "text", "text": body.question}], resume_at, packet.get("intent")
    text = core.markdown(body.packet_id)
    if body.question != packet["question"].strip():
        text += f"\n\n## 이번 질문\n\n{body.question}"
    images = [
        {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": base64.b64encode(core.image(item["image"]["url"])).decode()}}
        for item in packet["evidence"]
        if item["image"]
    ]
    return [*images, {"type": "text", "text": text}], resume_at, packet.get("intent")


def _turn(
    cli: ClaudeCli, core: CoreClient, body: ChatIn, content: list[dict], resume_at: str | None, events: queue.Queue,
    busy: threading.Lock, running: "_Running", run_id: str, cancel: threading.Event, model: str | None, system_extra: str,
) -> None:
    started, outcome = time.monotonic(), "error"
    try:
        events.put({"type": "start", "run_id": run_id})
        run = cli.run(
            content, resume=body.session_id, model=model, fork=body.fork, resume_at=resume_at, cancel=cancel, system_extra=system_extra,
            effort=CHAT_EFFORT,
        )
        for event in run:
            if event["type"] == "delta":
                events.put(event)
                continue
            if event["cancelled"]:
                events.put({"type": "cancelled"})  # 답을 저장하지 않는다
                outcome = "cancelled"
            elif event["is_error"] or not event["session_id"]:
                events.put({"type": "error", "code": "CLAUDE_FAILED", "message": event["error"] or "Claude Code가 답하지 못했습니다."})
            else:
                context = (event["context_tokens"], event["context_window"])
                answer = core.save_answer(body.packet_id, body.question, event["text"], event["session_id"], context, event["message_id"])
                events.put({"type": "done", "answer": answer})
                outcome = "ok"
    except (CoreUnavailable, CoreRefused) as failure:
        events.put({"type": "error", "code": "SAVE_FAILED", "message": f"답을 Paperloom에 저장하지 못했습니다: {failure}"})
    except Exception:
        log.exception("대화 차례 실패 packet=%s", body.packet_id)
        events.put({"type": "error", "code": "BRIDGE_FAILED", "message": "브리지에서 오류가 났습니다. 브리지 창의 로그를 확인하세요."})
    finally:
        running.end(run_id)
        busy.release()
        events.put(None)
        log.info(
            "대화 차례 packet=%s 이어묻기=%s 갈래=%s 결과=%s %.1f초",
            body.packet_id, body.session_id is not None, body.fork, outcome, time.monotonic() - started,
        )


def _stream(events: queue.Queue) -> Iterator[bytes]:
    while (event := events.get(timeout=RUN_TIMEOUT_SECONDS + 60)) is not None:
        yield (json.dumps(event, ensure_ascii=False) + "\n").encode()


def _error(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse({"code": code, "message": message}, status_code=status)
