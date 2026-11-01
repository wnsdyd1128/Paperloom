import { useEffect, useState } from "react";

import { getOutbox, type WikiOutbox } from "./api";
import { outboxProblem } from "./draft";

export type Outbox = Readonly<{
  outbox: WikiOutbox | null;
  /** 내보내기를 막는 이유. 버튼의 툴팁으로 보인다. 막지 않으면 null */
  problem: string | null;
}>;

const CHECKING = "Wiki로 보낼 폴더를 확인하는 중입니다.";
const UNREACHABLE = "Wiki로 보낼 폴더를 확인하지 못했습니다. 백엔드 연결을 확인하세요.";

/** outbox 상태 (기능 명세 F-08). 처음 한 번 묻는다. 서버는 내보내기 직전에 다시 확인한다 */
export function useOutbox(): Outbox {
  const [state, setState] = useState<Outbox>({ outbox: null, problem: CHECKING });

  useEffect(() => {
    let cancelled = false;
    getOutbox()
      .then((outbox) => !cancelled && setState({ outbox, problem: outboxProblem(outbox) }))
      .catch(() => !cancelled && setState({ outbox: null, problem: UNREACHABLE }));
    return () => {
      cancelled = true;
    };
  }, []);
  return state;
}
