"""내보내기 요청을 저장된 값과 맞춰 본다 (03-api-spec §4).

없는 것은 NOT_FOUND로 바로 거부하고, 서로 맞지 않는 것은 이유를 모아 INVALID_BUNDLE로 거부한다(보낸 값은 돌려주지 않는다).
제안과 답변이 가리키는 Anchor는 그 판본의 고른 Anchor에 더한다. 제안 하나는 판본 하나만 가리키고, 판본을 섞지 않는다.
"""

from collections.abc import Callable
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path

from paperloom.answers.models import AnswerOut
from paperloom.answers.service import AnswerService
from paperloom.documents import repository as documents
from paperloom.documents.models import PaperOut, VersionOut
from paperloom.evidence_bundles.models import AutoAddedAnchor, BundleRequest, PaperChoice
from paperloom.infrastructure.database.sqlite import connect
from paperloom.reading.models import AnchorOut
from paperloom.reading.service import AnchorService


class BundleRefused(Exception):
    """code는 03-api-spec §9의 오류 코드다. 라우트가 상태 코드와 문구로 바꾼다."""

    def __init__(self, code: str, details: dict | None = None) -> None:
        super().__init__(code)
        self.code = code
        self.details = details


@dataclass
class SelectedPaper:
    choice: PaperChoice
    paper: PaperOut
    version: VersionOut
    anchors: dict[str, AnchorOut]  # 들어갈 Anchor. 제안·답변이 더한 것까지


@dataclass(frozen=True)
class Selection:
    papers: list[SelectedPaper]
    answers: list[AnswerOut]
    auto_added: list[AutoAddedAnchor]


def select(request: BundleRequest, db_path: Path, anchors: AnchorService, answers: AnswerService) -> Selection:
    errors: list[dict] = []
    auto_added: list[AutoAddedAnchor] = []
    papers = _papers(request, db_path, errors)

    def find(anchor_id: str, field: str) -> AnchorOut:
        anchor = anchors.get(anchor_id)
        if anchor is None:
            raise BundleRefused("NOT_FOUND", {"field": field})
        return anchor

    def add(paper: SelectedPaper, anchor: AnchorOut, reason: str) -> None:
        if anchor.anchor_id not in paper.anchors:
            paper.anchors[anchor.anchor_id] = anchor
            auto_added.append(AutoAddedAnchor(version_id=anchor.version_id, anchor_id=anchor.anchor_id, reason=reason))

    _chosen_anchors(request, papers, find, errors)
    _proposal_anchors(request, papers, find, add, errors)
    selected: dict[str, AnswerOut] = {}
    for index, answer_id in enumerate(request.answer_ids):
        answer = answers.get(answer_id)
        if answer is None or answer.discarded_at is not None or answer.origin != "claude_code":
            raise BundleRefused("NOT_FOUND", {"field": f"answer_ids[{index}]"})
        if not any(version_id in papers for version_id in answer.source_versions):
            errors.append({"loc": ["answer_ids", index], "reason": "answer_version_not_selected"})
            continue
        selected[answer_id] = answer
        for citation in answer.citations:
            paper = papers.get(citation.version_id)
            # 논문 본문 근거는 anchor_id가 비어 있다. 풀지 못한 근거로 남는다
            anchor = anchors.get(citation.anchor_id) if paper and citation.anchor_id else None
            if anchor is not None:
                add(paper, anchor, "cited_by_answer")
    if errors:
        raise BundleRefused("INVALID_BUNDLE", {"errors": errors})
    return Selection(list(papers.values()), list(selected.values()), auto_added)


def _papers(request: BundleRequest, db_path: Path, errors: list[dict]) -> dict[str, SelectedPaper]:
    papers: dict[str, SelectedPaper] = {}
    with closing(connect(db_path)) as connection:
        for index, choice in enumerate(request.papers):
            version = documents.get_version(connection, choice.version_id)
            if version is None:
                raise BundleRefused("NOT_FOUND", {"field": f"papers[{index}].version_id"})
            if choice.version_id in papers:
                errors.append({"loc": ["papers", index, "version_id"], "reason": "duplicate_version"})
                continue
            papers[choice.version_id] = SelectedPaper(choice, documents.get_paper(connection, version.paper_id), version, {})
            for position, pages in enumerate(choice.text.ranges):
                if not 0 <= pages.start <= pages.to < version.page_count:
                    errors.append({"loc": ["papers", index, "text", "ranges", position], "reason": "invalid_range"})
    return papers


def _chosen_anchors(request: BundleRequest, papers: dict[str, SelectedPaper], find: Callable, errors: list[dict]) -> None:
    for index, choice in enumerate(request.papers):
        for position, anchor_id in enumerate(choice.anchor_ids):
            anchor = find(anchor_id, f"papers[{index}].anchor_ids[{position}]")
            if anchor.version_id == choice.version_id:
                papers[choice.version_id].anchors[anchor_id] = anchor
            else:
                errors.append({"loc": ["papers", index, "anchor_ids", position], "reason": "anchor_other_version"})


def _proposal_anchors(request: BundleRequest, papers: dict[str, SelectedPaper], find: Callable, add: Callable, errors: list[dict]) -> None:
    for index, proposal in enumerate(request.proposals):
        paper = papers.get(proposal.version_id)
        if paper is None:
            errors.append({"loc": ["proposals", index, "version_id"], "reason": "proposal_version_not_selected"})
            continue
        for position, anchor_id in enumerate(proposal.anchor_ids):
            anchor = find(anchor_id, f"proposals[{index}].anchor_ids[{position}]")
            if anchor.version_id == proposal.version_id:
                add(paper, anchor, "linked_by_proposal")
            else:
                errors.append({"loc": ["proposals", index, "anchor_ids", position], "reason": "anchor_other_version"})
