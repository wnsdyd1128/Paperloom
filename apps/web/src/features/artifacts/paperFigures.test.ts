import { afterEach, describe, expect, it, vi } from "vitest";

import { figureReferences, loadFigureImages, missingFigure, withFigureImages } from "./paperFigures";

const PNG = new Uint8Array([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]);

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("figureReferences", () => {
  it("이미지 주소로 쓴 그림 번호를 나온 차례로 한 번씩 찾는다 (HTML·SVG·Markdown·React)", () => {
    const content = [
      '<img src="paperloom-figure:3" alt="Figure 3">',
      '<image href="paperloom-figure:S1"/>',
      "![Figure 3](paperloom-figure:3)",
      "const src = 'paperloom-figure:10';",
      "paperloom-figure:3a paperloom-figure: paperloom-figure:x",
    ].join("\n");
    expect(figureReferences(content)).toEqual(["paperloom-figure:3", "paperloom-figure:S1", "paperloom-figure:10"]);
  });
});

describe("withFigureImages", () => {
  it("받은 그림의 참조만 바꾸고, 번호가 이어지는 다른 참조(3과 30)는 건드리지 않는다", () => {
    const images = new Map([["paperloom-figure:3", "data:image/png;base64,AAA"]]);
    expect(withFigureImages('<img src="paperloom-figure:3"><img src="paperloom-figure:30">', images)).toBe(
      '<img src="data:image/png;base64,AAA"><img src="paperloom-figure:30">',
    );
    expect(withFigureImages("paperloom-figure:3", new Map())).toBe("paperloom-figure:3");
  });
});

describe("loadFigureImages", () => {
  it("판본의 그림 PNG를 data: URL로 받고, 없거나 받지 못한 그림은 자리 그림이다", async () => {
    const fetched: string[] = [];
    vi.stubGlobal("fetch", async (url: string) => {
      fetched.push(url);
      if (url.includes("/figures/1/")) return new Response(new Blob([PNG], { type: "image/png" }));
      if (url.includes("/figures/2/")) return new Response(JSON.stringify({ code: "NOT_FOUND" }), { status: 404 });
      throw new TypeError("Failed to fetch");
    });

    const images = await loadFigureImages("v 1", "paperloom-figure:1 paperloom-figure:2 paperloom-figure:S3 paperloom-figure:1");

    expect(fetched).toEqual([
      "/api/v1/versions/v%201/figures/1/image?scale=2",
      "/api/v1/versions/v%201/figures/2/image?scale=2",
      "/api/v1/versions/v%201/figures/S3/image?scale=2",
    ]);
    expect(images.get("paperloom-figure:1")).toBe(`data:image/png;base64,${btoa(String.fromCharCode(...PNG))}`);
    expect(images.get("paperloom-figure:2")).toBe(missingFigure("2"));
    expect(images.get("paperloom-figure:S3")).toBe(missingFigure("S3"));
  });

  it("판본을 모르면 묻지 않고 자리 그림이고, 참조가 없으면 아무것도 받지 않는다", async () => {
    const fetch = vi.fn();
    vi.stubGlobal("fetch", fetch);
    expect(await loadFigureImages(null, "paperloom-figure:4")).toEqual(new Map([["paperloom-figure:4", missingFigure("4")]]));
    expect((await loadFigureImages("v1", "<p>그림 없음</p>")).size).toBe(0);
    expect(fetch).not.toHaveBeenCalled();
  });

  it("자리 그림은 그 번호를 적은 SVG data: URL이다", () => {
    const placeholder = missingFigure("7");
    expect(placeholder.startsWith("data:image/svg+xml;charset=utf-8,")).toBe(true);
    expect(decodeURIComponent(placeholder.slice(placeholder.indexOf(",") + 1))).toContain("Figure 7");
  });
});
