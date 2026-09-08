"""Unit tests for bebshax.llm.json_utils — the single fence-strip/JSON-parse
utility that replaced seven duplicated inline variants."""

import pytest

from bebshax.llm.json_utils import parse_llm_json, repair_json_delimiters, strip_md_fences, unwrap_list


class TestStripMdFences:
    def test_unfenced_text_is_returned_stripped(self):
        assert strip_md_fences('  {"a": 1}  ') == '{"a": 1}'

    def test_plain_fence_is_stripped(self):
        assert strip_md_fences('```\n{"a": 1}\n```') == '{"a": 1}'

    def test_json_language_tag_is_stripped(self):
        assert strip_md_fences('```json\n{"a": 1}\n```') == '{"a": 1}'

    def test_arbitrary_language_tag_is_stripped(self):
        assert strip_md_fences('```javascript\n[1, 2]\n```') == "[1, 2]"

    def test_inner_backticks_survive(self):
        # Only the OUTER fence is stripped; content stays intact.
        assert strip_md_fences('```json\n{"code": "x"}\n```') == '{"code": "x"}'

    def test_crlf_fences(self):
        assert strip_md_fences('```json\r\n{"a": 1}\r\n```') == '{"a": 1}'


class TestParseLlmJson:
    def test_bare_object(self):
        assert parse_llm_json('{"reply": "hi"}') == {"reply": "hi"}

    def test_bare_array(self):
        assert parse_llm_json("[1, 2, 3]") == [1, 2, 3]

    def test_fenced_object_with_json_tag(self):
        assert parse_llm_json('```json\n{"a": [1, 2]}\n```') == {"a": [1, 2]}

    def test_fenced_array_plain_fence(self):
        assert parse_llm_json('```\n[{"id": "r1"}]\n```') == [{"id": "r1"}]

    def test_leading_prose_before_object(self):
        text = 'Sure! Here is the JSON you asked for:\n{"ok": true}'
        assert parse_llm_json(text) == {"ok": True}

    def test_leading_prose_before_array_returns_array_not_inner_object(self):
        # Regression guard: the array must win over its first inner object.
        text = 'Here you go: [{"a": 1}, {"a": 2}] — hope that helps!'
        assert parse_llm_json(text) == [{"a": 1}, {"a": 2}]

    def test_trailing_prose_after_object(self):
        text = '{"a": 1}\nLet me know if you need anything else.'
        assert parse_llm_json(text) == {"a": 1}

    def test_prose_wrapped_fenced_payload(self):
        text = 'Model reasoning...\n```json\n{"done": 1}\n```'
        # Fence is not at the start, so the block extractor recovers the object.
        assert parse_llm_json(text) == {"done": 1}

    def test_invalid_input_raises_value_error(self):
        with pytest.raises(ValueError):
            parse_llm_json("I could not produce JSON, sorry.")

    def test_empty_input_raises_value_error(self):
        with pytest.raises(ValueError):
            parse_llm_json("")

    def test_broken_json_raises_value_error(self):
        # Cut off before its closers: the truncation signature, never "repaired".
        with pytest.raises(ValueError):
            parse_llm_json('{"a": 1')


# Verbatim llama3.2:3b reply from the business-matrix run (2026-09-08): three
# perfectly usable questions, array closed with '}' instead of ']'. Two such
# replies in a row turned a whole study's script step into a 502.
_LIVE_MISMATCHED_CLOSER = (
    '{"questions": ["Can you walk me through your current process for generating the '
    'sustainability report required by EU CSRD?", "How do you currently handle the discrepancy '
    'between your existing ERP data and the reporting requirements of EU CSRD?", "Would you be '
    'willing to pay a premium for a tool that could automate the mapping of EU CSRD requirements '
    'onto your existing ERP data?"}}'
)


