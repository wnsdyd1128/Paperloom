import { Icon } from "../../shared/Icon";

/**
 * 대화를 새 탭으로 분리한 동안 Reader 사이드바의 대화 칸 자리 (2026-11-09 사용자 요청). 대화는 그 탭에서만 이어 가고,
 * 여기서 고른 위치·3줄 요약은 그 탭으로 간다. 되돌리면 그 탭을 닫고 사이드바에서 다시 대화한다.
 */
export function DetachedChat({ onShow, onReturn }: Readonly<{ onShow: () => void; onReturn: () => void }>) {
  return (
    <section className="side-section chat-detached" aria-labelledby="chat-detached-heading">
      <header className="side-head is-strong">
        <h2 id="chat-detached-heading" className="side-title">
          Claude와 대화
        </h2>
      </header>
      <div className="chat-detached-body">
        <p>대화를 별도 탭에서 하고 있습니다. 여기서 고른 위치와 3줄 요약은 그 탭으로 갑니다.</p>
        <button type="button" className="btn btn-secondary" onClick={onShow}>
          <Icon name="popOut" size={14} />
          대화 탭 보기
        </button>
        <button type="button" className="btn btn-ghost" onClick={onReturn}>
          사이드바로 되돌리기
        </button>
      </div>
    </section>
  );
}
