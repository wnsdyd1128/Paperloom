"""Windows 압축본 시험. 압축본의 Python으로 실행한다(CI): dist\\Paperloom\\python\\python.exe ops\\bundle\\smoke.py

- python313._pth가 격리 모드를 켜는지
- 두 모델을 실제로 여는지(onnxruntime과 모델 파일). 그때 MSVC 런타임(msvcp140*.dll)을 압축본에서 읽는지. 러너에는 VC++ 재배포
  패키지가 깔려 있어 import가 되는 것만으로는 그 패키지가 없는 PC에서도 도는지 알 수 없다
- 실행기(paperloom.launcher)가 서버와 브리지를 켜고 웹을 내주는지(Claude Code는 없어도 된다)
"""

import ctypes
import json
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

from paperloom import __version__
from paperloom.bootstrap.config import load_settings
from paperloom.documents import layout_model, ocr_model

PYTHON = Path(sys.executable).parent
CONFIG = PYTHON.parent / "config" / "paperloom.yaml"
WEB = "http://127.0.0.1:8000"
BRIDGE = "http://127.0.0.1:8001"


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")  # 격리 모드라 CI의 PYTHONUTF8을 보지 않는다
    assert sys.flags.isolated, "python313._pth가 격리 모드를 켜지 않았습니다"
    settings = load_settings(CONFIG)
    layout = layout_model.LayoutModel(layout_model.model_file(settings), settings.layout.device).load()
    ocr = ocr_model.OcrModel(ocr_model.model_file(settings), settings.ocr.device).load()
    print(f"모델을 열었습니다: 레이아웃 {layout}, 글줄 인식 {ocr}")
    loaded = {name: path for name in ("msvcp140.dll", "msvcp140_1.dll") if (path := loaded_module(name))}
    assert loaded, "onnxruntime이 MSVC 런타임을 읽지 않았습니다"
    for name, path in loaded.items():
        assert path.parent.samefile(PYTHON), f"{name}을 압축본 밖에서 읽었습니다: {path}"

    launcher = subprocess.Popen([sys.executable, "-m", "paperloom.launcher", "--config", str(CONFIG), "--no-browser"])
    try:
        health = wait_json(f"{WEB}/api/v1/health")
        assert health["version"] == __version__ and health["layout_model"] and health["ocr_model"], health
        assert wait_json(f"{BRIDGE}/health")["bridge"] == "paperloom-claude-code"
        with urllib.request.urlopen(WEB, timeout=10) as page:
            assert b'<div id="root">' in page.read()
    finally:
        launcher.terminate()
        launcher.wait(30)
    print("압축본 시험을 통과했습니다.")


def loaded_module(name: str) -> Path | None:
    """이 프로세스가 읽은 DLL의 경로. 읽지 않았으면 None"""
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.GetModuleHandleW.argtypes = [ctypes.c_wchar_p]
    kernel32.GetModuleHandleW.restype = ctypes.c_void_p
    kernel32.GetModuleFileNameW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_uint32]
    handle = kernel32.GetModuleHandleW(name)
    if not handle:
        return None
    buffer = ctypes.create_unicode_buffer(32768)
    kernel32.GetModuleFileNameW(handle, buffer, len(buffer))
    return Path(buffer.value)


def wait_json(url: str, timeout: float = 60) -> dict:
    deadline = time.monotonic() + timeout
    while True:
        try:
            with urllib.request.urlopen(url, timeout=10) as response:
                return json.loads(response.read())
        except (urllib.error.URLError, ConnectionError):
            if time.monotonic() > deadline:
                raise
            time.sleep(0.5)


if __name__ == "__main__":
    main()
