"""Unit tests for bebshax.llm.json_utils — the single fence-strip/JSON-parse
utility that replaced seven duplicated inline variants."""

import pytest

from bebshax.llm.json_utils import parse_llm_json, strip_md_fences


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
        with pytest.raises(ValueError):
            parse_llm_json('{"a": 1')
