/**
 * 논문 정보 창 (U4, IMPL §10.8): 머리의 정보 단추로 연다. 제목·저자·연도·DOI·쪽·본문 추출 상태·파일을 보이고, 제목·저자·
 * 연도·DOI를 고친다(2026-10-02 사용자 결정 D5: DOI는 본문 추출이 앞쪽에서 찾고, 나머지는 직접 적는다). 시안에는 단추만
 * 있어 모양은 가정이다. 바깥을 누르거나 Esc로 닫으며, 저장하지 않은 고침은 버린다.
 */
import { useEffect, useRef, useState } from "react";

import { Icon } from "../../shared/Icon";
import { type PageTexts, type Paper, updatePaperMetadata, type Version } from "../library/api";
import { pageRanges } from "../threads/pageRanges";
import { metadataForm, type MetadataForm, readMetadataForm } from "./paperMetadata";

type Props = Readonly<{
  paper: Paper;
  version: Version;
  texts: PageTexts | null;
  onSaved: (paper: Paper) => void;
}>;

export function PaperInfoMenu({ paper, version, texts, onSaved }: Props) {
  const [open, setOpen] = useState(false);
  // null이면 보기, 아니면 고치는 중인 칸들
  const [form, setForm] = useState<MetadataForm | null>(null);
  const [errors, setErrors] = useState<Partial<Record<keyof MetadataForm, string>>>({});
  const [saving, setSaving] = useState(false);
  const [failed, setFailed] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) {
      setForm(null);
      setErrors({});
      setFailed(false);
      return;
    }
    const onPointerDown = (event: PointerEvent) => {
      if (!ref.current?.contains(event.target as Node)) setOpen(false);
    };
    const onKey = (event: KeyboardEvent) => {
      if (event.key !== "Escape" || event.isComposing) return;
      setOpen(false);
      ref.current?.querySelector<HTMLButtonElement>(".info-button")?.focus();
    };
    document.addEventListener("pointerdown", onPointerDown, true);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("pointerdown", onPointerDown, true);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  async function save(values: MetadataForm) {
    const read = readMetadataForm(values);
    setErrors(read.ok ? {} : read.errors);
    if (!read.ok) return;
    setSaving(true);
    setFailed(false);
    try {
      onSaved(await updatePaperMetadata(paper.paper_id, read.value));
      setForm(null);
    } catch {
      setFailed(true);
    } finally {
      setSaving(false);
    }
  }

  const field = (name: keyof MetadataForm) => ({
    value: form?.[name] ?? "",
    "aria-invalid": errors[name] ? true : undefined,
    onChange: (event: { target: { value: string } }) => setForm((current) => current && { ...current, [name]: event.target.value }),
  });
  const error = (name: keyof MetadataForm) => errors[name] && <span className="field-error">{errors[name]}</span>;
  const none = <span className="muted">없음</span>;
  return (
    <div className="info-menu" ref={ref}>
      <button
        type="button"
        className="btn btn-icon head-icon info-button"
        aria-label="논문 정보"
        title="논문 정보"
        aria-haspopup="dialog"
        aria-expanded={open}
        onClick={() => setOpen((value) => !value)}
      >
        <Icon name="info" size={17} />
      </button>
      {open && (
        <div className="menu-popover paper-info" role="dialog" aria-label="논문 정보">
          {form ? (
            <form
              className="paper-info-form"
              onSubmit={(event) => {
                event.preventDefault();
                void save(form);
              }}
            >
              <label>
                제목
                <input className="input" {...field("title")} />
                {error("title")}
              </label>
              <label>
                저자 <span className="muted">한 줄에 한 사람</span>
                <textarea className="input" rows={3} {...field("authors")} />
                {error("authors")}
              </label>
              <label>
                연도
                <input className="input" inputMode="numeric" placeholder="2022" {...field("year")} />
                {error("year")}
              </label>
              <label>
                DOI
                <input className="input" placeholder="10.1145/3487581" {...field("doi")} />
                {error("doi")}
              </label>
              {failed && <p className="status error">저장하지 못했습니다. 백엔드 연결을 확인하세요.</p>}
              <div className="paper-info-actions">
                <button type="button" className="btn btn-plain" onClick={() => (setForm(null), setErrors({}))}>
                  취소
                </button>
                <button type="submit" className="btn btn-primary" disabled={saving}>
                  저장
                </button>
              </div>
            </form>
          ) : (
            <>
              <p className="paper-info-title">{paper.title}</p>
              <dl className="paper-info-list">
                <dt>저자</dt>
                <dd>{paper.authors.length > 0 ? paper.authors.join(", ") : none}</dd>
                <dt>연도</dt>
                <dd>{paper.year ?? none}</dd>
                <dt>DOI</dt>
                <dd>
                  {paper.doi ? (
                    <a href={`https://doi.org/${paper.doi}`} target="_blank" rel="noreferrer">
                      {paper.doi}
                    </a>
                  ) : (
                    none
                  )}
                </dd>
                <dt>쪽</dt>
                <dd>{version.page_count}쪽</dd>
                <dt>본문 추출</dt>
                <dd>{extractionSummary(texts, version)}</dd>
                <dt>파일</dt>
                <dd>
                  {fileSize(version.size_bytes)} · {new Date(version.created_at).toLocaleDateString("ko-KR")} 등록
                </dd>
              </dl>
              <div className="paper-info-actions">
                <button type="button" className="btn btn-plain" onClick={() => setForm(metadataForm(paper))}>
                  <Icon name="pencil" size={14} />
                  고치기
                </button>
              </div>
            </>
          )}
        </div>
      )}
    </div>
  );
}

