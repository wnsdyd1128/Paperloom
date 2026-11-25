---
name: Paperloom
description: 읽다가 고른 문장을 바로 묻고 답의 근거를 논문에서 확인하는 개인용 논문 리더
colors:
  accent: "#ec3013"
  accent-dark: "#ff563c"
  accent-100: "#fff2ef"
  accent-200: "#ffe0d9"
  accent-300: "#ffc4b8"
  accent-400: "#ff9783"
  accent-500: "#ff563c"
  accent-600: "#dd2b0f"
  accent-700: "#ae1800"
  accent-800: "#7c1405"
  accent-900: "#4d170e"
  bg: "#ffffff"
  bg-dark: "#171716"
  surface: "#f6f6f4"
  surface-dark: "#1f1f1e"
  raised: "#ffffff"
  raised-dark: "#2a2a28"
  text: "#1c1b19"
  text-dark: "#ecece9"
  divider: "color-mix(in srgb, #1c1b19 12%, transparent)"
  divider-dark: "color-mix(in srgb, #ecece9 13%, transparent)"
  border-strong: "color-mix(in srgb, #1c1b19 22%, transparent)"
  border-strong-dark: "color-mix(in srgb, #ecece9 24%, transparent)"
  neutral-100: "#f6f6f4"
  neutral-200: "#eeeeeb"
  neutral-300: "#e2e2de"
  neutral-400: "#c8c8c3"
  neutral-500: "#a1a19b"
  neutral-600: "#73736d"
  neutral-700: "#5c5c57"
  neutral-800: "#3f3f3b"
  neutral-900: "#272725"
  ok: "#1a7f37"
  ok-dark: "#4ac26b"
  warn: "#b25e09"
  warn-dark: "#e0a13c"
  danger: "#ae1800"
  danger-dark: "#ff9783"
  reader-stage: "#e2e2de"
  reader-stage-dark: "#0f0f0e"
  mark-selection: "rgb(236 48 19 / 18%)"
  mark-note: "rgb(255 151 131 / 28%)"
  mark-focus: "rgb(236 48 19 / 30%)"
  mark-c1: "#ffe0d9"
  mark-c2: "#ff9783"
  mark-c3: "#d7d3d3"
typography:
  headline:
    fontFamily: "Wanted Sans Variable, Wanted Sans, system-ui, sans-serif"
    fontSize: "20px"
    fontWeight: 700
    lineHeight: 1.3
    letterSpacing: "-0.01em"
  title:
    fontFamily: "Wanted Sans Variable, Wanted Sans, system-ui, sans-serif"
    fontSize: "16px"
    fontWeight: 700
    lineHeight: 1.12
    letterSpacing: "-0.015em"
  body:
    fontFamily: "Wanted Sans Variable, Wanted Sans, system-ui, sans-serif"
    fontSize: "14px"
    fontWeight: 400
    lineHeight: 1.55
  body-strong:
    fontFamily: "Wanted Sans Variable, Wanted Sans, system-ui, sans-serif"
    fontSize: "14px"
    fontWeight: 600
    lineHeight: 1.4
  control:
    fontFamily: "Wanted Sans Variable, Wanted Sans, system-ui, sans-serif"
    fontSize: "13px"
    fontWeight: 500
    lineHeight: 1.2
  label:
    fontFamily: "Wanted Sans Variable, Wanted Sans, system-ui, sans-serif"
    fontSize: "12px"
    fontWeight: 400
    lineHeight: 1.4
  micro:
    fontFamily: "Wanted Sans Variable, Wanted Sans, system-ui, sans-serif"
    fontSize: "11px"
    fontWeight: 400
  quote:
    fontFamily: "Times New Roman, Times, serif"
    fontSize: "13px"
    fontWeight: 400
  mono:
    fontFamily: "ui-monospace, Menlo, Consolas, monospace"
    fontSize: "12px"
    fontWeight: 400
rounded:
  sm: "4px"
  md: "6px"
  lg: "10px"
  pill: "999px"
