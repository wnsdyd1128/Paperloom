"""실행 설정 계약 (IMPL §3). YAML 파일을 읽어 검증한다.

알 수 없는 키는 거부한다. 비용 경계 플래그는 v0.1에서 false만 허용하지만, 설정 값만으로
비용 경계를 보장하지는 않는다 — 의존성 감사(tests/contract)와 함께 둔다.
모델 API 키 환경변수는 읽지 않는다.
"""

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class AppSettings(_Strict):
    # `connected` 프로파일은 없다(MCP 연결 W07은 2026-10-05에 뺐다).
    mode: Literal["local", "test"] = "local"
    bind_host: str = "127.0.0.1"
    port: int = Field(default=8000, ge=1, le=65535)
    data_dir: Path
    # 빌드된 웹 정적 파일. 없으면 API만 제공하고 웹은 Vite 개발 서버가 맡는다.
    web_dist_dir: Path | None = None
    # Reader의 Claude 대화 탭이 부르는 이 PC의 Claude Code 브리지 주소 (ADR 0003). 웹이 health로 받는다.
    claude_code_url: str = "http://127.0.0.1:8001"


class CostPolicy(_Strict):
    mode: Literal["plan_only"] = "plan_only"
    paid_model_calls_allowed: Literal[False] = False
    paid_fallback_allowed: Literal[False] = False
    automatic_credit_purchase_allowed: Literal[False] = False


class Settings(_Strict):
    app: AppSettings
    cost_policy: CostPolicy = CostPolicy()


def load_settings(path: Path) -> Settings:
    """설정 파일을 읽는다. 파일 안의 상대 경로는 실행 위치가 아니라 설정 파일 위치 기준이다."""
    settings = Settings.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")) or {})
    base = path.resolve().parent
    web_dist_dir = settings.app.web_dist_dir
    app = settings.app.model_copy(
        update={
            "data_dir": _resolve(base, settings.app.data_dir),
            "web_dist_dir": _resolve(base, web_dist_dir) if web_dist_dir else None,
        }
    )
    return settings.model_copy(update={"app": app})


def _resolve(base: Path, path: Path) -> Path:
    return path if path.is_absolute() else (base / path).resolve()
