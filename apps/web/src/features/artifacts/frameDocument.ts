/**
 * 아티팩트를 그릴 격리 문서(iframe srcdoc). 창은 iframe을 sandbox="allow-scripts"(allow-same-origin 없음)로 열어
 * 문서가 출처 없는(opaque) 곳에서 돈다: Paperloom의 DOM·쿠키·저장소·API 응답을 읽지 못하고, 창을 띄우거나 바깥 창을
 * 옮기거나 양식을 보내지 못한다. 문서 맨 앞의 CSP는 바깥 주소에서 무엇이든 불러오는 것(스크립트·이미지·글꼴·fetch·
 * WebSocket)을 막는다. 문서 안의 스크립트와 스타일, data:·blob: 이미지만 된다.
 *
 * 막지 못하는 것: 문서가 스스로 다른 주소로 이동하는 것(링크·location). 창은 이동을 알아채면 그 화면을 치우지만 이동 요청은
 * 이미 나간다(ArtifactWindow).
 */

export const FRAME_CSP = [
  "default-src 'none'",
  "script-src 'unsafe-inline'",
  "style-src 'unsafe-inline'",
  "img-src data: blob:",
  "font-src data:",
  "media-src data: blob:",
  "form-action 'none'",
  "base-uri 'none'",
].join("; ");

const CSP_META = `<meta http-equiv="Content-Security-Policy" content="${FRAME_CSP}">`;
const HEAD = `<!doctype html>${CSP_META}<meta charset="utf-8">`;

/**
 * HTML 아티팩트. CSP를 문서의 어떤 글보다 앞에 둔다(그 앞의 스크립트는 CSP 없이 돌기 때문이다). 아티팩트의 doctype은
 * 떼고 앞에 다시 쓴다(meta 뒤의 doctype은 무시되어 quirks 모드가 된다). 뒤에 오는 <html>·<head>는 HTML 파서가 합친다.
 */
export function htmlDocument(html: string): string {
  return HEAD + html.replace(/^\s*<!doctype[^>]*>/i, "");
}

/** SVG 그림·Mermaid 다이어그램: 흰 바탕 가운데에 창 크기에 맞춰 */
export function svgDocument(svg: string): string {
  return (
    HEAD +
    "<style>html,body{margin:0;height:100%;background:#fff}body{display:flex;align-items:center;justify-content:center;padding:16px;box-sizing:border-box}" +
    "body>svg{max-width:100%;max-height:100%;height:auto}</style>" +
    svg
  );
}

/**
 * React 아티팩트. runtime은 React·ReactDOM을 전역에 두는 스크립트(reactRuntime.ts의 빌드), compiled는 sucrase가 바꾼
 * CommonJS 코드다(import → require, export default → exports.default). react 밖의 라이브러리는 지원하지 않는다.
 * 오류는 화면에 글로 보인다.
 */
export function reactDocument(runtime: string, compiled: string): string {
  const program = `(function () {
  var show = function (error) {
    var box = document.getElementById("artifact-error");
    box.textContent = "아티팩트를 그리지 못했습니다: " + (error && error.message ? error.message : String(error));
    box.hidden = false;
  };
  window.addEventListener("error", function (event) { show(event.error || event.message); });
  try {
    var modules = { react: window.React, "react-dom": window.ReactDOM, "react-dom/client": window.ReactDOM };
    var require = function (name) {
      if (!(name in modules)) throw new Error("지원하지 않는 라이브러리입니다: " + name + " (react만 쓸 수 있습니다)");
      return modules[name];
    };
    var module = { exports: {} };
    var exports = module.exports;
    (function (require, module, exports, React) {
${compiled}
    })(require, module, exports, window.React);
    var App = module.exports.default || module.exports;
    if (typeof App !== "function") throw new Error("export default로 React 컴포넌트를 내보내야 합니다.");
    window.ReactDOM.createRoot(document.getElementById("root")).render(window.React.createElement(App));
  } catch (error) {
    show(error);
  }
})();`;
  return (
    HEAD +
    "<style>body{margin:0;font-family:system-ui,sans-serif}#artifact-error{margin:16px;color:#b42318;white-space:pre-wrap}</style>" +
    '<div id="root"></div><p id="artifact-error" hidden></p>' +
    `<script>${escapeScript(runtime)}</script><script>${escapeScript(program)}</script>`
  );
}

/** 스크립트 글 안의 </script>가 스크립트를 끝내지 않게 한다 */
function escapeScript(code: string): string {
  return code.replace(/<\/(script)/gi, "<\\/$1");
}
