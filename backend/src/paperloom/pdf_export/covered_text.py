"""번역본 PDF에서 번역문으로 덮은 원문 글 지우기 (2026-11-17 사용자 보고: 내보낸 번역본을 외부 뷰어에서 끌어 고르면 흰 상자
밑의 원문 글까지 잡혀 빈 자리에 선택 막대가 생기고, 복사하면 원문과 번역문이 섞였다).

쪽 내용에서 글 그리기 연산(Tj·TJ·'·")만 빼고 나머지 연산(그림·선·글 상태)은 그대로 둔다. pdfium으로 쪽 내용을 다시 만들면
음영(sh) 같은 연산을 잃으므로 쓰지 않는다. 어느 연산이 덮였는지는 pdfium 글 객체의 상자로 잰다: pdfium은 빈 글이 아닌 글
그리기 연산마다 글 객체를 하나씩 차례대로 만들므로 n번째 글 객체가 n번째 연산이다. 둘의 수가 다르면 그 쪽은 덮기만 한다.
쪽 내용에서 부르는 Form XObject 안의 글도 지우지 않는다(덮기만 한다).

위치를 옮기지 않고 앞 글에 이어 쓰는 연산(같은 줄의 글꼴 바꿈 등)은 앞 글 폭만큼 나아간 자리에 놓이므로, 그런 연산이 남으면
그 앞 연산도 남긴다(지우면 남은 글이 당겨진다).
"""

import ctypes
from collections.abc import Sequence

from pypdf.generic import ByteStringObject, TextStringObject

Box = tuple[float, float, float, float]  # x0, y0, x1, y1 (PDF 사용자 공간)
Operation = tuple[list, bytes]

COVERED = 0.8  # 글 객체 상자의 이만큼이 덮개 밑이면 지운다. 덮개 밖으로 보이는 글은 남긴다
_SHOW = {b"Tj", b"TJ", b"'", b'"'}
_NEW_LINE = {b"'", b'"'}  # 다음 줄로 옮긴 뒤 쓴다
_MOVE = {b"BT", b"Td", b"TD", b"Tm", b"T*"}
_STRINGS = (TextStringObject, ByteStringObject)


def strip_covered_text(writer, source: str, covers: dict[int, list[Box]]) -> None:
    """writer(pypdf.PdfWriter, source를 연 것)의 쪽마다(covers: 쪽 차례 → 덮개 상자) 덮개 밑 원문 글을 지운다."""
    import pypdfium2 as pdfium

    document = pdfium.PdfDocument(source)
    try:
        for index, boxes in covers.items():
            page = writer.pages[index]
            content = page.get_contents()
            if content is None:
                continue
            operations = strip(content.operations, _covered(document[index], boxes))
            if operations is not None:
                content.operations = operations
                page.replace_contents(content)
    finally:
        document.close()


def strip(operations: Sequence[Operation], covered: Sequence[bool]) -> list[Operation] | None:
    """covered: 글을 그리는 연산마다 덮였는지(차례대로). 수가 맞지 않으면 None(그 쪽은 그대로 둔다).
    지운 '·" 연산은 줄 옮김(T*)과 글 간격 설정(Tw·Tc)을 남긴다."""
    drawing = [i for i, (operands, operator) in enumerate(operations) if operator in _SHOW and _draws(operands, operator)]
    if len(drawing) != len(covered):
        return None
    remove = {i for i, hidden in zip(drawing, covered, strict=True) if hidden}
    draws = set(drawing)
    kept_after = False  # 뒤에서부터 보며: 지금 줄 조각에서 뒤에 남는 글이 있다
    for i in range(len(operations) - 1, -1, -1):
        operator = operations[i][1]
        if i in remove and kept_after:
            remove.discard(i)
        if i in draws and i not in remove:
            kept_after = True
        if operator in _MOVE or operator in _NEW_LINE:
            kept_after = False
    result: list[Operation] = []
    for i, (operands, operator) in enumerate(operations):
        if i not in remove:
            result.append((operands, operator))
        elif operator == b"'":
            result.append(([], b"T*"))
        elif operator == b'"':
            result += [([operands[0]], b"Tw"), ([operands[1]], b"Tc"), ([], b"T*")]
    return result


def _draws(operands: list, operator: bytes) -> bool:
    """pdfium처럼 빈 글만 쓰는 연산(글 없이 자리만 옮기는 TJ 포함)은 글 객체를 만들지 않는다."""
    if operator == b"TJ":
        return bool(operands) and any(isinstance(item, _STRINGS) and len(item) > 0 for item in operands[0])
    index = 2 if operator == b'"' else 0
    return len(operands) > index and isinstance(operands[index], _STRINGS) and len(operands[index]) > 0


def _covered(page, boxes: Sequence[Box]) -> list[bool]:
    """쪽의 최상위 글 객체마다(쪽 내용 차례) 덮개 밑인지. page(pdfium 쪽)는 닫는다."""
    import pypdfium2.raw as raw

    covered = []
    try:
        for i in range(raw.FPDFPage_CountObjects(page.raw)):
            item = raw.FPDFPage_GetObject(page.raw, i)
            if raw.FPDFPageObj_GetType(item) != raw.FPDF_PAGEOBJ_TEXT:
                continue
            left, bottom, right, top = (ctypes.c_float() for _ in range(4))
            found = raw.FPDFPageObj_GetBounds(item, *(ctypes.byref(value) for value in (left, bottom, right, top)))
            covered.append(bool(found) and _share((left.value, bottom.value, right.value, top.value), boxes) >= COVERED)
    finally:
        page.close()
    return covered


def _share(box: Box, covers: Sequence[Box]) -> float:
    """box 넓이 가운데 덮개들 밑에 든 몫. 넓이가 없는 상자(빈 글자 등)는 가운데 점으로 본다."""
    x0, y0, x1, y1 = box
    area = (x1 - x0) * (y1 - y0)
    if area <= 0:
        x, y = (x0 + x1) / 2, (y0 + y1) / 2
        return 1.0 if any(c0 <= x <= c1 and d0 <= y <= d1 for c0, d0, c1, d1 in covers) else 0.0
    inside = sum(max(0.0, min(x1, c1) - max(x0, c0)) * max(0.0, min(y1, d1) - max(y0, d0)) for c0, d0, c1, d1 in covers)
    return min(1.0, inside / area)
