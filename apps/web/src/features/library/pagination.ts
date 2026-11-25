/**
 * 서재 표의 페이지 나누기 (2026-11-25 사용자 요청). 목록은 서버가 한 번에 주므로 화면에서 나눈다.
 * 페이지당 편 수는 이 브라우저에서만 기억하는 편의 설정이다(리더의 사이드바 너비와 같다).
 */
export const PAGE_SIZES = [5, 10, 20, 50, 100] as const;
export const DEFAULT_PAGE_SIZE = 20;

const PAGE_SIZE_KEY = "paperloom.library.pageSize";

/** 기억한 페이지당 편 수. 고를 수 있는 값이 아니면(없거나 손으로 바꾼 값) 기본값이다. */
export function storedPageSize(): number {
  try {
    const value = Number(localStorage.getItem(PAGE_SIZE_KEY));
    return (PAGE_SIZES as readonly number[]).includes(value) ? value : DEFAULT_PAGE_SIZE;
  } catch {
    return DEFAULT_PAGE_SIZE;
  }
}

export function rememberPageSize(size: number): void {
  try {
    localStorage.setItem(PAGE_SIZE_KEY, String(size));
  } catch {
    // 기억하지 못해도 이번 화면에서는 바뀐다
  }
}

/** 페이지 수. 논문이 없어도 한 페이지다. */
export function pageCount(total: number, size: number): number {
  return Math.max(1, Math.ceil(total / size));
}

/** 범위 안의 페이지 번호(1부터). 논문을 지우거나 걸러 페이지가 줄면 마지막 페이지가 된다. */
export function clampPage(page: number, total: number, size: number): number {
  return Math.min(Math.max(1, page), pageCount(total, size));
}

/** 그 페이지에 보일 것 */
export function pageSlice<T>(items: readonly T[], page: number, size: number): readonly T[] {
  const current = clampPage(page, items.length, size);
  return items.slice((current - 1) * size, current * size);
}

/** 페이지당 편 수를 바꾼 뒤의 페이지: 보고 있던 페이지의 첫 논문이 든 페이지 */
export function pageAfterResize(page: number, size: number, nextSize: number): number {
  return Math.floor(((page - 1) * size) / nextSize) + 1;
}

/**
 * 페이지 번호 단추에 놓을 것. 일곱 칸을 넘으면 처음·끝과 지금 페이지 둘레만 두고 사이는 null(줄임표)로 줄인다.
 * 칸 수가 늘 일곱이라 페이지를 넘겨도 단추 자리가 흔들리지 않는다.
 */
export function pageWindow(current: number, count: number): readonly (number | null)[] {
  if (count <= 7) return Array.from({ length: count }, (_, index) => index + 1);
  if (current <= 4) return [1, 2, 3, 4, 5, null, count];
  if (current >= count - 3) return [1, null, count - 4, count - 3, count - 2, count - 1, count];
  return [1, null, current - 1, current, current + 1, null, count];
}
