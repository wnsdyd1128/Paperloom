import { describe, expect, it } from "vitest";

import { formatRoute, parseRoute, type Route, readerRoute } from "./route";

describe("Reader 주소 (IMPL §4.3)", () => {
  it("버전 고정 링크를 읽고 다시 같은 주소로 쓴다", () => {
    const url = "/reader/paper-1?version=version-1&anchor=anchor-1";
    const route = parseRoute("/reader/paper-1", "?version=version-1&anchor=anchor-1");
    expect(route).toEqual({
      kind: "reader",
      paperId: "paper-1",
      versionId: "version-1",
      anchorId: "anchor-1",
      page: null,
      blockId: null,
      session: null,
    });
    expect(formatRoute(route)).toBe(url);
  });

  it("버전·위치가 없는 주소", () => {
    const route: Route = readerRoute("p", null);
    expect(parseRoute("/reader/p/", "")).toEqual(route);
    expect(parseRoute("/reader/p", "?version=&anchor=&block=")).toEqual(route);
    expect(formatRoute(route)).toBe("/reader/p");
  });

  it("검색 결과의 쪽·문단 (W05)", () => {
    const url = "/reader/p?version=v&page=3&block=b-1";
    const route = parseRoute("/reader/p", "?version=v&page=3&block=b-1");
    expect(route).toEqual({ ...readerRoute("p", "v"), page: 3, blockId: "b-1" });
    expect(formatRoute(route)).toBe(url);
  });

  it.each(["0", "-1", "1.5", "abc", ""])("잘못된 쪽 번호 %s는 버린다", (page) => {
    expect(parseRoute("/reader/p", `?page=${page}`)).toEqual(readerRoute("p", null));
  });

  it("식별자를 인코딩한다", () => {
    const route: Route = { ...readerRoute("a/b c", "v&1"), blockId: "x y" };
    const url = formatRoute(route);
    const [pathname, search] = url.split("?");
    expect(parseRoute(pathname, `?${search}`)).toEqual(route);
  });

  it("답변 화면에서 연 대화 (U6): session", () => {
    const url = "/reader/p?version=v&anchor=a&session=s-1";
    const route = parseRoute("/reader/p", "?version=v&anchor=a&session=s-1");
    expect(route).toEqual({ ...readerRoute("p", "v"), anchorId: "a", session: "s-1" });
    expect(formatRoute(route)).toBe(url);
  });

  it("답변 화면 (U6)", () => {
    expect(parseRoute("/answers", "")).toEqual({ kind: "answers" });
    expect(parseRoute("/answers/", "")).toEqual({ kind: "answers" });
    expect(formatRoute({ kind: "answers" })).toBe("/answers");
  });

  it("별도 탭의 쪽 번역 (U7)", () => {
    const route = parseRoute("/reader/p%2F1/translation", "?version=v1&page=3");
    expect(route).toEqual({ kind: "translation", paperId: "p/1", versionId: "v1", page: 3 });
    expect(formatRoute(route)).toBe("/reader/p%2F1/translation?version=v1&page=3");
    expect(parseRoute("/reader/p/translation", "")).toEqual({ kind: "translation", paperId: "p", versionId: null, page: 1 });
  });

  it("그 밖의 주소는 Library", () => {
    expect(parseRoute("/", "")).toEqual({ kind: "library" });
    expect(parseRoute("/reader", "")).toEqual({ kind: "library" });
    expect(parseRoute("/reader/p/extra", "")).toEqual({ kind: "library" });
    expect(formatRoute({ kind: "library" })).toBe("/");
  });
});
