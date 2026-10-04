import { describe, expect, it } from "vitest";

import { isCopyShortcut, pageRegionImageUrl } from "./clipboard";

const key = (code: string, key: string, modifiers: Partial<Record<"ctrlKey" | "metaKey" | "altKey" | "shiftKey", boolean>> = {}) => ({
  code,
  key,
  ctrlKey: false,
  metaKey: false,
  altKey: false,
  shiftKey: false,
  ...modifiers,
});

describe("isCopyShortcut", () => {
  it("Ctrl+C, Cmd+C, 한글 입력 상태의 Ctrl+ㅊ", () => {
    expect(isCopyShortcut(key("KeyC", "c", { ctrlKey: true }))).toBe(true);
    expect(isCopyShortcut(key("KeyC", "c", { metaKey: true }))).toBe(true);
    expect(isCopyShortcut(key("KeyC", "ㅊ", { ctrlKey: true }))).toBe(true);
  });

  it("수정 키 없음, Shift·Alt 조합, 다른 키는 아니다", () => {
    expect(isCopyShortcut(key("KeyC", "c"))).toBe(false);
    expect(isCopyShortcut(key("KeyC", "C", { ctrlKey: true, shiftKey: true }))).toBe(false);
    expect(isCopyShortcut(key("KeyC", "c", { ctrlKey: true, altKey: true }))).toBe(false);
    expect(isCopyShortcut(key("KeyV", "v", { ctrlKey: true }))).toBe(false);
  });
});

it("pageRegionImageUrl은 정본 상자를 쉼표로 이어 보낸다", () => {
  const url = pageRegionImageUrl("v 1", 3, { u0: 0.1, v0: 0.2, u1: 0.3, v1: 0.4 });
  expect(url).toBe("/api/v1/versions/v%201/pages/3/image?box=0.1%2C0.2%2C0.3%2C0.4&scale=2");
});
