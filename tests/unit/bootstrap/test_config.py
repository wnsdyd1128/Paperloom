import shutil
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


def home(tmp_path: Path, monkeypatch) -> Path:
    """~가 가리킬 사용자 폴더 (Path.expanduser: Windows는 USERPROFILE, 그 밖은 HOME)"""
    folder = tmp_path / "home"
    monkeypatch.setenv("HOME", str(folder))
    monkeypatch.setenv("USERPROFILE", str(folder))
    return folder


def test_tilde_paths_resolve_against_the_user_folder(tmp_path, monkeypatch):
    user = home(tmp_path, monkeypatch)
    path = write_config(tmp_path, "app:\n  data_dir: ~/.paperloom/data\n")

    assert load_settings(path).app.data_dir == user / ".paperloom" / "data"


def test_bundle_config_keeps_web_and_models_inside_the_bundle_and_the_library_outside(tmp_path, monkeypatch):
    """Windows 압축본(ops/bundle/build.py)은 bundle.yaml을 config/paperloom.yaml로 넣는다. 새 판으로 폴더를 바꿔도 서재가 남는다."""
    user = home(tmp_path, monkeypatch)
    bundle = tmp_path / "Paperloom"
    config = bundle / "config" / "paperloom.yaml"
    config.parent.mkdir(parents=True)
    shutil.copy(REPO_ROOT / "ops" / "config" / "bundle.yaml", config)

    settings = load_settings(config)

    assert (settings.app.mode, settings.app.bind_host) == ("local", "127.0.0.1")
    assert settings.app.data_dir == user / ".paperloom" / "data"
    assert settings.app.web_dist_dir == (bundle / "web").resolve()
    assert settings.layout.model_path.is_relative_to(bundle.resolve())
    assert settings.ocr.model_path.is_relative_to(bundle.resolve())


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
