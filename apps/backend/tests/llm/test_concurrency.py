import asyncio

from bebshax.llm import ChatMessage, LLMRequest, PoolConfig, PoolRouter, TaskType, TokenUsage
from bebshax.llm.adapters.base import AdapterCompletion, ProviderAdapter, RouteCandidate


class CountingAdapter(ProviderAdapter):
    """Tracks peak in-flight complete() calls to verify semaphore behavior."""

    remote_processing = False

    def __init__(self) -> None:
        self.inflight = 0
        self.peak = 0
        self.total = 0

    async def candidates(self) -> list[RouteCandidate]:
        return [RouteCandidate(provider="counting", model="m")]

    async def complete(self, candidate: RouteCandidate, request: LLMRequest) -> AdapterCompletion:
        self.inflight += 1
        self.peak = max(self.peak, self.inflight)
        self.total += 1
        await asyncio.sleep(0.02)
        self.inflight -= 1
        return AdapterCompletion(text="ok", usage=TokenUsage(), provider="counting", model="m")


async def test_pool_concurrency_limit_respected_under_20_parallel_requests() -> None:
    # Brief acceptance TEST 7: 20 concurrent requests respect concurrency limits.
    adapter = CountingAdapter()
    router = PoolRouter(
        {"counting": adapter},
        pools={"conversation": PoolConfig(name="conversation", adapters=["counting"], max_concurrency=3)},
        task_pool_map={TaskType.PERSONA_RESPONSE: "conversation"},
    )

    def request() -> LLMRequest:
        return LLMRequest(
            task=TaskType.PERSONA_RESPONSE,
            messages=[ChatMessage(role="user", content="hi")],
        )

    results = await asyncio.gather(*[router.complete(request()) for _ in range(20)])

    assert len(results) == 20 and all(r.text == "ok" for r in results)
    assert adapter.total == 20
    assert adapter.peak <= 3, f"semaphore breached: peak={adapter.peak}"


async def test_pools_limit_independently() -> None:
    fast = CountingAdapter()
    slow = CountingAdapter()
    router = PoolRouter(
        {"fast": fast, "slow": slow},
        pools={
            "a": PoolConfig(name="a", adapters=["fast"], max_concurrency=1),
            "b": PoolConfig(name="b", adapters=["slow"], max_concurrency=4),
        },
        task_pool_map={TaskType.MEMORY_RETRIEVAL: "a", TaskType.CRITIC: "b"},
    )

    def request(task: TaskType) -> LLMRequest:
        return LLMRequest(task=task, messages=[ChatMessage(role="user", content="x")])

    await asyncio.gather(
        *[router.complete(request(TaskType.MEMORY_RETRIEVAL)) for _ in range(6)],
        *[router.complete(request(TaskType.CRITIC)) for _ in range(6)],
    )
    assert fast.peak <= 1
    assert slow.peak <= 4
