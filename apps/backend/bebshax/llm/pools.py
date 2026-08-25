"""Model pools and the task→pool map — configuration as data, not code branches.

Adapter names refer to the keys handed to PoolRouter (production names come
from bebshax.llm.adapters.factory). Ordering inside a pool = preference order;
every pool ends at the local adapter so cross-adapter fallback terminates
on-machine, except `emergency`, which is local-FIRST.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from bebshax.llm.types import TaskType

OPENROUTER = "openrouter"
FREELLMPOOL = "freellmpool"
OLLAMA = "ollama"


class PoolConfig(BaseModel):
    name: str
    adapters: list[str] = Field(min_length=1)
    max_concurrency: int = Field(default=4, ge=1)


POOLS: dict[str, PoolConfig] = {
    p.name: p
    for p in [
        PoolConfig(name="reasoning", adapters=[OPENROUTER, FREELLMPOOL, OLLAMA], max_concurrency=2),
        PoolConfig(name="conversation", adapters=[OPENROUTER, FREELLMPOOL, OLLAMA], max_concurrency=5),
        PoolConfig(name="long_context", adapters=[OPENROUTER, FREELLMPOOL, OLLAMA], max_concurrency=2),
        PoolConfig(name="structured", adapters=[OPENROUTER, FREELLMPOOL, OLLAMA], max_concurrency=3),
        PoolConfig(name="fast", adapters=[OPENROUTER, FREELLMPOOL, OLLAMA], max_concurrency=5),
        PoolConfig(name="local", adapters=[OLLAMA], max_concurrency=2),
        PoolConfig(name="emergency", adapters=[OLLAMA, FREELLMPOOL], max_concurrency=2),
    ]
}

TASK_POOL_MAP: dict[TaskType, str] = {
    TaskType.PERSONA_GENERATION: "reasoning",
    TaskType.PERSONA_REFINEMENT: "reasoning",
    TaskType.PERSONA_VALIDATION: "reasoning",
    TaskType.PERSONA_INTERVIEW: "conversation",
    TaskType.PERSONA_RESPONSE: "conversation",
    TaskType.EVIDENCE_EXTRACTION: "structured",
    TaskType.EVIDENCE_CLASSIFICATION: "structured",
    TaskType.MEMORY_RETRIEVAL: "fast",
    TaskType.MEMORY_SUMMARIZATION: "fast",
    TaskType.CONTRADICTION_CHECK: "reasoning",
    TaskType.CRITIC: "reasoning",
    TaskType.REPORT_GENERATION: "long_context",
    TaskType.STRUCTURED_OUTPUT: "structured",
    TaskType.PERSONA_NARRATIVE: "reasoning",
    TaskType.BEHAVIORAL_SIMULATION: "reasoning",
    TaskType.BROWSER_AGENT: "structured",
    TaskType.TOOL_CALLING: "structured",
    TaskType.EMERGENCY_FALLBACK: "emergency",
}
