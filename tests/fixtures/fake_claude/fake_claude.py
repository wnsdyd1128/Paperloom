"""시험용 가짜 Claude Code CLI (ADR 0003). 실제 모델을 부르지 않고 사용량을 쓰지 않는다.

브리지가 부르는 모양만 흉내 낸다: `--version`, `auth status`(JSON), `-p … --input-format stream-json` (stdin의 사용자
메시지 한 줄 → stream-json 사건들). 받은 인자·환경변수 이름·메시지를 FAKE_CLAUDE_LOG 파일에 한 줄씩 남긴다.

환경변수:
- FAKE_CLAUDE_AUTH: auth status의 authMethod (기본 claude.ai). "none"이면 로그인하지 않은 것으로 답한다.
- FAKE_CLAUDE_MODE: ok(기본) | error(결과가 오류) | crash(결과 없이 끝남)
- FAKE_CLAUDE_SLOW: 답하기 전에 기다릴 초 (동시 실행 확인용)
- 질문에 "(느리게)"가 있으면 답하기 전에 10초 기다린다 (E2E 중단 확인용, 브리지가 끝낸다)
- 질문에 "(문단)"이 있으면 답 끝에 문단 근거 [근거 1¶2]와 문단 범위 [근거 1¶3–4]를 붙인다 (E2E 문단 근거 확인용)
- 질문에 "(아티팩트)"가 있으면 답 끝에 아티팩트 여섯 종류(ARTIFACTS)를 붙인다 (E2E 아티팩트 창·격리 확인용)
- 질문에 "(코드 블록)"이 있으면 답 끝에 아티팩트 형식이 아닌 보통 코드 블록(FENCED)을 붙인다 (E2E 확인용)
- 질문에 "(원본 그림)"이 있으면 받은 "이 논문의 그림" 목록의 번호로 원본 그림을 넣은 아티팩트(figure_artifacts)를 붙인다
  (E2E 확인용)
- FAKE_CLAUDE_STEP: 글 조각 사이에 기다릴 초 (생성되는 대로 전달되는지 확인용)
- FAKE_CLAUDE_REFRESH_RACE: 작업 폴더에서 처음 이만큼의 실행(프로세스를 가로질러 센다)은 실제 CLI처럼 로그인 토큰 갱신이 겹친
  API 오류(모델 <synthetic>, 오류 결과)로 끝난다 (2026-10-13 기록의 모양)
- 쪽 번역(U7, 글에 "## 번역할 쪽 (JSON)"): 문장 id마다 "[번역] 원문"을 JSON으로 답한다. FAKE_CLAUDE_TRANSLATION이
  missing이면 여러 문장인 첫 문단의 둘째 문장(없으면 마지막 문장)을 빼고, text면 JSON이 아닌 글로, joined면 코드 블록으로 감싸고 두 문장 이상인 문단의 둘째 문장을
  첫 문장 번역("[번역·합침] …")에 합친다(뒤 id는 빈 글). stutter면 그 둘째 문장 id를 값 없이 한 번 더 써 JSON 문법을 깬다
  (2026-10-16 사용자 논문에서 본 모양 `"13.3","13.3":"…"`). 받은 쪽 글은 작업 폴더에 대화 ID로 남긴다.
- 고쳐 달라는 글("## 앞 답을 읽지 못했습니다", --resume): 그 대화에서 받은 쪽 글로 다시 답한다. 모드 끝이 "-once"면
  (missing-once 등) 처음 답만 그 모드로 틀리고 다시 답할 때는 맞게 답한다. 아니면 다시 답해도 같은 모드다.
"""

import contextlib
import json
import os
import re
import sys
import time
import uuid

WATCHED_ENV = ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_BASE_URL", "CLAUDE_CODE_OAUTH_TOKEN", "CLAUDE_CODE_USE_BEDROCK")
STALE_LOCK_SECONDS = 2  # 기록 잠금 파일이 이보다 오래되었으면 잡은 채 죽은 차례의 것이다
REFRESH_RACE = (
    "Failed to refresh OAuth token: another Claude Code process is refreshing it or exited mid-refresh. This is usually transient; "
    "retry in a minute, and if it persists close other Claude Code processes or sign in again"
)


