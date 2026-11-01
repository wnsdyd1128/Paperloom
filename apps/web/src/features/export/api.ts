/** Wiki로 내보내기 REST 클라이언트 (backend/src/paperloom/evidence_bundles/routes.py, docs/integration/paperloom). */

import { ApiError, jsonRequest, parseJson, postJson } from "../../shared/http";

export type OutboxStatus = "ready" | "not_configured" | "unwritable";
/** path는 컨테이너 안 경로이거나 사용자 폴더를 ~로 쓴 경로다. 사용자 이름이 드러나지 않는다 */
export type WikiOutbox = Readonly<{ status: OutboxStatus; path: string | null }>;

export type TextMode = "none" | "anchor_pages" | "all" | "ranges";
/** 쪽 범위. 0부터, 양 끝 포함 (화면은 1부터다) */
export type PageRange = Readonly<{ from: number; to: number }>;

export type BundleRequest = Readonly<{
  papers: readonly Readonly<{
    version_id: string;
    anchor_ids: readonly string[];
    include_comments: boolean;
    include_region_images: boolean;
    text: Readonly<{ mode: TextMode; ranges?: readonly PageRange[] }>;
  }>[];
  answer_ids: readonly string[];
  proposals: readonly Readonly<{ version_id: string; title: string; content_markdown: string; anchor_ids: readonly string[] }>[];
}>;

export type BundleWarning = Readonly<{ code: string; detail: string }>;

export type BundlePreview = Readonly<{
  file_count: number;
  total_bytes: number;
  files: readonly Readonly<{ path: string; kind: string; size_bytes: number }>[];
  auto_added_anchors: readonly Readonly<{ version_id: string; anchor_id: string; reason: "cited_by_answer" | "linked_by_proposal" }>[];
  warnings: readonly BundleWarning[];
  limits: Readonly<{ max_files: number; max_file_bytes: number; max_total_bytes: number }>;
  schema_version: string;
}>;

export type BundlePaper = Readonly<{ paper_id: string; version_id: string; title: string }>;

export type Bundle = Readonly<{
  bundle_id: string;
  directory: string;
  status: "written" | "failed";
  schema_version: string | null;
  manifest_sha256: string | null;
  file_count: number;
  size_bytes: number;
  papers: readonly BundlePaper[];
  counts: Readonly<{ anchors: number; proposals: number; answers: number; assets: number; texts: number }>;
  created_at: string;
}>;

export type BundleDetail = Bundle &
  Readonly<{
    files: readonly Readonly<{ path: string; sha256: string; size_bytes: number }>[];
    error_code: string | null;
    present_in_outbox: boolean;
  }>;

export type BundleListItem = Pick<Bundle, "bundle_id" | "status" | "created_at" | "file_count" | "size_bytes" | "papers"> &
  Readonly<{ present_in_outbox: boolean }>;

export async function getOutbox(): Promise<WikiOutbox> {
  // health는 데이터 폴더를 쓸 수 없으면 503이지만 본문은 같다
  return ((await (await fetch("/api/v1/health")).json()) as { wiki_outbox: WikiOutbox }).wiki_outbox;
}

/** 만들 bundle을 계산만 한다. 아무것도 쓰지 않는다 */
export async function previewBundle(request: BundleRequest): Promise<BundlePreview> {
  return parseJson<BundlePreview>(await fetch("/api/v1/evidence-bundles/preview", jsonRequest("POST", request)));
}

/** outbox에 bundle을 쓴다. 응답을 받지 못하면 같은 키로 한 번 더 보내므로 bundle은 하나만 생긴다 */
export async function createBundle(request: BundleRequest): Promise<Bundle> {
  return parseJson<Bundle>(await postJson("/api/v1/evidence-bundles", request));
}

export async function listBundles(): Promise<readonly BundleListItem[]> {
  return (await parseJson<{ bundles: BundleListItem[] }>(await fetch("/api/v1/evidence-bundles"))).bundles;
}

export async function getBundle(bundleId: string): Promise<BundleDetail> {
  return parseJson<BundleDetail>(await fetch(`/api/v1/evidence-bundles/${encodeURIComponent(bundleId)}`));
}

const ERRORS: Readonly<Record<string, string>> = {
  OUTBOX_UNAVAILABLE: "Wiki로 보낼 폴더를 쓸 수 없습니다. outbox 연결을 확인하세요.",
  BUNDLE_TOO_LARGE: "내보낼 내용이 한도(64개·32 MiB)를 넘습니다. 이미지나 추출문 범위를 줄이세요.",
  TEXT_NOT_READY: "아직 본문을 추출하지 않은 쪽이 있습니다. 추출이 끝난 뒤 다시 하거나 범위를 바꾸세요.",
  NOT_FOUND: "논문·위치·답변을 찾을 수 없습니다. 그 사이 지워졌을 수 있습니다. 창을 닫고 다시 여세요.",
  IDEMPOTENCY_IN_PROGRESS: "같은 내보내기를 처리하는 중입니다. 잠시 뒤 기록을 보세요.",
  BUNDLE_WRITE_FAILED: "bundle을 쓰다 실패했습니다. 남은 파일은 없습니다. 디스크 공간·권한을 확인하세요.",
};

const INVALID_REASONS: Readonly<Record<string, string>> = {
  duplicate_version: "같은 논문을 두 번 넣음",
  anchor_other_version: "다른 판본의 위치",
  proposal_version_not_selected: "제안의 논문이 목록에 없음",
  answer_version_not_selected: "답변의 논문이 목록에 없음",
  invalid_range: "쪽 범위가 논문 밖이거나 거꾸로임",
};

/** 오류 코드마다 사용자 문구와 다음 행동 (기능 명세 F-09) */
export function describeError(error: unknown): string {
  if (!(error instanceof ApiError)) return "내보내지 못했습니다. 백엔드 연결을 확인하세요.";
  if (error.body.code === "INVALID_BUNDLE") {
    const items = (error.body.details?.errors ?? []) as readonly { reason: string }[];
    const reasons = [...new Set(items.map((item) => INVALID_REASONS[item.reason] ?? item.reason))];
    return `내보낼 수 없는 선택입니다: ${reasons.join(", ")}. 표시된 칸을 고치세요.`;
  }
  return ERRORS[error.body.code] ?? error.message;
}
