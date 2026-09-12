import importlib.util

import pytest

from bebshax.llm.adapters import embeddings
from bebshax.llm.adapters.factory import build_default_adapters, build_embedding_backend


async def test_default_adapter_composition_is_remote_only() -> None:
    adapters = build_default_adapters()
    try:
        assert list(adapters) == ["freellmpool", "openrouter"]
    finally:
        for adapter in adapters.values():
            await adapter.aclose()


@pytest.mark.parametrize("backend", ["auto", "ollama", "banana"])
def test_removed_embedding_configuration_fails_closed(backend) -> None:
    with pytest.raises(ValueError, match="expected 'local' or 'freellmpool'"):
        build_embedding_backend(backend)


async def test_hash_embeddings_keep_the_same_space_and_vectors() -> None:
    backend = build_embedding_backend()
    assert backend.space == "local-hash-384"
    assert await backend.embed(["complete synthetic source text"]) == await embeddings.HashEmbedding().embed(
        ["complete synthetic source text"]
    )


def test_removed_embedding_implementations_are_not_exported() -> None:
    assert not hasattr(embeddings, "AutoEmbedding")
    assert not hasattr(embeddings, "OllamaEmbedding")
    assert not hasattr(embeddings, "DEFAULT_OLLAMA_EMBED_MODEL")


def test_real_local_adapter_implementation_is_removed() -> None:
    import importlib

    module = importlib.import_module("bebshax.llm.adapters.ollama_adapter")
    assert not hasattr(module, "OllamaAdapter")
    assert not hasattr(module, "DEFAULT_BASE_URL")
    assert not hasattr(module, "_required_ctx")