# 시스템 프롬프트(cli.SYSTEM_PROMPT)의 아티팩트 형식. HTML은 격리를 스스로 재어 글로 적는다: 스크립트가 돌았는지, 바깥 주소
# 요청(fetch)·저장소·바깥 창(Paperloom) DOM이 막혔는지. fetch는 no-cors라 CORS로는 실패하지 않고 CSP만 막는다.
# React는 눌러 바뀌는 상태로 실행을 보인다.
ARTIFACTS = """격리 시험 페이지입니다.

```artifact type="html" title="격리 시험"
<!doctype html>
<html><head><title>격리 시험</title></head>
<body>
<p id="script">스크립트 전</p><p id="network">요청 전</p><p id="storage">저장소 전</p><p id="parent">바깥 창 전</p>
<script>
document.getElementById("script").textContent = "스크립트 실행됨";
fetch("http://127.0.0.1:8791/api/v1/health", { mode: "no-cors" }).then(
  function () { document.getElementById("network").textContent = "바깥 요청 열림"; },
  function () { document.getElementById("network").textContent = "바깥 요청 막힘"; });
try { localStorage.setItem("paperloom", "1"); document.getElementById("storage").textContent = "저장소 열림"; }
catch (error) { document.getElementById("storage").textContent = "저장소 막힘"; }
try { void parent.document.title; document.getElementById("parent").textContent = "바깥 창 열림"; }
catch (error) { document.getElementById("parent").textContent = "바깥 창 막힘"; }
</script>
</body></html>
```

```artifact type="svg" title="네모 그림"
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 120 40"><rect x="2" y="2" width="116" height="36" fill="none" stroke="black"/><text x="12" y="26">SVG 그림</text></svg>
```

```artifact type="mermaid" title="읽기 흐름"
graph LR
  A[논문 읽기] --> B[근거 고르기]
```

```artifact type="react" title="눌러 세기"
import { useState } from "react";

export default function Counter(): JSX.Element {
  const [count, setCount] = useState(0);
  return <button onClick={() => setCount(count + 1)}>눌린 수 {count}</button>;
}
```

````artifact type="markdown" title="정리 문서"
# 정리

- 첫째 줄
- 둘째 줄

```python
print("문서 안 코드")
```
````

```artifact type="code" language="python" title="합 계산"
print(sum([1, 2]))
```

아티팩트 여섯 개를 만들었습니다."""

# 아티팩트 형식 없이 보통 코드 블록으로 준 답 (2026-11-08 Sonnet이 "claude artifact로 만들어줘"에 준 모양). 웹은 완전한 HTML
# 문서·svg·mermaid 블록만 아티팩트로 열고, 조각 HTML·다른 언어는 코드 블록으로 둔다.
FENCED = """바로 쓸 수 있는 단일 HTML 코드로 드립니다.

```html
<!DOCTYPE html>
<html lang="ko">
<head><meta charset="utf-8"><title>발표 예상 질문</title></head>
<body><p id="script">스크립트 전</p><script>document.getElementById("script").textContent = "스크립트 실행됨";</script></body>
</html>
```

```svg
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 120 40"><text x="12" y="26">블록 그림</text></svg>
```

```mermaid
graph LR
  A[질문] --> B[답]
```

```html
<div class="card">조각 HTML</div>
```

```python
print("코드는 코드로")
```"""


def figure_artifacts(text: str) -> str:
    """받은 "이 논문의 그림" 목록의 번호로 원본 그림을 넣은 HTML·문서 아티팩트. 목록에 없는 번호 99도 하나 넣는다."""
    labels = re.findall(r"^- paperloom-figure:(\w+) ·", text, re.MULTILINE)
    images = "".join(f'<img class="figure" src="paperloom-figure:{label}" alt="Figure {label}">' for label in labels)
    markdown = "\n\n".join(f"![Figure {label}](paperloom-figure:{label})" for label in labels)
    return (
        '```artifact type="html" title="그림 슬라이드"\n'
        f'<!DOCTYPE html><html><body><h1>원본 그림</h1>{images}<img id="missing" src="paperloom-figure:99" alt="Figure 99"></body></html>\n'
        "```\n\n"
        '````artifact type="markdown" title="그림 문서"\n'
        f"# 그림 문서\n\n{markdown}\n"
        "````"
    )


