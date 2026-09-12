"""Legacy local transport is absent; remote envelope coverage lives beside this file."""

import inspect

from bebshax.llm.adapters import ollama_adapter


def test_retired_local_module_has_no_transport_or_stream_entrypoint() -> None:
    assert not any(inspect.isclass(value) or inspect.isfunction(value) for value in vars(ollama_adapter).values())