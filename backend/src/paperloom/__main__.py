"""`python -m paperloom --config <yaml>` 실행 진입점."""

import argparse
import logging
import os
from pathlib import Path

import uvicorn

from paperloom.bootstrap.app import create_app
from paperloom.bootstrap.config import load_settings


def main() -> None:
    parser = argparse.ArgumentParser(prog="paperloom")
    parser.add_argument(
        "--config",
        type=Path,
        default=os.environ.get("PAPERLOOM_CONFIG"),
        help="설정 YAML 경로 (기본값: PAPERLOOM_CONFIG 환경변수)",
    )
    args = parser.parse_args()
    if args.config is None:
        parser.error("설정 파일을 --config 또는 PAPERLOOM_CONFIG로 지정하세요.")
    settings = load_settings(args.config)
    # uvicorn은 자기 로거만 설정한다. 본문 추출 작업 기록(작업 ID·상태·소요 시간, IMPL §15)이 보이도록 paperloom 로거를 연다.
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(levelname)s:     %(name)s - %(message)s"))
    logging.getLogger("paperloom").addHandler(handler)
    logging.getLogger("paperloom").setLevel(logging.INFO)
    uvicorn.run(create_app(settings), host=settings.app.bind_host, port=settings.app.port)


if __name__ == "__main__":
    main()
