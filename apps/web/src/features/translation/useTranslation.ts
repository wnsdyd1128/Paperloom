/**
 * 쪽 번역 상태와 차례 (U7). 번역 보기를 켠 동안(active) 지금 쪽을 바로 번역하고(D3·D10), 사용자가 "모든 쪽 번역"을
 * 시작하면 남은 쪽을 한 쪽씩 번역한다(D11, 본문 없는 쪽 제외. 참고문헌 부분 문단은 서버가 뺀다). 번역은 이 PC의 브리지가 하고 Core에 저장된다.
 * 저장된 쪽은 다시 실행하지 않는다(브리지도 저장된 번역을 그대로 준다). 대화와 겹치면(BUSY) 잠시 뒤 다시 시도한다.
 */
import { useCallback, useEffect, useRef, useState } from "react";

import { ApiError } from "../../shared/http";
import type { Bridge } from "../chat/BridgeStatus";
import { getPageBlocks, type TextBlock } from "../library/api";
import { deleteTranslations, getPageTranslation, getTranslatedPages, type Language, type PageTranslation, translatePage } from "./api";
import { batchProgress, nextPageToTranslate, type PageInfo } from "./schedule";

export type PageEntry =
  | Readonly<{ status: "loading" }>
  | Readonly<{ status: "missing" }>
  | Readonly<{ status: "translating" }>
  | Readonly<{ status: "ready"; translation: PageTranslation; blocks: readonly TextBlock[] }>
  | Readonly<{ status: "failed"; code: string; message: string }>;

const BUSY_RETRY_MS = 3_000;

type Options = Readonly<{
  versionId: string;
  language: Language;
  bridge: Bridge;
  pages: readonly PageInfo[];
  /** 지금 쪽(0부터) */
  current: number;
  /** 번역을 실행하는지(번역 보기를 켰는지). 꺼져 있어도 저장된 번역은 읽는다 */
  active: boolean;
}>;

