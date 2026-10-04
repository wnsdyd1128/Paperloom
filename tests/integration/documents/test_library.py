"""PDF 등록·Library 수직 경로 (G1 L06–L09)."""

import hashlib
import os
from pathlib import Path
from urllib.parse import quote

import pytest
from fastapi.testclient import TestClient

from paperloom.bootstrap.app import create_app
from paperloom.bootstrap.config import AppSettings, Settings
from paperloom.documents.service import UploadLimits


def make_client(data_dir: Path, limits: UploadLimits = UploadLimits()) -> TestClient:
    return TestClient(create_app(Settings(app=AppSettings(mode="test", data_dir=data_dir)), upload_limits=limits))


def upload(client: TestClient, content, filename: str = "paper.pdf", content_type: str = "application/pdf"):
    headers = {"Content-Type": content_type, "X-Paperloom-Filename": quote(filename)}
    return client.post("/api/v1/papers", content=content, headers=headers)


def stored_files(data_dir: Path, subdir: str) -> list[Path]:
    return sorted((data_dir / subdir).iterdir())


@pytest.fixture
def data_dir(tmp_path: Path) -> Path:
    return tmp_path / "data"


@pytest.fixture
def client(data_dir: Path) -> TestClient:
    return make_client(data_dir)


def test_upload_registers_paper_and_keeps_original_bytes(client, data_dir, make_pdf):
    original = make_pdf(pages=3, title="  Attention\x00 Is  All You Need  ")

    response = upload(client, original, filename="download (1).pdf")

    assert response.status_code == 201
    paper = response.json()
    version = paper["current_version"]
    assert paper["title"] == "Attention Is All You Need"
    assert version["sha256"] == hashlib.sha256(original).hexdigest()
    assert (version["size_bytes"], version["page_count"], version["status"]) == (len(original), 3, "READY_TO_READ")
    assert client.get("/api/v1/papers").json()["papers"] == [paper]
    assert client.get(f"/api/v1/papers/{paper['paper_id']}").json() == paper

    served = client.get(f"/api/v1/versions/{version['version_id']}/pdf")
    assert served.headers["content-type"] == "application/pdf"
    assert served.content == original

    (stored,) = stored_files(data_dir, "sources")
    assert stored.name == f"{version['version_id']}.pdf"
    assert stored.read_bytes() == original
    assert not os.access(stored, os.W_OK)  # 원본은 읽기 전용
    assert stored_files(data_dir, "tmp") == []


def test_title_falls_back_to_filename_without_using_it_as_path(client, data_dir, make_pdf):
    response = upload(client, make_pdf(), filename="../../밖으로/..\\evil 논문.PDF")

    assert response.status_code == 201
    assert response.json()["title"] == "evil 논문"
    assert [path.parent for path in stored_files(data_dir, "sources")] == [data_dir / "sources"]
    assert sorted(path.name for path in data_dir.parent.iterdir()) == ["data"]


def test_same_bytes_are_reported_as_duplicate(client, data_dir, make_pdf):
    original = make_pdf(title="First")
    first = upload(client, original).json()

    response = upload(client, original, filename="renamed copy.pdf")

    assert response.status_code == 409
    body = response.json()
    assert body["code"] == "DUPLICATE_SOURCE"
    assert body["details"] == {"paper_id": first["paper_id"]}
    assert set(body) >= {"message", "request_id", "retryable"}
    assert len(client.get("/api/v1/papers").json()["papers"]) == 1
    assert len(stored_files(data_dir, "sources")) == 1
    assert stored_files(data_dir, "tmp") == []


def test_same_title_with_different_bytes_is_not_merged(client, make_pdf):
    upload(client, make_pdf(pages=1, title="Same Title"))

    response = upload(client, make_pdf(pages=2, title="Same Title"))

    assert response.status_code == 201
    assert len(client.get("/api/v1/papers").json()["papers"]) == 2


@pytest.mark.parametrize(
    ("content", "code"),
    [
        (b"", "NOT_PDF"),
        (b"hello, not a pdf", "NOT_PDF"),
        (b"%PDF-1.7\n garbage without objects", "MALFORMED_PDF"),
        ("encrypted", "PASSWORD_REQUIRED"),
    ],
)
def test_invalid_pdfs_are_rejected_without_leftovers(client, data_dir, make_pdf, content, code):
    body = make_pdf(user_password="secret") if content == "encrypted" else content

    response = upload(client, body)

    assert response.status_code == 422
    assert response.json()["code"] == code
    assert client.get("/api/v1/papers").json()["papers"] == []
    assert stored_files(data_dir, "sources") == []
    assert stored_files(data_dir, "tmp") == []


@pytest.mark.parametrize("chunked", [False, True])
def test_oversized_upload_is_rejected(data_dir, make_pdf, chunked):
    client = make_client(data_dir, UploadLimits(max_bytes=100))
    original = make_pdf()
    # chunked 전송에는 Content-Length가 없어 스트리밍 중 크기 검사를 탄다.
    content = iter([original[:60], original[60:]]) if chunked else original

    response = upload(client, content)

    assert response.status_code == 413
    assert response.json()["code"] == "TOO_LARGE"
    assert stored_files(data_dir, "tmp") == []


def test_page_limit_and_inspect_timeout_are_resource_limits(data_dir, make_pdf):
    too_many_pages = make_client(data_dir, UploadLimits(max_pages=2))
    assert upload(too_many_pages, make_pdf(pages=3)).json()["code"] == "RESOURCE_LIMIT"

    too_slow = make_client(data_dir, UploadLimits(inspect_timeout_seconds=0.001))
    assert upload(too_slow, make_pdf()).json()["code"] == "RESOURCE_LIMIT"
    assert stored_files(data_dir, "sources") == []


def test_wrong_media_type_is_rejected(client, make_pdf):
    response = upload(client, make_pdf(), content_type="application/octet-stream")

    assert response.status_code == 415
    assert response.json()["code"] == "UNSUPPORTED_MEDIA_TYPE"


def test_library_and_original_survive_restart(data_dir, make_pdf):
    original = make_pdf(title="Persistent")
    paper = upload(make_client(data_dir), original).json()

    restarted = make_client(data_dir)

    assert restarted.get("/api/v1/papers").json()["papers"] == [paper]
    version_id = paper["current_version"]["version_id"]
    assert restarted.get(f"/api/v1/versions/{version_id}/pdf").content == original


def test_incomplete_uploads_are_removed_on_start_but_sources_are_kept(data_dir, make_pdf):
    paper = upload(make_client(data_dir), make_pdf()).json()
    leftover = data_dir / "tmp" / "crashed-upload.part"
    leftover.write_bytes(b"%PDF-partial")

    make_client(data_dir)

    assert not leftover.exists()
    assert [path.stem for path in stored_files(data_dir, "sources")] == [paper["current_version"]["version_id"]]


def test_source_pdf_supports_range_requests(client, make_pdf):
    original = make_pdf()
    version_id = upload(client, original).json()["current_version"]["version_id"]

    response = client.get(f"/api/v1/versions/{version_id}/pdf", headers={"Range": "bytes=0-4"})

    assert response.status_code == 206
    assert response.content == original[:5] == b"%PDF-"


@pytest.mark.parametrize(
    "path", ["/api/v1/papers/unknown", "/api/v1/versions/unknown/pdf", "/api/v1/versions/..%2F..%2Fpaperloom.sqlite3/pdf"]
)
def test_unknown_ids_are_not_found(client, path):
    response = client.get(path)

    assert response.status_code == 404
    assert response.json()["code"] == "NOT_FOUND"