const FAILURE_REASONS: Record<string, string> = {
  NO_TEXT_LAYER: "글자 층 없음(스캔)",
  RESOURCE_LIMIT: "처리 한도 넘음",
  PARSER_ERROR: "추출 오류",
  PASSWORD_REQUIRED: "암호",
  MALFORMED_PDF: "손상된 PDF",
};

function fileSize(bytes: number): string {
  return bytes >= 1024 * 1024 ? `${(bytes / 1024 / 1024).toFixed(1)} MB` : `${Math.max(1, Math.round(bytes / 1024))} KB`;
}

/**
 * 문서 상태, 쪽 상태가 섞였으면 상태별 쪽 수, 참고문헌 쪽 (IMPL §5.3). 예: "정상 · 참고문헌 27–29쪽",
 * "일부 · 정상 20쪽 · 이미지 2쪽". 쪽 목록은 추출이 끝날 때까지 다시 받는다(usePageTexts).
 */
function extractionSummary(texts: PageTexts | null, version: Version): string {
  const status = texts?.status ?? version.status;
  if (status === "READY_TO_READ" || status === "PARSING") return "추출 중";
  if (status === "FAILED") return `실패 · ${FAILURE_REASONS[version.status_reason ?? ""] ?? version.status_reason ?? "이유 모름"}`;
  const pages = texts?.pages ?? [];
  const count = (kind: string) => pages.filter((page) => page.text_status === kind).length;
  const parts = [
    [count("usable"), "정상"],
    [count("partial"), "일부"],
    [count("image_only"), "이미지"],
    [count("unknown"), "글자 없음"],
  ].filter(([pagesOf]) => pagesOf);
  const mixed = parts.length > 1 || (parts.length === 1 && parts[0][1] !== "정상");
  const details = mixed ? parts.map(([pagesOf, label]) => `${label} ${pagesOf}쪽`) : [];
  const references = pages.filter((page) => page.flags.includes("references")).map((page) => page.page_index + 1);
  if (references.length > 0) details.push(`참고문헌 ${pageRanges(references).replace(/^p\./, "")}쪽`);
  return [status === "INDEXED" ? "정상" : "일부", ...details].join(" · ");
}