spacing:
  "1": "4px"
  "2": "8px"
  "3": "12px"
  "4": "16px"
  "6": "24px"
  "8": "32px"
components:
  button:
    backgroundColor: "transparent"
    textColor: "{colors.text}"
    typography: "{typography.body-strong}"
    rounded: "{rounded.md}"
    padding: "8px 14.4px"
  button-primary:
    backgroundColor: "{colors.text}"
    textColor: "{colors.bg}"
    rounded: "{rounded.md}"
    padding: "8px 14.4px"
  button-primary-hover:
    backgroundColor: "color-mix(in srgb, #1c1b19 86%, #ffffff)"
  button-secondary:
    backgroundColor: "transparent"
    textColor: "{colors.text}"
    rounded: "{rounded.md}"
    padding: "8px 14.4px"
  button-ghost:
    backgroundColor: "transparent"
    textColor: "{colors.neutral-700}"
    rounded: "{rounded.md}"
    padding: "8px 8px"
  button-icon:
    backgroundColor: "transparent"
    textColor: "{colors.text}"
    rounded: "{rounded.md}"
    size: "36px"
  input:
    backgroundColor: "{colors.bg}"
    textColor: "{colors.text}"
    typography: "{typography.body}"
    rounded: "{rounded.md}"
    padding: "6px 10px"
    height: "36px"
  search-field:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.text}"
    typography: "{typography.control}"
    rounded: "{rounded.md}"
    padding: "0 10px"
    height: "32px"
    width: "280px"
  nav-tab:
    backgroundColor: "transparent"
    textColor: "{colors.neutral-700}"
    typography: "{typography.control}"
    rounded: "{rounded.md}"
    padding: "6px 10px"
  nav-tab-active:
    backgroundColor: "color-mix(in srgb, #1c1b19 8%, transparent)"
    textColor: "{colors.text}"
  tag-chip:
    backgroundColor: "{colors.neutral-200}"
    textColor: "{colors.neutral-800}"
    typography: "{typography.label}"
    rounded: "{rounded.sm}"
    padding: "2px 8px"
  tag-chip-hover:
    backgroundColor: "{colors.neutral-300}"
  tag-chip-on:
    backgroundColor: "{colors.text}"
    textColor: "{colors.bg}"
  segmented:
    backgroundColor: "{colors.neutral-200}"
    textColor: "{colors.neutral-700}"
    rounded: "{rounded.md}"
    padding: "2px"
  segmented-option-on:
    backgroundColor: "{colors.raised}"
    textColor: "{colors.text}"
    rounded: "{rounded.sm}"
    padding: "5px 10px"
  table-header:
    backgroundColor: "transparent"
    textColor: "{colors.neutral-600}"
    typography: "{typography.label}"
    padding: "8px 10px"
  table-cell:
    backgroundColor: "transparent"
    textColor: "{colors.text}"
    padding: "10px"
  paper-thumb:
    backgroundColor: "{colors.surface}"
    rounded: "{rounded.sm}"
    width: "48px"
    height: "64px"
  popover:
    backgroundColor: "{colors.raised}"
    textColor: "{colors.text}"
    typography: "{typography.control}"
    rounded: "{rounded.lg}"
    padding: "4px 0"
    width: "264px"
  dialog:
    backgroundColor: "{colors.bg}"
    textColor: "{colors.text}"
    rounded: "{rounded.lg}"
  switch:
    backgroundColor: "{colors.neutral-400}"
    rounded: "{rounded.pill}"
    width: "40px"
    height: "22px"
  switch-on:
    backgroundColor: "{colors.text}"
  kbd:
    backgroundColor: "transparent"
    textColor: "{colors.neutral-700}"
    rounded: "{rounded.sm}"
    padding: "0 5px"
---

# Design System: Paperloom

## Overview

**Creative North Star: "기준 제품의 표준 화면"**