class TestDelimiterRepair:
    def test_live_mismatched_array_closer_is_parsed(self):
        parsed = parse_llm_json(_LIVE_MISMATCHED_CLOSER)
        assert isinstance(parsed["questions"], list)
        assert len(parsed["questions"]) == 3
        assert parsed["questions"][2].endswith("onto your existing ERP data?")

    def test_payload_cut_off_before_its_closers_is_not_finished_for_the_model(self):
        # A report reply cut by the token limit right after a complete value
        # must not be "repaired" into a report that is silently missing sections.
        assert repair_json_delimiters('{"roles": [{"role": "A"}, {"role": "B"}') is None
        result = None
        try:
            result = parse_llm_json('{"executive_summary": "...", "key_findings": ["a"]')
        except ValueError:
            pass
        # The block extractor may still surface the inner array (pre-existing
        # leniency); it must never surface the truncated report object.
        assert not (isinstance(result, dict) and "executive_summary" in result)

    def test_trailing_comma_before_closer_is_dropped(self):
        assert parse_llm_json('{"items": [1, 2, 3,], }') == {"items": [1, 2, 3]}

    def test_stray_extra_closer_is_dropped(self):
        assert parse_llm_json('{"a": [1, 2]}]') == {"a": [1, 2]}

    def test_brackets_inside_strings_are_never_touched(self):
        text = '{"q": "Use [brackets] and {braces} freely?", "list": ["a"}}'
        assert parse_llm_json(text) == {"q": "Use [brackets] and {braces} freely?", "list": ["a"]}

    def test_escaped_quote_inside_string_keeps_string_state(self):
        text = '{"q": "She said \\"go\\" then left", "n": [1}}'
        assert parse_llm_json(text) == {"q": 'She said "go" then left', "n": [1]}

    def test_repaired_payload_with_trailing_prose_is_recovered(self):
        text = '{"questions": ["a", "b"}} Hope this helps!'
        assert parse_llm_json(text) == {"questions": ["a", "b"]}

    def test_cut_off_mid_string_is_not_finished_for_the_model(self):
        # Half a sentence handed back as a question would be a fabrication.
        assert repair_json_delimiters('{"questions": ["How do you currently han') is None
        with pytest.raises(ValueError):
            parse_llm_json('{"questions": ["How do you currently han')

    def test_valid_json_reports_nothing_to_repair(self):
        assert repair_json_delimiters('{"a": [1, {"b": 2}]}') is None

    def test_mis_repair_never_yields_a_fragment(self):
        # A MISSING opener cannot be repaired; the repaired text is still invalid
        # and the inner "[1, 2]" must not be mined out of it as the answer.
        with pytest.raises(ValueError):
            parse_llm_json('{"a": [1, 2}, {"b": 3}]')

    def test_repair_never_changes_string_contents(self):
        original = '{"text": "keep, this] exactly {as} is", "tail": [1, 2}}'
        assert parse_llm_json(original)["text"] == "keep, this] exactly {as} is"


class TestUnwrapList:
    """json_object mode forbids a top-level array, so models wrap (or, observed
    live, return one item). The list is recovered without adding anything."""

    def test_bare_list_is_returned_as_is(self):
        assert unwrap_list([1, 2]) == [1, 2]

    def test_preferred_key_wins(self):
        parsed = {"note": ["ignored"], "roles": [{"role": "A"}]}
        assert unwrap_list(parsed, keys=("roles",)) == [{"role": "A"}]

    def test_only_list_value_is_used_for_unknown_wrappers(self):
        parsed = {"persona_role_suggestions": [{"role": "A"}], "count": 1}
        assert unwrap_list(parsed, keys=("roles",), item_keys=("role",)) == [{"role": "A"}]

    def test_single_item_object_becomes_a_one_item_list(self):
        item = {"id": "role_1", "role": "INDEPENDENT PIANO PEDAGOGUE", "count": 3}
        assert unwrap_list(item, keys=("roles",), item_keys=("role",)) == [item]

    def test_item_with_its_own_list_field_is_still_one_item(self):
        item = {"name": "Lars", "attributes": [{"category": "Goals"}]}
        assert unwrap_list(item, keys=("personas",), item_keys=("name",)) == [item]

    def test_ambiguous_or_foreign_shapes_yield_nothing(self):
        assert unwrap_list({"a": [1], "b": [2]}, keys=("roles",)) == []
        assert unwrap_list({"answer": "no list here"}, keys=("roles",), item_keys=("role",)) == []
        assert unwrap_list("text") == []
        assert unwrap_list(None) == []
