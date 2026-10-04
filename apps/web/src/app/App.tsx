import { lazy, Suspense, useCallback, useEffect, useState } from "react";

import { LibraryShell } from "../features/library/LibraryShell";
import { PreferencesProvider } from "../features/settings/PreferencesProvider";
import { useNewVersion } from "./newVersion";
import { ReaderRoute } from "./ReaderRoute";
import { formatRoute, parseRoute, type Route, readerRoute } from "./route";

// 별도 탭의 쪽 번역(U7)은 PDF.js를 쓰므로 그 탭을 열 때만 불러온다.
const TranslationTab = lazy(() => import("../features/translation/TranslationTab").then((module) => ({ default: module.TranslationTab })));

export function App() {
  // 화면은 주소가 정한다. 새로고침·뒤로 가기·링크로 열어도 같은 화면이 된다 (IMPL §4.3).
  const [route, setRoute] = useState<Route>(() => parseRoute(location.pathname, location.search));
  const stale = useNewVersion();

  useEffect(() => {
    const onPopState = () => setRoute(parseRoute(location.pathname, location.search));
    window.addEventListener("popstate", onPopState);
    return () => window.removeEventListener("popstate", onPopState);
  }, []);

  const navigate = useCallback((next: Route, { replace = false }: { replace?: boolean } = {}) => {
    if (replace) history.replaceState(null, "", formatRoute(next));
    else history.pushState(null, "", formatRoute(next));
    setRoute(next);
  }, []);

  return (
    <PreferencesProvider>
      {stale && (
        <p className="new-version" role="status">
          Paperloom이 새로 빌드되었습니다. 새로고침해야 새 화면이 적용됩니다.
          <button type="button" onClick={() => location.reload()}>
            새로고침
          </button>
        </p>
      )}
      {route.kind === "reader" ? (
        <ReaderRoute route={route} navigate={navigate} />
      ) : route.kind === "translation" ? (
        <Suspense fallback={<p className="status pending">번역 탭을 불러오는 중…</p>}>
          <TranslationTab route={route} navigate={navigate} />
        </Suspense>
      ) : (
        <LibraryShell
          view={route.kind}
          onView={(view) => view !== route.kind && navigate({ kind: view })}
          onOpenPaper={(paper) => navigate(readerRoute(paper.paper_id, paper.current_version.version_id))}
          // 원문 위 대화는 그 위치(anchor)를 열고 그 자리 창을, 사이드바 대화는 사이드바 대화를 연다.
          onOpenConversation={(conversation) =>
            navigate({
              ...readerRoute(conversation.paper_id, conversation.version_id),
              anchorId: conversation.placement === "inline" ? conversation.anchor_id : null,
              session: conversation.session_id,
            })
          }
          onOpenCitation={(citation) =>
            navigate({
              ...readerRoute(citation.paper_id, citation.version_id),
              ...(citation.block_id ? { page: citation.page_index + 1, blockId: citation.block_id } : { anchorId: citation.anchor_id }),
            })
          }
        />
      )}
    </PreferencesProvider>
  );
}
