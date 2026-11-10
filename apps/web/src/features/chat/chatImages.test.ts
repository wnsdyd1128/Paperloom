import { describe, expect, it } from "vitest";

import { fitSize, imageFiles, MAX_SIDE } from "./chatImages";

describe("fitSize", () => {
  it("keeps images that already fit", () => {
    expect(fitSize(1200, 800)).toEqual({ width: 1200, height: 800 });
  });

  it("shrinks the long side to the limit and keeps the ratio", () => {
    expect(fitSize(3136, 1000)).toEqual({ width: MAX_SIDE, height: 500 });
    expect(fitSize(1000, 4704)).toEqual({ width: 333, height: MAX_SIDE });
  });

  it("never makes a side zero", () => {
    expect(fitSize(10_000, 1)).toEqual({ width: MAX_SIDE, height: 1 });
  });
});

describe("imageFiles", () => {
  it("keeps only image files", () => {
    const files = [new File(["a"], "shot.png", { type: "image/png" }), new File(["b"], "paper.pdf", { type: "application/pdf" })];
    const list = Object.assign(files, { item: (index: number) => files[index] }) as unknown as FileList;
    expect(imageFiles(list).map((file) => file.name)).toEqual(["shot.png"]);
    expect(imageFiles(null)).toEqual([]);
  });
});
