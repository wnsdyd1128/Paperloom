"""논문 정보: DOI 찾기와 고치기 검사 (2026-10-02 사용자 결정 D5: DOI는 본문 추출 때 자동, 제목·저자·연도·DOI는 직접 고친다).

DOI는 앞 두 쪽 글에서 처음 나오는 것이다(출판사 표지 쪽과 논문 첫 쪽). 참고문헌의 DOI를 집지 않도록 뒤쪽은 보지 않는다.
외부(Crossref 등)에는 묻지 않는다.
"""

import re

DOI_PAGES = 2
# Crossref가 권하는 꼴(10.접두 4–9자리/접미). 접미 끝의 문장 부호는 뺀다.
_DOI = re.compile(r"\b10\.\d{4,9}/[-._;()/:A-Za-z0-9]+")
DOI_PATTERN = r"^10\.\d{4,9}/\S+$"


def find_doi(texts: list[str]) -> str | None:
    """글들에서 처음 나오는 DOI. 끝의 마침표·쉼표·쌍반점·쌍점과 짝이 없는 닫는 괄호는 뺀다."""
    for text in texts:
        if match := _DOI.search(text):
            doi = match.group(0)
            while doi and (doi[-1] in ".,;:" or (doi[-1] == ")" and doi.count(")") > doi.count("("))):
                doi = doi[:-1]
            return doi
    return None


def paper_doi(pages: list[dict]) -> str | None:
    """본문 추출 결과(쪽마다 page_index·blocks[].text)의 앞 두 쪽에서 DOI."""
    return find_doi([block["text"] for page in pages if page["page_index"] < DOI_PAGES for block in page["blocks"]])
