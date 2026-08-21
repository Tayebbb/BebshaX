"""Tests for database models with SQLite backend."""

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from bebshax.db.models import Businesses, LLMRequests, ModelRegistry, Personas
from bebshax.llm.types import TaskType


@pytest.mark.asyncio
async def test_create_business(async_session: AsyncSession) -> None:
    """Test creating a business record."""
    business_id = str(uuid4())
    business = Businesses(
        id=business_id,
        name="Test Business",
        description="A test business",
    )

    async_session.add(business)
    await async_session.commit()

    # Verify it was persisted
    result = await async_session.get(Businesses, business_id)
    assert result is not None
    assert result.name == "Test Business"


@pytest.mark.asyncio
async def test_create_llm_request(async_session: AsyncSession) -> None:
    """Test creating an LLM request provenance record."""
    request_id = "test_request_001"
    record = LLMRequests(
        request_id=request_id,
        task=TaskType.PERSONA_GENERATION,
        pool="reasoning",
        persona_id="persona_123",
        routing_path=["freellmpool/auto", "ollama/local"],
        attempts=[],
        served_by_provider="freellmpool",
        request_model="gpt-4",
        response_model="gpt-4",
        input_tokens=100,
        output_tokens=200,
        total_latency_ms=1500.5,
        success=True,
    )

    async_session.add(record)
    await async_session.commit()

    # Verify it was persisted
    result = await async_session.get(LLMRequests, request_id)
    assert result is not None
    assert result.task == TaskType.PERSONA_GENERATION
    assert result.success is True
    assert result.input_tokens == 100


@pytest.mark.asyncio
async def test_llm_request_with_attempts_json(async_session: AsyncSession) -> None:
    """Test LLM request with JSONB attempts (stored as JSON in SQLite)."""
    request_id = "test_request_attempts"
    attempts = [
        {
            "attempt_number": 1,
            "provider": "freellmpool",
            "model": "mistral",
            "success": False,
            "failure_kind": "RATE_LIMITED",
        },
        {
            "attempt_number": 2,
            "provider": "ollama",
            "model": "qwen",
            "success": True,
            "failure_kind": None,
        },
    ]

    record = LLMRequests(
        request_id=request_id,
        task=TaskType.PERSONA_INTERVIEW,
        attempts=attempts,
        served_by_provider="ollama",
        request_model="qwen",
        success=True,
    )

    async_session.add(record)
    await async_session.commit()

    result = await async_session.get(LLMRequests, request_id)
    assert result is not None
    assert len(result.attempts) == 2
    assert result.attempts[0]["failure_kind"] == "RATE_LIMITED"
    assert result.attempts[1]["success"] is True


@pytest.mark.asyncio
async def test_create_model_registry(async_session: AsyncSession) -> None:
    """Test creating a model registry entry."""
    model_id = "freellmpool/gpt-4"
    model = ModelRegistry(
        id=model_id,
        provider_name="freellmpool",
        model_name="gpt-4",
        enabled=True,
        context_window=8192,
        supports_tools=True,
        supports_json=True,
        supports_vision=False,
        reasoning_level="advanced",
        quality_score=0.95,
        latency_score=0.8,
        health_score=0.99,
    )

    async_session.add(model)
    await async_session.commit()

    result = await async_session.get(ModelRegistry, model_id)
    assert result is not None
    assert result.provider_name == "freellmpool"
    assert result.quality_score == 0.95


@pytest.mark.asyncio
async def test_persona_with_business_fk(async_session: AsyncSession) -> None:
    """Test creating a persona with foreign key to business."""
    business_id = str(uuid4())
    persona_id = str(uuid4())

    business = Businesses(
        id=business_id,
        name="Test Business",
    )
    async_session.add(business)
    await async_session.flush()

    persona = Personas(
        id=persona_id,
        business_id=business_id,
        name="John Doe",
        status="active",
        version=1,
        generation_model="gpt-4",
    )
    async_session.add(persona)
    await async_session.commit()

    result = await async_session.get(Personas, persona_id)
    assert result is not None
    assert result.business_id == business_id
    assert result.name == "John Doe"


@pytest.mark.asyncio
async def test_llm_request_nullable_persona_id(async_session: AsyncSession) -> None:
    """Test that persona_id is nullable (for failed generations)."""
    request_id = "test_failed_generation"

    # Create a provenance record without persona_id
    record = LLMRequests(
        request_id=request_id,
        task=TaskType.PERSONA_GENERATION,
        persona_id=None,  # No persona yet
        served_by_provider="freellmpool",
        request_model="gpt-4",
        success=False,
    )

    async_session.add(record)
    await async_session.commit()

    result = await async_session.get(LLMRequests, request_id)
    assert result is not None
    assert result.persona_id is None
    assert result.success is False


@pytest.mark.asyncio
async def test_datetime_defaults(async_session: AsyncSession) -> None:
    """Test that datetime defaults are set correctly."""
    business_id = str(uuid4())

    business = Businesses(
        id=business_id,
        name="Test Business",
    )
    async_session.add(business)
    await async_session.commit()

    result = await async_session.get(Businesses, business_id)
    assert result is not None
    assert result.created_at is not None
    assert isinstance(result.created_at, datetime)
    # For SQLite, timezone info might not be preserved; just check it's a datetime
