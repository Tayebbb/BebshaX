from datetime import timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateTable

from bebshax.jobs.orm import DurableJobs, JobAttempts, JobCheckpoints, JobOwners
from bebshax.jobs.store import Lease, LeaseLost, SQLJobStore, utcnow


class RecordingSession:
    def __init__(self):
        self.statements = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    def begin(self):
        return self

    def get_bind(self):
        return SimpleNamespace(dialect=postgresql.dialect())

    async def execute(self, statement):
        self.statements.append(statement)

    async def scalar(self, statement):
        self.statements.append(statement)
        return None

    async def scalars(self, statement):
        self.statements.append(statement)
        return SimpleNamespace(all=lambda: [])


def sql_text(statement) -> str:
    return str(statement.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))


def test_journal_schema_compiles_for_postgresql() -> None:
    statements = {model.__tablename__: sql_text(CreateTable(model.__table__)) for model in (JobOwners, DurableJobs, JobAttempts, JobCheckpoints)}
    jobs = statements["durable_jobs"]
    assert "UNIQUE (owner_id, idempotency_key)" in jobs
    assert "input_revision VARCHAR(255) NOT NULL" in jobs
    assert "payload_expired_at TIMESTAMP WITH TIME ZONE" in jobs
    assert "PRIMARY KEY (job_id, item_key)" in statements["job_checkpoints"]
    assert "ON DELETE CASCADE" in statements["job_attempts"]


async def test_owner_admission_lock_compiles_as_conflict_safe_insert_then_update() -> None:
    session = RecordingSession()
    store = SQLJobStore(lambda: session)
    await store._lock_owner(session, "owner-1")
    assert "ON CONFLICT DO NOTHING" in sql_text(session.statements[0])
    assert "UPDATE job_owners SET revision=(job_owners.revision + 1)" in sql_text(session.statements[1])
    assert "WHERE job_owners.owner_id = 'owner-1'" in sql_text(session.statements[1])


async def test_claim_fence_recovery_and_retention_compile_with_scoped_guards() -> None:
    session = RecordingSession()
    store = SQLJobStore(lambda: session)
    assert await store.claim("job-1", worker_id="worker-1") is None
    claim = sql_text(session.statements[-1])
    assert "durable_jobs.status = 'queued'" in claim
    assert "durable_jobs.worker_id = 'worker-1'" in claim
    assert "RETURNING durable_jobs.id" in claim
    lease = Lease("job-1", "owner-1", "fence-token", 2, utcnow() + timedelta(seconds=600), 60)
    with pytest.raises(LeaseLost):
        await store.fence(session, lease)
    fence = sql_text(session.statements[-1])
    for guard in ("owner_id = 'owner-1'", "lease_token = 'fence-token'", "attempts = 2", "lease_expires_at >", "deadline_at >"):
        assert guard in fence
    await store.recover(owner_id="owner-1")
    assert "FOR UPDATE SKIP LOCKED" in sql_text(session.statements[-1])
    await store.compact_terminal(before=utcnow())
    retention = sql_text(session.statements[-1])
    assert "FOR UPDATE SKIP LOCKED" in retention
    assert "'queued'" not in retention and "'running'" not in retention