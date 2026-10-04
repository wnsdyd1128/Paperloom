import { describe, expect, it } from "vitest";

import { readMetadataForm } from "./paperMetadata";

const form = (changes: Partial<Record<"title" | "authors" | "year" | "doi", string>> = {}) => ({
  title: "Cache Paper",
  authors: "",
  year: "",
  doi: "",
  ...changes,
});

describe("readMetadataForm", () => {
  it("앞뒤 빈칸을 지우고, 저자는 줄마다 하나(빈 줄은 뺌), 빈 연도·DOI는 없음이다", () => {
    expect(readMetadataForm(form({ title: "  Cache Paper ", authors: " Jun Xiao \n\n Andy D. Pimentel\n", year: " 2022 ", doi: " 10.1145/3487581 " }))).toEqual({
      ok: true,
      value: { title: "Cache Paper", authors: ["Jun Xiao", "Andy D. Pimentel"], year: 2022, doi: "10.1145/3487581" },
    });
    expect(readMetadataForm(form())).toEqual({ ok: true, value: { title: "Cache Paper", authors: [], year: null, doi: null } });
  });

  it("DOI 주소·doi: 접두를 붙여 넣어도 DOI만 남긴다", () => {
    for (const doi of ["https://doi.org/10.1145/3487581", "http://dx.doi.org/10.1145/3487581", "doi:10.1145/3487581", "DOI: 10.1145/3487581"]) {
      expect(readMetadataForm(form({ doi }))).toMatchObject({ ok: true, value: { doi: "10.1145/3487581" } });
    }
  });

  it("맞지 않는 값은 칸마다 까닭을 준다", () => {
    expect(readMetadataForm(form({ title: "  ", year: "22", doi: "abc" }))).toEqual({
      ok: false,
      errors: { title: "제목을 쓰세요.", year: "연도는 1000–2100의 네 자리 숫자입니다.", doi: "DOI는 10.으로 시작합니다(예: 10.1145/3487581)." },
    });
    expect(readMetadataForm(form({ year: "2101" }))).toMatchObject({ ok: false, errors: { year: expect.any(String) } });
    expect(readMetadataForm(form({ authors: "x".repeat(301) }))).toMatchObject({ ok: false, errors: { authors: expect.any(String) } });
  });
});
