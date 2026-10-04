import { useEffect, useState } from "react";

import { listPageTexts, type PageText, type PageTexts } from "../library/api";

const POLL_MS = 2000;

/** 버전의 쪽별 본문 추출 상태. 추출이 끝날 때까지 다시 받는다. */
export function usePageTexts(versionId: string): PageTexts | null {
  const [texts, setTexts] = useState<PageTexts | null>(null);

  useEffect(() => {
    let cancelled = false;
    let timer = 0;
    const load = () => {
      listPageTexts(versionId)
        .then((next) => {
          if (cancelled) return;
          setTexts(next);
          if (next.status === "READY_TO_READ" || next.status === "PARSING") timer = window.setTimeout(load, POLL_MS);
        })
        .catch(() => undefined); // 표시만 비운다. 원문 읽기에는 영향이 없다
    };
    load();
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [versionId]);

  return texts;
}

/**
 * 지금 쪽의 본문 추출 상태 (IMPL §5.3). 추출하지 못한 쪽의 텍스트를 정상처럼 쓰지 않도록 알린다.
 * 글자를 고를 수 없는 쪽의 그림·표는 영역 선택으로 고른다.
 */
export function PageTextStatus({ texts, pageIndex }: { texts: PageTexts | null; pageIndex: number }) {
  if (!texts) return null;
  const page = texts.pages.find((item) => item.page_index === pageIndex);
  const [label, detail] = describe(texts.status, page);
  return (
    <span className="muted page-text-status" data-text-status={page?.text_status ?? texts.status} title={detail}>
      {label}
    </span>
  );
}

function describe(status: PageTexts["status"], page: PageText | undefined): [string, string] {
  if (!page) {
    if (status === "READY_TO_READ" || status === "PARSING") return ["본문 추출 중", "끝나면 이 쪽을 검색할 수 있습니다."];
    return ["본문 추출 실패", "다시 추출하려면 Library에서 다시 추출을 누르세요."];
  }
  const flags = new Set(page.flags);
  switch (page.text_status) {
    case "usable":
      return ["본문 정상", "이 쪽의 글자를 검색할 수 있습니다."];
    case "partial":
      return flags.has("unmapped_chars")
        ? ["본문 일부", "글자 일부를 유니코드로 바꾸지 못했습니다. 인용을 원문과 비교하세요."]
        : ["본문 일부", "쪽 대부분이 이미지입니다. 이미지 속 글자는 검색되지 않습니다."];
    case "image_only":
      return ["본문 없음 · 이미지", "글자 층이 없는 쪽입니다(스캔 등). 그림·표는 영역 선택으로 고르세요."];
    case "unknown":
      return flags.has("extract_failed")
        ? ["본문 추출 실패", "이 쪽은 처리 한도 안에 추출하지 못했습니다."]
        : ["글자 없음", "빈 쪽이거나 그림만 있는 쪽입니다."];
  }
}
