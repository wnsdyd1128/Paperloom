import { useState } from "react";

import { Icon } from "../../shared/Icon";
import { REGION_KIND_LABELS, type RegionKind } from "../annotations/api";
import type { ContextPacket, Evidence, EvidenceRole } from "../context/api";
import { pageRanges } from "./pageRanges";

/** 보낸 근거 줄에 쓰는 짧은 이름 (시안: "선택한 글 · 든 문단 · 앞 문단") */
const SHORT_LABELS: Readonly<Record<EvidenceRole, string>> = {
  selected_text: "선택한 글",
  selected_region: "고른 영역",
  containing_paragraph: "든 문단",
  previous_paragraph: "앞 문단",
  following_paragraph: "뒤 문단",
  caption: "캡션",
  region_text: "영역 안 글자",
  paper_text: "논문 본문",
};
const REASON_LABELS: Readonly<Record<string, string>> = {
  text_budget: "글자 한도",
  image_limit: "이미지 한도",
  text_not_extracted: "본문 추출 전",
  no_extracted_text: "추출된 글 없음",
};
const EXCERPT_CHARS = 400;

type Props = Readonly<{
  packet: ContextPacket;
  onShowAnchor: (anchorId: string) => void;
  onShowBlock: (pageIndex: number, blockId: string) => void;
}>;

/**
 * 묻을 때 Claude에게 보낸 근거 (시안 "보낸 근거" 줄). 접어 두면 근거 종류와 쪽만, 펼치면 근거마다 번호·글·이미지와
 * "원문에서 보기"가 보인다. 번호는 답의 [근거 n]과 같다.
 */
export function EvidenceSummary({ packet, onShowAnchor, onShowBlock }: Props) {
  const [open, setOpen] = useState(false);
  const roles = [...new Set(packet.evidence.map((item) => roleLabel(item)))];
  // 보낸 쪽들을 그대로(처음–끝만 적으면 "p.1–29"가 전문을 보낸 것처럼 보였다, 2026-10-02 사용자 확인)
  const pages = pageRanges(packet.evidence.map((item) => item.page_index + 1));
  const range = pages ? ` (${pages})` : "";
  return (
    <div className="evidence-summary" data-packet-id={packet.packet_id}>
      <button type="button" className="evidence-toggle" aria-expanded={open} onClick={() => setOpen((value) => !value)}>
        <span className="evidence-kicker">보낸 근거</span>
        <span className="evidence-roles">
          {roles.join(" · ")}
          {range}
        </span>
        <Icon name={open ? "chevronUp" : "chevronDown"} size={14} />
      </button>
      {open && (
        <div className="evidence-detail">
          <ol className="evidence-list">
            {packet.evidence.map((item, index) => (
              <li key={item.evidence_id} data-role={item.role} data-evidence-id={item.evidence_id}>
                <strong>
                  근거 {index + 1} · {roleLabel(item)} · {item.page_index + 1}쪽
                </strong>
                <EvidenceNotes item={item} />
                {item.role === "selected_region" ? (
                  item.image ? (
                    <img className="evidence-image" src={item.image.url} alt={`${item.page_index + 1}쪽 영역 이미지`} loading="lazy" />
                  ) : (
                    <p className="muted">이미지를 넣지 않음</p>
                  )
                ) : (
                  <>
                    <p className="evidence-text">{excerpt(item.text)}</p>
                    {item.image && <img className="evidence-image" src={item.image.url} alt={`${item.page_index + 1}쪽 원문 이미지`} loading="lazy" />}
                  </>
                )}
                {item.role !== "paper_text" && (
                  <button
                    type="button"
                    className="btn btn-ghost evidence-show"
                    onClick={() => (item.block_id ? onShowBlock(item.page_index, item.block_id) : onShowAnchor(item.anchor_id))}
                  >
                    원문에서 보기
                  </button>
                )}
              </li>
            ))}
          </ol>
          <p className="packet-limits" data-truncated={packet.limits.truncated}>
            본문 {packet.limits.used_text_chars.toLocaleString()}/{packet.limits.max_text_chars.toLocaleString()}자 · 이미지 {packet.limits.used_images}/
            {packet.limits.max_images}개 · {packet.limits.truncated ? "잘림 있음" : "잘림 없음"}
          </p>
          {packet.limits.excluded.length > 0 && (
            <ul className="packet-excluded">
              {packet.limits.excluded.map((item, index) => (
                <li key={index}>
                  넣지 않음: {item.page_index !== null ? `${item.page_index + 1}쪽 ` : ""}
                  {item.role === "context" ? "주변 문단" : (SHORT_LABELS[item.role as EvidenceRole] ?? "영역 이미지")} — {REASON_LABELS[item.reason] ?? item.reason}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}

function roleLabel(item: Evidence): string {
  if (item.role === "selected_region") return `고른 ${REGION_KIND_LABELS[item.kind as RegionKind] ?? "영역"}`;
  return SHORT_LABELS[item.role];
}

function EvidenceNotes({ item }: { item: Evidence }) {
  const notes = [
    item.truncated && "앞부분만 넣음",
    item.display_text && `추정 표기: ${item.display_text}`,
    item.text_status === null && "본문 추출 전",
    item.quality_flags.includes("split_across_pages") && "쪽을 넘어 이어지는 문단",
  ].filter(Boolean);
  return notes.length > 0 ? <p className="muted evidence-notes">{notes.join(" · ")}</p> : null;
}

function excerpt(text: string): string {
  return text.length > EXCERPT_CHARS ? `${text.slice(0, EXCERPT_CHARS)}…` : text;
}
