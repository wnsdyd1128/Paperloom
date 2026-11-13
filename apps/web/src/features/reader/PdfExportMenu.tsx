/**
 * PDF로 내보내기 창 (2026-11-13 사용자 요청): 머리의 내려받기 단추로 연다. 하이라이트·주석·설명·AI 질문 가운데 넣을 것을
 * 고르고(처음에는 모두), 원본 PDF에 그것을 PDF 표준 주석으로 붙인 파일을 내려받는다. 바깥을 누르거나 Esc로 닫는다.
 */
import { useEffect, useRef, useState } from "react";

import { ApiError, type ApiErrorBody } from "../../shared/http";
import { Icon } from "../../shared/Icon";
import { annotatedPdfUrl, PDF_PARTS, type PdfPart, pdfFileName } from "./pdfExport";

type Props = Readonly<{
  versionId: string;
  title: string;
  disabled: boolean;
  counts: Readonly<Record<PdfPart, number>>;
}>;

export function PdfExportMenu({ versionId, title, disabled, counts }: Props) {
  const [open, setOpen] = useState(false);
  const [chosen, setChosen] = useState<ReadonlySet<PdfPart>>(() => new Set(PDF_PARTS.map(({ part }) => part)));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) {
      setError(null);
      return;
    }
    const onPointerDown = (event: PointerEvent) => {
      if (!ref.current?.contains(event.target as Node)) setOpen(false);
    };
    const onKey = (event: KeyboardEvent) => {
      if (event.key !== "Escape" || event.isComposing) return;
      setOpen(false);
      ref.current?.querySelector<HTMLButtonElement>(".pdf-export-button")?.focus();
    };
    document.addEventListener("pointerdown", onPointerDown, true);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("pointerdown", onPointerDown, true);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  const toggle = (part: PdfPart) =>
    setChosen((current) => {
      const next = new Set(current);
      if (!next.delete(part)) next.add(part);
      return next;
    });

  async function download() {
    setBusy(true);
    setError(null);
    try {
      const parts = PDF_PARTS.map(({ part }) => part).filter((part) => chosen.has(part));
      const response = await fetch(annotatedPdfUrl(versionId, parts));
      if (!response.ok) throw new ApiError(response.status, (await response.json()) as ApiErrorBody);
      const url = URL.createObjectURL(await response.blob());
      const link = document.createElement("a");
      link.href = url;
      link.download = pdfFileName(title);
      link.click();
      window.setTimeout(() => URL.revokeObjectURL(url), 1000);
      setOpen(false);
    } catch (failure) {
      setError(failure instanceof ApiError ? failure.body.message : "PDF를 만들지 못했습니다. 백엔드 연결을 확인하세요.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="pdf-export-menu" ref={ref}>
      <button
        type="button"
        className="btn btn-icon head-icon pdf-export-button"
        aria-label="PDF로 내보내기"
        title="PDF로 내보내기: 하이라이트·주석·설명·AI 질문을 PDF 메모로 넣은 원문 PDF를 내려받습니다"
        aria-haspopup="dialog"
        aria-expanded={open}
        disabled={disabled}
        onClick={() => setOpen((value) => !value)}
      >
        <Icon name="download" size={17} />
      </button>
      {open && (
        <div className="pdf-export" role="dialog" aria-label="PDF로 내보내기">
          <p className="pdf-export-title">PDF로 내보내기</p>
          <p className="pdf-export-hint">원문 쪽은 그대로 두고, 고른 것을 PDF 메모로 넣습니다. Claude 대화는 넣지 않습니다.</p>
          <fieldset className="pdf-export-parts">
            <legend className="sr-only">넣을 것</legend>
            {PDF_PARTS.map(({ part, label, icon }) => (
              <label key={part} className="pdf-export-check">
                <input type="checkbox" checked={chosen.has(part)} onChange={() => toggle(part)} disabled={busy} />
                <Icon name={icon} size={15} />
                <span className="pdf-export-label">{label}</span>
                <span className="pdf-export-count" aria-label={`${counts[part]}개`}>
                  {counts[part]}
                </span>
              </label>
            ))}
          </fieldset>
          {error && (
            <p className="status error" role="alert">
              {error}
            </p>
          )}
          <button type="button" className="btn btn-primary" onClick={() => void download()} disabled={busy || chosen.size === 0}>
            <Icon name="download" size={15} />
            {busy ? "만드는 중…" : "PDF 내려받기"}
          </button>
        </div>
      )}
    </div>
  );
}
