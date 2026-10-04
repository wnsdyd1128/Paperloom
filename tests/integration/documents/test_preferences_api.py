"""U6 설정 (UI_PLAN §5 U6, A2, 사용자 결정 D7): 이 PC의 Core DB에 둔다. 웹·브리지가 같은 값을 읽는다."""

import json
import sqlite3
from contextlib import closing
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from paperloom.bootstrap.app import create_app
from paperloom.bootstrap.config import AppSettings, Settings

DEFAULTS = {
    "answer_language": "ko",
    "default_model": "sonnet",  # D7: 계정 기본(Opus) 대신 Sonnet
    "paper_text_chars": 120_000,
    "theme": "system",
    "font_size": 14,
    "translation_font_size": None,
    "math_delimiters": "dollar",
    "prompts": {"system": "", "explain": "", "translate": "", "summary": ""},
}
CHANGED = {
    "answer_language": "en",
    "default_model": "opus",
    "paper_text_chars": 40_000,
    "theme": "dark",
    "font_size": 16,
    "translation_font_size": 18,
    "math_delimiters": "bracket",
    "prompts": {"system": "대학원생입니다.", "explain": "직관부터", "translate": "용어는 영어로", "summary": "한계도"},
}


def make_client(data_dir: Path) -> TestClient:
    return TestClient(create_app(Settings(app=AppSettings(mode="test", data_dir=data_dir))))


@pytest.fixture
def data_dir(tmp_path: Path) -> Path:
    return tmp_path / "data"


@pytest.fixture
def client(data_dir: Path) -> TestClient:
    return make_client(data_dir)


def test_defaults_until_saved_and_saved_values_survive_a_restart(client, data_dir):
    assert client.get("/api/v1/settings").json() == DEFAULTS
    saved = client.put("/api/v1/settings", json=CHANGED)
    assert saved.status_code == 200 and saved.json() == CHANGED
    assert make_client(data_dir).get("/api/v1/settings").json() == CHANGED


@pytest.mark.parametrize(
    "changes",
    [
        {"answer_language": "ja"},
        {"default_model": "gpt"},
        {"default_model": None},
        {"paper_text_chars": 5_000},
        {"theme": "blue"},
        {"font_size": 30},
        {"font_size": 11},
        {"translation_font_size": 5},
        {"math_delimiters": "latex"},
        {"prompts": {**DEFAULTS["prompts"], "system": "x" * 2001}},
        {"prompts": {"system": ""}},
        {"extra": 1},
    ],
)
def test_bad_settings_are_rejected_and_nothing_changes(client, changes):
    response = client.put("/api/v1/settings", json={**DEFAULTS, **changes})
    assert (response.status_code, response.json()["code"]) == (422, "INVALID_REQUEST")
    assert client.get("/api/v1/settings").json() == DEFAULTS


def test_a_saved_value_that_no_longer_fits_the_contract_reads_as_the_defaults(client, data_dir):
    client.put("/api/v1/settings", json=CHANGED)
    older = {key: value for key, value in CHANGED.items() if key != "math_delimiters"}  # 예전 판이 저장한 값
    with closing(sqlite3.connect(data_dir / "paperloom.sqlite3")) as connection, connection:
        connection.execute("UPDATE preferences SET value_json = ?", (json.dumps(older),))
    assert client.get("/api/v1/settings").json() == DEFAULTS
    with closing(sqlite3.connect(data_dir / "paperloom.sqlite3")) as connection, connection:
        connection.execute("UPDATE preferences SET value_json = ?", ("{not json",))
    assert client.get("/api/v1/settings").json() == DEFAULTS


def test_every_setting_must_be_sent(client):
    partial = {key: value for key, value in CHANGED.items() if key != "theme"}
    assert client.put("/api/v1/settings", json=partial).status_code == 422
