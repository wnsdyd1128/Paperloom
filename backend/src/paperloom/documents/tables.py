"""표·의사코드 안의 문단 찾기 (2026-10-03 사용자 요청: 표 안 글은 번역하지 않고 캡션만 번역한다). 순수 함수만 둔다.

논문 표(booktabs)와 의사코드 상자는 같은 폭의 가로줄 여러 개로 둘러싸인다(위·머리 아래·아래). 같은 폭 가로줄 사이 띠에
놓인 문단을 표 안으로 본다. 다만
- 띠에 본문 폭의 여러 줄 문단이 있으면(가로줄로 둘러싼 초록 등) 표가 아니다. 다만 띠에 의사코드 줄 번호(1:, 12:)가
  여럿이면 넓은 입력 문단(Input:·Require:)이 있어도 의사코드 상자다(2026-10-05 사용자 요청: 알고리즘은 번역하지 않는다).
- 가로줄이 둘뿐이면 그 사이가 짧은 줄(표 칸) 여럿일 때만 표다.
- 캡션(Table 1. …, PSEUDOCODE 1: …)은 띠 안에 있어도 번역한다.
휴리스틱이다. 바꾸면 text_layout.LAYOUT_VERSION을 올린다.
"""

import re

from paperloom.documents.block_kinds import is_caption
from paperloom.reading.figures import Graphic

Box = tuple[float, float, float, float]  # 정본 좌표 (u0, v0, u1, v1)

RULE_THICKNESS = 2.0  # pt. 이보다 얇은 경로가 가로줄이다
RULE_MIN_WIDTH = 0.2  # 쪽 너비 비율. 이보다 짧은 줄은 분수 막대 등이다
SAME_EDGE = 0.02  # 쪽 너비 비율. 좌우 끝이 이만큼 안에서 같으면 한 표의 줄이다
MAX_BAND = 0.5  # 쪽 높이 비율. 이보다 멀리 떨어진 두 줄(머리글 밑줄과 바닥글 윗줄 등)은 한 표가 아니다
BODY_LINES = 3  # 줄 수. 이만큼 이상이고
BODY_WIDTH = 0.8  # 가로줄 폭의 이 비율 이상인 문단은 본문이다
SHORT_SHARE = 0.6  # 가로줄이 둘뿐이면 사이 문단의 이 비율 이상이 한 줄이어야 표다
LINE_NUMBER = re.compile(r"(?:^|\s)\d{1,3}:(?=\s|$)")  # 의사코드 줄 번호. 비율(1:2)·시각(10:30)은 아니다
PSEUDOCODE_NUMBERS = 3  # 띠 안 줄 번호가 이만큼 이상이면 의사코드 상자다


def horizontal_rules(graphics: list[Graphic], view_box: tuple[float, float, float, float]) -> list[Box]:
    """쪽의 가로줄(얇고 긴, 보이는 경로) 상자. 위에서 아래로."""
    x0, y0, x1, y1 = view_box
    width, height = x1 - x0, y1 - y0
    rules = []
    for graphic in graphics:
        left, bottom, right, top = graphic.box
        if graphic.kind == "path" and (graphic.stroked or graphic.filled) and top - bottom <= RULE_THICKNESS and right - left >= RULE_MIN_WIDTH * width:
            rules.append(((left - x0) / width, (y1 - top) / height, (right - x0) / width, (y1 - bottom) / height))
    return sorted(rules, key=lambda rule: rule[1])


def table_blocks(blocks: list[tuple[list[list[float]], str]], rules: list[Box]) -> set[int]:
    """표 안 문단의 차례. blocks는 문단마다 (줄 상자들(정본 좌표), 글), rules는 horizontal_rules."""
    found: set[int] = set()
    for group in _same_width(rules):
        bands = []
        for upper, lower in zip(group, group[1:]):
            if lower[1] - upper[3] > MAX_BAND:
                continue
            inside = [index for index, (regions, _) in enumerate(blocks) if _within(regions, upper, lower)]
            if inside and (_pseudocode([blocks[index][1] for index in inside]) or not any(_body_paragraph(blocks[index][0], upper) for index in inside)):
                bands.append(inside)
        members = [index for inside in bands for index in inside]
        if len(group) == 2 and (len(members) < 2 or sum(len(blocks[index][0]) == 1 for index in members) < SHORT_SHARE * len(members)):
            continue
        found.update(index for index in members if not is_caption(blocks[index][1]))
    return found


def _same_width(rules: list[Box]) -> list[list[Box]]:
    """좌우 끝이 같은 가로줄끼리(위에서 아래로). 줄이 둘 이상인 묶음만."""
    groups: list[list[Box]] = []
    for rule in rules:
        for group in groups:
            if abs(group[0][0] - rule[0]) <= SAME_EDGE and abs(group[0][2] - rule[2]) <= SAME_EDGE:
                group.append(rule)
                break
        else:
            groups.append([rule])
    return [group for group in groups if len(group) >= 2]


def _within(regions: list[list[float]], upper: Box, lower: Box) -> bool:
    """문단 상자의 가운데가 두 가로줄 사이, 줄의 좌우 안에 있는지."""
    left, right = min(region[0] for region in regions), max(region[2] for region in regions)
    top, bottom = min(region[1] for region in regions), max(region[3] for region in regions)
    middle, center = (top + bottom) / 2, (left + right) / 2
    return upper[1] <= middle <= lower[3] and upper[0] - SAME_EDGE <= center <= upper[2] + SAME_EDGE


def _pseudocode(texts: list[str]) -> bool:
    return sum(len(LINE_NUMBER.findall(text)) for text in texts) >= PSEUDOCODE_NUMBERS


def _body_paragraph(regions: list[list[float]], rule: Box) -> bool:
    width = max(region[2] for region in regions) - min(region[0] for region in regions)
    return len(regions) >= BODY_LINES and width >= BODY_WIDTH * (rule[2] - rule[0])
