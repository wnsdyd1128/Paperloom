import { describe, expect, it } from "vitest";

import { navigationKeyAction } from "./navigationKeys";

const key = (code: string, key: string, modifiers: Partial<Record<"ctrlKey" | "metaKey" | "altKey" | "shiftKey", boolean>> = {}) => ({
  code,
  key,
  ctrlKey: false,
  metaKey: false,
  altKey: false,
  shiftKey: false,
  ...modifiers,
});

describe("navigationKeyAction", () => {
  it("Ctrl(Cmd)+Shift+O는 목차, Ctrl(Cmd)+F는 찾기다. 한글 입력 상태에서도 물리 키로 본다", () => {
    expect(navigationKeyAction(key("KeyO", "O", { ctrlKey: true, shiftKey: true }))).toBe("toc");
    expect(navigationKeyAction(key("KeyO", "ㅐ", { metaKey: true, shiftKey: true }))).toBe("toc");
    expect(navigationKeyAction(key("KeyF", "f", { ctrlKey: true }))).toBe("find");
    expect(navigationKeyAction(key("KeyF", "ㄹ", { metaKey: true }))).toBe("find");
  });

  it("다른 조합은 받지 않는다", () => {
    expect(navigationKeyAction(key("KeyO", "o", { ctrlKey: true }))).toBeNull();
    expect(navigationKeyAction(key("KeyF", "F", { ctrlKey: true, shiftKey: true }))).toBeNull();
    expect(navigationKeyAction(key("KeyF", "f", { ctrlKey: true, altKey: true }))).toBeNull();
    expect(navigationKeyAction(key("KeyF", "f"))).toBeNull();
    expect(navigationKeyAction(key("KeyO", "O", { shiftKey: true }))).toBeNull();
  });
});