Paperloom의 화면은 무언가를 닮으려 하지 않는다. 문헌 관리 도구와 리더의 표준 화면을 Linear·Notion·Readwise Reader·Zotero 7과 나란히 놓일 수준으로 만든 것이 전부다. 도서관 라벨이나 노선도 같은 은유를 화면에 입히지 않고, 타이포그래피·여백·정렬만으로 만든다. 그래서 이 문서의 북극성은 은유가 아니라 기준이다.

바탕은 흰색, 그 위에 한 단계 어두운 무채색 면, 구분은 1px 선이다. 주 단추와 고른 상태는 잉크색(글자색)으로 드러낸다. 로고 색인 주홍은 근거와 "지금 가리키는 자리"에만 쓴다. 글꼴은 Wanted Sans 한 벌이고 본문은 14px이다. 밝은 판과 어두운 판이 같은 토큰 이름으로 함께 배포된다. 어두운 판은 단계를 뒤집고 그림자 대신 가는 테두리로 면을 띄운다.

PDF 쪽과 그 위의 표시(선택·하이라이트·주석)는 이 시스템의 바깥이다. 쪽은 원문 색 그대로이고 `--mark-*` 값은 테마와 상관없이 같다.

**Key Characteristics:**
- 흰 바탕, 무채색 면 한 단계, 1px 구분선
- 주 단추·고른 상태는 잉크색, 주홍은 근거·포커스·검색 표시
- Wanted Sans 한 벌, 굵기 400·500·600·700, 크기 11·12·13·14·16·20px
- 모서리 6px(조작 요소) / 4px(칩·썸네일) / 10px(떠 있는 면·창)
- 문제가 있는 줄만 색으로 드러나고, 정상 상태는 조용하다
- 줄의 보조 동작(삭제·태그 붙이기)은 마우스를 올리거나 포커스가 올 때만 보인다
- 밝은 판·어두운 판 동시 지원, PDF 쪽은 테마 밖

## Colors

거의 무채색인 팔레트에 주홍 하나가 얹힌다. 무채색은 아주 약하게 따뜻한 쪽(`#f6f6f4`, `#1c1b19`)이다.

### Primary
- **주홍** (`accent`, 어두운 판 `accent-dark`): 로고 색. 근거 번호·쪽 링크의 밑줄(`.cite-chip`), 키보드 포커스 테두리, 입력 칸의 커서와 포커스 고리, 글 선택 바탕(30%), 검색에 걸린 글자 표시(25%), 끌어 놓는 동안의 창 점선 테두리에 쓴다. 단추나 고른 상태의 바탕으로 쓰지 않는다.
- **주홍 단계** (`accent-100`–`accent-900`): 근거 글의 색(`accent-700`)과 근거 위 마우스 바탕(`accent-100`)에 쓰인다. 어두운 판에서는 단계가 뒤집힌다(값은 `.impeccable/design.json`의 `colorMeta`).

### Neutral
- **종이 흰색** (`bg`): 화면 바탕, 입력 칸 바탕, 주 단추의 글자.
- **한 단계 어두운 면** (`surface`, `neutral-100`과 같은 값): 검색 칸, 설정 창의 왼쪽 탭 단, 고른 설정 항목, 썸네일이 뜨기 전 자리.
- **떠 있는 면** (`raised`): 펼친 메뉴와 구간 선택의 고른 칸. 밝은 판에서는 바탕과 같은 흰색이고, 어두운 판에서만 한 단계 밝다.
- **잉크** (`text`): 본문, 주 단추의 바탕, 고른 태그·거르기 칩의 바탕, 켜진 스위치, 체크 상자·라디오의 고른 색.
- **구분선** (`divider`): 잉크 12% 투명. 머리 아래 선, 표의 줄 선, 메뉴 테두리.
- **모양 테두리** (`border-strong`): 잉크 22%. 입력 칸·테두리 단추·썸네일처럼 테두리가 곧 모양인 곳.
- **무채색 단계** (`neutral-200`–`neutral-900`): 칩 바탕(200, 마우스를 올리면 300), 스크롤 막대·꺼진 스위치(400), 흐린 아이콘(500), 메타 글·표 머리글(600), 보조 글·탭의 기본 글자(700), 칩 글자(800).

