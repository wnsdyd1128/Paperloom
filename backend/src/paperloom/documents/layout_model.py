"""문서 레이아웃 모델로 쪽의 영역(표·알고리즘·수식·그림·머리글·바닥글 …)을 찾는다 (2026-10-19 사용자 요청: "알고리즘이나
표 이런 게 자꾸 번역되네" → 후보 평가 docs/gates/evidence/ui/2026-10-19_dla-evaluation.md).

- 모델: PaddlePaddle/PP-DocLayout_plus-L_onnx(Apache-2.0, RT-DETR-L, 20분류). 130MB라 저장소에 넣지 않는다.
  `python -m paperloom.documents.layout_model download --config <설정>`이 Hugging Face에서 받아 sha256을 확인한다. Docker 이미지는
  빌드할 때 받는다. 파일이 없으면 이 모듈을 쓰지 않는다(규칙만으로 가린다).
- 입력은 본문 추출 하위 프로세스(documents.extract, 자원 제한)가 그린 800×800 RGB다. 세션·장치(auto·cpu·cuda)는
  infrastructure.onnx_models가 맡는다.
"""

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

from paperloom.infrastructure.onnx_models import LazySession, download

MODEL_NAME = "PP-DocLayout_plus-L"
# 커밋을 고정한 주소와 그 파일의 sha256(Hugging Face X-Linked-ETag와 같다)
MODEL_URL = "https://huggingface.co/PaddlePaddle/PP-DocLayout_plus-L_onnx/resolve/feb74619326f634e0e883218598096a3733ad9f7/inference.onnx"
MODEL_SHA256 = "77afb2caa74dd13240d087d2eced91d7fcd2caebd16006a0a66162fc8707ff0e"
DEFAULT_MODEL = Path("models") / "pp-doclayout-plus-l" / "inference.onnx"  # 데이터 폴더 기준
INPUT_SIZE = 800  # 모델 입력 한 변(px). 쪽을 비율 없이 이 크기로 줄인다(모델 설정 keep_ratio: false)
MIN_SCORE = 0.5
LABELS = (
    "paragraph_title", "image", "text", "number", "abstract", "content", "figure_title", "formula", "table", "reference",
    "doc_title", "footnote", "header", "algorithm", "footer", "seal", "chart", "formula_number", "aside_text", "reference_content",
)


@dataclass(frozen=True)
class Region:
    label: str
    score: float
    box: tuple[float, float, float, float]  # 쪽 그림(/Rotate를 적용한 화면 쪽)의 정규화 좌표 (u0, v0, u1, v1), 0–1, 좌상단 원점


class LayoutModel(LazySession):
    """레이아웃 모델 파일 하나(처음 쓸 때 연다). device_in_use는 연 뒤의 실제 장치("cuda"·"cpu")다."""

    name = MODEL_NAME

    def detect(self, image: bytes) -> list[Region]:
        """INPUT_SIZE×INPUT_SIZE RGB(행 우선, 바이트)에서 점수 MIN_SCORE 이상인 영역"""
        import numpy as np

        session = self.session()
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
    if arguments.path is None:
        from paperloom.bootstrap.config import load_settings

        arguments.path = model_file(load_settings(arguments.config))
    download(MODEL_URL, MODEL_SHA256, arguments.path, f"{MODEL_NAME}(약 130MB)")


if __name__ == "__main__":
    sys.exit(_main())
