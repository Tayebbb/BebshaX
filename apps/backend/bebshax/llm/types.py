"""Core request/response types for the LLM abstraction. Provider-agnostic."""

from __future__ import annotations

import uuid
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field

from bebshax.llm.provenance import ProvenanceRecord


class TaskType(StrEnum):
    """The application always knows its task — no LLM is used to classify these."""

    PERSONA_GENERATION = "PERSONA_GENERATION"
    PERSONA_REFINEMENT = "PERSONA_REFINEMENT"
    PERSONA_VALIDATION = "PERSONA_VALIDATION"
    PERSONA_INTERVIEW = "PERSONA_INTERVIEW"
    PERSONA_RESPONSE = "PERSONA_RESPONSE"
    EVIDENCE_EXTRACTION = "EVIDENCE_EXTRACTION"
    EVIDENCE_CLASSIFICATION = "EVIDENCE_CLASSIFICATION"
    MEMORY_RETRIEVAL = "MEMORY_RETRIEVAL"
    MEMORY_SUMMARIZATION = "MEMORY_SUMMARIZATION"
    CONTRADICTION_CHECK = "CONTRADICTION_CHECK"
    CRITIC = "CRITIC"
    REPORT_GENERATION = "REPORT_GENERATION"
    STRUCTURED_OUTPUT = "STRUCTURED_OUTPUT"
    BROWSER_AGENT = "BROWSER_AGENT"
    TOOL_CALLING = "TOOL_CALLING"
    PERSONA_NARRATIVE = "PERSONA_NARRATIVE"
    BEHAVIORAL_SIMULATION = "BEHAVIORAL_SIMULATION"
    EMERGENCY_FALLBACK = "EMERGENCY_FALLBACK"


class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant", "tool"]
    content: str


class TokenUsage(BaseModel):
    input_tokens: int | None = None
    output_tokens: int | None = None


class LLMRequest(BaseModel):
    request_id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    task: TaskType
    messages: list[ChatMessage]
    json_mode: bool = False
    tools_required: bool = False
    max_output_tokens: int | None = Field(default=None, gt=0, strict=True)
    temperature: float | None = Field(default=None, ge=0, le=2, allow_inf_nan=False)
    persona_id: str | None = None
    conversation_id: str | None = None
    owner_user_id: str | None = None
    study_id: str | None = None
    data_classification: Literal["synthetic", "private"] | None = None
    # §7 model selection: None = Auto (router decides). A preference PRIORITIZES
    # matching routes — eligibility, policies and fallback still apply, so an
    # unavailable preferred model degrades to Auto instead of failing.
    preferred_provider: str | None = None
    preferred_model: str | None = None

    def retry_copy(self) -> "LLMRequest":
        """The same request under a NEW request_id. Application-level retries
        (an unusable reply is re-asked once) must not reuse the id: every
        ``complete()`` call writes its own provenance row keyed by it."""
        return self.model_copy(update={"request_id": uuid.uuid4().hex})


class LLMResult(BaseModel):
    text: str
    provider: str
    model: str
    usage: TokenUsage = Field(default_factory=TokenUsage)
    provenance: ProvenanceRecord
