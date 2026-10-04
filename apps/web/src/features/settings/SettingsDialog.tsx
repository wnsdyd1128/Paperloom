/**
 * 설정 창 880×720 (U6, 시안 Settings): 기본 설정 · 화면 설정 · 프롬프트 개인화. Library 머리의 "설정"과 Reader 머리의
 * 설정 단추로 연다. 기본·화면 설정은 바꾸는 대로 저장하고, 프롬프트 개인화는 "저장"을 눌러야 저장한다. Esc나 닫기로 닫는다.
 * 저장은 이 PC의 Core에만 한다(A2). 화면 언어는 한국어로 고정이다(D4).
 */
import "./settings.css";

import { type ReactNode, useEffect, useRef, useState } from "react";

import { Icon, type IconName } from "../../shared/Icon";
import type { MathDelimiters } from "../../shared/mathCopy";
import { type Bridge, BridgeStatus } from "../chat/BridgeStatus";
import { approxPages, type ChatModelName, CHARS_PER_PAGE, DEFAULT_PREFERENCES, type Preferences, type PromptKey } from "./api";
import { usePreferences } from "./PreferencesProvider";

type Tab = "basic" | "display" | "prompt";
const TABS: readonly Readonly<{ tab: Tab; label: string }>[] = [
  { tab: "basic", label: "기본 설정" },
  { tab: "display", label: "화면 설정" },
  { tab: "prompt", label: "프롬프트 개인화" },
];
const MODELS: readonly Readonly<{ value: ChatModelName; note: string }>[] = [
  { value: "sonnet", note: "기본 · 균형" },
  { value: "opus", note: "긴 증명·복잡한 수식" },
  { value: "haiku", note: "빠른 번역·짧은 설명" },
];
const LIMITS: readonly Preferences["paper_text_chars"][] = [12_000, 40_000, 120_000, 300_000];
const DELIMITERS: readonly Readonly<{ value: MathDelimiters; example: string }>[] = [
  { value: "bracket", example: "\\( \\), \\[ \\]" },
  { value: "dollar", example: "$, $$" },
  { value: "none", example: "U_{tot}" },
];
const PROMPTS: readonly Readonly<{ key: PromptKey; label: string; tags: readonly string[]; placeholder: string }>[] = [
  { key: "system", label: "시스템 프롬프트", tags: ["전체"], placeholder: "예: 실시간 시스템과 멀티코어 캐시를 연구하는 대학원생입니다. 이론과 구현을 함께 살피게 도와주세요." },
  { key: "explain", label: "설명 프롬프트", tags: ["수식", "그림", "문단", "문장"], placeholder: "예: 수식과 알고리즘은 직관을 먼저 설명하고 코드 구현과 연결해 주세요." },
  { key: "translate", label: "번역 프롬프트", tags: ["번역"], placeholder: "예: 영문 용어와 약어는 그대로 두고, 처음 나올 때만 괄호로 뜻을 붙여 주세요." },
  { key: "summary", label: "요약 프롬프트", tags: ["요약"], placeholder: "예: 해결하려는 문제, 핵심 방법, 실험 설정, 결과와 한계를 차례로 정리해 주세요." },
];

type Props = Readonly<{ bridge: Bridge; onClose: () => void }>;

export function SettingsDialog({ bridge, onClose }: Props) {
  const { preferences, save } = usePreferences();
  const [tab, setTab] = useState<Tab>("basic");
  const [error, setError] = useState<string | null>(null);
  const ref = useRef<HTMLDivElement>(null);
  const onCloseRef = useRef(onClose);
  onCloseRef.current = onClose;

  // 열 때 한 번: 고른 탭에 포커스, 닫을 때 연 단추로 돌린다. (onClose는 그릴 때마다 새 함수라 ref로 읽는다)
  useEffect(() => {
    const opener = document.activeElement as HTMLElement | null;
    ref.current?.querySelector<HTMLElement>("[aria-selected='true']")?.focus();
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !event.isComposing) onCloseRef.current();
    };
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("keydown", onKey);
      opener?.focus?.();
    };
  }, []);

  /** 기본·화면 설정: 바꾸는 대로 저장한다 */
  async function change(next: Partial<Preferences>) {
    setError(null);
    try {
      await save(next);
    } catch {
      setError("설정을 저장하지 못했습니다. 백엔드 연결을 확인하세요.");
    }
  }

  return (
    <div className="settings-backdrop" onPointerDown={(event) => event.target === event.currentTarget && onClose()}>
      <div className="settings-dialog" role="dialog" aria-modal="true" aria-labelledby="settings-title" ref={ref}>
        <header className="settings-head">
          <h2 id="settings-title">설정</h2>
          <button type="button" className="btn btn-icon" aria-label="설정 닫기" title="닫기 (Esc)" onClick={onClose}>
            <Icon name="x" size={16} />
          </button>
        </header>
        <div className="settings-body">
          <nav className="settings-tabs" role="tablist" aria-label="설정 종류">
            {TABS.map((item) => (
              <button key={item.tab} type="button" role="tab" aria-selected={tab === item.tab} onClick={() => setTab(item.tab)}>
                {item.label}
              </button>
            ))}
          </nav>
          <div className="settings-panel" role="tabpanel" aria-label={TABS.find((item) => item.tab === tab)!.label}>
            {error && (
              <p className="status error" role="alert">
                {error}
              </p>
            )}
            {tab === "basic" && <BasicSettings preferences={preferences} bridge={bridge} onChange={(next) => void change(next)} />}
            {tab === "display" && <DisplaySettings preferences={preferences} onChange={(next) => void change(next)} />}
            {tab === "prompt" && <PromptSettings preferences={preferences} onSave={(prompts) => save({ prompts })} />}
          </div>
        </div>
      </div>
    </div>
  );
}

