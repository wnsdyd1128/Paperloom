import { useEffect, useState } from "react";

import { getPageBlocks } from "../library/api";
import { boxToQuad, type Quad } from "./geometry";

/** 검색 결과에서 연 쪽·문단 (주소의 page·block, W05). */
export type TextFocus = Readonly<{ pageIndex: number; blockId: string | null }>;

/** 강조·스크롤할 곳. quads가 비면 문단을 찾지 못했으므로 쪽만 연다. */
export type FocusedText = Readonly<{ pageIndex: number; quads: readonly Quad[] }>;

/**
 * 주소의 문단을 그 쪽의 추출 결과에서 찾아 줄 상자(정본 좌표)를 quad로 돌려준다. block ID는 그 버전의 마지막
 * 추출의 것이다(다시 추출해도 같은 쪽에 글이 같은 문단은 그대로다). 글이 바뀌어 없어졌거나 추출 전이면 쪽만 돌려준다.
 */
export function useTextFocus(versionId: string, focus: TextFocus | null): FocusedText | null {
  const [focused, setFocused] = useState<FocusedText | null>(null);
  const pageIndex = focus?.pageIndex ?? null;
  const blockId = focus?.blockId ?? null;

  useEffect(() => {
    setFocused(null);
    if (pageIndex === null) return;
    let cancelled = false;
    const regions = blockId
      ? getPageBlocks(versionId, pageIndex)
          .then((blocks) => blocks.find((block) => block.block_id === blockId)?.regions ?? [])
          .catch(() => [])
      : Promise.resolve([]);
    void regions.then((boxes) => {
      if (cancelled) return;
      const quads = boxes.map(([u0, v0, u1, v1]) => boxToQuad({ u0, v0, u1, v1 }));
      setFocused({ pageIndex, quads });
    });
    return () => {
      cancelled = true;
    };
  }, [versionId, pageIndex, blockId]);

  return focused;
}
