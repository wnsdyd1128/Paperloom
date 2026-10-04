"""첨자 추정 fixture(G2 R14)가 생성기와 일치하는지. 추정 결과는 웹 E2E(apps/web/e2e/annotations.spec.ts)가 확인한다."""

import importlib.util
import json
from pathlib import Path

FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "pdf-layout"


def test_fixture_is_current():
    spec = importlib.util.spec_from_file_location("subscripts_generator", FIXTURE_DIR / "generate_subscripts.py")
    generator = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(generator)

    assert generator.build_pdf() == (FIXTURE_DIR / "subscripts.pdf").read_bytes()
    assert generator.expected() == json.loads((FIXTURE_DIR / "subscripts.json").read_text(encoding="utf-8"))
