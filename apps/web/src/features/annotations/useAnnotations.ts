import { useCallback, useEffect, useRef, useState } from "react";

import { ApiError } from "../../shared/http";
import {
  type Annotation,
  createAnchor,
  createAnnotation,
  deleteAnnotation,
  listAnnotations,
  type HighlightColor,
  type NewAnchor,
  type RegionKind,
  updateAnchorKind,
  updateAnnotation,
} from "./api";

export type AnnotationsState =
  | Readonly<{ kind: "loading" }>
  | Readonly<{ kind: "ready"; items: readonly Annotation[] }>
  | Readonly<{ kind: "failed" }>;

/**
 * 한 SourceVersion의 주석 목록과 변경. 수정·삭제가 revision 충돌(409)이나 이미 지워짐(404)으로
 * 거부되면 서버의 최신 목록을 다시 불러온 뒤 오류를 그대로 던진다(화면이 이유를 알린다).
 */
export function useAnnotations(versionId: string) {
  const [state, setState] = useState<AnnotationsState>({ kind: "loading" });
  const request = useRef(0); // 늦게 도착한 이전 응답이 최신 목록을 덮지 않게 한다

  const reload = useCallback(async () => {
    const id = ++request.current;
    try {
      const items = await listAnnotations(versionId);
      if (id === request.current) setState({ kind: "ready", items });
    } catch {
      if (id === request.current) setState({ kind: "failed" });
    }
  }, [versionId]);

  useEffect(() => {
    setState({ kind: "loading" });
    void reload();
  }, [reload]);

  const replaceItems = (change: (items: readonly Annotation[]) => Annotation[]) =>
    setState((current) => (current.kind === "ready" ? { kind: "ready", items: sortByPosition(change(current.items)) } : current));

  async function refreshOnStale<T>(action: () => Promise<T>): Promise<T> {
    try {
      return await action();
    } catch (error) {
      if (error instanceof ApiError && (error.status === 409 || error.status === 404)) await reload();
      throw error;
    }
  }

  /** 이미 저장한 위치(Anchor)에 주석을 단다 (번역 창의 "주석으로 저장"). color가 있으면 하이라이트다. */
  async function attach(anchorId: string, comment: string, color: HighlightColor | null = null): Promise<Annotation> {
    const saved = await createAnnotation(anchorId, comment, color);
    replaceItems((items) => [...items, saved]);
    return saved;
  }

  return {
    state,
    attach,
    async create(anchor: NewAnchor, comment: string, color: HighlightColor | null = null): Promise<Annotation> {
      return attach((await createAnchor(anchor)).anchor_id, comment, color);
    },
    async update(annotation: Annotation, comment: string): Promise<void> {
      const saved = await refreshOnStale(() => updateAnnotation(annotation, { comment }));
      replaceItems((items) => items.map((item) => (item.annotation_id === saved.annotation_id ? saved : item)));
    },
    /** 하이라이트 색을 바꾼다 (U5). */
    async recolor(annotation: Annotation, color: HighlightColor): Promise<void> {
      const saved = await refreshOnStale(() => updateAnnotation(annotation, { color }));
      replaceItems((items) => items.map((item) => (item.annotation_id === saved.annotation_id ? saved : item)));
    },
    async changeKind(annotation: Annotation, kind: RegionKind): Promise<void> {
      const anchor = await updateAnchorKind(annotation.anchor.anchor_id, kind);
      replaceItems((items) =>
        items.map((item) => (item.anchor.anchor_id === anchor.anchor_id ? { ...item, anchor } : item)),
      );
    },
    async remove(annotation: Annotation): Promise<void> {
      await refreshOnStale(() => deleteAnnotation(annotation));
      replaceItems((items) => items.filter((item) => item.annotation_id !== annotation.annotation_id));
    },
  };
}

/** 서버 목록과 같은 순서: 쪽, 첫 줄의 위(v), 왼쪽(u). */
function sortByPosition(items: readonly Annotation[]): Annotation[] {
  const key = ({ anchor }: Annotation) => [anchor.page_index, anchor.quads[0][1], anchor.quads[0][0]];
  return [...items].sort((a, b) => {
    const [ka, kb] = [key(a), key(b)];
    return ka[0] - kb[0] || ka[1] - kb[1] || ka[2] - kb[2];
  });
}
