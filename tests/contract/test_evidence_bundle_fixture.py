"""계약 fixture(NFR-10)가 생성기와 일치하고 수신기 규칙을 지키는지, 새 API가 OpenAPI에 있는지."""

import importlib.util
from pathlib import Path

import pytest

from paperloom.bootstrap.app import create_app
from paperloom.bootstrap.config import AppSettings, Settings

FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "evidence-bundles"


def _generator():
    spec = importlib.util.spec_from_file_location("bundle_generator", FIXTURE_DIR / "generate_bundles.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("name", ["v1", "v1.1"])
def test_fixture_is_current_and_follows_the_receiver_rules(name, check_evidence_bundle):
    generator = _generator()
    folder = generator.folder(name)
    on_disk = {path.relative_to(folder).as_posix(): path.read_bytes() for path in folder.rglob("*") if path.is_file()}

    assert on_disk == generator.build(name)
    assert check_evidence_bundle(folder)["schema_version"] == f"paperloom-bundle.{name}"


def test_new_routes_are_in_the_openapi_schema(tmp_path):
    paths = create_app(Settings(app=AppSettings(mode="test", data_dir=tmp_path))).openapi()["paths"]

    assert set(paths["/api/v1/evidence-bundles"]) == {"get", "post"}
    assert set(paths["/api/v1/evidence-bundles/preview"]) == {"post"}
    assert set(paths["/api/v1/evidence-bundles/{bundle_id}"]) == {"get"}
    assert "get" in paths["/api/v1/versions/{version_id}/anchors"]
