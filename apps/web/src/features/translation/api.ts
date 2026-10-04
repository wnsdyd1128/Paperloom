/** 쪽 번역 REST (U7): Core에서 읽고(backend translation/routes.py), 번역은 이 PC의 Claude Code 브리지가 한다. */

import { ApiError, expectOk, parseJson } from "../../shared/http";
import type { Preferences } from "../settings/api";

export type Language = Preferences["answer_language"];

/** 원문 문장의 [start, end) 글자 위치(그 문단 text 안)와 번역. 빈 번역은 앞 문장과 합쳐 옮긴 것이다. */
export type TranslatedSentence = Readonly<{ start: number; end: number; text: string }>;
export type TranslatedBlock = Readonly<{ block_id: string; sentences: readonly TranslatedSentence[] }>;

export type PageTranslation = Readonly<{
  version_id: string;
  page_index: number;
  language: Language;
  model: string | null;
  created_at: string;
  blocks: readonly TranslatedBlock[];
}>;

const base = (versionId: string) => `/api/v1/versions/${encodeURIComponent(versionId)}`;

/** 저장된 쪽 번역. 번역하지 않았으면(또는 다시 추출로 글이 바뀌었으면) null. */
export async function getPageTranslation(versionId: string, pageIndex: number, language: Language): Promise<PageTranslation | null> {
  try {
    return await parseJson<PageTranslation>(await fetch(`${base(versionId)}/pages/${pageIndex}/translations/${language}`));
  } catch (error) {
    if (error instanceof ApiError && error.body.code === "NOT_TRANSLATED") return null;
    throw error;
  }
}

/** 이 논문 버전의 그 언어 번역을 모두 지운다(번역 모두 지우기, 2026-10-04 사용자 요청) */
export async function deleteTranslations(versionId: string, language: Language): Promise<void> {
  await expectOk(await fetch(`${base(versionId)}/translations/${language}`, { method: "DELETE" }));
}

/** 번역을 저장한 쪽 번호들 */
export async function getTranslatedPages(versionId: string, language: Language): Promise<number[]> {
  return (await parseJson<{ pages: number[] }>(await fetch(`${base(versionId)}/translations/${language}`))).pages;
}

/**
 * 브리지에 쪽 하나를 번역하게 한다. 저장된 쪽이면 실행하지 않고 그 번역을 준다(force면 다시 번역).
 * 실패하면 ApiError(code: BUSY·NO_TEXT·BAD_TRANSLATION·CLAUDE_FAILED·BRIDGE_OFFLINE 등).
 */
/**
 * 쪽 하나를 번역한다(브리지). split: 보는 쪽이면 문단 묶음으로 나눠 동시에 번역한다(2026-10-03 사용자 결정). 모든 쪽 번역의
 * 다른 쪽은 통째로 한 차례다.
 */
export async function translatePage(bridgeUrl: string, versionId: string, pageIndex: number, force = false, split = false): Promise<PageTranslation> {
  let response: Response;
  try {
    response = await fetch(`${bridgeUrl}/translate-page`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ version_id: versionId, page_index: pageIndex, force, split }),
    });
  } catch {
    throw new ApiError(0, { code: "BRIDGE_OFFLINE", message: "Claude Code 브리지에 연결할 수 없습니다. 브리지를 켜 주세요.", request_id: "", retryable: true });
  }
  return (await parseJson<{ translation: PageTranslation }>(response)).translation;
}
