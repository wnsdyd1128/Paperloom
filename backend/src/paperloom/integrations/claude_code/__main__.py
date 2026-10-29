"""`python -m paperloom.integrations.claude_code`: Reader의 "Claude와 대화" 탭을 위한 이 PC의 브리지 (ADR 0003).

사용자가 로그인해 둔 공식 Claude Code CLI(claude)를 구독(claude.ai) 사용량으로 실행한다. 모델 API 키는 읽지 않고,
자식 프로세스에서 지운다. 127.0.0.1에서만 연다.

환경변수(선택):
- PAPERLOOM_URL: Paperloom 주소 (기본 http://127.0.0.1:8000)
- PAPERLOOM_CLAUDE_CLI: claude 실행 파일 경로 (기본: PATH, ~/.local/bin)
- PAPERLOOM_CLAUDE_WORK_DIR: 대화 세션을 둘 전용 폴더 (기본 ~/.paperloom/claude-chat)
"""

import argparse
import logging
import os
import sys
import urllib.parse
from collections.abc import Iterable
from pathlib import Path

import uvicorn
from fastapi import FastAPI

from paperloom.integrations.claude_code.app import build_app
from paperloom.integrations.claude_code.cli import ClaudeCli, locate
from paperloom.integrations.claude_code.core import CoreClient


def web_origins(paperloom_url: str) -> set[str]:
    """Paperloom 웹의 origin. 127.0.0.1과 localhost는 서로 바꿔 써도 받는다."""
    url = urllib.parse.urlsplit(paperloom_url)
    origins = {f"{url.scheme}://{url.netloc}"}
    for one, other in (("127.0.0.1", "localhost"), ("localhost", "127.0.0.1")):
        if url.hostname == one:
            origins.add(f"{url.scheme}://{other}" + (f":{url.port}" if url.port else ""))
    return origins


def main() -> None:
    parser = argparse.ArgumentParser(prog="paperloom.integrations.claude_code")
    parser.add_argument("--port", type=int, default=8001, help="127.0.0.1에서 열 포트 (기본 8001)")
    parser.add_argument("--paperloom-url", default=os.environ.get("PAPERLOOM_URL", "http://127.0.0.1:8000"))
    parser.add_argument("--allow-origin", action="append", default=[], help="더 받을 웹 origin (개발 서버 등)")
    args = parser.parse_args()
    sys.stderr.reconfigure(encoding="utf-8")
    logging.basicConfig(stream=sys.stderr, level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    app = build(claude_cli(), args.port, args.paperloom_url, args.allow_origin)
    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")


def claude_cli() -> ClaudeCli:
    """환경변수(PAPERLOOM_CLAUDE_CLI·PAPERLOOM_CLAUDE_WORK_DIR)를 따른 이 PC의 Claude Code CLI."""
    work_dir = Path(os.environ.get("PAPERLOOM_CLAUDE_WORK_DIR") or Path.home() / ".paperloom" / "claude-chat")
    return ClaudeCli(locate(os.environ.get("PAPERLOOM_CLAUDE_CLI")), work_dir)


def build(cli: ClaudeCli, port: int, paperloom_url: str, allow_origins: Iterable[str] = ()) -> FastAPI:
    """브리지 앱. 시작 기록(claude 판·로그인 방식)을 남긴다. 서버와 함께 켜는 paperloom.launcher도 쓴다."""
    origins = web_origins(paperloom_url) | set(allow_origins)
    status = cli.status()
    logging.getLogger("paperloom.claude_code").info(
        "브리지 시작 127.0.0.1:%d (Paperloom %s, claude %s, 로그인 %s, 웹 %s)",
        port, paperloom_url, status.get("version", "없음"), status.get("auth_method"), ", ".join(sorted(origins)),
    )
    return build_app(cli, CoreClient(paperloom_url), origins, port)


if __name__ == "__main__":
    main()
