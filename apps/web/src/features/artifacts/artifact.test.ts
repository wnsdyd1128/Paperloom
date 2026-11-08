import { describe, expect, it } from "vitest";

import { artifactFileName, fencedArtifact, parseArtifact } from "./artifact";
import { FRAME_CSP, htmlDocument, reactDocument, svgDocument } from "./frameDocument";

describe("parseArtifact", () => {
  it("울타리 줄의 type·title·language를 읽고 끝 줄바꿈을 뗀다 (시스템 프롬프트 형식)", () => {
    expect(parseArtifact('type="code" language="python" title="합 계산"', "print(1)\n")).toEqual({
      type: "code",
      title: "합 계산",
      language: "python",
      content: "print(1)",
    });
    expect(parseArtifact('type="html" title="그림" language="x"', "<p>")?.language).toBeNull(); // code만 언어가 있다
    expect(parseArtifact('type="svg"', "<svg/>")?.title).toBe("그림"); // 제목이 없으면 종류의 이름
  });

  it("type이 없거나 모르는 값이면 아티팩트가 아니다(보통 코드 블록으로 보인다)", () => {
    expect(parseArtifact(undefined, "x")).toBeNull();
    expect(parseArtifact('title="제목"', "x")).toBeNull();
    expect(parseArtifact('type="pdf" title="제목"', "x")).toBeNull();
  });
});

describe("fencedArtifact", () => {
  it("```html의 완전한 문서는 HTML 아티팩트이고 제목은 <title>이다 (2026-11-08 Sonnet이 형식 대신 준 답)", () => {
    const page = '<!DOCTYPE html>\n<html lang="ko">\n<head><title> Capuchin 발표 예상 질문 </title></head>\n<body></body>\n</html>\n';
    expect(fencedArtifact("html", page)).toEqual({ type: "html", title: "Capuchin 발표 예상 질문", language: null, content: page.slice(0, -1) });
    expect(fencedArtifact("HTML", "\n<html><body>x</body></html>")?.title).toBe("HTML 페이지"); // <title>이 없으면 종류의 이름
  });

  it("svg 요소와 mermaid 블록도 연다", () => {
    expect(fencedArtifact("svg", '<svg viewBox="0 0 1 1"></svg>')).toMatchObject({ type: "svg", title: "그림" });
    expect(fencedArtifact("mermaid", "flowchart LR\n  A --> B\n")).toMatchObject({ type: "mermaid", content: "flowchart LR\n  A --> B" });
  });

  it("조각 HTML·다른 언어·빈 블록은 보통 코드 블록으로 둔다", () => {
    expect(fencedArtifact("html", '<div class="card">예</div>')).toBeNull();
    expect(fencedArtifact("html", "<htmlx>")).toBeNull();
    expect(fencedArtifact("svg", "<path d='M0 0'/>")).toBeNull();
    expect(fencedArtifact("xml", "<svg></svg>")).toBeNull();
    expect(fencedArtifact("mermaid", "\n")).toBeNull();
    expect(fencedArtifact("python", "<!doctype html>")).toBeNull();
  });
});

describe("artifactFileName", () => {
  const artifact = (type: "html" | "code" | "react", title: string, language: string | null = null) => ({ type, title, language, content: "" });

  it("제목에 종류·언어에 맞는 확장자를 붙이고, 파일 이름에 못 쓰는 글자는 바꾼다", () => {
    expect(artifactFileName(artifact("html", "캐시 간섭: 시각화?"))).toBe("캐시 간섭_ 시각화_.html");
    expect(artifactFileName(artifact("code", "합 계산", "Python"))).toBe("합 계산.py");
    expect(artifactFileName(artifact("code", "설정", "toml"))).toBe("설정.txt"); // 모르는 언어
    expect(artifactFileName(artifact("react", "  "))).toBe("React 화면.jsx");
  });
});

describe("격리 문서", () => {
  const cspAt = (html: string) => html.indexOf(`content="${FRAME_CSP}"`);

  it("CSP는 아티팩트의 어떤 글보다 앞이고, 바깥 주소에서 불러오기·fetch를 막는다", () => {
    expect(FRAME_CSP).toContain("default-src 'none'"); // connect-src도 이것을 따른다
    expect(FRAME_CSP).not.toMatch(/https?:|\*/);
    const html = htmlDocument("<script>fetch('https://example.com')</script><!doctype html><html><head></head></html>");
    expect(cspAt(html)).toBeGreaterThan(0);
    expect(cspAt(html)).toBeLessThan(html.indexOf("<script>"));
  });

  it("아티팩트의 doctype은 떼고 맨 앞에 다시 쓴다(뒤에 오면 quirks 모드가 된다)", () => {
    const html = htmlDocument("  <!DOCTYPE html>\n<html><body>본문</body></html>");
    expect(html.startsWith("<!doctype html><meta http-equiv")).toBe(true);
    expect(html.match(/<!doctype/gi)).toHaveLength(1);
    expect(cspAt(svgDocument("<svg/>"))).toBeGreaterThan(0);
  });

  it("React 문서는 코드 안의 </script>가 스크립트를 끝내지 못하게 하고, react 밖 라이브러리는 글로 알린다", () => {
    const html = reactDocument("window.React = {};", 'const tag = "</script><img src=x>";');
    expect(html.match(/<\/script>/g)).toHaveLength(2); // 문서가 연 두 스크립트의 끝뿐이다
    expect(html).toContain('"<\\/script><img src=x>"');
    expect(html).toContain("react만 쓸 수 있습니다");
    expect(cspAt(html)).toBeLessThan(html.indexOf("<script>"));
  });
});
