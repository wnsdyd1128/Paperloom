---
version: 1
slug: "apps-web-src-features-library-librarypage-tsx"
primary_target: "apps/web/src/features/library/LibraryPage.tsx"
related_targets: ["apps/web/src/features/library/LibraryShell.tsx"]
---

# 서재 (Library)

## Scope

- 화면: 서재(`/`), 같은 틀을 쓰는 답변 화면. 방문자 모드: Operate.
- 이번 차례: 앱 전체의 새 모양(공용 토큰·컴포넌트)을 정하고 서재에 먼저 입힌다. 리더·설정 창은 색·글꼴만 따라 바뀌고 배치는 다음 차례다.

## Audience and task

- 한국어권 대학원생·연구자. 이어 읽기, 쌓인 논문에서 찾기, 새 논문 올려 바로 읽기를 고르게 한다.
- 성공 기준(사용자 답): 논문이 서로 구분된다(첫 쪽 썸네일), 표가 빽빽하고 딱딱하지 않다, 인상이 낡지 않다. 어디까지 읽었는지 보이기는 읽은 위치를 서버가 저장하지 않아 이번 차례에 넣지 않았다(미정).
- 지킬 것: 기능·문구·시험이 기대는 표 구조(`.shelf-table`, `tr[data-paper-id]`, `td[data-status]`, 칸 차례).

## Direction contract

THESIS: 문헌 관리 도구의 표준 화면을 기준 제품(Linear·Notion·Readwise Reader·Zotero 7) 수준으로 만든다. 은유·컨셉 입히기, 색 머리띠, 카드 줄, 알약 버튼을 거부한다. 논문은 첫 쪽 썸네일과 저자·연도·쪽 수 한 줄로 구분된다.

OWN-WORLD: 흰 바탕과 한 단계 어두운 무채색 면, 1px 머리카락 선, 모서리 6px(칩·썸네일 4px, 창 10px). 주 단추와 고른 상태는 잉크색, 주홍(로고 색)은 근거·포커스·검색 표시에만 쓴다. 실패·삭제는 위험 색(`--color-danger`), 주의는 `--color-warn`으로 따로 가른다. Wanted Sans 한 벌, 굵기 400·500·600·700, 글자 크기 여섯 단계(11·12·13·14·16·20px, 11px은 딱지·단축키에만), 14px 본문. 밝은 판과 어두운 판 모두.

STORY: 들어오면 최근에 연 논문이 위에 있다. 썸네일과 제목으로 알아보고 제목을 눌러 연다. 문제 있는 논문만 상태가 색으로 드러난다. 태그로 거르고, PDF를 끌어다 놓아 올린다.

FIRST VIEWPORT: 52px 머리(로고·서재/답변/설정 탭 · Claude Code 상태 · 제목 검색 · PDF 등록 잉크 단추) 아래, 가운데 1120px 폭의 한 단. "서재 n편" 제목 줄, 그 아래 조용한 머리글의 표: 썸네일(48×64)과 제목·저자 줄, 본문 추출, 주석, 대화, 태그, 마지막 열람(짧은 시각, 오른쪽 맞춤). 줄 끝의 삭제는 따로 떨어진 칸에 두고 줄에 마우스를 올릴 때만 보인다. 주 동작은 제목(열기)과 머리의 PDF 등록.

FORM: 업계 표준(사용자가 결정 페이지의 후보를 모두 거절하고 기준 제품을 지정). seed:f3ff9a79e5fac058 — canon.

FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance

## Unresolved

- 읽은 위치 저장과 표시(스키마 변경이 필요하다).
- 리더·설정 창·답변 화면의 배치.
