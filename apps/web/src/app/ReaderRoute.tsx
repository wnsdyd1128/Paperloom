import { lazy, Suspense, useEffect, useState } from "react";

import { getPaper, getVersion, markOpened, type Paper, type Version } from "../features/library/api";
import { ApiError } from "../shared/http";
import { formatRoute, type Route } from "./route";

// PDF.js는 Reader를 열 때만 불러온다.
const ReaderPage = lazy(() => import("../features/reader/ReaderPage").then((module) => ({ default: module.ReaderPage })));

type ReaderRouteValue = Extract<Route, { kind: "reader" }>;
type Navigate = (route: Route, options?: { replace?: boolean }) => void;
type Loaded =
  | Readonly<{ kind: "loading" }>
  | Readonly<{ kind: "ready"; paper: Paper; version: Version }>
  | Readonly<{ kind: "failed"; message: string }>;

/**
 * Reader 주소를 논문·버전으로 푼다 (IMPL §4.3, §6.3). 주소의 버전을 그대로 열고, 최신 버전으로 조용히
 * 바꾸지 않는다. 버전이 없는 주소는 지금의 최신 버전으로 고정해 두어 새로고침해도 같은 버전을 연다.
 */
export function ReaderRoute({ route, navigate }: { route: ReaderRouteValue; navigate: Navigate }) {
  const { paperId, versionId } = route;
  const [loaded, setLoaded] = useState<Loaded>({ kind: "loading" });

  useEffect(() => {
    let cancelled = false;
    setLoaded({ kind: "loading" });
    (async () => {
      const paper = await getPaper(paperId);
      if (!versionId) {
        navigate({ ...route, versionId: paper.current_version.version_id }, { replace: true });
        return;
      }
      const version =
        versionId === paper.current_version.version_id
          ? { ...paper.current_version, paper_id: paper.paper_id }
          : await getVersion(versionId);
      if (version.paper_id !== paper.paper_id) throw new LinkError("링크의 버전이 이 논문에 속하지 않습니다.");
      if (!cancelled) setLoaded({ kind: "ready", paper, version });
      // 서재의 "마지막 열람"과 차례. 기록하지 못해도 읽기는 된다.
      if (!cancelled) markOpened(paper.paper_id).catch(() => undefined);
    })().catch((error: unknown) => {
      if (!cancelled) setLoaded({ kind: "failed", message: describeFailure(error) });
    });
    return () => {
      cancelled = true;
    };
    // route 전체가 아니라 논문·버전이 바뀔 때만 다시 불러온다 (anchor만 바뀌면 Reader가 처리한다).
  }, [paperId, versionId]);

  const toLibrary = () => navigate({ kind: "library" });
  if (loaded.kind === "loading") return <p className="status pending">논문을 불러오는 중…</p>;
  if (loaded.kind === "failed") {
    return (
      <main className="shell">
        <p className="status error" role="status">
          {loaded.message}
        </p>
        <button type="button" onClick={toLibrary}>
          ← Library
        </button>
      </main>
    );
  }
  const { paper, version } = loaded;
  // 위치(anchor)로 옮기면 검색에서 연 쪽·문단은 지운다.
  const readerRoute = (anchorId: string | null): Route => ({
    ...route,
    versionId: version.version_id,
    anchorId,
    page: null,
    blockId: null,
  });
  return (
    <Suspense fallback={<p className="status pending">Reader를 불러오는 중…</p>}>
      <ReaderPage
        key={version.version_id}
        paper={paper}
        version={version}
        anchorId={route.anchorId}
        openSession={route.session}
        textFocus={route.page !== null ? { pageIndex: route.page - 1, blockId: route.blockId } : null}
        anchorHref={(anchorId) => formatRoute(readerRoute(anchorId))}
        pageHref={(page) => formatRoute({ ...route, versionId: version.version_id, anchorId: null, page, blockId: null })}
        onNavigate={(anchorId, options) => navigate(readerRoute(anchorId), options)}
        onFocusText={(pageIndex, blockId) =>
          navigate({ ...route, versionId: version.version_id, anchorId: null, page: pageIndex + 1, blockId })
        }
        onPaperChange={(next) => setLoaded({ kind: "ready", paper: next, version })}
        onClose={toLibrary}
      />
    </Suspense>
  );
}

class LinkError extends Error {}

function describeFailure(error: unknown): string {
  if (error instanceof LinkError) return error.message;
  if (error instanceof ApiError && error.status === 404) return "링크의 논문이나 버전을 찾을 수 없습니다.";
  return "논문을 불러오지 못했습니다. 백엔드 연결을 확인하세요.";
}
