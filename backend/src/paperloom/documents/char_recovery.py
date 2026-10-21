"""pdfium이 유니코드를 주지 못한 글자를 PDF 글꼴 정보로 되찾는다 (본문 추출 하위 프로세스 documents.extract가 쓴다).

pdfium은 글꼴이 글자를 알려 주지 않으면 글자 코드를 그대로 주며 매핑 오류로 표시하거나, 제어 문자·사용자 영역 글자를 준다.
글자마다 아래 해독기를 차례로 해 보고 처음 답을 낸 것을 쓴다(답 " "는 늘이는 괄호 조각처럼 글자가 아닌 것). 글자 코드 그대로가
맞다고 확인되면 같은 글자를 돌려준다(매핑 오류 표시만 뗀다). 1·3·4·5번 해독기는 조건이 맞으면 답이 없어도 거기서 멈춘다(그
글꼴은 뒤 해독기가 다룰 꼴이 아니다). 2번은 답이 없으면 다음 해독기로 넘어간다.

1. 매핑 오류, 글리프 번호 글꼴(Type0 Identity-H, ToUnicode·cmap 없음): 매킨토시 표준 차례 — 한 글꼴의 글을 모아 말글처럼 보일
   때만 쓴다(finish, 2026-10-19 SayCan)
2. 매핑 오류, 글꼴 안 인코딩을 쓰는 TeX 큰 기호 글꼴(CMEX): TeX 자리표(2026-10-21)
3. 수식 글꼴의 제어 문자: /Differences 글리프 이름(2026-10-04). 본문 글꼴의 0x02는 줄 끝 하이픈이라 건드리지 않는다
4. 3B2 AdvP 수식 글꼴: TeX 글꼴 자리(2026-10-14)
5. 사용자 영역 글자: Adobe 글리프 목록의 Symbol 글자·Symbol 코드(2026-10-14)
6. 매핑 오류, 글꼴 안 인코딩을 쓰는 Symbol 글꼴: Symbol 인코딩(2026-10-21)
7. 매핑 오류, /Differences 글리프 이름: 표준 이름(matplotlib 차트 /zero·/A)이면 그 글자, 글리프 번호 이름이면 번호의 매킨토시
   차례 글자가 글자 코드와 같을 때 그 글자(2026-10-21)
글꼴 사전이 필요한 해독기(5 말고 모두)는 간이 추출(--plain)에서는 쓰지 않는다(differences가 None).
"""

from dataclasses import replace

from paperloom.documents.glyphs import MAC_GLYPHS, FontDifferences, looks_like_text, pua_text
from paperloom.documents.text_layout import Char


class CharRecovery:
    """한 쪽의 글자 되찾기. char()로 글자마다 묻고, 쪽의 글자를 다 읽은 뒤 finish()로 모아서 판단하는 해독기(1)를 적용한다."""

    def __init__(self, differences: FontDifferences | None, page_index: int) -> None:
        self._fonts = differences
        self._page = page_index
        self._glyph_ids: dict[str, list[tuple[int, str | None]]] = {}  # 글꼴 → (chars 안 자리, 매킨토시 차례의 글자)

    def char(self, font: str, code: int, unmapped: bool, math_font: bool, position: int) -> str | None:
        """글자(pdfium의 글꼴 이름·글자 코드, 매핑 오류인지, 수식 글꼴인지)의 되찾은 글. 모르면 None. position은 그 글자가 들어갈
        chars 자리다(해독기 1이 finish에서 고친다)."""
        fonts, page = self._fonts, self._page
        if fonts is not None and unmapped and fonts.glyph_ids(page, font):
            self._glyph_ids.setdefault(font, []).append((position, MAC_GLYPHS.get(code)))
            return None
        if fonts is not None and unmapped and (found := fonts.cmex_text(page, font, code)) is not None:
            return found
        if 0 < code < 0x20 and math_font:
            return fonts.text(page, font, code) if fonts is not None else None
        if "AdvP" in font:
            return fonts.text_3b2(page, font, code) if fonts is not None else None
        if 0xE000 <= code <= 0xF8FF:
            return pua_text(font, code)
        if fonts is not None and unmapped:
            return fonts.symbol_text(page, font, code) or fonts.name_text(page, font, code)
        return None

    def finish(self, chars: list[Char]) -> None:
        """글리프 번호 글꼴(해독기 1)의 글자를 글꼴마다 모아 매킨토시 차례로 읽은 글이 말글처럼 보이면 chars에서 바꾼다."""
        for found in self._glyph_ids.values():
            if looks_like_text("".join(char or "" for _, char in found)):
                for position, char in found:
                    if char is not None:
                        chars[position] = replace(chars[position], text=char, unmapped=False) if char.strip() else Char(" ", None)
