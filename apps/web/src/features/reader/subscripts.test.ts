import { describe, expect, it } from "vitest";

import { estimateScriptedQuote, type TextFragment } from "./subscripts";

// 정규화 좌표의 글자 상자. text layer span처럼 상자 높이는 글꼴 크기이고 윗변은 기준선 − 0.8 × 크기다.
const H = 0.02; // 본문 글꼴 크기
const BASELINE = 0.3;
let cursor = 0.1;

function glyph(text: string, { size = H, baseline = BASELINE } = {}): TextFragment {
  const u0 = cursor;
  cursor += 0.01 * Math.max(1, text.length);
  return { text, box: { u0, v0: baseline - 0.8 * size, u1: cursor, v1: baseline + 0.2 * size } };
}

// TeX식 첨자: 0.7 크기, 아래첨자는 기준선을 0.25H 내리고 위첨자는 0.4H 올린다.
const sub = (text: string, baseline = BASELINE) => glyph(text, { size: 0.7 * H, baseline: baseline + 0.25 * H });
const sup = (text: string, baseline = BASELINE) => glyph(text, { size: 0.7 * H, baseline: baseline - 0.4 * H });

describe("estimateScriptedQuote", () => {
  it("겹친 위·아래첨자 (ACM 논문에서 f j k로 추출되던 줄)", () => {
    const line = [glyph("f"), sup("j"), sub("k"), glyph(" ≤ d"), sup("j"), sub("k"), glyph(" = r"), sup("j"), sub("k")];
    expect(estimateScriptedQuote(line)).toBe("f^j_k ≤ d^j_k = r^j_k");
  });

  it("아래첨자와 그 뒤 문장부호 앞 공백", () => {
    const line = [
      glyph("τ"),
      sub("k"),
      glyph(" = (C"),
      sub("k"),
      glyph(" , D"),
      sub("k"),
      glyph(" ,T"),
      sub("k"),
      glyph(" ) ∈ τ"),
    ];
    expect(estimateScriptedQuote(line)).toBe("τ_k = (C_k, D_k,T_k) ∈ τ");
  });

  it("여러 글자 첨자는 중괄호로 묶고, 첨자 앞 공백 조각은 없앤다", () => {
    expect(estimateScriptedQuote([glyph("x"), sub("ij"), glyph(" + y"), glyph(" "), sup("2")])).toBe("x_{ij} + y^2");
  });

  it("줄이 바뀌면 공백으로 잇고 줄마다 기준 글자를 따로 정한다", () => {
    const first = [glyph("first line with x"), sub("i")];
    const next = 0.35;
    const second = [glyph("second line", { baseline: next }), sup("n", next)];
    expect(estimateScriptedQuote([...first, ...second])).toBe("first line with x_i second line^n");
  });

  it("큰 연산자 하나가 기준 글자가 되지 않는다", () => {
    const line = [glyph("∑", { size: 1.6 * H, baseline: BASELINE + 0.2 * H }), sub("i"), glyph(" x y z")];
    expect(estimateScriptedQuote(line)).toBe("∑_i x y z");
  });

  it("문장 속 분수는 \\frac으로, 분자·분모 안의 첨자는 그 묶음 기준으로 적는다", () => {
    // 앞 글자 "="와 떨어진 분자(위)·분모(아래), 가로로 겹침. 분자 속 i는 줄 기준으로는 제자리(0.15H)라
    // 첨자로 보이지 않지만 분자 묶음에 붙고, 분자 글자 크기 기준으로는 아래첨자다.
    const eq = glyph("=");
    const space = glyph(" "); // PDF.js는 떨어진 조각 사이에 공백 조각을 넣는다
    cursor += 0.3 * H;
    const numerator = [glyph("C", { size: 0.7 * H, baseline: BASELINE - 0.4 * H }), glyph("i", { size: 0.5 * H, baseline: BASELINE - 0.3 * H })];
    cursor -= 0.02;
    const denominator = [glyph("T", { size: 0.7 * H, baseline: BASELINE + 0.45 * H }), glyph("i", { size: 0.5 * H, baseline: BASELINE + 0.55 * H })];
    expect(estimateScriptedQuote([glyph("U"), sub("i"), glyph(" "), eq, space, ...numerator, ...denominator, glyph(".")])).toBe(
      "U_i = \\frac{C_i}{T_i}.",
    );
  });

  it("분모를 먼저 그린 분수, 여는 괄호 바로 뒤(가장 좁은 간격)의 분수", () => {
    const open = glyph("(");
    cursor += 0.13 * H; // \nulldelimiterspace만 있는 간격
    const start = cursor;
    const denominator = sub("2");
    cursor = start;
    const numerator = sup("1");
    expect(estimateScriptedQuote([open, denominator, numerator, glyph(")")])).toBe("(\\frac{1}{2})");
  });

  it("여러 조각으로 나뉜 첨자는 한 첨자로 묶는다", () => {
    const base = glyph("I");
    const start = cursor;
    const upper = sup("c");
    cursor = start;
    expect(estimateScriptedQuote([base, upper, sub("i"), sub(","), sub("k"), glyph(" term")])).toBe("I^c_{i,k} term");
  });

  it("앞 글자에 붙은 위·아래첨자는 분수가 아니다", () => {
    const base = glyph("x");
    const start = cursor;
    const upper = sup("2");
    cursor = start + 0.09 * H; // 기준(0.1H)보다 가깝다
    expect(estimateScriptedQuote([base, upper, sub("i")])).toBe("x^2_i");
  });

  it("첨자가 없으면 null (크기만 작고 제자리인 글자, 한 줄 전체가 작은 글자)", () => {
    expect(estimateScriptedQuote([glyph("plain text"), glyph(" more")])).toBeNull();
    expect(estimateScriptedQuote([glyph("Small"), glyph("CAPS", { size: 0.75 * H })])).toBeNull();
    expect(estimateScriptedQuote([glyph("footnote", { size: 0.7 * H })])).toBeNull();
    expect(estimateScriptedQuote([])).toBeNull();
  });
});

