/** Library·버전·쪽 REST 클라이언트 (backend/src/paperloom/documents/routes.py). */

import { expectOk, parseJson } from "../../shared/http";

/** IMPL §5.2. READY_TO_READ(본문 추출 전)부터 어느 상태든 원본은 읽을 수 있다. */
export type VersionStatus = "READY_TO_READ" | "PARSING" | "INDEXED" | "PARTIAL" | "FAILED";

export type SourceVersion = Readonly<{
  version_id: string;
  sha256: string;
  size_bytes: number;
  page_count: number;
  status: VersionStatus;
  /** FAILED의 이유: NO_TEXT_LAYER, RESOURCE_LIMIT, PARSER_ERROR, PASSWORD_REQUIRED, MALFORMED_PDF */
  status_reason: string | null;
  created_at: string;
}>;

export type Paper = Readonly<{
  paper_id: string;
  title: string;
  authors: readonly string[];
  year: number | null;
  doi: string | null;
  created_at: string;
  current_version: SourceVersion;
  /** 서재 표 (U6) */
  tags: readonly string[];
  last_opened_at: string | null;
  annotation_count: number;
  conversation_count: number;
}>;

/** 버전 고정 링크가 버전의 논문을 확인할 때 쓴다 (GET /api/v1/versions/{id}). */
export type Version = SourceVersion & Readonly<{ paper_id: string }>;

/** 쪽의 본문 추출 상태 (IMPL §5.3). 휴리스틱이며 확률이 아니다. */
export type TextStatus = "usable" | "partial" | "image_only" | "unknown";

export type PageText = Readonly<{
  page_index: number;
  page_label: string | null;
  text_status: TextStatus;
  /** no_text, mostly_image, unmapped_chars, two_columns, extract_failed */
  flags: readonly string[];
}>;

export type PageTexts = Readonly<{ version_id: string; status: VersionStatus; pages: readonly PageText[] }>;

export type TextBlock = Readonly<{
  block_id: string;
  reading_order: number;
  text: string;
  /** 줄마다 정본 좌표 상자 [u0, v0, u1, v1] */
  regions: readonly (readonly number[])[];
  /** 굵게·기울임 구간 [시작, 끝, "b"|"i"|"bi"] (text 안). 전에 추출한 문단은 비어 있다 */
  styles: readonly (readonly [number, number, string])[];
  /** 가운데 글꼴 크기(pt). 전에 추출한 문단은 null */
  font_size: number | null;
}>;

/** 추출이 끝나지 않은 버전이면 상태와 빈 pages가 온다. */
export async function listPageTexts(versionId: string): Promise<PageTexts> {
  return parseJson<PageTexts>(await fetch(`/api/v1/versions/${encodeURIComponent(versionId)}/pages`));
}

/** 쪽의 문단(읽는 순서). 추출 전이면 409 TEXT_NOT_READY. */
export async function getPageBlocks(versionId: string, pageIndex: number): Promise<readonly TextBlock[]> {
  const url = `/api/v1/versions/${encodeURIComponent(versionId)}/pages/${pageIndex}`;
  return (await parseJson<{ blocks: TextBlock[] }>(await fetch(url))).blocks;
}

/** 논문의 태그를 이 목록으로 바꾼다 (U6). 대소문자만 다른 이름은 같은 태그다. */
export async function setPaperTags(paperId: string, tags: readonly string[]): Promise<Paper> {
  const response = await fetch(`/api/v1/papers/${encodeURIComponent(paperId)}/tags`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ tags }),
  });
  return parseJson<Paper>(response);
}

/** 태그 이름을 바꾼다(그 태그가 붙은 모든 논문, 2026-10-04). 이미 있는 다른 태그 이름이면 그 태그로 합친다. */
export async function renameTag(name: string, next: string): Promise<void> {
  const response = await fetch(`/api/v1/tags/${encodeURIComponent(name)}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name: next }),
  });
  await expectOk(response);
}

/** 태그를 모든 논문에서 떼고 지운다(논문은 그대로, 2026-10-04). */
export async function deleteTag(name: string): Promise<void> {
  await expectOk(await fetch(`/api/v1/tags/${encodeURIComponent(name)}`, { method: "DELETE" }));
}

/** 논문과 그 논문의 모든 기록·원본 PDF를 지운다(되돌릴 수 없다, 2026-10-05). 본문 추출 중이면 409다. */
export async function deletePaper(paperId: string): Promise<void> {
  await expectOk(await fetch(`/api/v1/papers/${encodeURIComponent(paperId)}`, { method: "DELETE" }));
}

/** Reader로 열었다 (U6 서재의 마지막 열람). 실패해도 읽기에는 영향이 없다. */
export async function markOpened(paperId: string): Promise<void> {
  await fetch(`/api/v1/papers/${encodeURIComponent(paperId)}/opened`, { method: "POST" });
}

/** 논문 정보 창에서 고치는 값 (U4, 사용자 결정 D5). 네 값을 모두 보낸다. */
export type PaperMetadata = Readonly<{ title: string; authors: readonly string[]; year: number | null; doi: string | null }>;

export async function updatePaperMetadata(paperId: string, metadata: PaperMetadata): Promise<Paper> {
  const response = await fetch(`/api/v1/papers/${encodeURIComponent(paperId)}/metadata`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(metadata),
  });
  return parseJson<Paper>(response);
}

/** 본문 제목 (documents.headings). box는 제목 줄의 정본 좌표 [u0, v0, u1, v1]. */
export type Heading = Readonly<{ title: string; page_index: number; level: number; block_id: string; box: readonly number[] }>;

/** 본문 제목으로 만든 목차 (U4, 사용자 결정 D6). 추출 전이면 409 TEXT_NOT_READY. */
export async function getHeadings(versionId: string): Promise<readonly Heading[]> {
  const url = `/api/v1/versions/${encodeURIComponent(versionId)}/headings`;
  return (await parseJson<{ headings: Heading[] }>(await fetch(url))).headings;
}

/** 본문을 다시 추출한다. 이미 대기·진행 중이면 409 PARSE_IN_PROGRESS. */
export async function requestParse(versionId: string): Promise<void> {
  await parseJson(await fetch(`/api/v1/versions/${encodeURIComponent(versionId)}/parse-runs`, { method: "POST" }));
}

export async function listPapers(): Promise<Paper[]> {
  const body = await parseJson<{ papers: Paper[] }>(await fetch("/api/v1/papers"));
  return body.papers;
}

export async function getPaper(paperId: string): Promise<Paper> {
  return parseJson<Paper>(await fetch(`/api/v1/papers/${encodeURIComponent(paperId)}`));
}

export async function getVersion(versionId: string): Promise<Version> {
  return parseJson<Version>(await fetch(`/api/v1/versions/${encodeURIComponent(versionId)}`));
}

export async function uploadPaper(file: File): Promise<Paper> {
  const response = await fetch("/api/v1/papers", {
    method: "POST",
    // 파일명은 제목 후보로만 쓰이며, 비ASCII 이름을 위해 percent-encoding한다.
    headers: { "Content-Type": "application/pdf", "X-Paperloom-Filename": encodeURIComponent(file.name) },
    body: file,
  });
  return parseJson<Paper>(response);
}

export function sourcePdfUrl(versionId: string): string {
  return `/api/v1/versions/${encodeURIComponent(versionId)}/pdf`;
}