export function useTranslation({ versionId, language, bridge, pages, current, active }: Options) {
  const [entries, setEntries] = useState<ReadonlyMap<number, PageEntry>>(new Map());
  const [done, setDone] = useState<ReadonlySet<number>>(new Set());
  const [skip, setSkip] = useState<ReadonlySet<number>>(new Set());
  const [running, setRunning] = useState<number | null>(null);
  const [batch, setBatch] = useState(false);
  const [waiting, setWaiting] = useState(false); // 다른 쪽 번역(다른 탭 등)이 브리지를 쓰는 중(BUSY)이라 잠시 기다린다
  const [listed, setListed] = useState(false); // 저장된 쪽 목록을 받았는지
  const key = `${versionId}:${language}`;
  const keyRef = useRef(key);
  keyRef.current = key;

  const setEntry = useCallback((page: number, entry: PageEntry) => setEntries((map) => new Map(map).set(page, entry)), []);
  const mark = (set: typeof setDone, page: number, on: boolean) =>
    set((current) => {
      const next = new Set(current);
      if (on) next.add(page);
      else next.delete(page);
      return next;
    });

  // 논문·언어가 바뀌면 처음부터
  useEffect(() => {
    setEntries(new Map());
    setDone(new Set());
    setSkip(new Set());
    setRunning(null);
    setBatch(false);
    setListed(false);
  }, [versionId, language]);

  // 저장된 쪽 목록. 번역 보기를 다시 켜면 다시 받는다(별도 탭이 번역한 쪽). 목록에 없는 쪽은 번역을 묻지 않는다.
  useEffect(() => {
    let cancelled = false;
    getTranslatedPages(versionId, language)
      .then((list) => {
        if (cancelled) return;
        setDone(new Set(list));
        setEntries((map) => new Map([...map].filter(([page, entry]) => !(entry.status === "missing" && list.includes(page)))));
      })
      .catch(() => undefined)
      .finally(() => !cancelled && setListed(true));
    return () => {
      cancelled = true;
    };
  }, [versionId, language, active]);
  const doneRef = useRef(done);
  doneRef.current = done;

  /** 그 쪽의 저장된 번역과 문단을 읽는다. 저장된 쪽 목록에 없으면 묻지 않고 missing(saved면 목록과 상관없이 묻는다). */
  const load = useCallback(
    async (page: number, saved = false) => {
      const loadKey = keyRef.current;
      if (!saved && !doneRef.current.has(page)) {
        setEntry(page, { status: "missing" });
        return;
      }
      setEntry(page, { status: "loading" });
      try {
        const [translation, blocks] = await Promise.all([getPageTranslation(versionId, page, language), getPageBlocks(versionId, page)]);
        if (keyRef.current !== loadKey) return;
        setEntry(page, translation ? { status: "ready", translation, blocks } : { status: "missing" });
        mark(setDone, page, translation !== null);
      } catch {
        if (keyRef.current === loadKey) setEntry(page, { status: "missing" });
      }
    },
    [versionId, language, setEntry],
  );

  // 지금 쪽과 앞뒤 쪽의 저장된 번역을 읽어 둔다.
  useEffect(() => {
    if (!listed) return;
    for (const page of [current, current - 1, current + 1]) {
      if (page >= 0 && page < pages.length && !entries.has(page)) void load(page);
    }
  }, [listed, current, pages.length, entries, load]);

  const run = useCallback(
    async (page: number, force: boolean, split: boolean) => {
      const runKey = keyRef.current;
      setRunning(page);
      setEntry(page, { status: "translating" });
      try {
        const translation = await translatePage(await bridge.resolveUrl(), versionId, page, force, split);
        const blocks = await getPageBlocks(versionId, page);
        if (keyRef.current !== runKey) return;
        setEntry(page, { status: "ready", translation, blocks });
        mark(setDone, page, true);
        mark(setSkip, page, false);
      } catch (error) {
        if (keyRef.current !== runKey) return;
        const code = error instanceof ApiError ? error.body.code : "FAILED";
        const message = error instanceof ApiError ? error.body.message : "번역하지 못했습니다.";
        if (code === "BUSY") {
          setEntry(page, { status: "missing" });
          setWaiting(true);
          window.setTimeout(() => setWaiting(false), BUSY_RETRY_MS);
          return;
        }
        if (code === "BRIDGE_OFFLINE") {
          bridge.markOffline();
          setBatch(false);
        }
        setEntry(page, { status: "failed", code, message });
        mark(setSkip, page, true); // 저절로 다시 하지 않는다(다시 시도는 사용자가)
      } finally {
        if (keyRef.current === runKey) setRunning(null);
      }
    },
    [bridge, versionId, setEntry],
  );

  // 한 번에 한 쪽: 지금 쪽, 일괄 번역 중이면 그다음 남은 쪽
  useEffect(() => {
    if (!active || !listed || running !== null || waiting || pages.length === 0) return;
    const next = nextPageToTranslate({ current, pages, done, skip, batch });
    if (next !== null) void run(next, false, next === current); // 보는 쪽만 나눠 동시에
    else if (batch && !pages.some((info) => info.hasText && !done.has(info.pageIndex) && !skip.has(info.pageIndex))) setBatch(false);
  }, [active, listed, running, waiting, current, pages, done, skip, batch, run]);

  return {
    entries,
    running,
    waiting,
    batch,
    progress: batchProgress(pages, done),
    /** 다시 번역(저장된 번역을 바꾼다) */
    retranslate: (page: number) => running === null && void run(page, true, true),
    /** 저절로 번역하지 않는 쪽(참고문헌·실패한 쪽)을 지금 번역한다 */
    translateNow: (page: number) => running === null && void run(page, false, true),
    startBatch: () => setBatch(true),
    stopBatch: () => setBatch(false),
    load,
    /** 다른 탭이 그 쪽 번역을 저장했다: 저장된 쪽 목록과 상관없이 다시 읽는다 */
    reload: (page: number) => void load(page, true),
    /** 이 논문의 번역을 모두 지운다. 번역 보기를 켠 동안이면 보는 쪽은 바로 다시 번역한다(D10) */
    clearAll: async () => {
      await deleteTranslations(versionId, language);
      setEntries(new Map());
      setDone(new Set());
      setSkip(new Set());
      setBatch(false);
    },
  };
}

export type Translation = ReturnType<typeof useTranslation>;
