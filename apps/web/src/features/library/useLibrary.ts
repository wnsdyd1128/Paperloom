/**
 * 서재의 논문 목록과 바꾸기 (U6). 본문 추출이 끝날 때까지 목록을 다시 받는다. 올리기(단추·끌어 놓기)·다시 추출·태그는
 * 서버에 보낸 뒤 목록을 바꾼다. 안내(notice)는 머리 아래 한 줄로 보인다.
 */
import { useCallback, useEffect, useRef, useState } from "react";

import { ApiError } from "../../shared/http";
import { deleteTag as deleteTagRequest, listPapers, type Paper, renameTag as renameTagRequest, requestParse, setPaperTags, uploadPaper } from "./api";

export type ListState = Readonly<{ kind: "loading" }> | Readonly<{ kind: "ready"; papers: readonly Paper[] }> | Readonly<{ kind: "failed" }>;
export type Notice = Readonly<{ tone: "ok" | "error" | "pending"; text: string }> | null;

const POLL_MS = 1500;

export function useLibrary() {
  const [list, setList] = useState<ListState>({ kind: "loading" });
  const [notice, setNotice] = useState<Notice>(null);
  const [uploading, setUploading] = useState(false);
  const tagSaves = useRef({ chain: Promise.resolve(), latest: new Map<string, number>() });
  const papers = list.kind === "ready" ? list.papers : [];

  const reload = useCallback(
    () =>
      listPapers()
        .then((next) => setList({ kind: "ready", papers: next }))
        .catch(() => setList((current) => (current.kind === "ready" ? current : { kind: "failed" }))),
    [],
  );

  useEffect(() => {
    void reload();
  }, [reload]);

  const extracting = papers.some((paper) => ["READY_TO_READ", "PARSING"].includes(paper.current_version.status));
  // 본문 추출이 끝날 때까지 목록을 다시 받아 상태를 바꾼다.
  useEffect(() => {
    if (!extracting) return;
    const timer = setTimeout(() => void reload(), POLL_MS);
    return () => clearTimeout(timer);
  }, [list, extracting, reload]);

  /** PDF를 차례로 올린다(끌어 놓기는 여러 개일 수 있다). PDF가 아닌 파일은 올리지 않는다. */
  async function upload(files: readonly File[]) {
    const pdfs = files.filter((file) => file.type === "application/pdf" || file.name.toLowerCase().endsWith(".pdf"));
    if (pdfs.length === 0) {
      setNotice({ tone: "error", text: "PDF 파일만 올릴 수 있습니다." });
      return;
    }
    setUploading(true);
    try {
      for (const file of pdfs) {
        setNotice({ tone: "pending", text: `“${file.name}” 확인 중…` });
        try {
          const paper = await uploadPaper(file);
          setList((current) => ({ kind: "ready", papers: [paper, ...(current.kind === "ready" ? current.papers : [])] }));
          setNotice({ tone: "ok", text: `등록됨: ${paper.title}` });
        } catch (error) {
          setNotice({ tone: "error", text: describeUploadError(error, papers) });
          return;
        }
      }
    } finally {
      setUploading(false);
    }
  }

  async function retry(paper: Paper) {
    try {
      await requestParse(paper.current_version.version_id);
      await reload();
    } catch (error) {
      setNotice({ tone: "error", text: error instanceof ApiError ? error.message : "다시 추출하지 못했습니다." });
    }
  }

  const replacePaper = (next: Paper) =>
    setList((current) =>
      current.kind === "ready" ? { kind: "ready", papers: current.papers.map((item) => (item.paper_id === next.paper_id ? next : item)) } : current,
    );

  /**
   * 태그는 바로 보이게 바꾸고 차례로 저장한다. 저장이 끝나기 전에 또 바꾸면(태그를 켜고 곧바로 새 태그를 적으면) 다음 바꾸기가
   * 앞 바꾸기 위에 쌓여야 하고, 늦게 온 앞 응답이 화면을 되돌리면 안 된다. 그래서 그 논문의 마지막 저장 응답만 반영한다.
   */
  async function setTags(paper: Paper, tags: readonly string[]) {
    const saves = tagSaves.current;
    const turn = (saves.latest.get(paper.paper_id) ?? 0) + 1;
    saves.latest.set(paper.paper_id, turn);
    replacePaper({ ...paper, tags: [...tags] });
    const request = saves.chain.then(() => setPaperTags(paper.paper_id, tags));
    saves.chain = request.then(
      () => undefined,
      () => undefined,
    );
    try {
      const saved = await request;
      if (saves.latest.get(paper.paper_id) === turn) replacePaper(saved);
    } catch (error) {
      if (saves.latest.get(paper.paper_id) === turn) void reload(); // 서버에 있는 태그로 되돌린다
      setNotice({ tone: "error", text: error instanceof ApiError ? error.message : "태그를 저장하지 못했습니다. 백엔드 연결을 확인하세요." });
    }
  }

  /** 태그 이름 바꾸기·지우기(서재 태그 메뉴, 2026-10-04): 모든 논문에서 바꾸고 목록을 다시 받는다. 되면 true */
  async function changeTag(request: () => Promise<void>, failure: string): Promise<boolean> {
    try {
      await request();
      await reload();
      return true;
    } catch (error) {
      setNotice({ tone: "error", text: error instanceof ApiError ? error.message : failure });
      return false;
    }
  }
  const renameTag = (name: string, next: string) => changeTag(() => renameTagRequest(name, next), "태그 이름을 바꾸지 못했습니다.");
  const deleteTag = (name: string) => changeTag(() => deleteTagRequest(name), "태그를 지우지 못했습니다.");

  return { list, papers, notice, uploading, upload, retry, setTags, renameTag, deleteTag };
}

export type Library = ReturnType<typeof useLibrary>;

function describeUploadError(error: unknown, papers: readonly Paper[]): string {
  if (!(error instanceof ApiError)) return "업로드하지 못했습니다. 백엔드 연결을 확인하세요.";
  if (error.body.code === "DUPLICATE_SOURCE") {
    const existing = papers.find((paper) => paper.paper_id === error.body.details?.paper_id);
    return existing ? `이미 등록된 논문입니다: ${existing.title}` : error.message;
  }
  return error.message;
}
