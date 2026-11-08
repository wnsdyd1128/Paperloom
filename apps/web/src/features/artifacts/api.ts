/** 아티팩트 링크 REST 클라이언트 (backend/src/paperloom/artifacts/routes.py). */

import { jsonRequest, parseJson } from "../../shared/http";

/** url은 이 서버의 경로(/artifacts/<id>), path는 저장한 파일(사용자 폴더는 ~, Docker면 저장소의 var/artifacts 기준)이다 */
export type ArtifactLink = Readonly<{ artifact_id: string; url: string; path: string }>;

/** 페이지 문서를 파일로 쓰고 링크를 받는다. 같은 내용은 같은 링크다. 실패하면 사용자 문구를 담은 Error를 던진다 */
export async function createArtifactLink(html: string): Promise<ArtifactLink> {
  let response: Response;
  try {
    response = await fetch("/api/v1/artifacts", jsonRequest("POST", { html }));
  } catch {
    throw new Error("링크를 만들지 못했습니다. 백엔드 연결을 확인하세요.");
  }
  return parseJson<ArtifactLink>(response); // 서버 거절은 그 문구의 ApiError
}
