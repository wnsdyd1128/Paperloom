/**
 * 사용자 설정을 앱 전체에 준다 (U6). 처음에 한 번 받고, 바꾸면 바로 반영한 뒤 서버에 저장한다. 다른 탭에서 저장한 설정도 받는다.
 * 화면 설정(테마·글꼴 크기)은 문서 뿌리에 둔다: data-theme(system이면 운영체제), --reading-font-size.
 */
import { createContext, type ReactNode, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";

import { DEFAULT_PREFERENCES, getPreferences, type Preferences, putPreferences } from "./api";

type Value = Readonly<{
  preferences: Preferences;
  /**
   * 바꾼 항목만 받아 지금 설정에 합쳐 바로 반영하고 저장한다. 실패하면 서버의 설정으로 되돌리고 던진다.
   * 저장이 끝나기 전에 또 바꿔도(모델을 고르고 곧바로 언어를 고르면) 앞 바꾸기 위에 쌓인다.
   */
  save: (change: Partial<Preferences>) => Promise<void>;
}>;

const PreferencesContext = createContext<Value>({ preferences: DEFAULT_PREFERENCES, save: async () => undefined });

// 저장한 설정을 같은 브라우저의 다른 탭(대화 탭·번역 탭)에도 알린다. 대화가 별도 탭이 된 뒤(2026-11-09) 원문 탭에서
// 테마·기본 모델을 바꾸면 대화 탭도 바로 바뀌어야 한다. 이 탭이 보낸 소식은 받지 않는다.
const CHANNEL = "paperloom-preferences";
const TAB = `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`;
type Announcement = Readonly<{ from: string; preferences: Preferences }>;

function announce(preferences: Preferences): void {
  if (typeof BroadcastChannel === "undefined") return;
  const channel = new BroadcastChannel(CHANNEL);
  channel.postMessage({ from: TAB, preferences } satisfies Announcement);
  channel.close(); // 보낸 소식은 닫아도 간다
}

export function PreferencesProvider({ children }: Readonly<{ children: ReactNode }>) {
  const [preferences, setPreferences] = useState<Preferences>(DEFAULT_PREFERENCES);
  // 저장은 차례로 보내고, 마지막 저장의 응답만 반영한다(늦게 온 앞 응답이 화면을 되돌리지 않게).
  const saves = useRef({ latest: DEFAULT_PREFERENCES, chain: Promise.resolve(), turn: 0 });

  const apply = useCallback((next: Preferences) => {
    saves.current.latest = next;
    setPreferences(next);
  }, []);

  useEffect(() => {
    getPreferences()
      .then((loaded) => saves.current.turn === 0 && apply(loaded))
      .catch(() => undefined); // 받지 못하면 기본값으로 쓴다
  }, [apply]);

  useEffect(() => {
    if (typeof BroadcastChannel === "undefined") return;
    const channel = new BroadcastChannel(CHANNEL);
    channel.onmessage = (event: MessageEvent<Announcement>) => {
      if (event.data.from !== TAB) apply(event.data.preferences);
    };
    return () => channel.close();
  }, [apply]);

  useEffect(() => {
    const root = document.documentElement;
    if (preferences.theme === "system") delete root.dataset.theme;
    else root.dataset.theme = preferences.theme;
    root.style.setProperty("--reading-font-size", `${preferences.font_size}px`);
  }, [preferences.theme, preferences.font_size]);

  const save = useCallback(
    async (change: Partial<Preferences>) => {
      const current = saves.current;
      const next = { ...current.latest, ...change };
      const turn = ++current.turn;
      apply(next);
      const request = current.chain.then(() => putPreferences(next));
      current.chain = request.then(
        () => undefined,
        () => undefined,
      );
      try {
        const saved = await request;
        if (current.turn === turn) {
          apply(saved);
          announce(saved);
        }
      } catch (error) {
        if (current.turn === turn) getPreferences().then(apply, () => undefined);
        throw error;
      }
    },
    [apply],
  );
  const value = useMemo(() => ({ preferences, save }), [preferences, save]);
  return <PreferencesContext.Provider value={value}>{children}</PreferencesContext.Provider>;
}

export function usePreferences(): Value {
  return useContext(PreferencesContext);
}
