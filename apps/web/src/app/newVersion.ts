/**
 * 새 빌드 알림 (2026-10-04 사용자 확인: 다시 빌드한 뒤에도 열려 있던 탭이 옛 웹앱을 계속 돌려 새 번역 표시 <sub>·<sup>이 글자 그대로
 * 보였다. 2026-10-03의 <b>·<i>도 같았다). 서버의 index.html은 매번 다시 확인하지만(no-cache) 이미 열린 탭은 새로고침해야 바뀐다.
 * 탭이 다시 보일 때와 5분마다 서버의 index.html 진입 스크립트(빌드마다 이름의 해시가 바뀐다)를 지금 탭의 것과 견준다.
 */
import { useEffect, useState } from "react";

const CHECK_MS = 5 * 60_000;

/** index.html의 진입 스크립트 경로(/assets/index-<해시>.js). 개발 서버처럼 해시 이름이 없으면 null */
export function entryScript(html: string): string | null {
  return /<script\b[^>]*\bsrc="(\/assets\/index-[^"]+\.js)"/.exec(html)?.[1] ?? null;
}

/** 서버에 새 빌드가 올라왔는지(이 탭이 옛 웹앱인지) */
export function useNewVersion(): boolean {
  const [stale, setStale] = useState(false);
  useEffect(() => {
    const current = entryScript(document.documentElement.outerHTML);
    if (!current) return; // 개발 서버
    const check = () =>
      void fetch("/", { cache: "no-store" })
        .then((response) => response.text())
        .then((html) => {
          const latest = entryScript(html);
          if (latest && latest !== current) setStale(true);
        })
        .catch(() => undefined); // 서버가 잠시 꺼져 있으면 다음에 다시 본다
    const onVisible = () => document.visibilityState === "visible" && check();
    window.addEventListener("focus", check);
    document.addEventListener("visibilitychange", onVisible);
    const timer = window.setInterval(check, CHECK_MS);
    return () => {
      window.removeEventListener("focus", check);
      document.removeEventListener("visibilitychange", onVisible);
      window.clearInterval(timer);
    };
  }, []);
  return stale;
}
