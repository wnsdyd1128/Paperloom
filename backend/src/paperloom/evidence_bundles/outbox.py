"""LLM Wiki가 읽기 전용으로 붙이는 outbox 폴더 (03-api-spec §5.3). Paperloom은 이 폴더에 bundle을 쓰기만 한다.

다 쓴 bundle만 `bundle_<id>` 이름으로 보인다: 숨김 임시 폴더에 다 쓰고 fsync한 뒤 이름을 바꾼다. LLM Wiki는 숨김 이름을 보지
않으므로 쓰는 중인 bundle은 보이지 않는다. 다 쓴 bundle은 고치거나 지우지 않는다. 지우기는 사용자가 파일 탐색기로 한다.
"""

import errno
import os
import shutil
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import Literal

Status = Literal["ready", "not_configured", "unwritable"]
TEMPORARY = ".tmp-"


class Outbox:
    def __init__(self, path: Path | None) -> None:
        self._path = path

    def status(self) -> Status:
        """폴더가 있고 쓸 수 있는지. 시험 파일을 만들었다 지워 본다(Windows에서는 os.access를 믿을 수 없다)."""
        if self._path is None or not self._path.is_dir():
            return "not_configured"
        try:
            with tempfile.NamedTemporaryFile(dir=self._path, prefix=".probe-"):
                return "ready"
        except OSError:
            return "unwritable"

    def shown_path(self) -> str | None:
        """화면에 보일 경로. Docker면 컨테이너 안 경로다. 이 PC에서 바로 돌면 사용자 이름이 드러나지 않게 사용자 폴더를 ~로 쓴다."""
        if self._path is None:
            return None
        try:
            return f"~/{self._path.relative_to(Path.home()).as_posix()}"
        except ValueError:
            return self._path.as_posix()

    def discard_incomplete(self) -> int:
        """이전 실행이 쓰다 끊긴 임시 폴더를 지운다. 폴더가 없으면 할 일이 없다."""
        if self._path is None or not self._path.is_dir():
            return 0
        leftovers = list(self._path.glob(f"{TEMPORARY}*"))
        for path in leftovers:
            shutil.rmtree(path, ignore_errors=True)
        return len(leftovers)

    def holds(self, bundle_id: str) -> bool:
        return self._path is not None and (self._path / f"bundle_{bundle_id}").is_dir()

    def write(self, bundle_id: str, files: Mapping[str, bytes]) -> None:
        """files(bundle 안 경로 → 내용)를 차례대로 쓰고 이름을 바꾼다. manifest.json이 맨 뒤여야 한다. 실패하면 OSError이고 아무것도 남지 않는다."""
        if self._path is None:
            raise FileNotFoundError("outbox를 설정하지 않았습니다.")
        temporary = self._path / f"{TEMPORARY}{bundle_id}"
        try:
            temporary.mkdir()
            folders = {temporary}
            for relative, content in files.items():
                target = temporary / relative
                target.parent.mkdir(exist_ok=True)
                folders.add(target.parent)
                with target.open("xb") as out:
                    out.write(content)
                    out.flush()
                    os.fsync(out.fileno())
            for folder in folders:
                _sync_folder(folder)
            os.rename(temporary, self._path / f"bundle_{bundle_id}")
            _sync_folder(self._path)
        except BaseException:
            shutil.rmtree(temporary, ignore_errors=True)
            raise


def _sync_folder(path: Path) -> None:
    """폴더의 이름 목록을 디스크에 맞춘다. Windows는 폴더를 열 수 없고, 파일 공유(Docker Desktop bind mount)는 폴더 fsync를 거부할
    수 있다. 그래도 파일 내용은 이미 fsync했고 이름 바꾸기는 그대로 원자적이다."""
    if os.name == "nt":
        return
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    except OSError as error:
        if error.errno not in (errno.EINVAL, errno.ENOTSUP):
            raise
    finally:
        os.close(descriptor)
