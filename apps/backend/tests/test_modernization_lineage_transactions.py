from __future__ import annotations

from types import SimpleNamespace

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from bebshax.db.models import Base, MarketSegments, SegmentationRuns, Studies


@pytest.fixture
async def lineage_maker(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'lineage.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    try:
        yield async_sessionmaker(engine, expire_on_commit=False)
    finally:
        await engine.dispose()


async def test_failed_segment_flush_rolls_back_before_recording_original_run(lineage_maker, monkeypatch):
    from bebshax.segmentation import service as segmentation

    monkeypatch.setattr(segmentation, "check_segmentation_readiness", lambda *args: SimpleNamespace(can_run=True))
    monkeypatch.setattr(segmentation, "select_segmentation_variables", lambda *args: [])
    monkeypatch.setattr(segmentation, "cluster_dataset_populations", lambda **kwargs: [])

    async def invalid_segments(**kwargs):
        return [SimpleNamespace(
            name=None, cluster_label="invalid", description="Invalid test segment",
            population_count=1, population_percentage=100, confidence_score=0.5,
            status="ready", characteristics={}, variable_distributions={},
            evidence_citations=[], differentiation_summary="Synthetic test",
        )]

    monkeypatch.setattr(segmentation, "interpret_market_segments", invalid_segments)
    async with lineage_maker() as session:
        session.add(Studies(id="seg_study", title="Fixture", user_id="owner_one"))
        await session.commit()
        with pytest.raises(IntegrityError):
            await segmentation.SegmentationEngineService(session).run_segmentation("seg_study", user_id="owner_one")
    async with lineage_maker() as session:
        runs = (await session.scalars(select(SegmentationRuns))).all()
        assert len(runs) == 1
        assert runs[0].status == "failed"
        assert runs[0].configuration["error_code"] == "run_failed"
        assert runs[0].completed_at is not None
        assert (await session.scalars(select(MarketSegments))).all() == []