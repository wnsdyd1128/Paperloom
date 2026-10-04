/** 원문 위치·주석 REST 클라이언트 (backend/src/paperloom/reading/routes.py, annotations/routes.py). */

import { expectOk, jsonRequest, parseJson, postJson } from "../../shared/http";
import type { Quad } from "../reader/geometry";

/** 사용자가 끈 사각형 영역의 종류 (IMPL §10.6). */
export type RegionKind = "figure" | "table" | "equation" | "generic";
export const REGION_KINDS: readonly RegionKind[] = ["figure", "table", "equation", "generic"];
export const REGION_KIND_LABELS: Readonly<Record<RegionKind, string>> = {
  figure: "그림",
  table: "표",
  equation: "수식",
  generic: "영역",
};

/**
 * anchor.v1 (IMPL §6.2). kind가 text면 텍스트 선택(quote는 추출된 그대로, display_quote는 첨자 추정 표기,
 * IMPL §5.4)이고, 그 밖이면 사각형 영역(quad 하나, quote는 비어 있을 수 있음)이다.
 */
export type Anchor = Readonly<{
  schema_version: "anchor.v1";
  kind: "text" | RegionKind;
  anchor_id: string;
  version_id: string;
  page_index: number;
  quads: readonly Quad[];
  quote: string;
  display_quote: string | null;
  prefix: string;
  suffix: string;
  created_at: string;
}>;

export type NewAnchor = Omit<Anchor, "anchor_id" | "created_at">;

/** 하이라이트 색 (U5): c1 연한 주황 · c2 주황 · c3 회색. 없으면(null) 색 없는 주석이다. */
export type HighlightColor = "c1" | "c2" | "c3";

export type Annotation = Readonly<{
  annotation_id: string;
  anchor: Anchor;
  comment: string;
  color: HighlightColor | null;
  revision: number;
  created_at: string;
  updated_at: string;
}>;

export async function createAnchor(anchor: NewAnchor): Promise<Anchor> {
  return parseJson<Anchor>(await postJson("/api/v1/anchors", anchor));
}

export async function getAnchor(anchorId: string): Promise<Anchor> {
  return parseJson<Anchor>(await fetch(`/api/v1/anchors/${encodeURIComponent(anchorId)}`));
}

/** 영역의 종류만 바꾼다. 위치·인용은 바뀌지 않는다. */
export async function updateAnchorKind(anchorId: string, kind: RegionKind): Promise<Anchor> {
  return parseJson<Anchor>(await fetch(`/api/v1/anchors/${encodeURIComponent(anchorId)}`, jsonRequest("PATCH", { kind })));
}

/** Anchor가 가리키는 영역의 PNG (화면에 보이는 방향). scale은 PDF 1 pt당 픽셀 수다. */
export function anchorImageUrl(anchorId: string, scale = 2): string {
  return `/api/v1/anchors/${encodeURIComponent(anchorId)}/image?scale=${scale}`;
}

export async function listAnnotations(versionId: string): Promise<Annotation[]> {
  const url = `/api/v1/versions/${encodeURIComponent(versionId)}/annotations`;
  return (await parseJson<{ annotations: Annotation[] }>(await fetch(url))).annotations;
}

export async function createAnnotation(anchorId: string, comment: string, color: HighlightColor | null = null): Promise<Annotation> {
  return parseJson<Annotation>(await postJson("/api/v1/annotations", { anchor_id: anchorId, comment, color }));
}

/** 보낸 것만 바꾼다(메모·색). revision은 화면이 마지막으로 본 값이다. 그사이 바뀌었으면 409 REVISION_CONFLICT. */
export async function updateAnnotation(
  annotation: Annotation,
  changes: Readonly<{ comment?: string; color?: HighlightColor | null }>,
): Promise<Annotation> {
  const url = `/api/v1/annotations/${encodeURIComponent(annotation.annotation_id)}`;
  return parseJson<Annotation>(await fetch(url, jsonRequest("PATCH", { revision: annotation.revision, ...changes })));
}

export async function deleteAnnotation(annotation: Annotation): Promise<void> {
  const id = encodeURIComponent(annotation.annotation_id);
  await expectOk(await fetch(`/api/v1/annotations/${id}?revision=${annotation.revision}`, { method: "DELETE" }));
}