/**
 * 실제 논문(사용자 ACM 논문)에서 잰 값. 단위는 본문 span 높이 H, center는 본문 가운데에서 아래로 +.
 * PDF.js가 넣은 공백 조각도 그대로 둔다. (텍스트, 가로 시작, 가로 끝, 높이, 세로 가운데)
 */
type Measured = readonly [string, number, number, number, number];
const measured = (rows: readonly Measured[]): TextFragment[] =>
  rows.map(([text, u0, u1, h, center]) => ({ text, box: { u0, u1, v0: center - h / 2, v1: center + h / 2 } }));

describe("실제 논문에서 잰 조각", () => {
  it("p.8 문장 속 분수 U_i = C_i / T_i", () => {
    const line = measured([
      ["where", 4.576, 7.122, 1, 0],
      [" ", 7.118, 7.368, 1, 0],
      ["U", 7.308, 8.031, 1, 0],
      ["i", 7.947, 8.151, 0.729, 0.233],
      [" ", 8.172, 8.355, 0.729, 0.233],
      ["=", 8.567, 9.152, 1, 0],
      [" ", 9.201, 9.48, 1, 0],
      ["C", 9.576, 10.064, 0.729, -0.374],
      ["i", 10.085, 10.238, 0.551, -0.204],
      ["T", 9.611, 10.056, 0.729, 0.428],
      ["i", 10.035, 10.188, 0.551, 0.599],
      [" ", 10.231, 10.368, 0.551, 0.599],
      [".", 10.509, 10.76, 1, 0],
    ]);
    expect(estimateScriptedQuote(line)).toBe("where U_i = \\frac{C_i}{T_i}.");
  });

  it("p.6 겹친 위·아래첨자는 앞 글자에 붙어 있어 분수로 보지 않는다", () => {
    const line = measured([
      ["absolute deadline:", 4.611, 11.941, 1, 0],
      [" ", 11.944, 12.194, 1, 0],
      ["f", 12.271, 12.605, 1, 0],
      [" ", 12.587, 12.838, 1, 0],
      ["j", 12.841, 13.045, 0.729, -0.411],
      ["k", 12.612, 12.978, 0.729, 0.472],
      [" ", 12.987, 13.171, 0.729, 0.472],
      ["≤", 13.475, 14.025, 1, 0],
      [" ", 14.109, 14.388, 1, 0],
      ["d", 14.368, 14.868, 1, 0],
      [" ", 14.856, 15.107, 1, 0],
      ["j", 14.959, 15.162, 0.729, -0.411],
      ["k", 14.88, 15.246, 0.729, 0.472],
      [" ", 15.261, 15.445, 0.729, 0.472],
      ["=", 15.661, 16.246, 1, 0],
      [" ", 16.3, 16.579, 1, 0],
      ["r", 16.534, 16.868, 1, 0],
      [" ", 16.891, 17.141, 1, 0],
      ["j", 17.027, 17.231, 0.729, -0.411],
      ["k", 16.925, 17.291, 0.729, 0.472],
      [" ", 17.306, 17.489, 0.729, 0.472],
      ["+", 17.652, 18.236, 1, 0],
      [" ", 18.286, 18.565, 1, 0],
      ["D", 18.501, 19.224, 1, 0],
      ["k", 19.199, 19.565, 0.729, 0.247],
      [" ", 19.579, 19.762, 0.729, 0.247],
      [".", 19.701, 19.952, 1, 0],
    ]);
    expect(estimateScriptedQuote(line)).toBe("absolute deadline: f^j_k ≤ d^j_k = r^j_k + D_k.");
  });
});
