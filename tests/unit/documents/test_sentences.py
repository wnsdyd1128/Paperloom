"""문단을 문장으로 나누기 (U7 쪽 번역: 문장마다 번역해 원문 문장과 짝짓는다)."""

from paperloom.documents.sentences import sentence_spans


def sentences(text: str) -> list[str]:
    return [text[start:end] for start, end in sentence_spans(text)]


def test_splits_at_sentence_ends_followed_by_space():
    text = "Shared caches cause delays. We propose CITTA! Does it scale? Yes."
    assert sentences(text) == ["Shared caches cause delays.", "We propose CITTA!", "Does it scale?", "Yes."]


def test_does_not_split_after_abbreviations_initials_or_before_lowercase():
    text = "As shown in Fig. 6 and Eq. 3, e.g. the delay of tasks, i.e. the WCET, grows. J. Xiao et al. proposed it. It is fast vs. slow."
    assert sentences(text) == [
        "As shown in Fig. 6 and Eq. 3, e.g. the delay of tasks, i.e. the WCET, grows.",
        "J. Xiao et al. proposed it.",
        "It is fast vs. slow.",
    ]


def test_keeps_decimals_closing_quotes_and_brackets_with_the_sentence():
    text = 'The ratio is 0.5 (see Sec. 2). He said "done." Then it ended [12]. Next one'
    assert sentences(text) == ["The ratio is 0.5 (see Sec. 2).", 'He said "done."', "Then it ended [12].", "Next one"]


def test_spans_cover_the_text_without_surrounding_space():
    text = "  First one.   Second one.  "
    spans = sentence_spans(text)
    assert [text[start:end] for start, end in spans] == ["First one.", "Second one."]
    assert sentence_spans("") == [] and sentence_spans("   ") == []
    assert sentences("No end mark at all") == ["No end mark at all"]
