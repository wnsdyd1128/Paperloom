/**
 * 내보낸 bundle 기록 (기능 명세 F-06): 만든 때(최근 것부터)·논문·파일 수·크기·상태. 줄을 누르면 파일과 해시를 본다.
 * 지우기와 다시 쓰기는 없다. outbox 정리는 사용자가 파일 탐색기로 한다. 폴더를 지웠으면 "outbox에 없음"으로 알린다(기록은 남긴다).
 */
import "./export.css";

import { useEffect, useState } from "react";

import { Icon } from "../../shared/Icon";
import { formatTime } from "../../shared/time";
import { type BundleDetail, type BundleListItem, getBundle, listBundles } from "./api";
import { formatBytes } from "./draft";

const HASH_CHARS = 12;

type List = Readonly<{ kind: "loading" }> | Readonly<{ kind: "ready"; items: readonly BundleListItem[] }> | Readonly<{ kind: "failed" }>;
type Detail = Readonly<{ kind: "none" }> | Readonly<{ kind: "ready"; bundle: BundleDetail }> | Readonly<{ kind: "failed" }>;

export function BundlesPage() {
  const [list, setList] = useState<List>({ kind: "loading" });
  const [detail, setDetail] = useState<Detail>({ kind: "none" });

  useEffect(() => {
    listBundles()
      .then((items) => setList({ kind: "ready", items }))
      .catch(() => setList({ kind: "failed" }));
  }, []);

  function open(bundleId: string) {
    if (detail.kind === "ready" && detail.bundle.bundle_id === bundleId) return setDetail({ kind: "none" });
    getBundle(bundleId)
      .then((bundle) => setDetail({ kind: "ready", bundle }))
      .catch(() => setDetail({ kind: "failed" }));
  }

  return (
    <section className="shelf" aria-labelledby="bundles-heading">
      <div className="shelf-head">
        <div className="shelf-title">
          <h2 id="bundles-heading">내보낸 bundle</h2>
          {list.kind === "ready" && <span className="shelf-count">{list.items.length}개</span>}
        </div>
      </div>
      {list.kind === "loading" && <p className="muted">기록을 불러오는 중…</p>}
      {list.kind === "failed" && <p className="status error">기록을 불러오지 못했습니다. 백엔드 연결을 확인하세요.</p>}
      {list.kind === "ready" && list.items.length === 0 && <p className="muted">아직 내보낸 bundle이 없습니다. 서재에서 논문을 고르거나 Reader에서 "Wiki로 내보내기"를 누르세요.</p>}
      {list.kind === "ready" && list.items.length > 0 && (
        <table className="table bundle-table">
          <thead>
            <tr>
              <th scope="col">만든 때</th>
              <th scope="col">논문</th>
              <th scope="col" className="num">
                판본
              </th>
              <th scope="col" className="num">
                파일
              </th>
              <th scope="col" className="num">
                크기
              </th>
              <th scope="col">상태</th>
            </tr>
          </thead>
          <tbody>
            {list.items.map((item) => (
              <tr key={item.bundle_id} data-bundle-id={item.bundle_id}>
                <td>
                  <button type="button" className="link-button" aria-expanded={detail.kind === "ready" && detail.bundle.bundle_id === item.bundle_id} onClick={() => open(item.bundle_id)}>
                    {formatTime(item.created_at)}
                  </button>
                </td>
                <td>{item.papers.map((paper) => paper.title).join(" · ")}</td>
                <td className="num">{item.papers.length}</td>
                <td className="num">{item.file_count}</td>
                <td className="num">{formatBytes(item.size_bytes)}</td>
                <td>
                  <span className={item.status === "written" ? "tag tag-neutral" : "tag tag-accent"}>{item.status === "written" ? "written" : "failed"}</span>
                  {item.status === "written" && !item.present_in_outbox && <span className="muted bundle-missing">outbox에 없음</span>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {detail.kind === "failed" && <p className="status error">기록을 불러오지 못했습니다. 백엔드 연결을 확인하세요.</p>}
      {detail.kind === "ready" && <Details bundle={detail.bundle} />}
    </section>
  );
}

function Details({ bundle }: Readonly<{ bundle: BundleDetail }>) {
  const [copied, setCopied] = useState(false);
  const counts = bundle.counts;
  return (
    <section className="bundle-detail" aria-label="bundle 상세">
      <header>
        <code>{bundle.bundle_id}</code>
        <button
          type="button"
          className="btn btn-ghost"
          onClick={() =>
            void navigator.clipboard.writeText(bundle.bundle_id).then(() => setCopied(true))
          }
        >
          <Icon name="copy" size={14} />
          {copied ? "복사했습니다" : "ID 복사"}
        </button>
      </header>
      {bundle.error_code && <p className="status error">실패 코드: {bundle.error_code}</p>}
      {bundle.status === "written" && !bundle.present_in_outbox && <p className="muted">outbox에 없음: 폴더가 지워졌습니다. 기록은 남겨 둡니다.</p>}
      {bundle.status === "written" && (
        <>
          <p className="muted">
            위치 {counts.anchors} · 제안 {counts.proposals} · 답변 {counts.answers} · 이미지 {counts.assets} · 추출문 {counts.texts}
          </p>
          <p className="muted">
            manifest SHA-256 <code>{bundle.manifest_sha256}</code>
          </p>
          <table className="table export-files">
            <thead>
              <tr>
                <th scope="col">경로</th>
                <th scope="col">SHA-256</th>
                <th scope="col" className="num">
                  크기
                </th>
              </tr>
            </thead>
            <tbody>
              {bundle.files.map((file) => (
                <tr key={file.path}>
                  <td className="export-path">{file.path}</td>
                  <td>
                    <code>{file.sha256.slice(0, HASH_CHARS)}</code>
                  </td>
                  <td className="num">{formatBytes(file.size_bytes)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
    </section>
  );
}
