<div align="center">

<img src=".github/assets/logo.svg" alt="Paperloom 로고" width="160" height="160">

# 🧵 Paperloom

***읽다가 고른 문장을 바로 묻고 답의 근거를 논문에서 확인하는 개인용 논문 리더***

[![CI](https://github.com/wnsdyd1128/Paperloom/actions/workflows/ci.yml/badge.svg)](https://github.com/wnsdyd1128/Paperloom/actions/workflows/ci.yml)
[![release](https://img.shields.io/github/v/release/wnsdyd1128/Paperloom?label=release)](https://github.com/wnsdyd1128/Paperloom/releases)
[![Stars](https://img.shields.io/github/stars/wnsdyd1128/Paperloom?style=social)](https://github.com/wnsdyd1128/Paperloom/stargazers)
[![license](https://img.shields.io/github/license/wnsdyd1128/Paperloom)](LICENSE)
[![image](https://img.shields.io/badge/image-ghcr.io-2496ED?logo=docker&logoColor=white)](https://github.com/wnsdyd1128/Paperloom/pkgs/container/paperloom)

</div>

Paperloom은 논문 PDF를 읽으면서 고른 문장·그림·수식을 바로 설명·번역·질문하는 개인용 논문 리더입니다.
AI 기능은 이 PC에 로그인한 Claude Code(claude.ai 구독)로 실행하므로 API 키가 필요 없고 논문과 기록은 모두 내 PC에 저장됩니다.

- **근거가 보이는 답**: 답에 붙은 `근거 n`을 누르면 논문의 그 문단으로 바로 갑니다.
- **원문 옆 쪽 번역**: 원문 레이아웃을 그대로 둔 채 번역하고 원문과 번역을 문장 단위로 짝지어 강조합니다.
- **로컬 우선**: 서버는 `127.0.0.1`에서만 열리고 데이터는 Docker 볼륨에 남습니다.

## 목차

- [주요 기능](#주요-기능)
- [동작 방식](#동작-방식)
- [요구 사항](#요구-사항)
- [빠른 시작](#빠른-시작)
- [사용법](#사용법)
- [데이터와 개인정보](#데이터와-개인정보)
- [업데이트](#업데이트)
- [문제 해결](#문제-해결)
- [개발](#개발)
- [기여](#기여)
- [서드파티](#서드파티)
- [라이선스](#라이선스)

## 주요 기능

| 영역 | 할 수 있는 일 |
|---|---|
| 서재 | PDF 등록(여러 개, 화면에 끌어 놓기, 파일당 100 MiB·300쪽까지), 제목 검색, 태그 붙이기·이름 바꾸기·거르기, 본문 추출 상태 확인 |
| 리더 | 쪽 미리보기·목차(PDF에 목차가 없으면 본문 제목으로 만듦), 본문에서 찾기, 25–500% 확대·회전, 참고문헌 번호 `Ctrl`+클릭으로 이동하고 돌아오기, 논문 정보(저자·연도·DOI) 고치기 |
| 고른 부분에 묻기 | 글을 골라 설명·번역·AI에게 질문·하이라이트(3색)·주석. `Ctrl`+드래그로 그림·표·수식 영역을 골라 설명(수식은 LaTeX와 기호 설명)하거나 이미지로 복사 |
| Claude와 대화 | 논문 본문 또는 현재 쪽을 근거로 대화, 3줄 요약, 대화 기록·이름 바꾸기, 답마다 갈래 만들기, 모델(Sonnet·Opus·Haiku) 고르기 |
| 쪽 번역 | 레이아웃 유지·글로 읽기·별도 탭 세 가지 보기, 보는 쪽 바로 번역, 모든 쪽 번역, 원문 ↔ 번역 문장 강조. 수식·표·그림 속 글자·알고리즘 의사코드·머리글·참고문헌은 원문 그대로 두고 캡션은 번역 |
| 기록 | 하이라이트·주석 패널(검색, 색·종류 거르기, Markdown으로 모두 복사), 모든 논문의 대화를 모은 답변 화면 |
| 설정 | 답변·번역 언어(한국어·English), 기본 모델, 논문 본문 한도(약 4–100쪽), 다크 모드, 글꼴 크기, 수식 구분 기호, 설명·번역·요약 프롬프트 개인화 |

## 동작 방식

```text
브라우저 ──────────► Paperloom 서버 (Docker, 127.0.0.1:8000)
   │                  PDF 원본 · 추출한 본문 · 주석 · 대화 · 번역 (SQLite)
   │                        ▲
   │                        │ 근거 읽기 · 답 저장
   └─────────────► Claude Code 브리지 (이 PC, 127.0.0.1:8001)
                            │
                            ▼
                     claude CLI (구독 로그인) ──► Anthropic
```

- 서버는 PDF를 보관하고 글자 층이 있는 PDF는 본문을 추출해 검색·근거·번역에 씁니다.
- 브리지는 이 PC에서 `claude` CLI를 실행합니다. Docker 안에서는 Claude Code 로그인을 쓸 수 없어서 따로 켭니다. 브리지가 꺼져 있어도 읽기·검색·하이라이트·주석은 그대로 됩니다.

## 요구 사항

- Windows 10/11 (아래 명령은 PowerShell 기준)
- [Docker Desktop](https://www.docker.com/products/docker-desktop/)
- Python 3.13 (브리지용)
- Claude Code CLI와 claude.ai 구독 계정 로그인 (API 키 로그인은 브리지가 거부합니다)
- 브라우저: Microsoft Edge 또는 Chrome (Edge에서 시험)

## 빠른 시작

### 1. 서버 실행

```powershell
git clone <저장소 주소> Paperloom
cd Paperloom
docker compose -f ops/compose/compose.yaml up -d --build
```

브라우저에서 <http://127.0.0.1:8000>을 엽니다. 서버는 재부팅 뒤 Docker가 시작되면 자동으로 다시 올라옵니다.

빌드하지 않고 [릴리스 이미지](https://github.com/wnsdyd1128/Paperloom/pkgs/container/paperloom)를 받아 쓸 수도 있습니다. 위 Compose와 같은 데이터 볼륨을 쓰므로 둘 가운데 하나만 실행합니다.

```powershell
docker run -d --name paperloom --restart unless-stopped -p 127.0.0.1:8000:8000 -v paperloom_paperloom-data:/data ghcr.io/wnsdyd1128/paperloom:latest
```

### 2. Claude Code 로그인

Claude Code를 설치한 뒤 터미널에서 `claude`를 실행해 claude.ai 구독 계정으로 로그인합니다.

### 3. 브리지 설치 (처음 한 번)

```powershell
python -m venv backend\.venv
backend\.venv\Scripts\python.exe -m pip install --require-hashes -r backend\requirements-dev.lock
backend\.venv\Scripts\python.exe -m pip install --no-deps -e backend
```

### 4. 브리지 실행 (AI 기능을 쓰는 동안 켜 둡니다)

```powershell
backend\.venv\Scripts\python.exe -m paperloom.integrations.claude_code
```

화면 오른쪽 위 `Claude Code (이 PC)` 표시에서 `꺼짐`이 사라지면 준비가 끝났습니다.

## 사용법

### 논문 등록

서재에서 `PDF 등록`을 누르거나 PDF를 화면에 끌어다 놓습니다. 등록하면 본문을 추출하고 `검색 가능`이 되면 제목 검색·근거·번역을 쓸 수 있습니다. 스캔한 PDF처럼 글자 층이 없으면 `검색 불가`로 표시됩니다(OCR은 하지 않습니다).

### 고른 부분에 묻기

본문의 글을 고르면 메뉴가 뜹니다.

| 메뉴 | 키 | 하는 일 |
|---|---|---|
| 설명 | `E` | 고른 글을 앞뒤 문단과 함께 설명 |
| 번역 | `T` | 고른 글을 번역 (`원문 함께 보기`, `주석으로 저장`) |
| 하이라이트 | `H` | 마지막에 쓴 색으로 칠하기 (연한 주황·주황·회색) |
| 주석 | `C` | 메모 남기기 |
| AI에게 질문 | `Enter` | 고른 부분을 두고 직접 묻기 |

답은 원문 위 창에 열립니다. `이어서 물어보기…`로 계속 묻거나 `사이드바로 옮기기`로 대화창에 옮겨 이어 갑니다. 그림·표·수식은 `Ctrl`을 누른 채 끌어 영역으로 고릅니다. 위쪽 도구 막대의 `영역 설명`을 켜거나 그림을 눌러도 됩니다.

### Claude와 대화

오른쪽 사이드바의 `Claude와 대화`에서는 논문 전체를 놓고 묻습니다.

- 범위는 `논문 본문`(기본값, 설정의 본문 한도만큼 앞쪽부터)과 `현재 쪽` 가운데 고릅니다. 같은 대화에 한 번 보낸 본문은 다시 보내지 않아 사용량을 아낍니다.
- 답의 `근거 n`을 누르면 그 문단으로 이동합니다. `[12]` 같은 대괄호 번호는 논문의 참고문헌입니다.
- `여기서 갈래`를 누르면 그 답에서 대화를 갈라 다른 방향으로 이어 갑니다.

### 쪽 번역

위쪽 도구 막대의 `쪽 번역`을 켜면 지금 보는 쪽을 바로 번역해 저장합니다. 한 번 번역한 쪽은 다시 열어도 저장한 번역을 그대로 씁니다.

- `보기 방식`: `레이아웃 유지`(원문 자리에 번역), `글로 읽기`(문단 글로), `별도 탭`(다른 창·모니터에서 보기, 쪽 이동이 따라감)
- `모든 쪽` 시작·멈춤, `다시 번역`, `번역 모두 지우기`, `A−`/`A+` 글꼴 크기
- 번역 문장에 마우스를 올리면 원문 문장이, 원문 문장에 올리면 번역 문장이 강조됩니다.

### 단축키

| 키 | 동작 |
|---|---|
| `Ctrl`+`F` | 본문에서 찾기 (`Enter` 다음, `Shift`+`Enter` 이전, `Esc` 닫기) |
| `Ctrl`+`Shift`+`O` | 논문 목차 |
| `Ctrl`+`+` / `Ctrl`+`-` / `Ctrl`+`0` | 확대 / 축소 / 100% |
| `Ctrl`+휠 | 커서 자리를 기준으로 확대·축소 |
| `Ctrl`+드래그 | 그림·표·수식 영역 고르기 (`Ctrl`+`C`로 이미지 복사) |
| `Ctrl`+클릭 | 참고문헌 번호 `[25]`로 이동 (`Alt`+`←`로 돌아오기) |
| `E` `T` `H` `C` `Enter` | 선택 메뉴: 설명·번역·하이라이트·주석·질문 |
| `Esc` | 메뉴·창 닫기 |

## 데이터와 개인정보

- **저장 위치**: Docker 볼륨 `paperloom_paperloom-data`. `docker compose ... down -v`는 이 볼륨까지 지우므로 서재가 사라집니다.
- **접속 범위**: 서버와 브리지는 `127.0.0.1`에만 열려 같은 PC에서만 접속할 수 있습니다.
- **Anthropic으로 가는 것**: 질문과 그 근거(고른 글·앞뒤 문단, 범위에 따른 논문 본문, 고른 영역 이미지), 번역할 쪽의 문단. claude.ai 구독 사용량으로 처리되며 그 밖의 외부 서비스는 부르지 않습니다.
- **API 키**: 쓰지 않습니다. 환경 변수에 API 키가 있어도 브리지가 Claude Code에 넘기지 않습니다.

## 업데이트

```powershell
git pull
docker compose -f ops/compose/compose.yaml up -d --build
```

- 릴리스 이미지로 실행했다면 `docker pull ghcr.io/wnsdyd1128/paperloom:latest` 뒤 `docker rm -f paperloom`으로 컨테이너를 지우고 위 `docker run`을 다시 실행합니다. 데이터는 볼륨에 남습니다.
- 열려 있던 탭에 `새로고침` 띠가 뜨면 눌러 새 화면을 받습니다.
- 브리지도 껐다가 다시 켭니다.
- 본문 추출 방식이 바뀐 버전이면 서버가 시작할 때 등록한 논문을 한 번 다시 추출합니다. 그동안 쪽 번역은 잠시 기다리고 문단이 바뀐 쪽은 열 때 다시 번역합니다.

## 문제 해결

| 증상 | 해결 |
|---|---|
| `Claude Code 브리지가 꺼져 있습니다` | [브리지를 실행](#빠른-시작)한 뒤 `다시 확인` |
| `Claude Code에 로그인하지 않았습니다` | 터미널에서 `claude`를 실행해 구독 계정으로 로그인 |
| 본문 추출이 `검색 불가 · 글자 층 없음(스캔·이미지)` | 스캔 PDF는 글자를 읽지 못해 검색·근거·번역을 쓸 수 없습니다 |
| 화면이 예전 모습 그대로 | 다시 빌드하기 전에 열어 둔 탭을 새로고침 |
| 8000번 포트를 이미 쓰는 중 | `ops/compose/compose.yaml`의 포트를 바꾸고 브리지에는 `PAPERLOOM_URL` 환경 변수로 새 주소를 알려 줍니다 |

## 개발

필요한 것: Python 3.13, Node.js 22, (브라우저 시험용) Microsoft Edge.

```powershell
python -m venv backend\.venv
backend\.venv\Scripts\python.exe -m pip install --require-hashes -r backend\requirements-dev.lock
backend\.venv\Scripts\python.exe -m pip install --no-deps -e backend
cd apps\web; npm ci
```

| 할 일 | 명령 | 비고 |
|---|---|---|
| 서버 | `backend\.venv\Scripts\python.exe -m paperloom --config ops\config\local.yaml` | 데이터는 `var/` |
| 웹 개발 서버 | `apps\web`에서 `npm run dev` | <http://127.0.0.1:5173>, 서버는 따로 실행 |
| 백엔드 시험 | `backend\.venv\Scripts\python.exe -m pytest -q` | |
| 웹 시험 | `apps\web`에서 `npm run typecheck`, `npx vitest run` | |
| 브라우저 시험 | `apps\web`에서 `npx playwright test` | 8791·8794 포트에 서버와 가짜 Claude CLI를 띄움(구독 사용량 없음) |

```text
backend/src/paperloom/          서버: 문서·본문 추출, 원문 위치, 주석, 문맥, 답변, 대화, 번역, 설정
backend/src/paperloom/integrations/claude_code/   Claude Code 브리지
apps/web/                       웹앱 (React, PDF.js)
tests/                          단위·통합·계약 시험, 합성 PDF fixture, 가짜 Claude CLI
ops/                            Docker Compose와 실행 설정
```

유료 모델 API·SDK는 의존성에 넣지 않습니다. `tests/contract/test_dependency_policy.py`가 잠금 파일과 소스를 검사합니다.

푸시와 PR마다 [GitHub Actions](https://github.com/wnsdyd1128/Paperloom/actions)가 백엔드·웹 시험, Docker 이미지 빌드, Windows에서 Edge로 브라우저 시험을 돌립니다. `v*` 태그를 올리면 같은 검사를 거쳐 이미지를 `ghcr.io/wnsdyd1128/paperloom`에 올리고 GitHub Release를 만듭니다.

## 기여

버그 제보와 제안은 [Issues](https://github.com/wnsdyd1128/Paperloom/issues)에 남겨 주세요. 코드를 보내기 전에 [기여 안내](CONTRIBUTING.md)를 읽어 주세요. 보안 문제는 공개 이슈 대신 [보안 정책](SECURITY.md)의 방법으로 알려 주세요.

## 서드파티

- [Wanted Sans](https://github.com/wanteddev/wanted-sans): SIL Open Font License 1.1 (`apps/web/src/shared/theme/fonts/OFL.txt`)
- [PDF.js](https://mozilla.github.io/pdf.js/): Apache License 2.0

## 라이선스

[MIT](LICENSE) © 2026 Jun-Yong Park
