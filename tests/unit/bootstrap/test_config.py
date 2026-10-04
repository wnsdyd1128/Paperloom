from pathlib import Path

import pytest
from pydantic import ValidationError

from paperloom.bootstrap.config import load_settings

REPO_ROOT = Path(__file__).resolve().parents[3]


def write_config(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "config" / "paperloom.yaml"
    path.parent.mkdir()
    path.write_text(text, encoding="utf-8")
    return path


def test_local_config_binds_loopback_and_uses_repo_var():
    settings = load_settings(REPO_ROOT / "ops" / "config" / "local.yaml")

    assert settings.app.mode == "local"
    assert settings.app.bind_host == "127.0.0.1"
    assert settings.app.data_dir == REPO_ROOT / "var"
    assert settings.cost_policy.mode == "plan_only"


def test_relative_paths_resolve_against_config_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)  # 실행 위치와 설정 파일 위치를 다르게 둔다
    path = write_config(tmp_path, "app:\n  data_dir: ../data\n  web_dist_dir: web\n")

    settings = load_settings(path)

    assert settings.app.data_dir == (tmp_path / "data").resolve()
    assert settings.app.web_dist_dir == (tmp_path / "config" / "web").resolve()


@pytest.mark.parametrize(
    "flag", ["paid_model_calls_allowed", "paid_fallback_allowed", "automatic_credit_purchase_allowed"]
)
def test_paid_cost_flags_are_rejected(tmp_path, flag):
    path = write_config(tmp_path, f"app:\n  data_dir: data\ncost_policy:\n  {flag}: true\n")

    with pytest.raises(ValidationError):
        load_settings(path)


@pytest.mark.parametrize(
    "extra",
    [
        "openai_api_key: sk-test",  # 알 수 없는 최상위 키
        "app:\n  data_dir: data\n  mode: connected",  # connected 프로파일은 없다(MCP 연결은 뺐다)
    ],
)
def test_unknown_keys_and_unimplemented_modes_are_rejected(tmp_path, extra):
    text = extra if extra.startswith("app:") else f"app:\n  data_dir: data\n{extra}\n"
    path = write_config(tmp_path, text)

    with pytest.raises(ValidationError):
        load_settings(path)
