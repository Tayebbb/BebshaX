"""Persona generation runs: stale-run recovery and redacted failure messages."""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from bebshax.db.models import Base, MarketSegments, PersonaGenerationRuns, Studies
from bebshax.personas import service as service_module
from bebshax.personas.service import STALE_RUN_AFTER, PersonaGenerationService

_SECRET = "Bearer sk-live-do-not-leak"


@pytest.fixture
async def seeded_maker():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        session.add(Studies(id="std_runs", title="Runs", status="active", step=2))
        session.add(
            MarketSegments(
                id="seg_runs_1", study_id="std_runs", segmentation_run_id="srun_1",
                name="Budget Students", cluster_label="c0", description="d",
                population_count=10, population_percentage=100.0,
                characteristics={"demographics": {"age_range": [19, 23]}},
            )
        )
        await session.commit()
    yield maker
    await engine.dispose()


def _stuck_run(run_id: str, age: timedelta, status: str = "saving_personas") -> PersonaGenerationRuns:
    started = datetime.now(timezone.utc) - age
    return PersonaGenerationRuns(
        id=run_id, study_id="std_runs", status=status, target_count=2, generated_count=0,
        valid_count=0, warning_count=0, started_at=started, created_at=started,
    )


async def test_stale_active_run_is_marked_failed_and_no_longer_blocks(seeded_maker):
    async with seeded_maker() as session:
        session.add(_stuck_run("pgen_stale", STALE_RUN_AFTER + timedelta(minutes=1)))
        await session.commit()

        service = PersonaGenerationService(session)
        run, personas = await service.create_generation_run(
            study_id="std_runs", target_count=2, distribution_strategy="equal"
        )
        assert run.status == "completed" and len(personas) == 2

        stale = await session.get(PersonaGenerationRuns, "pgen_stale")
        assert stale.status == "failed"
        assert stale.completed_at is not None
        assert stale.error_message.startswith("StaleRun:")


@pytest.mark.parametrize("status", ["generating_personas", "saving_personas", "pending"])
async def test_recent_active_run_still_blocks_a_new_one(seeded_maker, status):
    async with seeded_maker() as session:
        session.add(_stuck_run("pgen_live", timedelta(minutes=5), status=status))
        await session.commit()

        service = PersonaGenerationService(session)
        with pytest.raises(ValueError, match="already in progress"):
            await service.create_generation_run(study_id="std_runs", target_count=1)

        live = await session.get(PersonaGenerationRuns, "pgen_live")
        assert live.status == status  # untouched


async def test_generation_failure_persists_class_name_not_the_message(seeded_maker, monkeypatch, caplog):
    async def exploding(**_kwargs):
        raise RuntimeError(f"upstream rejected {_SECRET}")

    monkeypatch.setattr(service_module, "generate_personas_for_study", exploding)

    async with seeded_maker() as session:
        service = PersonaGenerationService(session)
        with caplog.at_level("ERROR"), pytest.raises(RuntimeError):
            await service.create_generation_run(study_id="std_runs", target_count=1)

        run = (await session.execute(select(PersonaGenerationRuns))).scalar_one()
        assert run.status == "failed"
        assert run.error_message.startswith("RuntimeError (ref ")
        assert _SECRET not in run.error_message
    # Operators still get the full text in the log.
    assert any(r.exc_info and _SECRET in str(r.exc_info[1]) for r in caplog.records)
