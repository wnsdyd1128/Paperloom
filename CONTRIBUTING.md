# 기여 안내

Paperloom에 관심을 가져 주셔서 고맙습니다. 버그 제보, 제안, 코드 기여 모두 환영합니다.

## 시작하기 전에

- 버그는 [Issues](https://github.com/wnsdyd1128/Paperloom/issues)에 재현 방법(PDF 종류, 화면, 브라우저)과 함께 남겨 주세요. 논문 PDF를 올릴 때는 공개해도 되는 파일인지 먼저 확인해 주세요.
- 큰 변경(새 기능, 데이터 구조 변경)은 이슈로 먼저 이야기한 뒤 시작하면 헛수고를 줄일 수 있습니다.
- 보안 문제는 공개 이슈 대신 [보안 정책](SECURITY.md)을 따라 알려 주세요.

## 개발 환경

필요한 것과 설치·실행 명령은 [README의 개발](README.md#개발) 절에 있습니다. 명령은 Windows PowerShell 기준입니다.

## 시험

PR을 보내기 전에 아래가 모두 통과해야 합니다. CI도 같은 검사를 돌립니다.

```powershell
backend\.venv\Scripts\python.exe -m pytest -q
cd apps\web
npm run typecheck
npx vitest run
npx playwright test
```

브라우저 시험은 실제 Claude Code 대신 가짜 Claude CLI(`tests/fixtures/fake_claude`)를 띄우므로 구독 사용량을 쓰지 않습니다.

## 지켜 주세요

- **유료 모델 API를 쓰지 않습니다.** 모델 SDK, API 키, 유료 API 호스트를 의존성이나 소스에 넣으면 `tests/contract/test_dependency_policy.py`가 실패합니다. AI 기능은 이 PC의 Claude Code(구독)로만 실행합니다.
- **시험용 PDF는 합성 파일만 씁니다.** 실제 논문은 저작권이 있어 저장소에 넣지 않습니다. `tests/fixtures/pdf-layout/generate_*.py`처럼 PDF를 만드는 스크립트와 그 결과를 함께 올려 주세요.
- **본문 추출 규칙을 바꾸면 `LAYOUT_VERSION`을 올립니다** (`backend/src/paperloom/documents/text_layout.py`). 서버가 시작할 때 저장된 논문을 다시 추출합니다.
- **줄 끝은 LF로 씁니다.** PDF는 `.gitattributes`에서 바이너리로 다룹니다.
- 고친 동작에는 그 동작을 확인하는 시험을 함께 넣어 주세요.

## 커밋 메시지

```text
type(scope): subject

본문: 무엇을 어떻게가 아니라 왜 바꿨는지
```

- `type`은 `feat`, `fix`, `refactor`, `test`, `docs`, `chore` 가운데 하나입니다. 호환을 깨는 변경은 `feat(api)!:`처럼 `!`를 붙입니다.
- 제목은 영어 명령형으로 50자 안에 쓰고 마침표를 찍지 않습니다.
- 본문은 한국어로 쓰고 한 줄을 72자 안에서 줄바꿈합니다.
- 커밋 하나에는 목적 하나만 담습니다.

## PR

- 무엇을 왜 바꿨는지, 어떻게 확인했는지 적어 주세요. 화면이 바뀌면 스크린샷을 붙여 주세요.
- CI가 통과해야 병합합니다.

## 릴리스 (관리자)

`v`로 시작하는 태그를 올리면 CI를 거친 뒤 Docker 이미지를 `ghcr.io/wnsdyd1128/paperloom`에 올리고 GitHub Release를 만듭니다(`.github/workflows/release.yml`).

```powershell
git tag v0.1.0
git push origin v0.1.0
```

## 라이선스

기여한 코드는 이 저장소의 [MIT 라이선스](LICENSE)로 배포됩니다.
