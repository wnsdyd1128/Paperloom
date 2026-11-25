/**
 * 서재 표 아래의 페이지 이동과 페이지당 편 수 (2026-11-25 사용자 요청).
 * 한 페이지뿐이어도 편 수는 바꿀 수 있어야 하므로 표가 있으면 늘 보이고, 페이지 단추는 두 페이지부터 나온다.
 */
import { Icon } from "../../shared/Icon";
import { PAGE_SIZES, pageCount, pageWindow } from "./pagination";

type Props = Readonly<{
  /** 거르고 찾은 뒤의 논문 수 */
  total: number;
  /** 지금 페이지 (1부터, 범위 안) */
  page: number;
  size: number;
  onPage: (page: number) => void;
  onSize: (size: number) => void;
}>;

export function ShelfPager({ total, page, size, onPage, onSize }: Props) {
  const count = pageCount(total, size);
  const first = (page - 1) * size + 1;
  const last = Math.min(page * size, total);
  return (
    <div className="shelf-pager">
      <label className="pager-size">
        페이지당
        <select className="input" aria-label="페이지당 논문 수" value={size} onChange={(event) => onSize(Number(event.target.value))}>
          {PAGE_SIZES.map((option) => (
            <option key={option} value={option}>
              {option}편
            </option>
          ))}
        </select>
      </label>
      <span className="pager-range" data-testid="pager-range">
        {first}–{last} / {total}편
      </span>
      {count > 1 && (
        <nav className="pager-pages" aria-label="페이지 이동">
          <button type="button" className="btn btn-icon" aria-label="이전 페이지" disabled={page === 1} onClick={() => onPage(page - 1)}>
            <Icon name="chevronLeft" size={15} />
          </button>
          {pageWindow(page, count).map((item, index) =>
            item === null ? (
              <span key={`gap-${index}`} className="pager-gap" aria-hidden="true">
                …
              </span>
            ) : (
              <button key={item} type="button" className="pager-page" aria-label={`${item}페이지`} aria-current={item === page ? "page" : undefined} onClick={() => onPage(item)}>
                {item}
              </button>
            ),
          )}
          <button type="button" className="btn btn-icon" aria-label="다음 페이지" disabled={page === count} onClick={() => onPage(page + 1)}>
            <Icon name="chevronRight" size={15} />
          </button>
        </nav>
      )}
    </div>
  );
}
