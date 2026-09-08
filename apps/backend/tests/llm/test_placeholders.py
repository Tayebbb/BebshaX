"""bebshax.llm.placeholders — the prompts' own example strings are never content.

Table-driven: every entry of the data table is rejected; real sentences (even
ones that merely resemble an example or contain the word "question") pass.
"""

import pytest

from bebshax.llm.placeholders import PROMPT_PLACEHOLDERS, contains_placeholder, is_placeholder, normalise

_TABLE_ENTRIES = sorted(PROMPT_PLACEHOLDERS)

_VERBATIM_EXAMPLES = [
    # copilot / goal card
    "Conversational explanation and question to display to the user",
    "[specific hypothesis about their actual business]",
    "[Specific audience description based on their context]",
    "[Core assumption to validate]",
    "You want to research whether [specific hypothesis about their actual business]. [Key decision they need to make]. Does this capture what you're looking for?",
    # roles
    "ROLE TITLE IN CAPS",
    "ANOTHER ROLE",
    "Why this role is relevant",
    "ROLE NAME IN CAPS (max 4 words)",
    # persona template
    "Full Name",
    "Specific Job Title",
    "Descriptive Archetype",
    "The [Evocative Label]",
    "2-3 sentence vivid description of this person in the context of the product",
    "Realistic Income",
    "City, Country",
    # script
    "Question 1",
    "Question 2",
    # report
    "Finding 1 with concrete data",
    "Finding 2",
    "Recommendation 1",
    "Risk 1",
    "Opportunity 1",
    "Segment A",
    "Detailed target market overview",
    "Crisp 2-3 paragraph executive summary grounded in findings",
    "Market macro and competitive context",
    # judge schema
    "persona:<id>|report|interview:<id>|segment:<id>|evidence",
    "...",
]

_REAL_TEXT = [
    "What is the one question you ask yourself before ordering dinner online?",  # contains "question"
    "Question 1 for the walkers: how do you find new clients in winter?",  # starts like the example but is real
    "Dog owners in Berlin Mitte who travel for work at least twice a month.",
    "Time-poor consultant",  # a real archetype
    "Berlin, Germany",  # a real "City, Country" value
    "Software engineer at a fintech",  # a real occupation
    "Finding: 74% of respondents pay under 3,000 BDT per month for lunch.",
    "Recommendation: pilot with 20 owners before pricing above 18 EUR.",
    "persona:per_8f2a1c",  # a filled-in artifact reference
    "[Turn 2] She said the fee decides it.",  # brackets inside real text, not a whole-text slot
    "[Synthetic] 3 of 3 personas would pay 18 EUR [INFERRED]",  # labelled finding: starts AND ends with a bracket
    "[C2] Owners cite reliability over price [C4]",  # report prompt asks for exactly this citation style
    "I've reviewed your idea for on-demand dog walking. Which city do you launch in first?",
]


@pytest.mark.parametrize("entry", _TABLE_ENTRIES)
def test_every_table_entry_is_rejected(entry):
    assert is_placeholder(entry)


@pytest.mark.parametrize("text", _VERBATIM_EXAMPLES)
def test_prompt_example_strings_are_rejected_verbatim(text):
    assert is_placeholder(text)


@pytest.mark.parametrize("text", _REAL_TEXT)
def test_real_sentences_are_accepted(text):
    assert not is_placeholder(text)


def test_matching_ignores_case_whitespace_and_trailing_punctuation():
    assert is_placeholder("  conversational explanation   AND question to display\nto the user. ")
    assert is_placeholder("Question 1.")
    assert is_placeholder("FULL NAME")


@pytest.mark.parametrize(
    "text",
    [
        "[anything at all inside square brackets]",
        "<ISO 3166-1 alpha-2 of where this person lives, taken from the study context>",
        "<country name matching country_code>",
        "persona:<id>",
        "interview:<id>",
        "segment:<id>",
    ],
)
def test_unfilled_template_slots_are_rejected_by_shape(text):
    assert is_placeholder(text)


@pytest.mark.parametrize("value", [None, 42, 3.5, True, "", "   ", ["Question 1"], {"reply": "Question 1"}])
def test_non_strings_and_blanks_are_not_placeholders(value):
    assert not is_placeholder(value)


def test_contains_placeholder_over_iterables():
    assert contains_placeholder(["Dog owner", "Why this role is relevant"])
    assert contains_placeholder(("Lena", "Full Name"))
    assert not contains_placeholder(["Dog owner", "Books walks from her phone"])
    assert not contains_placeholder([])
    assert not contains_placeholder([None, 3, ""])


def test_table_is_stored_normalised():
    assert all(entry == normalise(entry) for entry in PROMPT_PLACEHOLDERS)
    assert "" not in PROMPT_PLACEHOLDERS
    assert len(PROMPT_PLACEHOLDERS) >= 55
