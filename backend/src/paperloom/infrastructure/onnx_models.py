"""이 PC에서 돌리는 ONNX 모델(문서 레이아웃 documents.layout_model, 글줄 인식 documents.ocr_model)의 공통 부분.

- 세션은 서버 프로세스에서 처음 쓸 때 한 번 연다(스레드 안전). 모델은 신뢰할 수 없는 PDF를 열지 않고 본문 추출 하위 프로세스가
  그린 그림만 받는다(CUDA는 하위 프로세스의 메모리 제한 아래에서 시작하지 못한다).
- 장치(device): auto면 CUDA를 쓸 수 있을 때 GPU, 아니면 CPU. GPU는 onnxruntime-gpu가 깔려 있고 CUDA·cuDNN 라이브러리를 찾을 수
  있어야 한다(Windows: CUDA_PATH의 bin\\x64·bin과 cuDNN 설치 폴더, 리눅스: nvidia-* pip 패키지 — ops/compose GPU 이미지).
- 모델 파일은 저장소에 넣지 않는다. 각 모델 모듈의 download가 커밋을 고정한 주소에서 받아 sha256을 확인한다.
"""

import hashlib
import logging
import os
import threading
import urllib.request
from pathlib import Path

log = logging.getLogger("paperloom.models")

# onnxruntime(리눅스 1.31)은 Microsoft 수집 서버(mobile.events.data.microsoft.com)로 사용 통계를 보낸다. disable_telemetry_events()로는
# 멈추지 않고, onnxruntime을 불러오기 전에 이 환경 변수가 있어야 멈춘다(2026-10-19 컨테이너의 연결을 보고 확인). 서버는 논문 읽기에
# 외부 서비스를 부르지 않는다(README). onnxruntime은 이 모듈만 불러온다(_session).
os.environ["ORT_DISABLE_TELEMETRY"] = "1"

CPU_THREADS = 4  # CPU로 돌 때 쓸 스레드. 서버의 다른 요청이 멈추지 않게 코어를 다 쓰지 않는다
CUDA_MAJOR = 13  # onnxruntime-gpu 1.31이 쓰는 CUDA 판(requirements-gpu.lock)


class LazySession:
    """ONNX 모델 파일 하나를 처음 쓸 때 연다(스레드 안전). device_in_use는 연 뒤의 실제 장치("cuda"·"cpu")다."""

    name = "model"  # 로그·health에 보일 모델 이름

    def __init__(self, path: Path, device: str = "auto") -> None:
        self.path = path
        self.device = device
        self.device_in_use: str | None = None
        self._session = None
        self._lock = threading.Lock()

    def identity(self) -> str:
        """추출기 버전에 넣을 모델 이름과 파일 해시 앞부분(모델을 바꾸면 다시 추출한다)"""
        return f"{self.name}-{sha256(self.path)[:8]}"

    def load(self) -> str:
        """모델을 미리 열고 쓰는 장치를 돌려준다(본문 추출 worker가 시작할 때)."""
        self.session()
        return self.device_in_use

    def session(self):
        with self._lock:
            if self._session is None:
                self._session, self.device_in_use = _session(self.path, self.device, self.name)
                log.info("%s를 %s로 열었습니다.", self.name, "GPU(CUDA)" if self.device_in_use == "cuda" else "CPU")
            return self._session


def _session(path: Path, device: str, name: str):
    import onnxruntime as ort

    options = ort.SessionOptions()
    options.intra_op_num_threads = CPU_THREADS
    options.log_severity_level = 3  # 쓰지 않는 초기값 경고(PaddleX 내보내기)를 숨긴다
    if device != "cpu" and "CUDAExecutionProvider" in ort.get_available_providers():
        _cuda_libraries(ort)
        try:
            session = ort.InferenceSession(str(path), options, providers=["CUDAExecutionProvider", "CPUExecutionProvider"])
            if session.get_providers()[0] == "CUDAExecutionProvider":
                return session, "cuda"
            log.warning("CUDA를 쓸 수 없어(라이브러리를 찾지 못함) %s를 CPU로 돌립니다.", name)
        except Exception:  # noqa: BLE001 - GPU 드라이버·라이브러리 문제는 CPU로 넘어간다
            log.warning("%s를 GPU로 열지 못해 CPU로 돌립니다.", name, exc_info=True)
    elif device == "cuda":
        log.warning("device: cuda지만 onnxruntime에 CUDA가 없습니다(onnxruntime-gpu가 아님). %s를 CPU로 돌립니다.", name)
    return ort.InferenceSession(str(path), options, providers=["CPUExecutionProvider"]), "cpu"


def _cuda_libraries(ort) -> None:
    """CUDA·cuDNN 라이브러리를 찾게 한다. Windows는 설치 폴더를 DLL 검색 경로에 더하고(CUDA 13은 bin\\x64, 안 하면
    cudart64_13.dll을 찾지 못한다), 그다음 onnxruntime-gpu가 nvidia-* pip 패키지(리눅스 GPU 이미지)나 그 경로에서 미리 읽게 한다."""
    if os.name == "nt":
        cuda = Path(os.environ.get("CUDA_PATH", ""))
        folders = [cuda / "bin" / "x64", cuda / "bin"] if os.environ.get("CUDA_PATH") else []
        # cuDNN 설치는 CUDA 판마다 폴더를 두고 DLL 이름(cudnn64_9.dll)이 같다. 다른 판 폴더가 먼저 잡히면 프로세스가 죽는다
        folders += sorted(Path(r"C:\Program Files\NVIDIA\CUDNN").glob(f"v*/bin/{CUDA_MAJOR}.*"), reverse=True)
        for folder in folders:
            if folder.is_dir():
                os.add_dll_directory(str(folder))
    try:
        ort.preload_dlls()
    except Exception:  # noqa: BLE001 - 없으면 세션이 CPU로 넘어간다
        pass


def download(url: str, expected: str, path: Path, label: str) -> None:
    """url을 받아 sha256(expected)을 확인한 뒤 path에 둔다. 이미 있고 해시가 같으면 받지 않는다."""
    if path.is_file() and sha256(path) == expected:
        print(f"이미 있습니다: {path}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_suffix(path.suffix + ".part")
    print(f"{label}를 받습니다: {url}")
    urllib.request.urlretrieve(url, partial)
    if (actual := sha256(partial)) != expected:
        partial.unlink()
        raise SystemExit(f"받은 파일의 sha256이 다릅니다: {actual}")
    partial.replace(path)
    print(f"받았습니다: {path}")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()
