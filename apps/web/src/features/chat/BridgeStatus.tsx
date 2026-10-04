import { useEffect, useRef, useState } from "react";

import { type BridgeHealth, bridgeHealth, claudeCodeUrl, START_COMMAND } from "./api";

export type Bridge = Readonly<{
  url: string | null;
  /** "checking": 확인 중, null: 꺼져 있음 */
  health: BridgeHealth | null | "checking";
  /** 브리지 주소. 아직 모르면 Paperloom health에서 받는다 */
  resolveUrl: () => Promise<string>;
  check: () => void;
  markOffline: () => void;
}>;

/** 이 PC의 Claude Code 브리지 주소와 상태 (ADR 0003). 처음 한 번 확인하고, check()로 다시 확인한다. */
export function useBridge(): Bridge {
  const [url, setUrl] = useState<string | null>(null);
  const [health, setHealth] = useState<BridgeHealth | null | "checking">("checking");
  const urlRef = useRef<string | null>(null);

  async function resolveUrl(): Promise<string> {
    urlRef.current ??= await claudeCodeUrl();
    setUrl(urlRef.current);
    return urlRef.current;
  }

  async function check() {
    setHealth("checking");
    setHealth(await bridgeHealth(await resolveUrl()));
  }

  useEffect(() => {
    void check();
  }, []);

  return { url, health, resolveUrl, check: () => void check(), markOffline: () => setHealth(null) };
}

/** 머리에 쓰는 짧은 상태: 준비됨·확인 중·꺼짐 */
export function bridgeState(bridge: Bridge): "ready" | "checking" | "offline" {
  if (bridge.health === "checking") return "checking";
  return bridge.health?.ready ? "ready" : "offline";
}

export function BridgeStatus({ bridge }: { bridge: Bridge }) {
  const { health } = bridge;
  if (health === "checking") return <p className="bridge-status muted">Claude Code 브리지 확인 중…</p>;
  if (health?.ready) {
    return (
      <p className="bridge-status status ok" data-bridge="ready">
        Claude Code 연결됨 · {health.claude.subscription ?? "구독"} 로그인
      </p>
    );
  }
  return (
    <div className="bridge-status status error" data-bridge={health ? "not-ready" : "offline"}>
      <p>{health?.error?.message ?? "Claude Code 브리지가 꺼져 있습니다. PowerShell에서 아래 명령으로 켜 주세요."}</p>
      {!health && <pre className="config-snippet">{START_COMMAND}</pre>}
      <button type="button" className="btn btn-secondary" onClick={bridge.check}>
        다시 확인
      </button>
    </div>
  );
}
