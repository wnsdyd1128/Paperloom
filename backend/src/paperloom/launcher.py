"""`python -m paperloom.launcher --config <설정>`: Paperloom 서버와 Claude Code 브리지를 한 번에 켜고 브라우저를 연다.

Windows 압축본(ops/bundle)의 Paperloom.cmd가 부른다. 사용자가 서버와 브리지를 터미널 두 개에서 따로 켜지 않아도 된다.
- 서버와 브리지는 따로 켜던 그대로 각자의 포트(설정의 app.port와 app.claude_code_url)에서 연다(ADR 0003). 프로세스만 하나다.
- 이미 떠 있는 쪽은 다시 띄우지 않는다(두 번 켰거나 서버를 Docker로 띄웠다). 둘 다 떠 있으면 브라우저만 연다.
- 시작할 때 Claude Code가 준비됐는지 창에 알린다. 준비되지 않아도 켠다(읽기·검색·하이라이트·주석은 된다).
- 창을 닫거나 Ctrl+C로 끈다.
"""

import argparse
import json
import os
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from pathlib import Path

import uvicorn
from fastapi import FastAPI

from paperloom.__main__ import configure_logging
from paperloom.bootstrap.app import create_app
from paperloom.bootstrap.config import load_settings
from paperloom.integrations.claude_code import __main__ as bridge
from paperloom.integrations.claude_code.cli import ClaudeCli, ClaudeNotReady

LOOPBACK = "127.0.0.1"
START_TIMEOUT_SECONDS = 60
# 떠 있는 브리지의 health는 claude --version·auth status를 실행하느라 몇 초 걸릴 수 있다. 아무도 듣지 않으면 바로 거부된다
PROBE_TIMEOUT_SECONDS = 15
STOP_TIMEOUT_SECONDS = 5  # 끌 때 진행 중인 응답(대화 스트림 등)을 기다리는 시간
# 이 PC의 주소를 물을 때 시스템 프록시(HTTP_PROXY 등)를 거치지 않는다
_LOCAL = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def main() -> int:
    parser = argparse.ArgumentParser(prog="python -m paperloom.launcher")
    parser.add_argument(
        "--config",
        type=Path,
        default=os.environ.get("PAPERLOOM_CONFIG"),
        help="설정 YAML 경로 (기본값: PAPERLOOM_CONFIG 환경변수)",
    )
    parser.add_argument("--no-browser", action="store_true", help="켠 뒤 브라우저를 열지 않는다")
    args = parser.parse_args()
    if args.config is None:
        parser.error("설정 파일을 --config 또는 PAPERLOOM_CONFIG로 지정하세요.")
    # 압축본의 Python은 격리 모드라 PYTHONUTF8을 보지 않는다. 출력을 파이프로 받아도(CI 등) 한글이 깨지지 않게 한다(콘솔은 원래 된다)
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8", errors="replace")
    settings = load_settings(args.config)
    configure_logging()
    web = f"http://{LOOPBACK}:{settings.app.port}"
    bridge_port = urllib.parse.urlsplit(settings.app.claude_code_url).port or 80

    servers = []
    if _answers(f"{web}/api/v1/health", "cost_policy"):
        print(f"Paperloom 서버가 이미 {web}에서 돌고 있어 그 서버를 씁니다(Docker로 띄운 서버라면 서재는 Docker 볼륨에 있습니다).")
    else:
        servers.append(_server(create_app(settings), settings.app.bind_host, settings.app.port))
    if _answers(f"http://{LOOPBACK}:{bridge_port}/health", "bridge"):
        print("Claude Code 브리지가 이미 돌고 있습니다.")
    else:
        cli = bridge.claude_cli()
        _report(cli)
        servers.append(_server(bridge.build(cli, bridge_port, web), LOOPBACK, bridge_port))

    threads = [threading.Thread(target=server.run, name=f"uvicorn-{server.config.port}", daemon=True) for server in servers]
    try:
        if not _start(servers, threads):
            return 1
        print(f"Paperloom: {web}")
        if not args.no_browser:
            webbrowser.open(web)
        if not servers:
            return 0
        print("이 창을 닫거나 Ctrl+C를 누르면 꺼집니다.")
        while all(thread.is_alive() for thread in threads):
            time.sleep(0.5)
        return 1  # 끄지 않았는데 한쪽이 멈췄다
    except KeyboardInterrupt:
        return 0
    finally:
        for server in servers:
            server.should_exit = True
        for thread in threads:
            if thread.is_alive():
                thread.join(STOP_TIMEOUT_SECONDS * 2)


def _server(app: FastAPI, host: str, port: int) -> uvicorn.Server:
    return uvicorn.Server(uvicorn.Config(app, host=host, port=port, log_level="warning", timeout_graceful_shutdown=STOP_TIMEOUT_SECONDS))


def _start(servers: list[uvicorn.Server], threads: list[threading.Thread]) -> bool:
    """서버마다 스레드 하나에서 띄우고 모두 열릴 때까지 기다린다. 한 이벤트 루프에 둘을 띄우면 uvicorn이 서로의 신호 처리기를
    덮어쓴다. 메인 스레드가 아니면 uvicorn은 신호 처리기를 달지 않으므로 Ctrl+C는 메인 스레드가 받아 둘 다 멈춘다(main)."""
    for thread in threads:
        thread.start()
    deadline = time.monotonic() + START_TIMEOUT_SECONDS
    while not all(server.started for server in servers):
        # 포트를 열지 못하면 uvicorn이 그 스레드에서 sys.exit한다
        failed = [str(server.config.port) for server, thread in zip(servers, threads) if not thread.is_alive() and not server.started]
        if failed:
            print(f"{', '.join(failed)}번 포트를 열지 못했습니다. 다른 프로그램이 그 포트를 쓰고 있는지 확인하세요.")
            return False
        if time.monotonic() > deadline:
            print(f"{START_TIMEOUT_SECONDS}초 안에 켜지 못했습니다. 위의 오류를 확인하세요.")
            return False
        time.sleep(0.1)
    return True


def _answers(url: str, key: str) -> bool:
    """url에서 Paperloom(key가 든 JSON)이 답하는지. 아무도 듣지 않거나 다른 프로그램이면 False."""
    try:
        with _LOCAL.open(url, timeout=PROBE_TIMEOUT_SECONDS) as response:
            body = response.read()
    except urllib.error.HTTPError as error:  # 서버 health는 데이터 폴더에 쓸 수 없으면 503으로 답한다
        body = error.read()
    except (urllib.error.URLError, OSError):
        return False
    try:
        answer = json.loads(body)
    except ValueError:
        return False
    return isinstance(answer, dict) and key in answer


def _report(cli: ClaudeCli) -> None:
    """Claude Code가 준비됐는지 창에 알린다."""
    try:
        cli.check_ready()
    except ClaudeNotReady as not_ready:
        print(f"Claude Code: {not_ready.message}")
        if not_ready.code == "CLAUDE_NOT_INSTALLED":
            print("  Claude Code를 설치하고 로그인한 뒤 Paperloom을 다시 켜세요: https://code.claude.com/docs/ko/setup")
        print("  AI 기능(설명·번역·대화)을 빼면 읽기·검색·하이라이트·주석은 지금도 쓸 수 있습니다.")
        return
    print(f"Claude Code {cli.status()['version']}: 준비됐습니다.")


if __name__ == "__main__":
    sys.exit(main())
