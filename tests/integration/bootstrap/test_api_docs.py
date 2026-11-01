"""API 문서 (/docs, /openapi.json): 모든 API가 설명되고, 문서가 실제 응답과 맞고, 화면이 외부로 나가지 않는다."""

import json
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import paperloom
from paperloom.api import docs
from paperloom.bootstrap.app import create_app
from paperloom.bootstrap.config import AppSettings, Settings

SOURCE = Path(paperloom.__file__).parent


def _client(tmp_path: Path, web_dist_dir: Path | None = None) -> TestClient:
    return TestClient(create_app(Settings(app=AppSettings(mode="test", data_dir=tmp_path / "data", web_dist_dir=web_dist_dir))))


@pytest.fixture
def schema(tmp_path) -> dict:
    return _client(tmp_path).get("/openapi.json").json()


def _operations(schema: dict):
    for path, operations in schema["paths"].items():
        for method, operation in operations.items():
            yield f"{method.upper()} {path}", operation


def test_every_operation_has_a_known_tag_and_a_written_summary(schema):
    known = {tag["name"] for tag in schema["tags"]}
    operations = dict(_operations(schema))
    assert len(operations) == 55
    for name, operation in operations.items():
        assert len(operation["tags"]) == 1 and operation["tags"][0] in known, name
        # 쓰지 않으면 FastAPI가 함수 이름으로 영어 제목을 만든다
        assert re.search("[가-힣]", operation["summary"]), name


def test_every_tag_is_used(schema):
    used = {operation["tags"][0] for _, operation in _operations(schema)}
    assert used == {tag["name"] for tag in schema["tags"]}


def test_the_framework_wording_is_gone(schema):
    assert "HTTPValidationError" not in schema["components"]["schemas"]
    text = json.dumps(schema, ensure_ascii=False)
    assert "Successful Response" not in text
    assert "Validation Error" not in text


def test_every_documented_error_uses_the_real_envelope(schema):
    for name, operation in _operations(schema):
        for status, response in operation["responses"].items():
            if int(status) >= 400 and name != "GET /api/v1/health":
                assert response["content"]["application/json"]["schema"] == {"$ref": "#/components/schemas/ErrorBody"}, (name, status)
                assert response["description"].startswith("- `"), (name, status)


def test_a_real_error_matches_the_documented_envelope(tmp_path):
    client = _client(tmp_path)
    for response in (client.get("/api/v1/papers/none"), client.get("/api/v1/search")):
        body = response.json()
        docs.ErrorBody.model_validate(body)
        assert set(docs.ErrorBody.model_fields) >= set(body)


def test_a_declared_422_also_keeps_the_format_error(schema):
    response = schema["paths"]["/api/v1/anchors"]["post"]["responses"]["422"]
    assert "`INVALID_REQUEST`" in response["description"]
    assert "`INVALID_ANCHOR`" in response["description"]
    assert "`IDEMPOTENCY_KEY_REUSED`" in response["description"]


def test_every_error_the_core_raises_is_in_the_table():
    documented = {(status, code.split("@")[0]) for code, (status, _) in docs._ERRORS.items()}
    raised = set()
    for path in SOURCE.rglob("*.py"):
        if "integrations" in path.parts or path.name == "errors.py":
            continue  # 브리지는 따로 도는 앱이고 문서를 열지 않는다
        text = path.read_text(encoding="utf-8")
        raised |= {(int(status), code) for status, code in re.findall(r'ApiError\(\s*(\d{3}),\s*"([A-Z_]+)"', text)}
        raised |= {(int(status), code) for code, status in re.findall(r'"([A-Z_]+)": \((\d{3}), ', text) if path.name == "routes.py"}
    assert len(raised) > 20
    assert raised <= documented, raised - documented


def test_every_upload_rejection_is_documented(schema):
    description = schema["paths"]["/api/v1/papers"]["post"]["responses"]["422"]["description"]
    source = (SOURCE / "documents" / "routes.py").read_text(encoding="utf-8")
    block = source[source.index("_REJECTION_MESSAGES = {") : source.index("}", source.index("_REJECTION_MESSAGES = {"))]
    codes = re.findall(r'"([A-Z_]+)":', block)
    assert len(codes) == 5
    for code in codes:
        assert f"`{code}`" in description


def test_the_upload_body_is_a_pdf_file(schema):
    operation = schema["paths"]["/api/v1/papers"]["post"]
    assert operation["requestBody"]["content"]["application/pdf"]["schema"]["format"] == "binary"
    assert [parameter["name"] for parameter in operation["parameters"]] == ["X-Paperloom-Filename"]


@pytest.mark.parametrize(
    "path, media_type",
    [
        ("/api/v1/versions/{version_id}/pdf", "application/pdf"),
        ("/api/v1/anchors/{anchor_id}/image", "image/png"),
        ("/api/v1/versions/{version_id}/pages/{page_index}/image", "image/png"),
        ("/api/v1/context-packets/{packet_id}/export.md", "text/markdown"),
        ("/api/v1/context-packets/{packet_id}/export.zip", "application/zip"),
    ],
)
def test_file_responses_name_their_type_and_not_json(schema, path, media_type):
    assert list(schema["paths"][path]["get"]["responses"]["200"]["content"]) == [media_type]


def test_the_retried_bundle_response_is_documented(schema):
    responses = schema["paths"]["/api/v1/evidence-bundles"]["post"]["responses"]
    assert {"200", "201"} <= set(responses)
    assert responses["200"]["content"]["application/json"]["schema"] == responses["201"]["content"]["application/json"]["schema"]


def test_the_health_model_matches_the_real_response(tmp_path):
    body = _client(tmp_path).get("/api/v1/health").json()
    docs.Health.model_validate(body)
    assert set(body) == set(docs.Health.model_fields)


@pytest.fixture
def web_dist(tmp_path: Path) -> Path:
    directory = tmp_path / "dist"
    directory.mkdir()
    (directory / "index.html").write_text("<!doctype html>", encoding="utf-8")
    return directory


def test_docs_page_loads_only_local_files(tmp_path, web_dist):
    client = _client(tmp_path, web_dist)
    response = client.get("/docs")
    assert response.status_code == 200
    assert 'src="/swagger/swagger-ui-bundle.js"' in response.text
    assert 'href="/swagger/swagger-ui.css"' in response.text
    assert 'href="/favicon.svg"' in response.text
    assert "http://" not in response.text and "https://" not in response.text


def test_the_page_that_would_call_a_cdn_is_closed(tmp_path, web_dist):
    client = _client(tmp_path, web_dist)
    assert client.get("/redoc").status_code == 404


def test_without_a_web_build_there_is_no_docs_page_but_the_schema_stays(tmp_path):
    client = _client(tmp_path)
    assert client.get("/docs").status_code == 404
    assert client.get("/redoc").status_code == 404
    assert client.get("/openapi.json").status_code == 200