### 상태 색
- **확인** (`ok`): 브리지 연결 점, 올리기 성공.
- **주의** (`warn`): 본문 추출 "일부", 브리지 꺼짐. 꺼짐은 오류가 아니라 AI를 못 쓰는 상태라서 주의 색이다.
- **위험** (`danger`): 본문 추출 실패의 글과 점, 삭제 단추에 마우스를 올렸을 때(12% 바탕 + 글자). 값은 주홍의 깊은 단계(`accent-700`)와 같아서 색상이 아니라 명도로 주홍과 갈린다.

### PDF 표시
- `mark-selection`, `mark-note`, `mark-focus`, `mark-c1`·`mark-c2`·`mark-c3`: 쪽 위의 선택·주석·초점·하이라이트 3색. 쪽이 밝은 원래 색이므로 어두운 판에서도 바꾸지 않는다. 화면의 색 견본도 같은 값을 쓴다.
- `reader-stage`: PDF 쪽 뒤의 바탕(밝은 판 `neutral-300`, 어두운 판은 바탕보다 더 어둡다).

### Named Rules
**The Evidence Accent Rule.** 주홍은 근거와 지금 가리키는 자리(포커스 테두리, 커서, 글 선택, 검색 표시, 끌어 놓을 자리)에만 쓴다. 주 단추도, 고른 탭도, 켜진 스위치도 주홍이 아니다.

**The Ink Selection Rule.** 골랐다는 뜻은 잉크로 말한다. 고른 탭은 잉크 8–9% 바탕에 굵기 600, 고른 칩과 켜진 스위치는 잉크 바탕에 바탕색 글자다.

**The Quiet Normal Rule.** 정상 상태는 색을 쓰지 않는다. 검색 가능한 논문은 흐린 확인 표시(`neutral-500`)뿐이고, 일부·실패만 `warn`·`danger` 점과 글로 드러난다. 색만으로 알리지 않고 언제나 글이 함께 간다.

## Typography

**Display Font:** Wanted Sans Variable (대체: Wanted Sans, system-ui, sans-serif)
**Body Font:** Wanted Sans Variable (같은 벌)
**Label/Mono Font:** ui-monospace, Menlo, Consolas (쪽 링크·코드에만)

**Character:** 제목과 본문이 같은 벌이고, 차이는 크기와 굵기로만 만든다. 한글과 라틴이 한 글꼴 안에서 맞고, 외부 CDN 없이 앱과 함께 배포된다(`shared/theme/fonts/`). 원문 인용만 `Times New Roman`(`--font-paper`)으로 따로 보여 "이것은 논문의 글"임을 가른다.

### Hierarchy
- **Headline** (700, 20px, 1.3, -0.01em): 화면 제목. 서재의 "서재" 한 줄.
- **Title** (700, 16px, 1.12, -0.015em): 창·패널 제목(리더 오른쪽 패널의 "Claude와 대화"), 화면 안 작은 제목.
- **Body** (400, 14px, 1.55): 본문과 기본 글자.
- **Body strong** (600, 14px, 1.4): 표의 논문 제목(두 줄까지 보이고 넘치면 줄인다), 기본 단추의 글.
- **Control** (500, 13px): 머리 탭, 표 안의 글(400), 검색 칸, 메뉴, 구간 선택.
- **Label** (400, 12px, 1.4): 메타 줄(저자·연도·쪽 수), 표 머리글(500), 칩, 상태 글, 마지막 열람 시각. 대문자·넓은 자간을 쓰지 않는다.
- **Micro** (11px): 개수 딱지, 단축키 표시, 촘촘한 보조 글(쪽 수 어림, 꼬리표). 본문이나 조작 요소에는 쓰지 않는다.
- **Quote** (Times New Roman, 13–14px): 리더에서 원문 인용.

