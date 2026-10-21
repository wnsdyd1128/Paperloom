"""글줄 인식(OCR) 모델로 PDF 글꼴 정보로는 읽지 못한 글줄을 그림에서 읽는다 (2026-10-21 사용자 요청: "Self-recovery 좀 더 고도화",
③ 글리프 그림 읽기 — 로컬 OCR 모델로 결정).

- 모델: PaddlePaddle/PP-OCRv6_small_rec_onnx(Apache-2.0, 21MB, 글자 18,708개 — 라틴·그리스·수식 기호 포함). 후보 셋(en_PP-OCRv5_mobile·
  PP-OCRv5_mobile·PP-OCRv6_small)을 정답 있는 글줄 718개로 견줘 글자 오류율 0.60%(공백 빼고 0.33%), CPU 21.6ms/줄로 골랐다
  (docs/gates/evidence/ui/2026-10-21_self-recovery.md). 파일(inference.onnx와 글자 사전 inference.yml)은 저장소에 넣지 않는다.
  `python -m paperloom.documents.ocr_model download --config <설정>`이 받아 sha256을 확인한다. 없으면 OCR을 하지 않는다.
- 입력은 본문 추출 하위 프로세스(documents.extract --ocr)가 그린 높이 OCR_HEIGHT의 글줄 RGB다. 출력은 CTC 글자 확률([N, T, C],
  0번은 빈칸, 마지막은 공백)이고 글과 평균 확률을 돌려준다. 세션·장치는 infrastructure.onnx_models가 맡는다.
"""

import argparse
import sys
from pathlib import Path

from paperloom.infrastructure.onnx_models import LazySession, download

MODEL_NAME = "PP-OCRv6_small_rec"
_BASE = "https://huggingface.co/PaddlePaddle/PP-OCRv6_small_rec_onnx/resolve/b8f84f0b80c529de40b4fbb3544b84fa7233a513/"
MODEL_URL, MODEL_SHA256 = _BASE + "inference.onnx", "5435fd747c9e0efe15a96d0b378d5bd157e9492ed8fd80edf08f30d02fa24634"
DICTIONARY_URL, DICTIONARY_SHA256 = _BASE + "inference.yml", "ab078671bb49f06228eadccd34f1bb501e157f7a047095ffb943ba81512c77d1"
DEFAULT_MODEL = Path("models") / "pp-ocrv6-small-rec" / "inference.onnx"  # 데이터 폴더 기준. 글자 사전은 같은 폴더의 inference.yml
OCR_HEIGHT = 48  # 모델 입력 높이(px)
BATCH = 16


class OcrModel(LazySession):
    """글줄 인식 모델 파일 하나와 같은 폴더의 글자 사전(inference.yml)."""

    name = MODEL_NAME

    def __init__(self, path: Path, device: str = "auto") -> None:
        super().__init__(path, device)
        self._characters: list[str] | None = None

    @property
    def available(self) -> bool:
        return self.path.is_file() and self.path.with_name("inference.yml").is_file()

    def read(self, lines: list[tuple[int, bytes]]) -> list[tuple[str, float]]:
        """글줄 그림(너비, 높이 OCR_HEIGHT의 RGB 바이트)마다 읽은 글과 글자 확률 평균(0–1)."""
        import numpy as np

        session, characters = self.session(), self._dictionary()
        results: list[tuple[str, float] | None] = [None] * len(lines)
        order = sorted(range(len(lines)), key=lambda index: lines[index][0])  # 너비가 비슷한 것끼리 묶어 덧붙임을 줄인다
        for start in range(0, len(order), BATCH):
            chunk = order[start : start + BATCH]
            batch = np.zeros((len(chunk), 3, OCR_HEIGHT, max(lines[index][0] for index in chunk)), dtype=np.float32)
            for row, index in enumerate(chunk):
                width, data = lines[index]
                pixels = np.frombuffer(data, dtype=np.uint8).reshape(OCR_HEIGHT, width, 3)[:, :, ::-1].astype(np.float32)  # BGR
                batch[row, :, :, :width] = ((pixels / 255.0 - 0.5) / 0.5).transpose(2, 0, 1)
            for row, probabilities in enumerate(session.run(None, {"x": batch})[0]):
                best, scores = probabilities.argmax(axis=1), probabilities.max(axis=1)
                text, kept, previous = [], [], -1
                for step, label in enumerate(best):
                    if label != previous and label != 0:
                        text.append(characters[label])
                        kept.append(float(scores[step]))
                    previous = label
                results[chunk[row]] = ("".join(text), sum(kept) / len(kept) if kept else 0.0)
        return results

    def _dictionary(self) -> list[str]:
        if self._characters is None:
            import yaml

            entries = yaml.safe_load(self.path.with_name("inference.yml").read_text(encoding="utf-8"))["PostProcess"]["character_dict"]
            self._characters = ["", *map(str, entries), " "]  # 0: CTC 빈칸, 끝: 공백
        return self._characters


def model_file(settings) -> Path:
    """설정의 모델 경로(없으면 데이터 폴더의 기본 자리)"""
    return settings.ocr.model_path or settings.app.data_dir / DEFAULT_MODEL


def _main() -> None:
    parser = argparse.ArgumentParser(prog="python -m paperloom.documents.ocr_model")
    commands = parser.add_subparsers(dest="command", required=True)
    fetch = commands.add_parser("download", help="글줄 인식 모델을 받는다")
    fetch.add_argument("--config", type=Path, help="Paperloom 설정 파일(모델 자리를 정한다)")
    fetch.add_argument("--path", type=Path, help="모델(inference.onnx)을 둘 자리(설정보다 먼저)")
    arguments = parser.parse_args()
    if arguments.path is None and arguments.config is None:
        parser.error("--config 또는 --path가 필요합니다")
    if arguments.path is None:
        from paperloom.bootstrap.config import load_settings

        arguments.path = model_file(load_settings(arguments.config))
    download(MODEL_URL, MODEL_SHA256, arguments.path, f"{MODEL_NAME}(약 21MB)")
    download(DICTIONARY_URL, DICTIONARY_SHA256, arguments.path.with_name("inference.yml"), f"{MODEL_NAME} 글자 사전")


if __name__ == "__main__":
    sys.exit(_main())
