/**
 * 쪽 번역 차례 (U7, 사용자 결정 D3·D10·D11). 번역 보기를 켠 동안 지금 쪽을 바로 번역한다(머문 시간 없이). 사용자가
 * "모든 쪽 번역"을 시작하면 지금 쪽 다음에 앞쪽부터 남은 쪽을 한 쪽씩 번역한다. 한 번에 한 쪽이다(브리지 자물쇠).
 * 번역할 본문이 없는 쪽(글 없음, 참고문헌·그림·표뿐)·번역한 쪽·실패한 쪽은 저절로 번역하지 않는다. 참고문헌 쪽의 본문
 * (결론·감사의 글)은 번역한다: 참고문헌 부분 문단만 서버가 뺀다(2026-10-03 사용자 요청).
 */

/** hasText: 번역할 본문이 있는 쪽 */
export type PageInfo = Readonly<{ pageIndex: number; hasText: boolean }>;

type Input = Readonly<{
  current: number;
  pages: readonly PageInfo[];
  /** 번역을 저장한 쪽 */
  done: ReadonlySet<number>;
  /** 실패했거나 글이 없다고 판정한 쪽(다시 시도는 사용자가) */
  skip: ReadonlySet<number>;
  batch: boolean;
}>;

export function nextPageToTranslate({ current, pages, done, skip, batch }: Input): number | null {
  const wanted = (info: PageInfo | undefined) => !!info && info.hasText && !done.has(info.pageIndex) && !skip.has(info.pageIndex);
  if (wanted(pages.find((info) => info.pageIndex === current))) return current;
  if (!batch) return null;
  return pages.find(wanted)?.pageIndex ?? null;
}

/** 일괄 번역 진행: 번역할 본문이 있는 쪽 가운데 번역한 쪽 */
export function batchProgress(pages: readonly PageInfo[], done: ReadonlySet<number>): Readonly<{ done: number; total: number }> {
  const eligible = pages.filter((info) => info.hasText);
  return { done: eligible.filter((info) => done.has(info.pageIndex)).length, total: eligible.length };
}
