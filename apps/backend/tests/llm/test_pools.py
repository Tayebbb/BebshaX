from bebshax.llm import POOLS, TASK_POOL_MAP, TaskType


def test_every_task_type_maps_to_an_existing_pool() -> None:
    for task in TaskType:
        assert task in TASK_POOL_MAP, f"{task} has no pool mapping"
        assert TASK_POOL_MAP[task] in POOLS, f"{task} maps to unknown pool"


def test_pools_have_adapters_and_positive_concurrency() -> None:
    for pool in POOLS.values():
        assert pool.adapters
        assert pool.max_concurrency >= 1


def test_emergency_pool_uses_independent_remote_fallback() -> None:
    assert POOLS["emergency"].adapters == ["freellmpool", "openrouter"]


def test_all_pools_prefer_freellmpool_with_openrouter_secondary() -> None:
    for pool in POOLS.values():
        assert pool.adapters == ["freellmpool", "openrouter"]


def test_local_pool_is_removed() -> None:
    assert "local" not in POOLS
