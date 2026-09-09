from bebshax.llm import POOLS, TASK_POOL_MAP, TaskType


def test_every_task_type_maps_to_an_existing_pool() -> None:
    for task in TaskType:
        assert task in TASK_POOL_MAP, f"{task} has no pool mapping"
        assert TASK_POOL_MAP[task] in POOLS, f"{task} maps to unknown pool"


def test_pools_have_adapters_and_positive_concurrency() -> None:
    for pool in POOLS.values():
        assert pool.adapters
        assert pool.max_concurrency >= 1


def test_emergency_pool_is_local_first() -> None:
    assert POOLS["emergency"].adapters[0] == "ollama"


def test_interactive_pools_prefer_openrouter() -> None:
    # Owner decision 2026-09-09: local Ollama measured 14-24 s/turn on the dev
    # machine under real load, so interactive replies prefer OpenRouter's fast
    # free models. Ollama stays LAST as the on-machine fallback (asserted by
    # test_every_pool_reaches_the_local_adapter).
    assert POOLS["conversation"].adapters[0] == "openrouter"
    assert POOLS["fast"].adapters[0] == "openrouter"
    assert POOLS["conversation"].adapters[-1] == "ollama"
    assert POOLS["fast"].adapters[-1] == "ollama"


def test_every_pool_reaches_the_local_adapter() -> None:
    # Cross-adapter fallback must terminate on-machine (brief §41/spec).
    for pool in POOLS.values():
        assert "ollama" in pool.adapters, f"pool {pool.name} never reaches local"