type SectionProps = Readonly<{ icon: IconName | "∃"; title: string; note: string; aside?: ReactNode; children?: ReactNode }>;

function Section({ icon, title, note, aside, children }: SectionProps) {
  return (
    <section className="settings-section">
      <span className="settings-icon" aria-hidden="true">
        {icon === "∃" ? "∃" : <Icon name={icon} size={16} />}
      </span>
      <div className="settings-section-head">
        <h3>{title}</h3>
        <p className="muted">{note}</p>
      </div>
      {aside && <div className="settings-aside">{aside}</div>}
      {children && <div className="settings-section-body">{children}</div>}
    </section>
  );
}

type ChangeProps = Readonly<{ preferences: Preferences; onChange: (next: Partial<Preferences>) => void }>;

function BasicSettings({ preferences, bridge, onChange }: ChangeProps & Readonly<{ bridge: Bridge }>) {
  return (
    <>
      <Section icon="languages" title="언어" note="화면 언어와 설명·번역 답변 언어입니다.">
        <div className="settings-fields">
          <label className="field">
            화면
            <select className="input" value="ko" disabled aria-label="화면 언어">
              <option value="ko">한국어</option>
            </select>
          </label>
          <label className="field">
            답변 · 번역
            <select className="input" value={preferences.answer_language} onChange={(event) => onChange({ answer_language: event.target.value as Preferences["answer_language"] })}>
              <option value="ko">한국어 (Korean)</option>
              <option value="en">English</option>
            </select>
          </label>
        </div>
      </Section>
      <Section icon="sparkles" title="AI 모델" note="이 PC의 Claude Code가 쓸 기본 모델입니다. 대화창에서 바꿀 수 있습니다.">
        <div className="settings-options" role="radiogroup" aria-label="기본 모델">
          {MODELS.map((model) => (
            <label key={model.value} className="radio">
              <input type="radio" name="default-model" checked={preferences.default_model === model.value} onChange={() => onChange({ default_model: model.value })} />
              <span className="dot" />
              <b>{model.value}</b>
              <span className="muted settings-option-note">{model.note}</span>
            </label>
          ))}
        </div>
      </Section>
      <Section icon="fileText" title="논문 본문 한도" note="대화 범위 '논문 본문'으로 보낼 글자 수입니다. 새 대화마다 이만큼 구독 사용량을 씁니다.">
        <div className="seg settings-limits" role="radiogroup" aria-label="논문 본문 한도">
          {LIMITS.map((limit) => (
            <label key={limit} className="seg-opt">
              <input type="radio" name="paper-text-chars" checked={preferences.paper_text_chars === limit} onChange={() => onChange({ paper_text_chars: limit })} />
              <span>{limit.toLocaleString("ko-KR")}자</span>
              <span className="settings-limit-pages">약 {approxPages(limit)}쪽</span>
            </label>
          ))}
        </div>
        <p className="muted settings-hint">
          쪽 수는 한 단 논문(쪽당 약 {CHARS_PER_PAGE.toLocaleString("ko-KR")}자) 기준 어림입니다. 두 단 논문은 그 절반쯤이 들어갑니다. 한도보다 짧은 논문은 전부 보냅니다.
        </p>
      </Section>
      <Section
        icon="chat"
        title="Claude Code 연결"
        note="이 PC에 로그인한 Claude Code를 구독 사용량으로 씁니다. API 키는 쓰지 않습니다."
        aside={
          bridge.health !== "checking" &&
          bridge.health?.ready && (
            <button type="button" className="btn btn-secondary" onClick={bridge.check}>
              상태 다시 확인
            </button>
          )
        }
      >
        <BridgeStatus bridge={bridge} />
      </Section>
    </>
  );
}

