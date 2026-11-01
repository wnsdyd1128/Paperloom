"""공용 fixture. 테스트 PDF는 저작권 문제가 없도록 실행 중에 합성한다 (IMPL §14.1)."""

import hashlib
import io
import json
import re
import struct
import zlib
from pathlib import Path

import pypdf
import pytest


def build_pdf(pages: int = 1, title: str | None = None, user_password: str | None = None) -> bytes:
    writer = pypdf.PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=612, height=792)
    if title is not None:
        writer.add_metadata({"/Title": title})
    if user_password is not None:
        writer.encrypt(user_password=user_password, owner_password="owner")
    buffer = io.BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


@pytest.fixture
def make_pdf():
    return build_pdf


def _decode_png(data: bytes) -> tuple[int, int, list[bytes]]:
    """영역 이미지 PNG(8비트 RGB, 행마다 필터 0)를 (폭, 높이, RGB 행 목록)으로 푼다. CRC도 확인한다."""
    assert data.startswith(b"\x89PNG\r\n\x1a\n")
    offset, chunks = 8, {}
    while offset < len(data):
        (length,) = struct.unpack(">I", data[offset : offset + 4])
        kind = data[offset + 4 : offset + 8]
        body = data[offset + 8 : offset + 8 + length]
        assert struct.unpack(">I", data[offset + 8 + length : offset + 12 + length])[0] == zlib.crc32(kind + body)
        chunks[kind] = chunks.get(kind, b"") + body
        offset += 12 + length
    width, height, depth, color_type = struct.unpack(">IIBB", chunks[b"IHDR"][:10])
    assert (depth, color_type) == (8, 2)
    raw = zlib.decompress(chunks[b"IDAT"])
    rows = [raw[y * (1 + 3 * width) : (y + 1) * (1 + 3 * width)] for y in range(height)]
    assert all(row[0] == 0 for row in rows)
    return width, height, [row[1:] for row in rows]


@pytest.fixture
def decode_png():
    return _decode_png


_BUNDLE_NAME = re.compile(r"bundle_[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
_BUNDLE_FOLDERS = {"proposals": (".json",), "artifacts": (".md",), "assets": (".png",), "texts": (".json",)}
_BUNDLE_TOP = {"manifest.json", "sources.json", "anchors.json"}
_SOURCE_FIELDS = {"source_ref", "paper_id", "version_id", "sha256", "page_count", "title"}
_ANCHOR_FIELDS = {"anchor_ref", "anchor_id", "source_ref", "kind", "page_index", "quads", "quote", "prefix", "suffix"}


def _check_evidence_bundle(folder: Path) -> dict:
    """bundle 폴더를 LLM Wiki 수신기의 거부 규칙(03-api-spec §10)대로 검사하고 manifest를 돌려준다. 수신기 저장소 없이 CI에서 도는
    사본이다. 실제 수신기는 tests/contract/test_llm_wiki_receiver.py가 부른다."""
    assert _BUNDLE_NAME.fullmatch(folder.name), folder.name
    present = {}
    for path in sorted(folder.rglob("*")):
        relative = path.relative_to(folder).as_posix()
        assert not path.is_symlink() and not path.name.startswith("."), relative
        assert not path.name.lower().endswith(".pdf"), relative  # 원본 PDF는 넣지 않는다
        if path.is_dir():
            assert relative in _BUNDLE_FOLDERS, relative
            continue
        top, *rest = relative.split("/")
        if rest:
            assert len(rest) == 1 and path.suffix in _BUNDLE_FOLDERS[top], relative
        else:
            assert relative in _BUNDLE_TOP, relative
        present[relative] = path.read_bytes()
    assert _BUNDLE_TOP <= set(present)
    assert len(present) <= 64
    assert sum(map(len, present.values())) <= 32 * 1024 * 1024
    assert all(len(data) <= 8 * 1024 * 1024 for data in present.values())
    for relative, data in present.items():
        if not relative.endswith(".png"):
            assert not data.startswith(b"\xef\xbb\xbf"), relative
            data.decode("utf-8")

    manifest = json.loads(present["manifest.json"])
    assert re.fullmatch(r"paperloom-bundle\.v1(\.\d+)?", manifest["schema_version"])
    assert f"bundle_{manifest['bundle_id']}" == folder.name
    assert manifest["producer"]["name"] == "paperloom" and manifest["created_at"]
    listed = [item["path"] for item in manifest["files"]]
    assert len(set(listed)) == len(listed)
    assert set(listed) == set(present) - {"manifest.json"}
    for item in manifest["files"]:
        assert item["size_bytes"] == len(present[item["path"]]), item["path"]
        assert item["sha256"] == hashlib.sha256(present[item["path"]]).hexdigest(), item["path"]

    sources, anchors = json.loads(present["sources.json"]), json.loads(present["anchors.json"])
    source_refs = [item["source_ref"] for item in sources]
    anchor_refs = [item["anchor_ref"] for item in anchors]
    assert len(set(source_refs)) == len(source_refs) and len(set(anchor_refs)) == len(anchor_refs)
    assert all(_SOURCE_FIELDS <= set(item) for item in sources) and all(_ANCHOR_FIELDS <= set(item) for item in anchors)
    assert all(re.fullmatch(r"[0-9a-f]{64}", item["sha256"]) for item in sources)
    assert all(item["source_ref"] in source_refs for item in anchors)
    assert all(item["asset"] in present for item in anchors if item.get("asset"))
    seen = set()
    for relative in (path for path in present if path.startswith("proposals/")):
        proposal = json.loads(present[relative])
        assert proposal["schema_version"] == "wiki-proposal.v1" and proposal["bundle_id"] == manifest["bundle_id"]
        assert proposal["operation"] == "propose_note" and proposal["requires_user_approval"] is True
        assert proposal["target_note_id"] is None and proposal["base_content_sha256"] is None
        assert proposal["content_file"].startswith("artifacts/") and proposal["content_file"] in present
        assert len(proposal["source_refs"]) == 1 and set(proposal["source_refs"]) <= set(source_refs)
        assert set(proposal["anchor_refs"]) <= set(anchor_refs)
        assert proposal["proposal_id"] not in seen
        seen.add(proposal["proposal_id"])
    has_texts = any(path.startswith("texts/") for path in present)
    assert manifest["schema_version"] == ("paperloom-bundle.v1.1" if has_texts else "paperloom-bundle.v1")
    assert manifest.get("features") == (["texts"] if has_texts else None)
    return manifest


@pytest.fixture
def check_evidence_bundle():
    return _check_evidence_bundle

