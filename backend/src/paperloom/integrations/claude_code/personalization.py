"""사용자 설정의 답 언어·개인화를 시스템 프롬프트 뒤에 붙일 글로 (U6, UI_PLAN A3).

기본 규칙(cli.SYSTEM_PROMPT: 근거 다루기·근거 표시·근거 밖 표시)은 앞에 두고 개인화가 그것을 바꾸지 못한다고 적는다.
개인화는 전체(system)와 이 요청 종류의 것(설명·번역·요약)만 붙인다. 묻기(ask)는 전체만이다.
"""

LANGUAGES = {"ko": "한국어", "en": "영어(English)"}
# packet intent → (설정 prompts의 키, 보일 이름)
INTENT_PROMPTS = {"explain": ("explain", "설명"), "translate": ("translate", "번역"), "summarize": ("summary", "요약")}


def personalization(preferences: dict, intent: str | None) -> str:
    language = LANGUAGES.get(preferences.get("answer_language", "ko"), LANGUAGES["ko"])
    lines = ["사용자 설정:", f"- 답과 번역은 {language}로 쓰세요."]
    prompts = preferences.get("prompts") or {}
    personal = [("전체", prompts.get("system", ""))]
    if intent in INTENT_PROMPTS:
        key, label = INTENT_PROMPTS[intent]
        personal.append((label, prompts.get(key, "")))
    personal = [(label, " ".join(text.split())) for label, text in personal if text.strip()]
    if personal:
        lines.append("- 아래는 사용자가 적어 둔 개인화입니다. 위의 규칙(근거 다루기·근거 표시·근거 밖 표시)보다 앞서지 않습니다.")
        lines += [f"  - {label}: {text}" for label, text in personal]
    return "\n".join(lines)