def emit(event: dict) -> None:
    sys.stdout.write(json.dumps(event, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stdin.reconfigure(encoding="utf-8")
    args = sys.argv[1:]
    if args == ["--version"]:
        print("9.9.9 (Claude Code, fake)")
        return 0
    if args[:2] == ["auth", "status"]:
        method = os.environ.get("FAKE_CLAUDE_AUTH", "claude.ai")
        print(json.dumps({"loggedIn": method != "none", "authMethod": method, "subscriptionType": "pro", "email": "fake@example.com"}))
        return 0 if method != "none" else 1
    message = json.loads(sys.stdin.readline())
    # 갈래(--fork-session)는 이어받은 대화의 새 ID다
    session = args[args.index("--resume") + 1] if "--resume" in args and "--fork-session" not in args else str(uuid.uuid4())
    if log := os.environ.get("FAKE_CLAUDE_LOG"):
        record = {"args": args, "env": sorted(key for key in WATCHED_ENV if key in os.environ), "message": message, "cwd": os.getcwd(), "session": session}
        if "--system-prompt-file" in args:  # 설정의 개인화가 시스템 프롬프트에 붙는지 본다 (U6)
            with open(args[args.index("--system-prompt-file") + 1], encoding="utf-8") as prompt:
                record["system_prompt"] = prompt.read()
        # 쪽 번역 묶음처럼 여러 차례가 동시에 쓰면 줄이 섞인다(Windows의 O_APPEND는 프로세스 사이에 원자적이지 않다).
        # 잠금 파일을 만든 차례만 쓴다
        lock = log + ".lock"
        deadline = time.monotonic() + 5
        locked = False
        while not locked:
            try:
                os.close(os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY))
                locked = True
            except (FileExistsError, PermissionError):  # Windows: 다른 차례가 지우는 중인 잠금 파일은 PermissionError다
                # 잠금은 몇 ms만 잡는다. 오래된 잠금은 잡은 채 끝난 차례(중단 시험이 끝낸 프로세스)의 것이라 지운다
                # (2026-10-17: 남은 잠금 때문에 그 뒤 차례마다 5초씩 기다려 E2E 번역 시험이 시간을 넘겼다)
                with contextlib.suppress(OSError):
                    if time.time() - os.path.getmtime(lock) > STALE_LOCK_SECONDS:
                        os.remove(lock)
                        continue
                if time.monotonic() > deadline:
                    break
                time.sleep(0.01)
        try:
            with open(log, "a", encoding="utf-8") as file:
                file.write(json.dumps(record, ensure_ascii=False) + "\n")
        finally:
            # 잡은 잠금만 지운다(못 잡았으면 다른 차례의 것이다). 지우는 중인 파일은 Windows에서 PermissionError다
            if locked:
                with contextlib.suppress(FileNotFoundError, PermissionError):
                    os.remove(lock)
    mode = os.environ.get("FAKE_CLAUDE_MODE", "ok")
    emit({"type": "system", "subtype": "init", "session_id": session, "model": "fake", "apiKeySource": "none", "tools": [], "mcp_servers": []})
    if lost_refresh_race(int(os.environ.get("FAKE_CLAUDE_REFRESH_RACE", "0"))):
        emit({"type": "assistant", "uuid": str(uuid.uuid4()), "session_id": session, "error": "server_error",
              "message": {"role": "assistant", "model": "<synthetic>", "content": [{"type": "text", "text": REFRESH_RACE}]}})
        emit({"type": "result", "subtype": "success", "is_error": True, "result": REFRESH_RACE, "session_id": session})
        return 1
    if mode == "crash":
        sys.stderr.write("fake crash\n")
        return 1
    content = message["message"]["content"]
    texts = [block["text"] for block in content if block["type"] == "text"]
    images = sum(1 for block in content if block["type"] == "image")
    question = texts[-1].strip().splitlines()[-1][:60]
    if "## 번역할 쪽 (JSON)" in texts[-1]:
        with open(f"fake-translation-{session}.txt", "w", encoding="utf-8") as saved:
            saved.write(texts[-1])
        return translate(texts[-1], session)
    if "## 앞 답을 읽지 못했습니다" in texts[-1]:
        with open(f"fake-translation-{session}.txt", encoding="utf-8") as saved:
            return translate(saved.read(), session, repair=True)
    answer = (
        f"**가짜 답**입니다. 근거를 봤고 [근거 1] 이미지 {images}개를 받았습니다. 참고문헌 [12]는 근거가 아닙니다.\n\n"
        f"- 근거 글 {len(texts)}개\n- 수식 $C_i \\le T_i$\n- 식 번호 $S = A_i \\tag{{1.4}}$\n\n질문: {question}"
    )
    if "(문단)" in texts[-1]:  # 문단 근거 확인용: 근거 1의 둘째 문단을 짚는다
        answer += "\n\n둘째 문단을 봤습니다 [근거 1¶2]. 이어진 문단은 [근거 1¶3–4]입니다."
    if "(아티팩트)" in texts[-1]:
        answer += "\n\n" + ARTIFACTS
    if "(코드 블록)" in texts[-1]:
        answer += "\n\n" + FENCED
    if "(원본 그림)" in texts[-1]:
        answer += "\n\n" + figure_artifacts(texts[-1])
    if mode == "error":
        emit({"type": "result", "subtype": "success", "is_error": True, "result": "Claude AI usage limit reached (fake)", "session_id": session})
        return 1
    time.sleep(10 if "(느리게)" in texts[-1] else float(os.environ.get("FAKE_CLAUDE_SLOW", "0")))
    for start in range(0, len(answer), 8):
        emit({"type": "stream_event", "event": {"type": "content_block_delta", "delta": {"type": "text_delta", "text": answer[start:start + 8]}}})
        time.sleep(float(os.environ.get("FAKE_CLAUDE_STEP", "0")))
    # 실제 CLI처럼 답 메시지(대화 기록의 항목 ID uuid)를 낸다. 브리지는 이것을 갈라질 자리로 남긴다(--resume-session-at)
    emit({"type": "assistant", "uuid": str(uuid.uuid4()), "session_id": session, "message": {"role": "assistant", "content": [{"type": "text", "text": answer}]}})
    # 실제 CLI의 result처럼 토큰 사용량과 모델별 창 크기를 준다(값은 고정: 3 + 1200 + 800 + 50 = 2,053)
    usage = {"input_tokens": 3, "cache_creation_input_tokens": 1200, "cache_read_input_tokens": 800, "output_tokens": 50}
    model_usage = {"claude-fake": {"inputTokens": 3, "outputTokens": 50, "contextWindow": 200000}}
    emit({"type": "result", "subtype": "success", "is_error": False, "result": answer, "session_id": session, "usage": usage, "modelUsage": model_usage})
    return 0


def lost_refresh_race(count: int) -> bool:
    """작업 폴더의 처음 count번 실행인가. 표시 파일을 O_EXCL로 하나씩 차지해 동시에 뜬 프로세스끼리도 정확히 count번만 센다."""
    for index in range(count):
        try:
            os.close(os.open(f"fake-refresh-race-{index}", os.O_CREAT | os.O_EXCL | os.O_WRONLY))
            return True
        except FileExistsError:
            continue
    return False


def translate(text: str, session: str, repair: bool = False) -> int:
    """쪽 번역 차례: 문장 id마다 번역을 담은 JSON 객체 하나로 답한다. repair는 고쳐 달라는 글에 다시 답하는 차례다."""
    time.sleep(float(os.environ.get("FAKE_CLAUDE_SLOW", "0")))
    payload = json.loads(text.split("```json")[1].split("```")[0])
    mode = os.environ.get("FAKE_CLAUDE_TRANSLATION", "ok")
    if mode.endswith("-once"):
        mode = "ok" if repair else mode.removesuffix("-once")
    answer = {}
    for paragraph in payload["paragraphs"]:
        sentences = paragraph["sentences"]
        for index, sentence in enumerate(sentences):
            answer[sentence["id"]] = f"[번역] {sentence['text']}"
        if mode == "joined" and len(sentences) > 1:
            answer[sentences[0]["id"]] = "[번역·합침] " + " ".join(sentence["text"] for sentence in sentences[:2])
            answer[sentences[1]["id"]] = ""
    several = next((paragraph["sentences"] for paragraph in payload["paragraphs"] if len(paragraph["sentences"]) > 1), None)
    second = several[1]["id"] if several else list(answer)[-1]
    if mode == "missing":
        answer.pop(second)
    result = "번역했습니다." if mode == "text" else json.dumps(answer, ensure_ascii=False)
    if mode == "stutter":
        result = result.replace(f'"{second}": ', f'"{second}", "{second}": ', 1)
    if mode == "joined":
        result = f"```json\n{result}\n```"
    emit({"type": "stream_event", "event": {"type": "content_block_delta", "delta": {"type": "text_delta", "text": result}}})
    emit({"type": "assistant", "uuid": str(uuid.uuid4()), "session_id": session, "message": {"role": "assistant", "content": [{"type": "text", "text": result}]}})
    # 실제 CLI의 result처럼 모델 호출 시간과 토큰 사용량을 준다(값은 고정)
    usage = {"input_tokens": 3, "cache_creation_input_tokens": 1200, "cache_read_input_tokens": 800, "output_tokens": 50}
    emit({"type": "result", "subtype": "success", "is_error": False, "result": result, "session_id": session, "duration_api_ms": 1234, "usage": usage})
    return 0


if __name__ == "__main__":
    sys.exit(main())
