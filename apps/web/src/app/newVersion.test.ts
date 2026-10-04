import { describe, expect, it } from "vitest";

import { entryScript } from "./newVersion";

describe("새 빌드 알림: index.html의 진입 스크립트", () => {
  it("빌드한 index.html에서 해시가 든 진입 스크립트 경로를 읽는다", () => {
    const html = `<head>
    <script type="module" crossorigin src="/assets/index-4R-dF_8I.js"></script>
    <link rel="stylesheet" crossorigin href="/assets/index-C_3KRaE1.css">
  </head>`;
    expect(entryScript(html)).toBe("/assets/index-4R-dF_8I.js");
  });

  it("개발 서버(해시 이름 없음)나 스크립트가 없으면 null이다", () => {
    expect(entryScript('<script type="module" src="/src/main.tsx"></script>')).toBeNull();
    expect(entryScript("<p>서버 오류</p>")).toBeNull();
  });
});
