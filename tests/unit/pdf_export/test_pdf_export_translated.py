"""번역본 바탕에서 하이라이트를 칠할 번역 문장 (paperloom.pdf_export.translated, 2026-11-15 사용자 결정:
하이라이트가 걸친 원문 문장의 번역문 전체에 칠한다)."""

from paperloom.pdf_export.translated import Group, TranslatedBlock, TranslatedPage, highlight_targets, sentence_groups
from paperloom.translation.models import TranslatedSentence

TEXT = "Caches cut the worst case. Partitioning keeps tasks apart. The bound holds."


def block(block_id: str, text: str, ranges: list[list[tuple[int, int]]]) -> TranslatedBlock:
    return TranslatedBlock(block_id, text, [[0.1, 0.1, 0.9, 0.12]], 10.0, "", [Group(f"번역 {index}", list(item)) for index, item in enumerate(ranges)])


# 문장 셋을 묶음 셋으로
BLOCK = block("b1", TEXT, [[(0, 26)], [(27, 58)], [(59, 75)]])


def test_empty_translations_join_the_group_before_them():
    sentences = [TranslatedSentence(start=0, end=26, text="앞."), TranslatedSentence(start=27, end=58, text=""), TranslatedSentence(start=59, end=75, text="뒤.")]
    assert sentence_groups(sentences) == [Group("앞.", [(0, 26), (27, 58)]), Group("뒤.", [(59, 75)])]


def test_a_highlight_paints_every_sentence_it_touches():
    assert highlight_targets("worst case", None, None, [BLOCK]) == (("b1", 0),)
    assert highlight_targets("case. Partitioning", None, None, [BLOCK]) == (("b1", 0), ("b1", 1))


def test_quotes_match_despite_spaces_hyphens_ligatures_and_case():
    assert highlight_targets("Parti-\ntioning KEEPS", None, None, [BLOCK]) == (("b1", 1),)
    assert highlight_targets("ﬁne", None, None, [block("b2", "A fine bound.", [[(0, 13)]])]) == (("b2", 0),)


def test_a_repeated_quote_is_found_by_the_text_around_it():
    repeated = block("b3", "The bound holds. The bound fails.", [[(0, 16)], [(17, 33)]])
    assert highlight_targets("The bound", None, None, [repeated]) == (("b3", 0),)
    assert highlight_targets("The bound", "holds.", "fails", [repeated]) == (("b3", 1),)


def test_a_highlight_across_paragraphs_paints_both():
    second = block("b2", "Next paragraph starts here.", [[(0, 27)]])
    assert highlight_targets("bound holds. Next paragraph", None, None, [BLOCK, second]) == (("b1", 2), ("b2", 0))


def test_a_quote_not_in_the_translated_paragraphs_keeps_its_place():
    assert highlight_targets("Figure 3 caption", None, None, [BLOCK]) == ()
    assert highlight_targets("  ", None, None, [BLOCK]) == ()


def test_the_writer_gets_only_what_it_draws():
    page = TranslatedPage(2, [BLOCK])
    assert page.drawing() == {"page_index": 2, "blocks": [{"block_id": "b1", "regions": [[0.1, 0.1, 0.9, 0.12]], "font_size": 10.0, "mark": "", "groups": ["번역 0", "번역 1", "번역 2"]}]}
