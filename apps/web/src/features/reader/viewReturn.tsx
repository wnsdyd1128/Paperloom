/**
 * 보던 자리로 돌아가기 (2026-10-02 사용자 요청): 참고문헌 번호를 따라간 뒤(referenceLinks) "N쪽으로 돌아가기" 단추나
 * Alt+←로 따라가기 전에 보던 자리로 돌아온다. 여러 번 따라갔으면 마지막에 보던 자리부터 차례로 돌아온다.
 *
 * 자리는 스크롤 영역 가운데 점이 놓인 쪽과 그 쪽 안의 비율로 기억한다. 확대·창 크기가 바뀌어도 같은 곳이 가운데로
 * 온다. 가운데가 쪽 사이 틈이면 가장 가까운 쪽이다(비율이 0–1 밖). 이 화면에서만 기억한다(주소·방문 기록에 남기지 않는다).
 */
import { type RefObject, useState } from "react";

import { Icon } from "../../shared/Icon";

export type ViewSpot = Readonly<{ pageIndex: number; x: number; y: number }>;

/** 스크롤 영역 가운데 점의 쪽과 쪽 안 비율. 쪽이 없으면 null */
export function captureView(container: HTMLElement): ViewSpot | null {
  const view = container.getBoundingClientRect();
  const x = view.left + container.clientWidth / 2;
  const y = view.top + container.clientHeight / 2;
  let nearest: { page: HTMLElement; rect: DOMRect; gap: number } | null = null;
  for (const page of container.querySelectorAll<HTMLElement>(".pdfViewer .page")) {
    const rect = page.getBoundingClientRect();
    const gap = Math.max(rect.top - y, 0, y - rect.bottom);
    if (!nearest || gap < nearest.gap) nearest = { page, rect, gap };
  }
  if (!nearest) return null;
  const { page, rect } = nearest;
  return { pageIndex: Number(page.dataset.pageNumber) - 1, x: (x - rect.left) / rect.width, y: (y - rect.top) / rect.height };
}

/** 기억한 점이 스크롤 영역 가운데에 오도록 스크롤한다(끝이면 스크롤할 수 있는 만큼). */
export function restoreView(container: HTMLElement, spot: ViewSpot): void {
  const page = container.querySelector<HTMLElement>(`.pdfViewer .page[data-page-number="${spot.pageIndex + 1}"]`);
  if (!page) return;
  const view = container.getBoundingClientRect();
  const rect = page.getBoundingClientRect();
  container.scrollLeft += rect.left + spot.x * rect.width - (view.left + container.clientWidth / 2);
  container.scrollTop += rect.top + spot.y * rect.height - (view.top + container.clientHeight / 2);
}

/** 돌아갈 자리들. back은 마지막 자리로 스크롤하고 그 자리를 빼며, 돌아갈 곳이 없었으면 false다. */
export function useViewReturns(containerRef: RefObject<HTMLDivElement | null>) {
  const [spots, setSpots] = useState<readonly ViewSpot[]>([]);
  return {
    spots,
    remember() {
      const spot = containerRef.current && captureView(containerRef.current);
      if (spot) setSpots((list) => [...list, spot]);
    },
    back(): boolean {
      const spot = spots.at(-1);
      if (!spot || !containerRef.current) return false;
      setSpots(spots.slice(0, -1));
      restoreView(containerRef.current, spot);
      return true;
    },
    clear: () => setSpots([]),
  };
}

/** 본문 아래 가운데의 돌아가기 단추와 닫기(움직이지 않고 기억한 자리를 버린다). 돌아갈 곳이 없으면 없다. */
export function ReturnBar({ spots, onBack, onClose }: Readonly<{ spots: readonly ViewSpot[]; onBack: () => void; onClose: () => void }>) {
  const last = spots.at(-1);
  if (!last) return null;
  return (
    <div className="reader-return" role="group" aria-label="보던 자리로 돌아가기">
      <button type="button" className="btn btn-plain" title="참고문헌으로 가기 전에 보던 자리로 (Alt+←)" onClick={onBack}>
        <Icon name="arrowLeft" size={14} />
        {last.pageIndex + 1}쪽으로 돌아가기
      </button>
      <button type="button" className="btn btn-icon" aria-label="돌아가기 닫기" title="닫기" onClick={onClose}>
        <Icon name="x" size={14} />
      </button>
    </div>
  );
}
