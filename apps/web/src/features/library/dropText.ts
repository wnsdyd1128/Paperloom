/**
 * PDF 받침(FileDrop)의 두 줄 글. 원본 File Drop(designbookmark.com/motion)의 Uploading·Upload complete 자리를
 * 서재의 올리기 단계와 서버 한도에 맞춰 쓴다.
 */
import type { UploadStatus } from "./useLibrary";

/** 서버 한도(UploadLimits, IMPL §5.1). 서재 머리의 "PDF를 끌어다 놓기" 안내와 같은 값이다. */
const LIMITS = "100 MiB · 300쪽까지";

/** 서버 한도와 같은 단위(MiB)로 쓴다. */
export function formatSize(bytes: number): string {
  const mib = bytes / 1024 ** 2;
  return mib >= 1 ? `${mib.toFixed(1)} MiB` : `${Math.max(1, Math.round(bytes / 1024))} KiB`;
}

/** 긴 파일 이름은 앞 10자와 끝 8자(.pdf 포함)만 남긴다(원본 short). */
export function shortName(name: string): string {
  const chars = [...name];
  return chars.length > 20 ? `${chars.slice(0, 10).join("")}…${chars.slice(-8).join("")}` : name;
}

export type DropText = Readonly<{ title: string; detail: string }>;

/** 받침 두 줄의 글. 고르기(pickable)를 받는 받침만 "누르면 파일을 고릅니다"를 쓴다. */
export function dropText(status: UploadStatus, near: boolean, pickable: boolean): DropText {
  switch (status.kind) {
    case "idle":
      return {
        title: near ? "놓으면 서재에 등록합니다" : "PDF를 끌어다 놓으세요",
        detail: pickable && !near ? `누르면 파일을 고릅니다 · ${LIMITS}` : `PDF · ${LIMITS}`,
      };
    case "sending":
      return {
        title: `“${shortName(status.name)}” 확인 중`,
        detail: status.count > 1 ? `${status.index} / ${status.count}편 · ${formatSize(status.bytes)}` : formatSize(status.bytes),
      };
    case "done":
      return { title: status.count > 1 ? `${status.count}편을 등록했습니다` : "서재에 등록했습니다", detail: status.title };
    case "failed":
      return { title: "등록하지 못했습니다", detail: status.message };
  }
}