수가 줄을 맞춰야 하는 곳(편 수, 주석·대화 수, 쪽 번호)은 `font-variant-numeric: tabular-nums`를 쓴다.

### Named Rules
**The Six Sizes Rule.** 글자 크기는 `--text-2xs`(11) · `--text-xs`(12) · `--text-sm`(13) · `--text-md`(14) · `--text-lg`(16) · `--text-xl`(20) 여섯 단계에서 고른다. 11px은 개수 딱지·단축키·촘촘한 보조 글에만 쓴다. 새 화면에 그 사이 값을 만들지 않는다.

**The Weight-Not-Case Rule.** 위계는 굵기 400·500·600·700과 색 단계(`text` → `neutral-700` → `neutral-600`)로 만든다. 대문자 변환과 넓힌 자간으로 머리글을 만들지 않는다.

## Layout

- **틀**: 창 높이를 꽉 채운 세로 격자. 서재는 52px 머리 · 안내 줄 · 스크롤되는 본문이고, 본문만 스크롤된다(`scrollbar-gutter: stable`).
- **머리(52px)**: 왼쪽에 로고(20px 표식 + 15px/700 이름)와 탭, 오른쪽 끝에 브리지 상태 · 검색 칸(280×32px) · 주 단추(높이 32px). 좌우 여백 20px, 아래 1px 구분선.
- **본문 단**: 가운데 한 단, 최대 폭 1120px, 좌우 32px, 위 28px, 아래 56px.
- **표**: `table-layout: fixed`. 제목 칸이 남는 폭을 모두 갖고 나머지 칸은 고정 폭이다(본문 추출 168px, 주석·대화 56px, 태그 178px, 마지막 열람 96px, 줄 끝 동작 36px). 수와 시각은 오른쪽 맞춤. 칸 안쪽 여백 10px이고, 표 위 제목 줄도 좌우 10px을 들여 제목이 썸네일과 같은 줄에서 시작한다.
- **논문 줄**: 48×64px 첫 쪽 썸네일 + 12px 간격 + 제목(14px/600, 두 줄까지) 아래 2px 띄운 메타 한 줄(12px, `neutral-600`).
- **간격 단계**: 4 · 8 · 12 · 16 · 24 · 32px(`--space-1`–`--space-8`). 조작 요소 안쪽은 6·10px 같은 값도 쓴다.
- **창**: 설정 창은 880×720px(창이 작으면 그 안에 맞춘다), 56px 머리, 200px 왼쪽 탭 단 + 내용. 리더의 오른쪽 패널은 420px(끌어서 바꾼다).
- **좁은 창**: 리더는 1100px 아래에서 오른쪽 패널과 목차를 본문 위에 겹쳐 띄운다. 그 밖의 좁은 창·모바일 대응은 없다(아래 Open Items).

## Elevation & Depth

평소에는 평평하다. 면의 구분은 1px 구분선과 무채색 면 한 단계로 하고, 그림자는 실제로 떠 있는 것(펼친 메뉴, 창, 본문 위의 창, 끌어 놓기 받침)에만 쓴다. 어두운 판에서는 그림자가 보이지 않으므로 같은 토큰이 1px 밝은 테두리 + 짙은 그림자로 바뀐다.

### Shadow Vocabulary
- **`--shadow-sm`** (`0 1px 2px rgb(0 0 0 / 7%)`): 구간 선택의 고른 칸, 쪽 미리보기.
- **`--shadow-md`** (`0 1px 2px rgb(0 0 0 / 6%), 0 4px 12px rgb(0 0 0 / 8%)`): 본문 위의 작은 도구 막대와 칩.
- **`--shadow-lg`** (`0 2px 6px rgb(0 0 0 / 6%), 0 16px 40px rgb(0 0 0 / 14%)`): 펼친 메뉴, 설정·내보내기 창, 원문 위 창, 끌어 놓기 받침.

