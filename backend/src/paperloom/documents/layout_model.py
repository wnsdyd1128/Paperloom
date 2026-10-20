"""문서 레이아웃 모델로 쪽의 영역(표·알고리즘·수식·그림·머리글·바닥글 …)을 찾는다 (2026-10-19 사용자 요청: "알고리즘이나
표 이런 게 자꾸 번역되네" → 후보 평가 docs/gates/evidence/ui/2026-10-19_dla-evaluation.md).

- 모델: PaddlePaddle/PP-DocLayout_plus-L_onnx(Apache-2.0, RT-DETR-L, 20분류). 130MB라 저장소에 넣지 않는다.
  `python -m paperloom.documents.layout_model download --config <설정>`이 Hugging Face에서 받아 sha256을 확인한다. Docker 이미지는
  빌드할 때 받는다. 파일이 없으면 이 모듈을 쓰지 않는다(규칙만으로 가린다).
- 입력은 본문 추출 하위 프로세스(documents.extract, 자원 제한)가 그린 800×800 RGB다. 이 모듈은 신뢰할 수 없는 PDF를 열지 않으므로
  서버 프로세스에서 한 번 열어 계속 쓴다(CUDA는 하위 프로세스의 메모리 제한 아래에서 시작하지 못한다).
- 장치(device): auto면 CUDA를 쓸 수 있을 때 GPU, 아니면 CPU. GPU는 onnxruntime-gpu가 깔려 있고 CUDA·cuDNN 라이브러리를 찾을 수
  있어야 한다(Windows: CUDA_PATH의 bin\\x64·bin과 cuDNN 설치 폴더, 리눅스: nvidia-* pip 패키지 — ops/compose GPU 이미지).
"""

import argparse
import hashlib
import logging
import os
import sys
import threading
import urllib.request
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger("paperloom.layout")

# onnxruntime(리눅스 1.31)은 Microsoft 수집 서버(mobile.events.data.microsoft.com)로 사용 통계를 보낸다. disable_telemetry_events()로는
# 멈추지 않고, onnxruntime을 불러오기 전에 이 환경 변수가 있어야 멈춘다(2026-10-19 컨테이너의 연결을 보고 확인). 서버는 논문 읽기에
# 외부 서비스를 부르지 않는다(README). onnxruntime은 이 모듈만 불러온다(_session).
os.environ["ORT_DISABLE_TELEMETRY"] = "1"

MODEL_NAME = "PP-DocLayout_plus-L"
# 커밋을 고정한 주소와 그 파일의 sha256(Hugging Face X-Linked-ETag와 같다)
MODEL_URL = "https://huggingface.co/PaddlePaddle/PP-DocLayout_plus-L_onnx/resolve/feb74619326f634e0e883218598096a3733ad9f7/inference.onnx"
MODEL_SHA256 = "77afb2caa74dd13240d087d2eced91d7fcd2caebd16006a0a66162fc8707ff0e"
DEFAULT_MODEL = Path("models") / "pp-doclayout-plus-l" / "inference.onnx"  # 데이터 폴더 기준
INPUT_SIZE = 800  # 모델 입력 한 변(px). 쪽을 비율 없이 이 크기로 줄인다(모델 설정 keep_ratio: false)
MIN_SCORE = 0.5
CPU_THREADS = 4  # CPU로 돌 때 쓸 스레드. 서버의 다른 요청이 멈추지 않게 코어를 다 쓰지 않는다
CUDA_MAJOR = 13  # onnxruntime-gpu 1.31이 쓰는 CUDA 판(requirements-gpu.lock)
LABELS = (
    "paragraph_title", "image", "text", "number", "abstract", "content", "figure_title", "formula", "table", "reference",
    "doc_title", "footnote", "header", "algorithm", "footer", "seal", "chart", "formula_number", "aside_text", "reference_content",
)


@dataclass(frozen=True)
class Region:
    label: str
    score: float
    box: tuple[float, float, float, float]  # 쪽 그림(/Rotate를 적용한 화면 쪽)의 정규화 좌표 (u0, v0, u1, v1), 0–1, 좌상단 원점


