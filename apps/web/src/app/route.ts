/**
 * 화면 주소 (IMPL §4.3). Reader 주소는 연 SourceVersion과 위치를 담아, 새로고침하거나 링크로 열어도
 * 같은 버전·같은 위치로 돌아온다.
 *
 *   /                                             Library (서재)
 *   /answers                                      답변 화면: 모든 논문의 대화 (U6, 사용자 결정 D8)
 *   /reader/{paper_id}/translation?version=&page= 별도 탭의 쪽 번역 (U7). 원문 탭과 쪽 이동을 맞춘다
 *   /reader/{paper_id}?version={version_id}&anchor={anchor_id}
 *   /reader/{paper_id}?version={version_id}&page={쪽 번호}&block={block_id}   검색 결과에서 연 문단 (W05)
 *
 * page는 화면의 쪽 번호(page_index + 1)다. block은 그 버전의 마지막 추출에서만 유효하므로, 다시 추출해
 * 사라졌으면 쪽만 연다. 영구 출처는 anchor다. session은 답변 화면에서 연 대화(U6)다. 그 대화를 사이드바나 원문 위에서 연다.
 */

export type Route =
  | Readonly<{ kind: "library" }>
  | Readonly<{ kind: "answers" }>
  | Readonly<{
      kind: "reader";
      paperId: string;
      versionId: string | null;
      anchorId: string | null;
      page: number | null;
      blockId: string | null;
      session: string | null;
    }>
  | Readonly<{ kind: "translation"; paperId: string; versionId: string | null; page: number }>;

export function parseRoute(pathname: string, search: string): Route {
  if (/^\/answers\/?$/.test(pathname)) return { kind: "answers" };
  const params = new URLSearchParams(search);
  const page = Number(params.get("page"));
  const translation = /^\/reader\/([^/]+)\/translation\/?$/.exec(pathname);
  if (translation) {
    return { kind: "translation", paperId: decodeURIComponent(translation[1]), versionId: params.get("version") || null, page: Number.isInteger(page) && page >= 1 ? page : 1 };
  }
  const match = /^\/reader\/([^/]+)\/?$/.exec(pathname);
  if (!match) return { kind: "library" };
  return {
    kind: "reader",
    paperId: decodeURIComponent(match[1]),
    versionId: params.get("version") || null,
    anchorId: params.get("anchor") || null,
    page: Number.isInteger(page) && page >= 1 ? page : null,
    blockId: params.get("block") || null,
    session: params.get("session") || null,
  };
}

export function formatRoute(route: Route): string {
  if (route.kind === "library") return "/";
  if (route.kind === "answers") return "/answers";
  const params = new URLSearchParams();
  if (route.kind === "translation") {
    if (route.versionId) params.set("version", route.versionId);
    params.set("page", String(route.page));
    return `/reader/${encodeURIComponent(route.paperId)}/translation?${params}`;
  }
  if (route.versionId) params.set("version", route.versionId);
  if (route.anchorId) params.set("anchor", route.anchorId);
  if (route.page !== null) params.set("page", String(route.page));
  if (route.blockId) params.set("block", route.blockId);
  if (route.session) params.set("session", route.session);
  const query = params.toString();
  return `/reader/${encodeURIComponent(route.paperId)}${query ? `?${query}` : ""}`;
}

export type ReaderLocation = Extract<Route, { kind: "reader" }>;

/** 논문을 처음부터 여는 주소 */
export function readerRoute(paperId: string, versionId: string | null): ReaderLocation {
  return { kind: "reader", paperId, versionId, anchorId: null, page: null, blockId: null, session: null };
}
