/** 아티팩트 REST 클라이언트 (backend/src/paperloom/artifacts/routes.py): 논문 대화의 아티팩트 목록과 링크. */

import { jsonRequest, parseJson } from "../../shared/http";
import type { Artifact } from "./artifact";

/** 대화 답 안의 아티팩트 하나. 서버가 저장된 답에서 웹과 같은 규칙으로 찾는다(artifacts/blocks.py) */
export type ChatArtifact = Artifact &
  Readonly<{
    answer_id: string;
    /** 그 답에서 몇 번째 아티팩트인지(0부터) */
    index: number;
    session_id: string | null;
    /** 그 차례의 질문 */
    prompt: string | null;
    created_at: string;
  }>;

/** 그 논문의 대화(사이드바 대화·선택 설명·질문)에서 버리지 않은 답의 아티팩트. 최근 답부터, 한 답 안에서는 나온 순서다 */
export async function listChatArtifacts(paperId: string): Promise<ChatArtifact[]> {
  return (await parseJson<{ artifacts: ChatArtifact[] }>(await fetch(`/api/v1/papers/${encodeURIComponent(paperId)}/artifacts`))).artifacts;
}

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
