/**
 * PDF.js 초기화. `pdf_viewer.mjs`는 로드되는 순간 `globalThis.pdfjsLib`를 읽으므로
 * core를 먼저 등록한 뒤 뷰어 모듈을 동적으로 불러온다. 이 모듈은 Reader 청크에서만 쓰인다.
 */
import * as pdfjsLib from "pdfjs-dist";
import workerUrl from "pdfjs-dist/build/pdf.worker.min.mjs?url";

pdfjsLib.GlobalWorkerOptions.workerSrc = workerUrl;
(globalThis as { pdfjsLib?: typeof pdfjsLib }).pdfjsLib = pdfjsLib;

export async function loadPdfJs() {
  const viewer = await import("pdfjs-dist/web/pdf_viewer.mjs");
  return { pdfjsLib, viewer };
}