창 뒤는 `#000` 50% 막으로 가린다(무채색 단계는 어두운 판에서 밝아지므로 쓰지 않는다).

### Named Rules
**The Flat-Until-Floating Rule.** 문서 흐름 안에 있는 것은 그림자를 갖지 않는다. 그림자는 다른 내용 위에 겹쳐 뜬 면에만 붙고, 그 면은 10px 모서리와 1px 구분선을 함께 갖는다.

## Shapes

모서리는 세 단계다. 조작 요소(단추, 입력 칸, 탭, 검색 칸, 구간 선택의 틀)는 6px(`--radius-md`), 칩·썸네일·단축키 표시·메뉴 안의 줄은 4px(`--radius-sm`), 떠 있는 면과 창은 10px(`--radius-lg`)이다. 원은 상태 점(7px), 라디오처럼 본래 둥근 것에만 쓰고, 알약(`--radius-pill`)은 개수 딱지·스위치·범위와 모델을 고르는 칩에만 쓴다.

선은 모두 1px이다. 표는 가로 줄 선만 있고 세로 선과 바깥 테두리가 없다. 썸네일은 테두리 대신 `0 0 0 1px` 고리(`border-strong`)로 종이 가장자리를 만든다. 아이콘은 `currentColor` 선 아이콘이고 글자와 같은 색을 따른다.

## Components

조용하고 촘촘하다. 쉬고 있을 때는 글자와 선뿐이고, 마우스를 올리면 잉크를 아주 옅게 깐다(3.5–8%). 상태 변화는 0.15초 `ease`로 색만 바뀐다.

### Buttons
- **Shape:** 6px 모서리, 안쪽 8px 14.4px, 14px/600. 머리의 단추는 높이 32px·13px로 줄인다.
- **Primary:** 잉크 바탕에 바탕색 글자(`button-primary`). 마우스를 올리면 잉크 86%, 누르면 74%로 옅어진다. 한 화면에 하나(서재의 "PDF 등록").
- **Secondary:** 투명 바탕에 `border-strong` 1px 테두리.
- **Ghost:** `neutral-700` 글자, 굵기 500, 좌우 8px. 마우스를 올리면 잉크색.
- **Icon:** 36×36px(줄 안에서는 26–28px). 줄 끝의 삭제는 평소 보이지 않다가 줄에 마우스·포커스가 오면 나타나고, 마우스를 올리면 `danger` 12% 바탕에 `danger` 글자가 된다.
- **Hover / Focus:** 기본 단추는 잉크 7% 바탕, 누르면 14%, 눌린 채(`aria-pressed`·`aria-expanded`)면 10%. 포커스는 주홍 2px 테두리(2px 띄움). 못 쓰는 상태는 불투명도 0.45.

### Chips
- **Style:** `neutral-200` 바탕, `neutral-800` 글자, 12px, 2px 8px, 4px 모서리. 최대 폭 120px에서 말줄임.
- **State:** 마우스를 올리면 `neutral-300`. 거르기에 쓰이는 중이면 잉크 바탕에 바탕색 글자. 표 위의 거르기 칩도 같은 잉크 칩이다.
- **태그 붙이기(+):** 22×22px, 줄에 마우스·포커스가 오거나 창이 열려 있을 때만 보인다.

### Table
- **머리글:** 12px/500, `neutral-600`, 아래 1px 구분선. 바탕 없음.
- **줄:** 아래 1px 구분선, 마우스를 올리면 잉크 3.5%(0.12초).
- **상태 칸:** 정상은 14px 흐린 확인 표시만(글은 화면 낭독기가 읽는다). 추출 중은 도는 고리(9px, 0.9초, `prefers-reduced-motion`에서는 멈춤), 일부는 `warn` 점, 실패는 `danger` 점과 글. 이유는 둘째 줄에 `neutral-600`으로 두 줄까지.
- **빈 칸:** 수가 없으면 비워 보인다.

