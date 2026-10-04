import { type ReactNode, useEffect, useState } from "react";

import { Icon } from "../../shared/Icon";
import { type Bridge, bridgeState } from "../chat/BridgeStatus";
import { MAX_ZOOM, MIN_ZOOM } from "./zoom";
import { ZoomMenu } from "./ZoomMenu";

type Props = Readonly<{
  title: string;
  ready: boolean;
  pageNumber: number;
  pageCount: number;
  zoom: number;
  rotation: number;
  regionMode: boolean;
  bridge: Bridge;
  /** 쪽 추출 상태 (PageTextStatus) */
  pageStatus: ReactNode;
  tocOpen: boolean;
  findOpen: boolean;
  /** 논문 정보 단추와 창 (PaperInfoMenu) */
  info: ReactNode;
  onToggleToc: () => void;
  onOpenFind: () => void;
  onHome: () => void;
  onOpenSettings: () => void;
  onGoToPage: (pageNumber: number) => void;
  onZoom: (scale: number) => void;
  onZoomStep: (direction: 1 | -1) => void;
  onRotate: () => void;
  onToggleRegion: () => void;
  translationOn: boolean;
  onToggleTranslation: () => void;
  onOpenChat: () => void;
  /** 사이드바 대화에서 논문 본문으로 3줄 요약을 묻는다 (A9) */
  onSummary: () => void;
  onCopyLink: () => void;
}>;

/**
 * Reader 머리 56px (시안 Reader v3). 왼쪽: 목차 토글·로고(서재로)·제목, 가운데: 논문 정보·찾기·배율·축소·확대·쪽 번호·영역 설명·3줄 요약,
 * 오른쪽: 쪽 추출 상태·Claude Code 상태·위치 링크 복사.
 */
export function ReaderHeader(props: Props) {
  const { title, ready, zoom, regionMode, bridge } = props;
  const state = bridgeState(bridge);
  const bridgeTitle =
    state === "ready" ? "Claude Code 연결됨 (이 PC, 구독 사용량)" : state === "checking" ? "Claude Code 브리지 확인 중" : "Claude Code 브리지가 꺼져 있습니다. 누르면 켜는 방법을 봅니다.";
  return (
    <header className="reader-header">
      <div className="reader-head-left">
        <button
          type="button"
          className="btn btn-icon toc-toggle"
          aria-label="논문 목차"
          aria-pressed={props.tocOpen}
          title="논문 목차 (Ctrl+Shift+O)"
          onClick={props.onToggleToc}
        >
          <Icon name="list" size={18} />
        </button>
        <span className="head-rule" aria-hidden="true" />
        <button type="button" className="brand" onClick={props.onHome} aria-label="서재로 돌아가기" title="서재로 돌아가기">
          <span className="brand-mark" aria-hidden="true" />
          <span className="brand-name">Paperloom</span>
        </button>
        <span className="head-rule" aria-hidden="true" />
        <h1 className="reader-title" title={title}>
          {title}
        </h1>
      </div>
      <div className="reader-head-center">
        {props.info}
        <button
          type="button"
          className="btn btn-icon head-icon"
          aria-label="본문에서 찾기"
          aria-pressed={props.findOpen}
          title="본문에서 찾기 (Ctrl+F)"
          onClick={props.onOpenFind}
          disabled={!ready}
        >
          <Icon name="search" size={17} />
        </button>
        <span className="head-rule is-thin" aria-hidden="true" />
        <ZoomMenu zoom={zoom} rotation={props.rotation} disabled={!ready} onZoom={props.onZoom} onRotate={props.onRotate} />
        <button type="button" className="btn btn-icon head-icon" onClick={() => props.onZoomStep(-1)} disabled={!ready || zoom <= MIN_ZOOM} aria-label="축소" title="축소 (Ctrl+-)">
          <Icon name="minus" size={17} />
        </button>
        <button type="button" className="btn btn-icon head-icon" onClick={() => props.onZoomStep(1)} disabled={!ready || zoom >= MAX_ZOOM} aria-label="확대" title="확대 (Ctrl++)">
          <Icon name="plus" size={17} />
        </button>
        <PageBox pageNumber={props.pageNumber} pageCount={props.pageCount} ready={ready} onGo={props.onGoToPage} />
        <span className="head-rule is-thin" aria-hidden="true" />
        <button
          type="button"
          className="btn btn-plain"
          onClick={props.onToggleRegion}
          disabled={!ready}
          aria-pressed={regionMode}
          title="그림·표·수식을 사각형으로 끌어 고릅니다 (Esc로 끝내기, Ctrl을 누른 채 끌어도 됩니다)"
        >
          <Icon name="region" size={15} />
          영역 설명
        </button>
        <button
          type="button"
          className="btn btn-plain"
          onClick={props.onToggleTranslation}
          disabled={!ready}
          aria-pressed={props.translationOn}
          title="보는 쪽을 번역해 원문 옆에 둡니다 (이 PC의 Claude Code, 쪽마다 구독 사용량을 씁니다)"
        >
          <Icon name="languages" size={15} />
          쪽 번역
        </button>
        <button
          type="button"
          className="btn btn-plain"
          onClick={props.onSummary}
          disabled={!ready}
          title="사이드바 대화에서 Claude가 이 논문을 세 줄로 요약합니다 (논문 본문을 보냅니다)"
        >
          <Icon name="fileText" size={15} />
          3줄 요약
        </button>
      </div>
      <div className="reader-head-right">
        {props.pageStatus}
        {/* 색만으로 구분하지 않도록 상태를 글로도 쓴다 (IMPL §10.4) */}
        <button type="button" className="bridge-indicator" data-state={state} title={bridgeTitle} onClick={props.onOpenChat}>
          <span className="bridge-dot" aria-hidden="true" />
          Claude Code{state === "offline" ? " 꺼짐" : state === "checking" ? " 확인 중" : ""}
        </button>
        <button type="button" className="btn btn-icon head-icon" aria-label="설정" title="설정" onClick={props.onOpenSettings}>
          <Icon name="settings" size={17} />
        </button>
        <button type="button" className="btn btn-icon head-icon" aria-label="위치 링크 복사" title="위치 링크 복사" onClick={props.onCopyLink} disabled={!ready}>
          <Icon name="share" size={17} />
        </button>
      </div>
    </header>
  );
}

/** 쪽 번호 칸: 지금 쪽을 보이고, 숫자를 쓰고 Enter를 누르면 그 쪽으로 간다. */
function PageBox({ pageNumber, pageCount, ready, onGo }: { pageNumber: number; pageCount: number; ready: boolean; onGo: (pageNumber: number) => void }) {
  const [draft, setDraft] = useState(String(pageNumber));
  useEffect(() => setDraft(String(pageNumber)), [pageNumber]);
  const go = () => {
    const value = Number(draft);
    if (Number.isInteger(value) && value >= 1 && value <= pageCount) onGo(value);
    else setDraft(String(pageNumber));
  };
  return (
    <span className="head-box page-box" data-page={ready ? pageNumber : undefined} data-pages={ready ? pageCount : undefined}>
      <input
        aria-label="쪽 번호"
        inputMode="numeric"
        value={ready ? draft : ""}
        disabled={!ready}
        onChange={(event) => setDraft(event.target.value.replace(/\D/g, ""))}
        onKeyDown={(event) => {
          if (event.key === "Enter") go();
          if (event.key === "Escape") setDraft(String(pageNumber));
        }}
        onBlur={() => setDraft(String(pageNumber))}
      />
      <span className="page-count">/ {ready ? pageCount : "–"}</span>
    </span>
  );
}
