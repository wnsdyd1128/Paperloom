"""outbox 쓰기 (03-api-spec §5.3): 다 쓴 bundle만 보이고, 실패하면 아무것도 남지 않고, 시작할 때 끊긴 임시 폴더를 지운다."""

import os
import tempfile
from pathlib import Path

import pytest

from paperloom.evidence_bundles import outbox as outbox_module
from paperloom.evidence_bundles.outbox import Outbox

BUNDLE = "0f6c2c1e-7a4b-4c8e-9d1a-2b3c4d5e6f70"
FILES = {"sources.json": b"[]", "artifacts/a.md": b"# a", "manifest.json": b"{}"}


def names(folder: Path) -> list[str]:
    return sorted(path.name for path in folder.iterdir())


def test_a_finished_bundle_appears_under_its_final_name_only(tmp_path):
    Outbox(tmp_path).write(BUNDLE, FILES)

    assert names(tmp_path) == [f"bundle_{BUNDLE}"]
    written = tmp_path / f"bundle_{BUNDLE}"
    assert {path.relative_to(written).as_posix(): path.read_bytes() for path in written.rglob("*") if path.is_file()} == FILES


def test_the_manifest_is_written_last_under_the_hidden_name(tmp_path, monkeypatch):
    """쓰는 중에는 숨김 이름이고, manifest가 맨 뒤다. 수신기는 manifest 없는 폴더를 받지 않는다."""
    seen = []
    real_fsync = os.fsync

    def recording_fsync(descriptor):
        seen.append(names(tmp_path))
        real_fsync(descriptor)

    monkeypatch.setattr(outbox_module.os, "fsync", recording_fsync)
    Outbox(tmp_path).write(BUNDLE, FILES)

    assert seen and all(listing == [f".tmp-{BUNDLE}"] for listing in seen[: len(FILES)])
    assert not (tmp_path / f"bundle_{BUNDLE}" / "nothing").exists()


@pytest.mark.parametrize("target", ["fsync", "rename"])
def test_a_failed_write_leaves_nothing(tmp_path, monkeypatch, target):
    def fail(*_):
        raise OSError("디스크가 찼습니다")

    monkeypatch.setattr(outbox_module.os, target, fail)
    with pytest.raises(OSError):
        Outbox(tmp_path).write(BUNDLE, FILES)

    assert names(tmp_path) == []


def test_only_interrupted_temporary_folders_are_discarded(tmp_path):
    (tmp_path / ".tmp-old").mkdir()
    (tmp_path / ".tmp-old" / "sources.json").write_bytes(b"[]")
    (tmp_path / f"bundle_{BUNDLE}").mkdir()

    assert Outbox(tmp_path).discard_incomplete() == 1
    assert names(tmp_path) == [f"bundle_{BUNDLE}"]


def test_status_needs_a_folder_that_takes_a_file(tmp_path, monkeypatch):
    assert Outbox(None).status() == "not_configured"
    assert Outbox(tmp_path / "없음").status() == "not_configured"
    assert Outbox(tmp_path).status() == "ready"
    assert names(tmp_path) == []  # 시험 파일을 남기지 않는다

    def refuse(**_):
        raise PermissionError

    monkeypatch.setattr(tempfile, "NamedTemporaryFile", refuse)
    assert Outbox(tmp_path).status() == "unwritable"


def test_nothing_to_discard_without_a_folder(tmp_path):
    assert Outbox(None).discard_incomplete() == 0
    assert Outbox(tmp_path / "없음").discard_incomplete() == 0


def test_the_shown_path_hides_the_user_folder():
    assert Outbox(None).shown_path() is None
    assert Outbox(Path.home() / "outbox").shown_path() == "~/outbox"
    assert Outbox(Path("/data/outbox")).shown_path() == "/data/outbox"