### Inputs / Fields
- **Style:** 바탕색, `border-strong` 1px, 6px 모서리, 최소 높이 36px, 6px 10px. 라벨은 위에 12px, 잉크 70%.
- **Focus:** 테두리가 주홍으로 바뀌고 주홍 22% 고리 3px이 두른다. 커서도 주홍.
- **검색 칸:** 테두리 없는 `surface` 면(280×32px). 돋보기 뒤에 검색 대상(제목·저자)을 고르는 테두리 없는 선택 칸이 있고 가는 선 하나로 입력 칸과 가른다. 마우스를 올리면 구분선 색 테두리, 포커스가 오면 바탕색 + 주홍 테두리 + 같은 고리.
- **라디오:** 16px 원, 고르면 잉크로 채우고 안쪽에 바탕색 고리. **체크 상자·범위 막대:** `accent-color`를 잉크로.
- **스위치:** 40×22px 알약, 꺼짐 `neutral-400`, 켜짐 잉크, 16px 손잡이.

### Navigation
- **머리 탭:** 13px/500, `neutral-700`, 6px 10px, 6px 모서리, 간격 2px. 마우스를 올리면 잉크 6% + 잉크색 글자. 지금 화면은 잉크 8% + 600.
- **설정 창의 옆 탭:** 같은 문법을 세로로(7px 12px, 고르면 잉크 9% + 600), `surface` 단 위에 놓인다.
- **구간 선택:** `neutral-200` 틀(6px) 안에 2px 간격의 칸(4px). 고른 칸은 `raised` 바탕 + 600 + `--shadow-sm`.

### Floating surfaces
- **펼친 메뉴:** `raised` 바탕, 1px 구분선, 10px 모서리, `--shadow-lg`, 폭 264px, 13px. 줄은 7px 8px에 4px 모서리, 마우스를 올리면 잉크 6%. 줄 끝의 수는 `tabular-nums`이고, 이름 바꾸기·지우기는 마우스를 올리면 수 자리에 나타난다. 아래 단은 1px 구분선으로 가른다.
- **창:** 바탕색, 10px 모서리, `--shadow-lg`, 머리 아래 1px 구분선. 내용의 항목은 1px 구분선으로 가르고 카드로 감싸지 않는다.

### 논문 줄 (Signature)
첫 쪽 썸네일(48×64px, 4px 모서리, 1px 고리, 쪽은 테마와 상관없이 흰 종이)과 제목·메타 한 줄. 제목이 곧 여는 단추이고 마우스를 올리면 밑줄(3px 띄움)이 생긴다. 검색에 걸린 글자는 주홍 25% 바탕으로 표시한다. 썸네일은 0.2초로 떠오르고, 그리지 못하면 흐린 문서 아이콘이 남는다.

### 페이지 이동
표 아래 한 줄(12px, `neutral-700`). 왼쪽에 페이지당 편 수를 고르는 작은 선택 칸(높이 28px), 오른쪽에 지금 범위("1–20 / 57편", `tabular-nums`)와 페이지 단추. 단추는 28px 정사각에 6px 모서리이고 지금 페이지는 머리 탭처럼 잉크 9% 바탕 + 600이다. 여덟 페이지부터는 처음·끝과 지금 둘레만 두고 줄임표로 줄여 늘 일곱 칸이다. 한 페이지뿐이면 페이지 단추는 없고 편 수 선택만 남는다.

### 근거 표시
답 안의 근거 번호와 쪽 링크는 주홍 1px 밑줄에 `accent-700` 글자(12px)이고, 마우스를 올리면 `accent-100` 바탕이 깔린다. 쪽 링크는 고정폭 글꼴. 문맥에 없는 번호는 점선 밑줄에 `neutral-700`이다.

### 브리지 상태
7px 점 + 12px 글. 연결 `ok`, 확인 중 `neutral-500`, 꺼짐 `warn`. 상태는 언제나 글로도 쓴다.

## Do's and Don'ts

