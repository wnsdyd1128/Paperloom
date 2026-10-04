"""원본 PDF 파일 저장소 (IMPL §4.2).

업로드는 `tmp/`에 스트리밍하면서 크기와 SHA-256을 계산하고, 검사가 끝난 뒤
`sources/<version_id>.pdf`로 원자적으로 옮긴다. 업로드 파일명은 경로에 쓰지 않는다.
저장된 원본은 읽기 전용으로 두어 실수로 덮어쓰지 않게 한다.
"""

import hashlib
import os
import stat
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path

_HEAD_BYTES = 1024  # PDF 헤더는 파일 앞 1024바이트 안에 있어야 한다


@dataclass(frozen=True)
class ReceivedFile:
    path: Path
    sha256: str
    size_bytes: int
    head: bytes


class UploadTooLarge(Exception):
    pass


class SourceStore:
    def __init__(self, data_dir: Path) -> None:
        self._root = data_dir
        self._tmp_dir = data_dir / "tmp"
        self._sources_dir = data_dir / "sources"
        self._tmp_dir.mkdir(parents=True, exist_ok=True)
        self._sources_dir.mkdir(parents=True, exist_ok=True)

    def discard_incomplete_uploads(self) -> int:
        """이전 실행에서 남은 임시 업로드를 지운다. 저장된 원본(`sources/`)은 건드리지 않는다."""
        leftovers = list(self._tmp_dir.glob("*.part"))
        for path in leftovers:
            path.unlink()
        return len(leftovers)

    async def receive(self, chunks: AsyncIterator[bytes], max_bytes: int) -> ReceivedFile:
        path = self._tmp_dir / f"{uuid.uuid4()}.part"
        digest = hashlib.sha256()
        size = 0
        head = b""
        try:
            with path.open("xb") as out:
                async for chunk in chunks:
                    size += len(chunk)
                    if size > max_bytes:
                        raise UploadTooLarge
                    if len(head) < _HEAD_BYTES:
                        head += chunk[: _HEAD_BYTES - len(head)]
                    digest.update(chunk)
                    out.write(chunk)
        except BaseException:
            path.unlink(missing_ok=True)
            raise
        return ReceivedFile(path=path, sha256=digest.hexdigest(), size_bytes=size, head=head)

    def commit(self, received: ReceivedFile, version_id: str) -> str:
        """임시 파일을 원본 위치로 옮기고 `storage_ref`를 돌려준다."""
        storage_ref = f"sources/{version_id}.pdf"
        target = self._root / storage_ref
        os.replace(received.path, target)  # tmp/와 sources/는 같은 파일시스템이므로 원자적
        target.chmod(stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)
        return storage_ref

    def remove_committed(self, storage_ref: str) -> None:
        """DB 등록에 실패한 사본만 지운다. 등록된 원본을 지우는 경로가 아니다."""
        target = self._root / storage_ref
        target.chmod(stat.S_IWUSR | stat.S_IRUSR)
        target.unlink()

    def path_for(self, storage_ref: str) -> Path:
        return self._root / storage_ref
