"""실행기(paperloom.launcher, Windows 압축본의 Paperloom.cmd): 서버와 Claude Code 브리지를 한 프로세스에서 함께 켠다.

실행기를 하위 프로세스로 띄운다. 브리지는 가짜 Claude Code CLI(tests/fixtures/fake_claude)를 쓰므로 사용량을 쓰지 않는다.
"""

import http.server
import json
import os
import signal
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures"
FAKE = [sys.executable, str(FIXTURES / "fake_claude" / "fake_claude.py")]


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def wait_json(url: str, timeout: float = 60) -> dict:
    deadline = time.monotonic() + timeout
    while True:
        try:
            with urllib.request.urlopen(url, timeout=10) as response:
                return json.loads(response.read())
        except (urllib.error.URLError, ConnectionError):
            assert time.monotonic() < deadline, url
            time.sleep(0.2)


@pytest.fixture
def launch(tmp_path):
    """실행기를 띄우는 함수와 서버·브리지 포트. 남은 실행기는 시험 끝에 끈다."""
    web, bridge = free_port(), free_port()
    config = tmp_path / "paperloom.yaml"
    config.write_text(f"app:\n  data_dir: data\n  port: {web}\n  claude_code_url: http://127.0.0.1:{bridge}\n", encoding="utf-8")
    env = {**os.environ, "PAPERLOOM_CLAUDE_CLI": json.dumps(FAKE), "PAPERLOOM_CLAUDE_WORK_DIR": str(tmp_path / "claude")}
    launched = []

    def start() -> subprocess.Popen:
        process = subprocess.Popen(
            [sys.executable, "-m", "paperloom.launcher", "--config", str(config), "--no-browser"],
            env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8",
        )
        launched.append(process)
        return process

    yield start, web, bridge
    for process in launched:
        if process.poll() is None:
            process.kill()
            process.communicate()


def test_the_launcher_runs_the_server_and_the_bridge_together(launch):
    start, web, bridge = launch
    first = start()

    health = wait_json(f"http://127.0.0.1:{web}/api/v1/health")
    assert health["claude_code_url"] == f"http://127.0.0.1:{bridge}"  # 웹은 health로 브리지를 찾는다
    bridge_health = wait_json(f"http://127.0.0.1:{bridge}/health")
    assert bridge_health["ready"] is True
    assert bridge_health["paperloom_url"] == f"http://127.0.0.1:{web}"

    # 두 번 켜면(Paperloom.cmd를 다시 누름) 떠 있는 것을 쓰고 바로 끝난다
    second = start()
    output, _ = second.communicate(timeout=60)
    assert second.returncode == 0
    assert "서버가 이미" in output and "브리지가 이미" in output

    if os.name == "nt":  # Windows는 다른 프로세스에 Ctrl+C만 보낼 수 없다
        first.terminate()
        first.communicate(timeout=30)
        return
    first.send_signal(signal.SIGINT)
    output, _ = first.communicate(timeout=30)
    assert first.returncode == 0, output
    assert "Claude Code 9.9.9 (Claude Code, fake): 준비됐습니다." in output


def test_the_launcher_names_the_port_another_program_holds(launch):
    start, web, _ = launch

    class NotPaperloom(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"hello")

        def log_message(self, *args):
            pass

    class Exclusive(http.server.HTTPServer):
        allow_reuse_address = False

    busy = Exclusive(("127.0.0.1", web), NotPaperloom)
    threading.Thread(target=busy.serve_forever, daemon=True).start()
    try:
        launcher = start()
        output, _ = launcher.communicate(timeout=60)
    finally:
        busy.shutdown()
        busy.server_close()

    assert launcher.returncode == 1
    assert f"{web}번 포트를 열지 못했습니다" in output
