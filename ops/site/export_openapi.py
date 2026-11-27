"""소개 페이지의 API 문서(site/api/index.html)가 읽을 OpenAPI 명세를 파일로 쓴다 (.github/workflows/pages.yml).

서버를 띄우지 않고 앱만 만들어 서버의 /openapi.json과 같은 명세를 꺼낸다.

실행: python ops/site/export_openapi.py <out.json>
"""

import json
import sys
import tempfile
from pathlib import Path

from paperloom.bootstrap.app import create_app
from paperloom.bootstrap.config import AppSettings, Settings


def export(out: Path) -> None:
    # 앱을 만들면 데이터 폴더에 DB가 생기므로 버릴 폴더를 준다
    with tempfile.TemporaryDirectory() as data_dir:
        schema = create_app(Settings(app=AppSettings(data_dir=Path(data_dir)))).openapi()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(schema, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    export(Path(sys.argv[1]))
