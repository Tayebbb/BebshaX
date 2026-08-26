"""Per-attempt latency budgets by task class — data table, not code branches.

An attempt that exceeds its budget times out and the policy loop advances to
the next candidate (FAILURE_POLICIES[TIMEOUT].try_next_candidate). Budgets
apply to REMOTE adapters; local Ollama keeps its own transport timeout because
there is no provider queue to escape from.
"""

from __future__ import annotations

from bebshax.llm.types import TaskType

DEFAULT_ATTEMPT_TIMEOUT_S = 90.0

# Interactive surfaces (a human is watching a spinner).
_INTERACTIVE_S = 25.0
# Structured/generation calls (progress UI, retry affordable).
_STANDARD_S = 75.0
# Long-context synthesis (large outputs are legitimately slow).
_LONG_S = 150.0

ATTEMPT_TIMEOUTS_S: dict[TaskType, float] = {
    TaskType.PERSONA_INTERVIEW: _INTERACTIVE_S,
    TaskType.PERSONA_RESPONSE: _INTERACTIVE_S,
    TaskType.MEMORY_RETRIEVAL: _INTERACTIVE_S,
    TaskType.MEMORY_SUMMARIZATION: _INTERACTIVE_S,
    TaskType.EMERGENCY_FALLBACK: _INTERACTIVE_S,
    TaskType.PERSONA_GENERATION: _STANDARD_S,
    TaskType.PERSONA_REFINEMENT: _STANDARD_S,
    TaskType.PERSONA_VALIDATION: _STANDARD_S,
    TaskType.PERSONA_NARRATIVE: _STANDARD_S,
    TaskType.BEHAVIORAL_SIMULATION: _STANDARD_S,
    TaskType.EVIDENCE_EXTRACTION: _STANDARD_S,
    TaskType.EVIDENCE_CLASSIFICATION: _STANDARD_S,
    TaskType.CONTRADICTION_CHECK: _STANDARD_S,
    TaskType.CRITIC: _STANDARD_S,
    TaskType.STRUCTURED_OUTPUT: _STANDARD_S,
    TaskType.BROWSER_AGENT: _STANDARD_S,
    TaskType.TOOL_CALLING: _STANDARD_S,
    TaskType.REPORT_GENERATION: _LONG_S,
}


def attempt_timeout_s(task: TaskType) -> float:
    return ATTEMPT_TIMEOUTS_S.get(task, DEFAULT_ATTEMPT_TIMEOUT_S)
