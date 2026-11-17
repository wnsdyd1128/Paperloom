"""논문 서지 조회 (2026-11-16 사용자 결정: D5의 "외부 조회 없음"을 바꿔, 비어 있는 저자·연도를 DOI·arXiv 번호로 물어 채운다).

DOI가 있으면 Crossref(api.crossref.org)에, 없거나 Crossref에 없으면 첫 쪽의 arXiv 번호로 arXiv API(export.arxiv.org)에 묻는다.
arXiv DOI(10.48550/arXiv.…)는 Crossref에 없으므로 arXiv에 묻는다. 밖으로 나가는 것은 이 식별자뿐이다.
arXiv 번호는 여백의 세로 표기(arXiv:1706.03762v7 [cs.CL] 2 Aug 2023)에 있다. 이 표기는 글자마다 문단이 되고(side_text) 읽는
차례가 쪽 위에서 아래라, 아래에서 위로(돌린 방향에 따라 위에서 아래로) 이어 읽는다. 서재의 arXiv 논문 넷에서 맞았다.
연도는 Crossref의 issued(처음 나온 해), arXiv의 published(첫 판을 올린 해)다.
"""

import json
import re
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ElementTree
from dataclasses import dataclass

from paperloom import __version__
from paperloom.documents.block_kinds import REFERENCE, SIDE_TEXT

_ARXIV = re.compile(r"arXiv:\s*(\d{4}\.\d{4,5}|[a-z][a-z.-]*/\d{7})(?:v\d+)?", re.IGNORECASE)
_ARXIV_DOI = re.compile(r"^10\.48550/arxiv\.(.+)$", re.IGNORECASE)
_ATOM = "{http://www.w3.org/2005/Atom}"
MAX_AUTHORS = 100  # 논문 정보 고치기(documents.models.MetadataIn)와 같은 한도
MAX_NAME = 300
TIMEOUT_SECONDS = 15
MAX_BYTES = 10_000_000  # Crossref 응답은 참고문헌 목록까지 담아 수백 KB가 되기도 한다


@dataclass(frozen=True)
class Record:
    authors: list[str]
    year: int | None


def find_arxiv_id(blocks: list[dict]) -> str | None:
    """첫 쪽 문단(text·regions·quality_flags, 읽는 차례)에서 arXiv 번호(판 번호 없이). 없으면 None."""
    side = sorted(
        (block for block in blocks if SIDE_TEXT in block["quality_flags"] and block["regions"]),
        key=lambda block: min(region[1] for region in block["regions"]),
    )
    stamps = ["".join(block["text"] for block in reversed(side)), "".join(block["text"] for block in side)]
    # 가로 글(머리글의 "Preprint. arXiv:…" 등)도 보되, 참고문헌이 인용한 다른 논문의 번호는 집지 않는다
    for text in [*stamps, *(block["text"] for block in blocks if REFERENCE not in block["quality_flags"])]:
        if match := _ARXIV.search(text):
            return match.group(1)
    return None


def identifiers(doi: str | None, blocks: list[dict]) -> list[tuple[str, str]]:
    """물을 차례: ("doi", DOI), ("arxiv", 번호). doi는 논문의 DOI(없거나 사용자가 지웠으면 None·빈 글), blocks는 첫 쪽 문단."""
    found: list[tuple[str, str]] = []
    if doi and (match := _ARXIV_DOI.match(doi)):
        found.append(("arxiv", match.group(1)))
    elif doi:
        found.append(("doi", doi))
    if (arxiv := find_arxiv_id(blocks)) and ("arxiv", arxiv) not in found:
        found.append(("arxiv", arxiv))
    return found


def crossref_record(body: dict) -> Record:
    """Crossref works 응답의 저자와 처음 나온 해"""
    message = body.get("message") or {}
    authors = [_crossref_name(author) for author in message.get("author") or []]
    year = None
    for key in ("issued", "published", "published-print", "published-online", "created"):
        parts = (message.get(key) or {}).get("date-parts") or []
        if parts and parts[0] and isinstance(parts[0][0], int):
            year = parts[0][0]
            break
    return _record(authors, year)


def _crossref_name(author: dict) -> str:
    if author.get("name"):  # 단체 저자
        return author["name"]
    return " ".join(part for part in (author.get("given"), author.get("family")) if part)


def arxiv_record(text: str) -> Record | None:
    """arXiv API(Atom) 응답의 저자와 첫 판을 올린 해. 그런 번호가 없으면 None."""
    entry = ElementTree.fromstring(text).find(f"{_ATOM}entry")
    if entry is None or "/api/errors" in (entry.findtext(f"{_ATOM}id") or ""):
        return None
    authors = [author.findtext(f"{_ATOM}name") or "" for author in entry.findall(f"{_ATOM}author")]
    published = (entry.findtext(f"{_ATOM}published") or "")[:4]
    record = _record(authors, int(published) if published.isdigit() else None)
    return record if record.authors or record.year else None


def _record(authors: list[str], year: int | None) -> Record:
    names = [" ".join(name.split())[:MAX_NAME] for name in authors]
    return Record([name for name in names if name][:MAX_AUTHORS], year if year is not None and 1000 <= year <= 2100 else None)


def fetch(kind: str, value: str) -> Record | None:
    """식별자(identifiers의 한 항목)로 서지를 묻는다. 그런 논문이 없으면 None.
    네트워크·서버 오류는 OSError, 알아볼 수 없는 응답은 ValueError·ElementTree.ParseError다(나중에 다시 묻는다)."""
    if kind == "doi":
        try:
            body = _get("https://api.crossref.org/works/" + urllib.parse.quote(value, safe="/"))
        except urllib.error.HTTPError as error:
            if error.code == 404:
                return None
            raise
        return crossref_record(json.loads(body))
    return arxiv_record(_get("https://export.arxiv.org/api/query?" + urllib.parse.urlencode({"id_list": value})).decode("utf-8"))


def _get(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": f"Paperloom/{__version__}"})
    with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
        return response.read(MAX_BYTES)