class LayoutModel:
    """모델 파일 하나를 처음 쓸 때 연다(스레드 안전). device_in_use는 연 뒤의 실제 장치("cuda"·"cpu")다."""

    def __init__(self, path: Path, device: str = "auto") -> None:
        self.path = path
        self.device = device
        self.device_in_use: str | None = None
        self._session = None
        self._lock = threading.Lock()

    def identity(self) -> str:
        """추출기 버전에 넣을 모델 이름과 파일 해시 앞부분(모델을 바꾸면 다시 추출한다)"""
        return f"{MODEL_NAME}-{_sha256(self.path)[:8]}"

    def load(self) -> str:
        """모델을 미리 열고 쓰는 장치를 돌려준다(본문 추출 worker가 시작할 때)."""
        self._open()
        return self.device_in_use

    def detect(self, image: bytes) -> list[Region]:
        """INPUT_SIZE×INPUT_SIZE RGB(행 우선, 바이트)에서 점수 MIN_SCORE 이상인 영역"""
        import numpy as np

        session = self._open()
        pixels = np.frombuffer(image, dtype=np.uint8).reshape(INPUT_SIZE, INPUT_SIZE, 3).astype(np.float32) / 255.0
        feeds = {
            "image": pixels.transpose(2, 0, 1)[None],
            "im_shape": np.array([[INPUT_SIZE, INPUT_SIZE]], dtype=np.float32),
            "scale_factor": np.array([[1.0, 1.0]], dtype=np.float32),
        }
        boxes = session.run(None, feeds)[0]  # [N, 6]: 분류, 점수, x0, y0, x1, y1 (입력 px)
        return [
            Region(LABELS[int(label)], round(float(score), 3), tuple(min(max(float(v) / INPUT_SIZE, 0.0), 1.0) for v in (x0, y0, x1, y1)))
            for label, score, x0, y0, x1, y1 in boxes
            if score >= MIN_SCORE and 0 <= int(label) < len(LABELS)
        ]

    def _open(self):
        with self._lock:
            if self._session is None:
                self._session, self.device_in_use = _session(self.path, self.device)
                log.info("레이아웃 모델 %s를 %s로 열었습니다.", MODEL_NAME, "GPU(CUDA)" if self.device_in_use == "cuda" else "CPU")
            return self._session


def _session(path: Path, device: str):
    import onnxruntime as ort

    options = ort.SessionOptions()
    options.intra_op_num_threads = CPU_THREADS
    if device != "cpu" and "CUDAExecutionProvider" in ort.get_available_providers():
        _cuda_libraries(ort)
        try:
            session = ort.InferenceSession(str(path), options, providers=["CUDAExecutionProvider", "CPUExecutionProvider"])
            if session.get_providers()[0] == "CUDAExecutionProvider":
                return session, "cuda"
            log.warning("CUDA를 쓸 수 없어(라이브러리를 찾지 못함) 레이아웃 모델을 CPU로 돌립니다.")
        except Exception:  # noqa: BLE001 - GPU 드라이버·라이브러리 문제는 CPU로 넘어간다
            log.warning("레이아웃 모델을 GPU로 열지 못해 CPU로 돌립니다.", exc_info=True)
    elif device == "cuda":
        log.warning("device: cuda지만 onnxruntime에 CUDA가 없습니다(onnxruntime-gpu가 아님). CPU로 돌립니다.")
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


def download(path: Path) -> None:
    """모델을 받아 sha256을 확인한 뒤 path에 둔다. 이미 있고 해시가 같으면 받지 않는다."""
    if path.is_file() and _sha256(path) == MODEL_SHA256:
        print(f"이미 있습니다: {path}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_suffix(".part")
    print(f"{MODEL_NAME}(약 130MB)를 받습니다: {MODEL_URL}")
    urllib.request.urlretrieve(MODEL_URL, partial)
    if (actual := _sha256(partial)) != MODEL_SHA256:
        partial.unlink()
        raise SystemExit(f"받은 파일의 sha256이 다릅니다: {actual}")
    partial.replace(path)
    print(f"받았습니다: {path}")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def model_file(settings) -> Path:
    """설정의 모델 경로(없으면 데이터 폴더의 기본 자리)"""
    return settings.layout.model_path or settings.app.data_dir / DEFAULT_MODEL


def _main() -> None:
    parser = argparse.ArgumentParser(prog="python -m paperloom.documents.layout_model")
    commands = parser.add_subparsers(dest="command", required=True)
    fetch = commands.add_parser("download", help="레이아웃 모델을 받는다")
    fetch.add_argument("--config", type=Path, help="Paperloom 설정 파일(모델 자리를 정한다)")
    fetch.add_argument("--path", type=Path, help="모델을 둘 자리(설정보다 먼저)")
    arguments = parser.parse_args()
    if arguments.path is None and arguments.config is None:
        parser.error("--config 또는 --path가 필요합니다")
    if arguments.path is not None:
        download(arguments.path)
        return
    from paperloom.bootstrap.config import load_settings

    download(model_file(load_settings(arguments.config)))


if __name__ == "__main__":
    sys.exit(_main())
