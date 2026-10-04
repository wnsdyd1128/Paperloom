/** 논문 정보 고치기 칸 읽기 (U4, 사용자 결정 D5). 서버 검사(PaperMetadataIn)와 같은 규칙을 먼저 알려 준다. */
import type { PaperMetadata } from "../library/api";

export type MetadataForm = Readonly<{ title: string; authors: string; year: string; doi: string }>;
type Field = keyof MetadataForm;

const DOI = /^10\.\d{4,9}\/\S+$/;
// 붙여 넣은 DOI 주소·접두는 떼어 낸다.
const DOI_PREFIX = /^(?:https?:\/\/(?:dx\.)?doi\.org\/|doi:\s*)/i;

export function readMetadataForm(form: MetadataForm): { ok: true; value: PaperMetadata } | { ok: false; errors: Partial<Record<Field, string>> } {
  const errors: Partial<Record<Field, string>> = {};
  const title = form.title.trim();
  if (!title) errors.title = "제목을 쓰세요.";
  else if (title.length > 500) errors.title = "제목은 500자까지입니다.";

  const authors = form.authors
    .split("\n")
    .map((author) => author.trim())
    .filter(Boolean);
  if (authors.length > 100 || authors.some((author) => author.length > 300)) errors.authors = "저자는 100명, 한 사람 300자까지입니다.";

  const yearText = form.year.trim();
  const year = yearText ? Number(yearText) : null;
  if (year !== null && !(/^\d{4}$/.test(yearText) && year >= 1000 && year <= 2100)) errors.year = "연도는 1000–2100의 네 자리 숫자입니다.";

  const doi = form.doi.trim().replace(DOI_PREFIX, "") || null;
  if (doi !== null && (!DOI.test(doi) || doi.length > 200)) errors.doi = "DOI는 10.으로 시작합니다(예: 10.1145/3487581).";

  return Object.keys(errors).length > 0 ? { ok: false, errors } : { ok: true, value: { title, authors, year, doi } };
}

export function metadataForm(metadata: PaperMetadata): MetadataForm {
  return { title: metadata.title, authors: metadata.authors.join("\n"), year: metadata.year === null ? "" : String(metadata.year), doi: metadata.doi ?? "" };
}
