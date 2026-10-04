/** 쪽 번호들(1부터)을 이어지는 묶음으로: [3, 4, 5, 27, 28, 29] → "p.3–5, 27–29". 없으면 빈 글 */
export function pageRanges(pages: readonly number[]): string {
  const sorted = [...new Set(pages)].sort((a, b) => a - b);
  const runs: number[][] = [];
  for (const page of sorted) {
    const last = runs.at(-1);
    if (last && page === last[last.length - 1] + 1) last.push(page);
    else runs.push([page]);
  }
  return runs.length === 0 ? "" : `p.${runs.map((run) => (run.length > 1 ? `${run[0]}–${run[run.length - 1]}` : `${run[0]}`)).join(", ")}`;
}