function DisplaySettings({ preferences, onChange }: ChangeProps) {
  const systemDark = typeof matchMedia === "function" && matchMedia("(prefers-color-scheme: dark)").matches;
  const dark = preferences.theme === "dark" || (preferences.theme === "system" && systemDark);
  return (
    <>
      <Section
        icon="info"
        title="다크 모드"
        note={preferences.theme === "system" ? "화면을 어두운 바탕으로 바꿉니다. PDF 쪽은 원래 색으로 둡니다. 지금은 운영체제 설정을 따릅니다." : "화면을 어두운 바탕으로 바꿉니다. PDF 쪽은 원래 색으로 둡니다."}
        aside={<Switch label="다크 모드" checked={dark} onChange={(on) => onChange({ theme: on ? "dark" : "light" })} />}
      >
        {preferences.theme !== "system" && (
          <button type="button" className="btn btn-ghost" onClick={() => onChange({ theme: "system" })}>
            운영체제 설정 따르기
          </button>
        )}
      </Section>
      <Section icon="fileText" title="글꼴 크기" note="설명·대화·번역 창의 글자 크기입니다.">
        <div className="settings-range">
          <span className="settings-range-value">{preferences.font_size}px</span>
          <input type="range" min={12} max={20} step={1} aria-label="글꼴 크기" value={preferences.font_size} onChange={(event) => onChange({ font_size: Number(event.target.value) })} />
        </div>
      </Section>
      <Section icon="∃" title="수식 구분 기호" note="답변의 수식이나 추정 표기를 복사할 때 쓰는 형식입니다.">
        <div className="settings-options" role="radiogroup" aria-label="수식 구분 기호">
          {DELIMITERS.map((delimiter) => (
            <label key={delimiter.value} className="radio">
              <input type="radio" name="math-delimiters" checked={preferences.math_delimiters === delimiter.value} onChange={() => onChange({ math_delimiters: delimiter.value })} />
              <span className="dot" />
              {delimiter.value}
              <code className="settings-option-note">{delimiter.example}</code>
            </label>
          ))}
        </div>
      </Section>
    </>
  );
}

function Switch({ label, checked, onChange }: Readonly<{ label: string; checked: boolean; onChange: (on: boolean) => void }>) {
  return <button type="button" role="switch" className="settings-switch" aria-checked={checked} aria-label={label} onClick={() => onChange(!checked)} />;
}

function PromptSettings({ preferences, onSave }: Readonly<{ preferences: Preferences; onSave: (prompts: Preferences["prompts"]) => Promise<void> }>) {
  const [draft, setDraft] = useState(preferences.prompts);
  const [state, setState] = useState<"idle" | "saving" | "saved" | "failed">("idle");
  const changed = PROMPTS.filter((item) => draft[item.key] !== preferences.prompts[item.key]).length;

  async function submit() {
    setState("saving");
    try {
      await onSave(draft);
      setState("saved");
    } catch {
      setState("failed");
    }
  }

  return (
    <div className="settings-prompts">
      <p className="muted">말투, 배경지식, 관심사를 적어 두면 Claude가 그에 맞춰 답합니다. 근거 다루기·근거 표시 같은 기본 규칙은 바뀌지 않습니다. 이 PC에만 저장됩니다.</p>
      {PROMPTS.map((item) => (
        <label key={item.key} className="field settings-prompt">
          <span className="settings-prompt-label">
            {item.label}
            {item.tags.map((tag) => (
              <span key={tag} className="tag tag-neutral">
                {tag}
              </span>
            ))}
          </span>
          <textarea
            className="input"
            rows={3}
            maxLength={2000}
            placeholder={item.placeholder}
            value={draft[item.key]}
            onChange={(event) => {
              setDraft({ ...draft, [item.key]: event.target.value });
              setState("idle");
            }}
          />
        </label>
      ))}
      <div className="settings-foot">
        <span className="muted" role="status">
          {state === "saved" ? "저장했습니다." : state === "failed" ? "저장하지 못했습니다. 백엔드 연결을 확인하세요." : `바뀐 항목 ${changed}개`}
        </span>
        <button type="button" className="btn btn-secondary" onClick={() => setDraft(DEFAULT_PREFERENCES.prompts)}>
          기본값으로
        </button>
        <button type="button" className="btn btn-primary" disabled={changed === 0 || state === "saving"} onClick={() => void submit()}>
          저장
        </button>
      </div>
    </div>
  );
}
