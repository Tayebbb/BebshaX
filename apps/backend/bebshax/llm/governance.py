"""Server-owned request context and remote processing approval, separate from input."""

from __future__ import annotations

from collections.abc import Awaitable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Literal, Self, TypeVar

from pydantic import BaseModel, ConfigDict, Field, model_validator


class LLMRequestContext(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    owner_user_id: str | None = Field(default=None, min_length=1)
    study_id: str | None = Field(default=None, min_length=1)
    data_classification: Literal["synthetic", "private"] = "private"

    @model_validator(mode="after")
    def require_private_owner(self) -> Self:
        if self.data_classification == "private" and not (self.owner_user_id or "").strip():
            raise ValueError("Private processing requires a verified owner")
        return self


class RemoteProcessingPolicy(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    policy_id: str = Field(default="deny-unapproved", min_length=1)
    synthetic_providers: frozenset[str] = frozenset()
    private_providers: frozenset[str] = frozenset()
    synthetic_openrouter_upstreams: frozenset[str] = frozenset()
    private_openrouter_upstreams: frozenset[str] = frozenset()

    def allowed_providers(self, classification: str) -> tuple[str, ...]:
        permissions = {"synthetic": self.synthetic_providers, "private": self.private_providers}
        return tuple(sorted(permissions.get(classification, frozenset())))

    def allowed_openrouter_upstreams(self, classification: str) -> tuple[str, ...]:
        permissions = {"synthetic": self.synthetic_openrouter_upstreams, "private": self.private_openrouter_upstreams}
        return tuple(sorted(permissions.get(classification, frozenset())))


@dataclass(frozen=True)
class DispatchApproval:
    provider_ids: tuple[str, ...]
    openrouter_upstreams: tuple[str, ...]


_request_context: ContextVar[LLMRequestContext | None] = ContextVar("llm_request_context", default=None)
_dispatch_approval: ContextVar[DispatchApproval | None] = ContextVar("llm_dispatch_approval", default=None)
_OperationResult = TypeVar("_OperationResult")


def get_dispatch_approval() -> DispatchApproval | None:
    return _dispatch_approval.get()


async def governed_operation(
    operation: Awaitable[_OperationResult], provider_ids: tuple[str, ...], openrouter_upstreams: tuple[str, ...],
) -> _OperationResult:
    token = _dispatch_approval.set(DispatchApproval(provider_ids, openrouter_upstreams))
    try:
        return await operation
    finally:
        _dispatch_approval.reset(token)


def get_llm_request_context() -> LLMRequestContext | None:
    return _request_context.get()


@contextmanager
def llm_request_context(context: LLMRequestContext) -> Iterator[None]:
    token = _request_context.set(context)
    try:
        yield
    finally:
        _request_context.reset(token)