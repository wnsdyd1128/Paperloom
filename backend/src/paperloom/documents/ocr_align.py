"""OCR이 읽은 글줄로 그 줄의 못 읽은 글자를 채운다 (2026-10-21 "Self-recovery 고도화" ③, documents.ocr_model·parsing). 순수 함수만 둔다.

글줄의 글자(pdfium 차례)와 OCR 글을 맞춘다(difflib). pdfium이 준 글이 OCR과 같은 못 읽은 글자는 그 글이 맞다고 보고(옛 TeX 비트맵
글꼴: 글은 맞는데 글꼴이 글자를 알려 주지 않는다), 다른 못 읽은 글자 구간은 OCR 글로 채운다(Word 수식 Type3: 글 자체가 깨졌다).
OCR은 공백을 글자로 그리지 않으므로, 못 읽은 공백은 OCR도 그 자리를 띄어 읽었을 때 공백으로 둔다(차트 Type3 글꼴의 공백 글리프).
OCR이 그 줄을 잘못 읽었을 수 있으므로 다음일 때만 쓴다.
- 글자 확률 평균이 OCR_SCORE 이상
- 이미 읽은 글자가 MIN_KNOWN 이상이면 그 가운데 AGREEMENT 이상이 OCR과 같다(실제 논문: 큰 괄호 몇 개만 못 읽은 줄을 OCR이
  "Multise pproaches … t count"로 읽었다 — 그 줄은 버린다)
이미 읽은 글자는 바꾸지 않는다. 줄 전체가 못 읽은 글자인데 OCR이 글자를 하나도 찾지 못하거나, pdfium이 글자 정보를 하나도 주지
않았고(모두 U+FFFD) OCR도 확신하지 못하면(OCR_SCORE 미만, 다국어 모델이 선을 目·二로 지어낸다) 그 글리프는 글자가 아니다(옛 LaTeX가
그림의 빗금 상자·화살표·선을 글꼴 글리프로 그렸다 — Liu & Layland 3·9쪽 그림): 모두 ""로 채운다.
"""

import re
import unicodedata
from difflib import SequenceMatcher

from paperloom.documents.text_layout import NO_TEXT

OCR_SCORE = 0.85
AGREEMENT = 0.8
MIN_KNOWN = 5
MAX_PIECE = 4  # 못 읽은 글자 한 개에 붙일 OCR 글의 최대 길이(수식 조각·합자). 구간이 이보다 길면 글자 수에 비례해 늘린다
# 한자·가나. 모델 글자 사전의 대부분(18,708자 가운데 15,884자)이라 한자·가나가 없는 글줄에서 선·상자·근호를 이것으로 지어낸다
# (Liu & Layland 그림의 目·十·二, 식의 立). 그런 글줄에서는 OCR 글에서 뺀다
_CJK = re.compile("[" + "".join(f"{chr(first)}-{chr(last)}" for first, last in ((0x3040, 0x30FF), (0x3400, 0x4DBF), (0x4E00, 0x9FFF), (0xF900, 0xFAFF))) + "]")
# 모델이 수식 글자를 닮은 다른 글자로 읽는 것. 못 읽은 글리프(글꼴이 글자를 알려 주지 않은 수식 글자)에만 채우므로 수식 글자로
# 되돌린다(논문 40편: €는 모두 ε 자리였다 — "error estimate ε", "H − ε with ε ≥ 0", "T − T′ − ε")
_LOOKALIKES = str.maketrans({"€": "ε"})


def fill(chars: list[tuple[str, bool]], read: str, score: float) -> dict[int, str]:
    """글줄 글자(글, 못 읽었는지)마다 OCR 글(read, 글자 확률 평균 score)로 채울 글. 키는 chars의 자리다. 못 읽은 구간을 OCR의 다른
    글자 수로 채우면 구간 글자들이 OCR 글을 차례로 나눠 받는다(한 글자가 여러 글자를 받거나, 모자라면 NO_TEXT). ""는 글자가 아닌
    그림 글리프다. 쓸 수 없으면 {}."""
    if not any(unmapped for _, unmapped in chars):
        return {}
    if not any(_CJK.search(text) for text, _ in chars):
        read = _CJK.sub("", read)
    read = read.translate(_LOOKALIKES)
    if all(unmapped for _, unmapped in chars) and (
        not read.strip() or (score < OCR_SCORE and all(text == "�" for text, _ in chars))
    ):
        return dict.fromkeys(range(len(chars)), "")
    if score < OCR_SCORE:
        return {}
    texts = [unicodedata.normalize("NFKC", text) for text, _ in chars]
    positions = [index for index, char in enumerate(read) if not char.isspace()]  # OCR 글에서 공백이 아닌 글자 자리
    letters = [read[index] for index in positions]
    blocks = SequenceMatcher(None, texts, letters, autojunk=False).get_opcodes()
    known = [index for index, (_, unmapped) in enumerate(chars) if not unmapped]
    agreed = sum(1 for tag, i1, i2, _, _ in blocks if tag == "equal" for index in range(i1, i2) if not chars[index][1])
    if len(known) >= MIN_KNOWN and agreed < AGREEMENT * len(known):
        return {}
    found: dict[int, str] = {}
    for tag, i1, i2, j1, j2 in blocks:
        if tag == "equal":
            found.update({index: texts[index] for index in range(i1, i2) if chars[index][1]})
        elif tag == "replace" and all(chars[index][1] for index in range(i1, i2)) and j2 - j1 <= MAX_PIECE * (i2 - i1):
            # 글자마다 OCR 글자를 차례로 고르게 나눈다(글자 상자를 살려야 글줄이 끊기지 않는다). 사이 공백은 앞 글자가 받고,
            # OCR 글자가 모자라면 뒤 글자가 NO_TEXT를 받는다
            count, end = i2 - i1, positions[j2 - 1] + 1
            letters_before = [-(-k * (j2 - j1) // count) for k in range(count)]  # k번째 글자 앞까지 나눈 OCR 글자 수(올림)
            starts = [positions[j1 + before] if before < j2 - j1 else end for before in letters_before] + [end]
            found.update({i1 + k: read[starts[k] : starts[k + 1]] or NO_TEXT for k in range(count)})
        elif tag == "delete" and all(chars[index][1] and texts[index] == " " for index in range(i1, i2)):
            if 0 < j1 < len(positions) and positions[j1] - positions[j1 - 1] > 1:  # OCR도 그 자리를 띄어 읽었다
                found.update(dict.fromkeys(range(i1, i2), " "))
    return found
