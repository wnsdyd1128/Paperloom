"""대화 질문에 함께 보내는 그림 (2026-11-10 사용자 요청: Claude가 그림 이미지를 받지 못해 축 글자와 본문으로만 답했다).

- 질문에 쓴 논문 그림 번호(Figure 3·Fig. 3·그림 3)를 찾는다. 브리지가 그 번호의 원본 그림을 Core에서 잘라 붙인다.
- 붙인 이미지가 메시지의 몇 번째 이미지인지 글로 알린다(근거 영역 이미지의 "이 메시지에 붙인 이미지 가운데 N번째"와 같은 방식).
"""

import re

MAX_FIGURE_IMAGES = 4  # 질문에 쓴 번호로 한 차례에 붙이는 원본 그림 수

# 그림 낱말 뒤의 번호 하나 또는 여럿(3, 4 · 3 and 4 · 3과 4)과 범위(3–5). 낱말 앞이 영문자면 다른 낱말이다(configure 3)
_FIGURE_REF = re.compile(
    r"(?:(?<![a-z])fig(?:ure)?s?\.?|그림)\s*(S?\d{1,3}(?:\s*(?:,|&|/|and|or|와|과|및|[-–~])\s*S?\d{1,3})*)", re.IGNORECASE
)
_FIGURE_PART = re.compile(r"([-–~])?\s*(S?\d{1,3})", re.IGNORECASE)


def figure_refs(question: str) -> list[str]:
    """질문에 쓴 그림 번호(캡션 번호처럼 대문자, "3"·"S1"), 처음 쓴 차례로 한 번씩. 범위는 MAX_FIGURE_IMAGES장까지 편다."""
    labels: list[str] = []
    for match in _FIGURE_REF.finditer(question):
        previous: str | None = None
        for dash, part in _FIGURE_PART.findall(match.group(1)):
            label = part.upper()
            if dash and previous is not None and previous.isdigit() and label.isdigit() and int(previous) < int(label):
                last = min(int(label), int(previous) + MAX_FIGURE_IMAGES)
                labels += [str(number) for number in range(int(previous) + 1, last + 1)]
            else:
                labels.append(label)
            previous = label
    return list(dict.fromkeys(labels))


def image_block(media_type: str, data: str) -> dict:
    """모델 메시지의 이미지 한 장(base64 글)."""
    return {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": data}}


def attachment_note(first: int, figures: list[dict], user_images: int, skipped: list[tuple[str, str]]) -> str:
    """메시지에 붙인 그림을 알리는 글. 이미지는 first번째부터 원본 그림(figures, 붙인 차례), 사용자 이미지 차례로 붙어 있다.
    skipped: 질문에 썼지만 붙이지 않은 그림 (번호, 이유). 붙인 것도 뺀 것도 없으면 빈 글이다."""
    lines = [
        f"- 이 메시지에 붙인 이미지 가운데 {first + index}번째: 이 논문의 Figure {figure['label']}(p.{figure['page_index'] + 1}) 원본 그림. "
        "원문 PDF에서 잘라 낸 그림입니다."
        for index, figure in enumerate(figures)
    ]
    lines += [f"- 이 메시지에 붙인 이미지 가운데 {first + len(figures) + index}번째: 사용자가 붙인 이미지 {index + 1}" for index in range(user_images)]
    lines += [f"- Figure {label}: {reason}" for label, reason in skipped]
    return "\n".join(["## 이 질문에 붙인 그림", "", *lines]) if lines else ""
