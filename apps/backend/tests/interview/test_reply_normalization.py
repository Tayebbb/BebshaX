"""L12: deterministic reply FORMAT normalization — content is never mutated."""

import pytest

from bebshax.interview.normalization import normalize_reply


def test_plain_reply_passes_through_unchanged() -> None:
    text = "Honestly, I'd hesitate at that price — my monthly budget is tight."
    assert normalize_reply(text, "Alex Mercer") == text


def test_closed_think_block_is_stripped() -> None:
    text = "<think>The user asks about price. Budget is 400.</think>I'd say that's too costly for me."
    assert normalize_reply(text) == "I'd say that's too costly for me."


def test_multiline_reasoning_block_is_stripped() -> None:
    text = "<reasoning>\nstep 1\nstep 2\n</reasoning>\n\nI usually shop weekly."
    assert normalize_reply(text) == "I usually shop weekly."


def test_dangling_open_tag_drops_only_the_tag() -> None:
    # Guessing where invisible reasoning ends risks deleting real content.
    text = "<think>Well, I take the bus most days."
    assert normalize_reply(text) == "Well, I take the bus most days."


def test_whole_reply_fence_is_unwrapped() -> None:
    text = "```markdown\nI would try it for a month first.\n```"
    assert normalize_reply(text) == "I would try it for a month first."


def test_persona_name_script_label_is_stripped() -> None:
    assert (
        normalize_reply("Alex Mercer: I mostly use bKash for payments.", "Alex Mercer")
        == "I mostly use bKash for payments."
    )
    assert (
        normalize_reply("**Alex:** I mostly use bKash.", "Alex Mercer")
        == "I mostly use bKash."
    )


def test_generic_labels_stripped_without_persona_name() -> None:
    assert normalize_reply("Persona: I ride 40km a day.") == "I ride 40km a day."
    assert normalize_reply("Interviewer: I ride 40km a day.") == "I ride 40km a day."


def test_whole_line_bold_label_leaves_no_residue() -> None:
    assert (
        normalize_reply("**Alex: I use bKash for everything**", "Alex Mercer")
        == "I use bKash for everything"
    )


def test_label_only_on_first_line_content_colons_survive() -> None:
    text = "My rule is simple: never spend more than I earn."
    assert normalize_reply(text, "Alex Mercer") == text


def test_never_returns_empty() -> None:
    text = "<think>only reasoning, nothing else</think>"
    assert normalize_reply(text) == text.strip()


@pytest.mark.parametrize("junk", ["", "   "])
def test_empty_input_stays_empty_string(junk: str) -> None:
    assert normalize_reply(junk) == ""
