"""대화 답의 아티팩트를 이 PC에서 여는 페이지 파일 (2026-11-08 사용자 요청: claude.ai 링크 대신 파일과 링크).

웹이 만든 격리 문서(apps/web/src/features/artifacts/standalone.ts)를 내용의 sha256으로 이름 붙여 `<id>.html`로 쓴다. 같은
내용은 같은 파일·링크다. 다 쓴 파일만 그 이름으로 보인다(숨김 임시 이름에 쓰고 fsync한 뒤 바꾼다). 쓴 파일은 고치지 않고,
지우기는 사용자가 파일 탐색기로 한다.
"""

import hashlib
import os
import re
import secrets
from pathlib import Path

ID = re.compile(r"[0-9a-f]{32}")
TEMPORARY = ".tmp-"


class ArtifactStore:
    def __init__(self, directory: Path, shown_dir: str | None = None) -> None:
        self._directory = directory
        self._shown_dir = shown_dir

    def save(self, html: str) -> tuple[str, bool]:
        """페이지의 id와 이번에 새로 썼는지. 쓰지 못하면 OSError이고 아무것도 남지 않는다."""
        content = html.encode("utf-8")
        artifact_id = hashlib.sha256(content).hexdigest()[:32]
        target = self._directory / f"{artifact_id}.html"
        if target.is_file():
            return artifact_id, False
        self._directory.mkdir(parents=True, exist_ok=True)
        temporary = self._directory / f"{TEMPORARY}{artifact_id}-{secrets.token_hex(4)}"
        try:
            with temporary.open("xb") as out:
                out.write(content)
                out.flush()
                os.fsync(out.fileno())
            os.replace(temporary, target)
        except BaseException:
            temporary.unlink(missing_ok=True)
            raise
        return artifact_id, True

    def file(self, artifact_id: str) -> Path | None:
        """id의 페이지 파일. id 모양이 아니거나(경로 글자 등) 파일이 없으면 None"""
        if not ID.fullmatch(artifact_id):
            return None
        path = self._directory / f"{artifact_id}.html"
        return path if path.is_file() else None

    def shown_path(self, artifact_id: str) -> str:
        """화면에 보일 파일 경로. Docker처럼 서버가 쓰는 폴더가 이 PC의 다른 폴더에 붙어 있으면 설정의 shown_dir 기준이다.
        이 PC에서 바로 돌면 사용자 이름이 드러나지 않게 사용자 폴더를 ~로 쓴다(Wiki outbox와 같다)."""
        name = f"{artifact_id}.html"
        if self._shown_dir:
            return f"{self._shown_dir.rstrip('/')}/{name}"
        path = self._directory / name
        try:
            return f"~/{path.relative_to(Path.home()).as_posix()}"
        except ValueError:
            return path.as_posix()
