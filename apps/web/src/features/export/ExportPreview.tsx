/** 내보내기 미리보기 (기능 명세 F-04): 쓸 파일·크기·경고·자동으로 더한 위치. 아무것도 쓰지 않는다. */
import type { BundlePreview } from "./api";
import { formatBytes } from "./draft";

const WARNING_LABELS: Readonly<Record<string, string>> = {
  pages_not_extracted: "본문을 추출하지 않은 쪽",
  near_limit: "한도의 80%를 넘음",
  over_limit: "한도를 넘음. 이미지, 추출문 범위 순으로 줄이세요",
  region_without_image: "이미지 없이 넣는 영역",
  empty_quote: "인용이 빈 위치",
  unresolved_answer_citation: "풀지 못한 답변 근거",
};

const REASON_LABELS: Readonly<Record<BundlePreview["auto_added_anchors"][number]["reason"], string>> = {
  cited_by_answer: "답변이 인용",
  linked_by_proposal: "제안의 근거",
};

export function overLimit(preview: BundlePreview): boolean {
  return preview.warnings.some((warning) => warning.code === "over_limit");
}

export function ExportPreview({ preview }: Readonly<{ preview: BundlePreview }>) {
  const { limits } = preview;
  return (
    <div className="export-preview">
      <section aria-label="크기">
        <Meter label="파일" text={`${preview.file_count} / ${limits.max_files}개`} share={preview.file_count / limits.max_files} />
        <Meter label="합계" text={`${formatBytes(preview.total_bytes)} / ${formatBytes(limits.max_total_bytes)}`} share={preview.total_bytes / limits.max_total_bytes} />
      </section>
      {preview.warnings.length > 0 && (
        <section aria-label="경고">
          <h4>경고</h4>
          <ul className="export-warnings">
            {preview.warnings.map((warning) => (
              <li key={`${warning.code}:${warning.detail}`} data-code={warning.code}>
                <b>{WARNING_LABELS[warning.code] ?? warning.code}</b> {warning.detail}
              </li>
            ))}
          </ul>
        </section>
      )}
      {preview.auto_added_anchors.length > 0 && (
        <section aria-label="자동으로 더한 위치">
          <h4>자동으로 더한 위치</h4>
          <ul className="export-warnings">
            {preview.auto_added_anchors.map((item) => (
              <li key={item.anchor_id}>
                <b>{REASON_LABELS[item.reason]}</b> {item.anchor_id.slice(0, 8)}
              </li>
            ))}
          </ul>
        </section>
      )}
      <section aria-label="쓸 파일">
        <h4>쓸 파일</h4>
        <table className="table export-files">
          <thead>
            <tr>
              <th scope="col">경로</th>
              <th scope="col">종류</th>
              <th scope="col" className="num">
                크기
              </th>
            </tr>
          </thead>
          <tbody>
            {preview.files.map((file) => (
              <tr key={file.path}>
                <td className="export-path">{file.path}</td>
                <td>{file.kind}</td>
                <td className="num">{formatBytes(file.size_bytes)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
      <p className="export-note">
        원본 PDF는 넣지 않습니다. Paperloom은 Wiki를 바꾸지 않습니다. LLM Wiki에서 받을지, 어떤 후보를 승인할지 다시 고릅니다.
      </p>
    </div>
  );
}

function Meter({ label, text, share }: Readonly<{ label: string; text: string; share: number }>) {
  return (
    <div className="export-meter" data-over={share > 1 || undefined}>
      <span>{label}</span>
      <span className="export-bar" aria-hidden="true">
        <span style={{ width: `${Math.min(100, share * 100)}%` }} />
      </span>
      <span className="export-meter-text">{text}</span>
    </div>
  );
}
