import { Icon } from "../../shared/Icon";
import { type Artifact, ARTIFACT_LABELS } from "./artifact";
import "./artifacts.css";

/**
 * 답 안의 아티팩트 자리. 누르면 Reader 본문 위 창(분리한 대화 탭이면 대화 옆 창)에서 연다. 답을 만드는 중(onOpen이 null)이면 열지 않는다(글이 아직 덜 왔다).
 */
export function ArtifactCard({ artifact, onOpen }: Readonly<{ artifact: Artifact; onOpen: ((artifact: Artifact) => void) | null }>) {
  const kind = ARTIFACT_LABELS[artifact.type] + (artifact.language ? ` · ${artifact.language}` : "");
  const body = (
    <>
      <Icon name="fileText" size={18} />
      <span className="artifact-card-text">
        <b>{artifact.title}</b>
        <small>{onOpen ? kind : `${kind} · 만드는 중…`}</small>
      </span>
    </>
  );
  return onOpen ? (
    <button type="button" className="artifact-card" data-artifact-type={artifact.type} onClick={() => onOpen(artifact)} aria-label={`아티팩트 열기: ${artifact.title}`}>
      {body}
      <span className="artifact-card-open">열기</span>
    </button>
  ) : (
    <div className="artifact-card is-pending" data-artifact-type={artifact.type}>
      {body}
    </div>
  );
}
