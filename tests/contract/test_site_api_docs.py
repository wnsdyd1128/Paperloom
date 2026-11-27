"""배포 계약: 소개 페이지의 API 문서(site/api)는 서버의 /docs와 같은 명세를 보여 주고, 요청을 밖으로 보내지 않아야 한다.

페이지가 읽는 파일은 저장소에 없고 배포할 때 넣는다(.github/workflows/pages.yml). 그 배포는 main에 올라간 뒤에만 돌아서,
빠진 파일이나 깨진 스크립트는 여기서 잡지 않으면 올라간 뒤 빈 화면으로 드러난다.
"""

import importlib.util
import json
import re
from pathlib import Path

from fastapi.testclient import TestClient

from paperloom.bootstrap.app import create_app
from paperloom.bootstrap.config import AppSettings, Settings

REPO_ROOT = Path(__file__).resolve().parents[2]
PAGE = (REPO_ROOT / "site" / "api" / "index.html").read_text(encoding="utf-8")
WORKFLOW = (REPO_ROOT / ".github" / "workflows" / "pages.yml").read_text(encoding="utf-8")


def export_script():
    spec = importlib.util.spec_from_file_location("site_export_openapi", REPO_ROOT / "ops" / "site" / "export_openapi.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_exported_schema_is_the_one_the_server_serves(tmp_path):
    out = tmp_path / "site" / "api" / "openapi.json"
    export_script().export(out)
    client = TestClient(create_app(Settings(app=AppSettings(mode="test", data_dir=tmp_path / "data"))))
    served = client.get("/openapi.json").json()
    assert len(served["paths"]) > 30
    assert json.loads(out.read_text(encoding="utf-8")) == served


def test_the_page_loads_only_files_the_deploy_puts_next_to_it():
    loaded = re.findall(r'<script src="([^"]+)"', PAGE) + re.findall(r'<link rel="stylesheet" href="([^"]+)"', PAGE)
    assert sorted(loaded) == ["swagger-ui-bundle.js", "swagger-ui.css"]
    for name in loaded:
        assert f"apps/web/node_modules/swagger-ui-dist/{name}" in WORKFLOW, name
    assert 'url: "openapi.json"' in PAGE
    assert "python ops/site/export_openapi.py _site/api/openapi.json" in WORKFLOW
    # 페이지 바닥에서 여는 Swagger UI의 라이선스(Apache-2.0은 사본을 함께 두게 한다)
    for name in re.findall(r'href="((?:LICENSE|NOTICE)[^"]*)"', PAGE):
        assert f"_site/api/{name}" in WORKFLOW, name


def test_the_page_sends_nothing_out():
    # 부를 서버가 없으므로 Try it out을 숨긴다. 켜 두면 요청이 github.io로 간다
    assert "supportedSubmitMethods: []" in PAGE
    # 끄지 않으면 Swagger UI가 공개 주소의 명세 주소를 validator.swagger.io로 보내는 배지를 단다
    assert "validatorUrl: null" in PAGE