### Do:
- **Do** 주 단추와 고른 상태를 잉크(`text`)로 만든다. 주 단추는 잉크 바탕, 고른 탭은 잉크 8–9% 바탕 + 굵기 600.
- **Do** 주홍을 근거 표시, 포커스(2px 테두리 · 입력 칸의 22% 고리 3px), 커서, 글 선택, 검색 표시, 끌어 놓을 자리에만 쓴다.
- **Do** 실패·삭제는 `danger`, 주의는 `warn`, 확인은 `ok`로 가르고, 색 옆에 언제나 글을 쓴다.
- **Do** 구분은 1px 선(`divider`)과 `surface` 한 단계로 한다.
- **Do** 모서리는 6px(조작 요소) · 4px(칩·썸네일) · 10px(떠 있는 면·창)에서 고른다.
- **Do** 글자 크기는 11·12·13·14·16·20px(`--text-*`), 굵기는 400·500·600·700에서 고른다.
- **Do** 보통 링크는 잉크색 글자에 흐린 밑줄로 쓴다. 주홍 글자는 근거로 가는 표시(`.cite-chip`)의 것이다.
- **Do** 색·그림자·모서리·글자 크기는 `tokens.css`의 변수로만 쓰고, 밝은 판과 어두운 판을 함께 확인한다.
- **Do** 줄의 보조 동작은 마우스를 올리거나 포커스가 올 때만 보이게 하고, 키보드 포커스(`:focus-within`)로도 나타나게 한다.
- **Do** 수가 세로로 맞아야 하는 곳에는 `tabular-nums`와 오른쪽 맞춤을 쓴다.

### Don't:
- **Don't** 주홍을 단추 바탕, 고른 탭·줄, 켜진 스위치, 실패 알림에 쓰지 않는다.
- **Don't** 한쪽 변에만 두꺼운 색 띠를 두른 카드·줄·알림을 만들지 않는다.
- **Don't** 대문자로 바꾸고 자간을 넓힌 작은 머리글을 만들지 않는다.
- **Don't** 은유나 컨셉(도서관 라벨, 노선도 같은 것)을 화면에 입히지 않는다.
- **Don't** 목록을 카드 줄이나 알약 단추로 바꾸지 않는다. 표와 1px 줄 선이 기본이다.
- **Don't** 예전 Modernist 모양(모서리 0, 2px 구분선, 빨강 주 단추)으로 돌아가지 않는다.
- **Don't** PDF 쪽과 `--mark-*` 표시의 색을 테마에 따라 바꾸지 않는다.
- **Don't** 흐름 안의 면에 그림자를 붙이지 않는다. 그림자는 떠 있는 면의 것이다.
- **Don't** 글꼴·아이콘을 외부 CDN에서 불러오지 않는다.

## Open Items

정해지지 않았거나 아직 이 시스템에 맞추지 못한 것. 시스템의 규칙이 아니다.

- **리더·번역 화면의 배치**: 색·글자 크기·모서리·그림자는 토큰에 맞췄고(2026-11-25) 배치는 예전 그대로다. 이 문서와 다른 채로 둔 것: 인용의 왼쪽 선(`.quote`·`.evidence-text`·`blockquote`, 인용 표시라서 둔다), 답을 기다리는 글자의 흐르는 빛(`chatMotion.css`), 알림의 튀는 등장(`toast.css`). 새 화면이 이 값을 따라 하지 않는다.
- **읽은 위치 표시**: 서버가 읽은 위치를 저장하지 않아 서재에 넣지 않았다. 모양도 정하지 않았다.
- **좁은 창·모바일**: 1100px 아래 창과 모바일은 지원 대상이 아니다. 리더의 1100px 겹침 처리 말고는 대응이 없다.
- **접근성 기준**: WCAG 수준을 정한 바 없다.
- **답변 화면·설정 창의 배치**: 서재와 같은 틀·토큰을 쓰지만 배치는 따로 다듬지 않았다.
