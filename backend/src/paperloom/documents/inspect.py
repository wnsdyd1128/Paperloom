"""업로드된 PDF를 격리된 하위 프로세스에서 연다 (IMPL §5.1).

신뢰할 수 없는 PDF의 파싱이 서버 프로세스를 멈추거나 메모리를 소진하지 않도록 시간 제한을 두고,
POSIX(컨테이너)에서는 메모리·CPU 제한도 건다(`infrastructure.isolation`). Windows에서는 시간 제한만 적용된다.

하위 프로세스: `python -m paperloom.documents.inspect <path>` → stdout에 JSON 한 줄.
"""

import json
import re
import subprocess
import sys
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from paperloom.infrastructure.isolation import limit_resources

_MAX_TITLE_CHARS = 300


@dataclass(frozen=True)
class PdfInfo:
    page_count: int
    title: str | None


class PdfRejected(Exception):
    """거부 사유 코드는 IMPL §5.2를 따른다: PASSWORD_REQUIRED, MALFORMED_PDF, RESOURCE_LIMIT, PARSER_ERROR."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def inspect_pdf(path: Path, timeout_seconds: float) -> PdfInfo:
    try:
        result = subprocess.run(
            [sys.executable, "-m", "paperloom.documents.inspect", str(path)],
            capture_output=True,
            timeout=timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired:
        raise PdfRejected("RESOURCE_LIMIT") from None
    try:
        report = json.loads(result.stdout)
    except ValueError:
        raise PdfRejected("PARSER_ERROR") from None  # 비정상 종료
    if "code" in report:
        raise PdfRejected(report["code"])
    return PdfInfo(page_count=report["page_count"], title=report["title"])


# 출판사가 메타데이터 제목에 넣는 표시 태그(<underline>·<italic>·<sub>·<inline-formula> 등, IEEE). 부등호(a < b)는 남는다.
_MARKUP = re.compile(r"</?[A-Za-z][\w.:-]*(?:\s[^<>]*)?/?>")


def clean_text(value: str | None, max_chars: int = _MAX_TITLE_CHARS) -> str | None:
    """PDF 메타데이터·파일명에서 온 문자열의 표시 태그와 제어 문자를 없애고 공백을 정리한다."""
    if not value:
        return None
    printable = "".join(" " if unicodedata.category(ch)[0] in "CZ" else ch for ch in _MARKUP.sub("", value))
    text = re.sub(r"\s+", " ", printable).strip()[:max_chars]
    return text or None


def _inspect(path: str) -> dict[str, object]:
    import pypdfium2 as pdfium
    import pypdfium2.raw as pdfium_c

    try:
        document = pdfium.PdfDocument(path)
    except pdfium.PdfiumError as error:
        return {"code": "PASSWORD_REQUIRED" if error.err_code == pdfium_c.FPDF_ERR_PASSWORD else "MALFORMED_PDF"}
    try:
        return {"page_count": len(document), "title": clean_text(document.get_metadata_dict().get("Title"))}
    finally:
        document.close()


def _main() -> None:
    limit_resources()
    try:
        report = _inspect(sys.argv[1])
    except MemoryError:
        report = {"code": "RESOURCE_LIMIT"}
    print(json.dumps(report))


if __name__ == "__main__":
    _main()
