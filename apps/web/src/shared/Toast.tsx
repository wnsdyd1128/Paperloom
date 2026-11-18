/**
 * 화면 우하단에 띄우는 안내 한 개(toast). 테마와 반대 색의 카드(밝은 테마는 어두운 카드)에 알림 종류 아이콘과 글, 필요하면
 * 바로가기 단추를 둔다. 본문을 밀지 않도록 위에 띄우고, 새 안내가 오면 그 자리에서 바꿔 다시 띄운다.
 *
 * 성공·오류 안내는 아래쪽 줄이 줄어들며 남은 시간을 보이고, 다 줄면 스스로 닫힌다. 오류는 읽고 바로가기를 누를 시간이
 * 필요해 더 오래 둔다. 마우스를 올리거나 단추에 초점이 있는 동안은 줄이 멈춰 닫히지 않는다. 진행 중 안내(pending)는
 * 스스로 닫히지 않고 결과 안내가 바꾼다.
 */
import "./toast.css";

import { Icon, type IconName } from "./Icon";

export type ToastNotice = Readonly<{
  tone: "ok" | "error" | "pending";
  text: string;
  /** 글 아래의 바로가기 (예: 이미 등록된 논문 열기) */
  action?: Readonly<{ label: string; run: () => void }>;
}>;

/** 스스로 닫히기까지의 시간(ms) */
const LIFETIME_MS = { ok: 4000, error: 8000 } as const;
const ICONS: Readonly<Record<ToastNotice["tone"], IconName>> = { ok: "check", error: "alert", pending: "loader" };

// 같은 글의 안내가 다시 와도 처음부터(등장·남은 시간) 다시 띄우도록 안내 객체마다 key를 준다
const keys = new WeakMap<ToastNotice, number>();
let lastKey = 0;
function keyOf(notice: ToastNotice): number {
  let key = keys.get(notice);
  if (key === undefined) {
    key = ++lastKey;
    keys.set(notice, key);
  }
  return key;
}

type Props = Readonly<{
  notice: ToastNotice | null;
  onClose: () => void;
}>;

export function Toast({ notice, onClose }: Props) {
  if (!notice) return null;
  const lifetime = notice.tone === "pending" ? null : LIFETIME_MS[notice.tone];
  return (
    <div key={keyOf(notice)} className="toast" data-tone={notice.tone}>
      <span className="toast-icon" aria-hidden="true">
        <Icon name={ICONS[notice.tone]} size={16} />
      </span>
      <div className="toast-body">
        <p className="toast-text" role="status">
          {notice.text}
        </p>
        {notice.action && (
          <button type="button" className="toast-action" onClick={notice.action.run}>
            {notice.action.label}
            <span aria-hidden="true"> →</span>
          </button>
        )}
      </div>
      {lifetime !== null && (
        <>
          <button type="button" className="toast-close" aria-label="알림 닫기" title="닫기" onClick={onClose}>
            <Icon name="x" size={14} />
          </button>
          {/* 남은 시간 줄. 이 줄의 애니메이션이 끝나면 닫으므로 멈추면(마우스·초점) 닫히지도 않는다 */}
          <span className="toast-time" style={{ animationDuration: `${lifetime}ms` }} onAnimationEnd={onClose} aria-hidden="true" />
        </>
      )}
    </div>
  );
}
