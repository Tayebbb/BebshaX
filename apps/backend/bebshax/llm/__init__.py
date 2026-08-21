"""BebshaX LLM abstraction layer.

Application code talks ONLY to `LLMService` with an `LLMRequest`.
Concrete providers (freellmpool, Ollama, ...) live behind `ProviderAdapter`
implementations in `bebshax.llm.adapters` — nothing else may import them.
"""

from bebshax.llm.failures import (
    FAILURE_POLICIES,
    AllCandidatesFailed,
    AttemptFailed,
    ContextWindowExceeded,
    FailureKind,
    FailurePolicy,
    LLMError,
)
from bebshax.llm.adapters.base import AdapterCompletion
from bebshax.llm.provenance import AttemptRecord, ProvenanceRecord
from bebshax.llm.service import LLMService, SingleAdapterLLMService
from bebshax.llm.types import ChatMessage, LLMRequest, LLMResult, TaskType, TokenUsage

__all__ = [
    "FAILURE_POLICIES",
    "AdapterCompletion",
    "AllCandidatesFailed",
    "AttemptFailed",
    "AttemptRecord",
    "ChatMessage",
    "ContextWindowExceeded",
    "FailureKind",
    "FailurePolicy",
    "LLMError",
    "LLMRequest",
    "LLMResult",
    "LLMService",
    "ProvenanceRecord",
    "SingleAdapterLLMService",
    "TaskType",
    "TokenUsage",
]
