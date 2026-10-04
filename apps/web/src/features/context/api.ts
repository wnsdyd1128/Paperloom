/** 문맥(ContextPacket) REST 클라이언트 (backend/src/paperloom/context/routes.py, IMPL §7.2–7.3). */

import { parseJson, postJson } from "../../shared/http";
import type { TextStatus } from "../library/api";

export type Intent = "explain" | "translate" | "summarize" | "ask";
/** 요청 종류별 기본 질문 (선택 메뉴의 설명·번역) */
export const DEFAULT_QUESTIONS: Readonly<Record<Intent, string>> = {
  explain: "고른 부분을 쉽게 설명해 주세요. 필요한 정의와 전제도 함께 알려 주세요.",
  translate: "고른 부분을 자연스러운 한국어로 번역해 주세요.",
  summarize: "고른 부분과 주변 문단의 핵심을 요약해 주세요.",
  ask: "",
};

export type EvidenceRole =
  | "selected_text"
  | "selected_region"
  | "containing_paragraph"
  | "previous_paragraph"
  | "following_paragraph"
  | "caption"
  | "region_text"
  | "paper_text";

/** 근거 역할 이름. 고른 영역(selected_region)은 영역 종류로 부르므로 없다 */
export const EVIDENCE_ROLE_LABELS: Readonly<Partial<Record<EvidenceRole, string>>> = {
  selected_text: "고른 글",
  containing_paragraph: "고른 글이 든 문단",
  previous_paragraph: "앞 문단",
  following_paragraph: "뒤 문단",
  caption: "캡션",
  region_text: "영역 안 글자",
  paper_text: "논문 본문",
};

export type Evidence = Readonly<{
  evidence_id: string;
  role: EvidenceRole;
  source_ref: string;
  version_id: string;
  page_index: number;
  anchor_id: string;
  kind: string | null;
  text: string;
  /** 첨자·분수 추정 표기. 추정이다 */
  display_text: string | null;
  truncated: boolean;
  regions: readonly (readonly number[])[];
  block_id: string | null;
  image: Readonly<{ url: string; scale: number }> | null;
  /** 그 쪽의 본문 추출 상태. null이면 추출 전 */
  text_status: TextStatus | null;
  quality_flags: readonly string[];
}>;

export type Excluded = Readonly<{ role: string; anchor_id: string; page_index: number | null; reason: string }>;

export type PacketStatus = "PREPARED" | "USER_CONFIRMED" | "HANDED_OFF" | "IMPORTED" | "CANCELLED";

export type ContextPacket = Readonly<{
  schema_version: "context-packet.v1";
  packet_id: string;
  intent: Intent;
  question: string;
  evidence: readonly Evidence[];
  sources: readonly Readonly<{ source_ref: string; paper_id: string; title: string; version_id: string; sha256: string }>[];
  limits: Readonly<{
    max_text_chars: number;
    used_text_chars: number;
    max_images: number;
    used_images: number;
    truncated: boolean;
    excluded: readonly Excluded[];
  }>;
  /** 범위와 그 쪽. U3 전에 만든 packet은 null */
  scope: Scope | null;
  scope_page: number | null;
  created_at: string;
  content_sha256: string;
  status: PacketStatus;
  handed_off_at: string | null;
  /** mcp: 공유한 packet을 AI 호스트가 읽었다 (W07, 2026-10-05에 뺐다 — 예전 packet) */
  handoff_method: "clipboard" | "file" | "mcp" | null;
}>;

/**
 * 대화 범위 (docs/UI_PLAN.md U3): 고른 위치만, 고른 위치 + 그 쪽 본문, 고른 위치 + 논문 본문,
 * 고른 위치 + 앞쪽부터 page_index쪽까지와 참고문헌 쪽(until_page, 원문 위 설명·질문은 고른 쪽 다음 쪽까지),
 * 고른 위치 + page_index쪽과 앞뒤 한 쪽, 참고문헌 쪽(around_page, 예전 원문 위 설명·질문)
 */
export type Scope = "selection" | "page" | "paper" | "until_page" | "around_page";

/**
 * 고른 위치(anchors)와 범위. 범위를 적지 않으면 고른 위치만이고, 고른 위치 없이 논문 버전만 주면 논문 본문이다.
 * page·paper·until_page·around_page 범위는 version_id가 필요하고, page·until_page·around_page는 page_index(0부터),
 * paper·until_page·around_page는
 * 본문 한도(paper_text_chars)를 고를 수 있다.
 */
export type PacketRequest = Readonly<{
  intent: Intent;
  question: string;
  anchors: readonly Readonly<{ anchor_id: string; include_context: boolean; include_image: boolean }>[];
  scope?: Scope;
  version_id?: string;
  page_index?: number;
  paper_text_chars?: number;
}>;

export async function createPacket(request: PacketRequest): Promise<ContextPacket> {
  return parseJson<ContextPacket>(await postJson("/api/v1/context-packets", request));
}

export async function getPacket(packetId: string): Promise<ContextPacket> {
  return parseJson<ContextPacket>(await fetch(packetUrl(packetId)));
}

function packetUrl(packetId: string): string {
  return `/api/v1/context-packets/${encodeURIComponent(packetId)}`;
}
