"""Batch interview turn retry.

Observed live: one transient route exhaustion (every candidate cooling or
timing out at the same moment) failed a whole background interview after a
single turn. A batch job now retries that one turn once after a pause and
records the retry; anything else still fails the interview honestly.
"""

import asyncio

import pytest

from bebshax.api import interviews as interviews_api
from bebshax.llm import AllCandidatesFailed
from bebshax.llm.provenance import ProvenanceRecord


class _Engine:
    def __init__(self, failures: list[BaseException]) -> None:
        self._failures = failures
        self.asked: list[str] = []

    async def ask(self, conversation_id: str, question: str, *, owner_id: str, deadline_at: float) -> None:
        assert owner_id == "batch-owner"
        assert deadline_at > asyncio.get_running_loop().time()
        self.asked.append(question)
        if self._failures:
            raise self._failures.pop(0)


def _exhausted() -> AllCandidatesFailed:
    return AllCandidatesFailed(ProvenanceRecord(request_id="r", task="PERSONA_INTERVIEW", pool="conversation"))


@pytest.fixture(autouse=True)
def _no_real_pause(monkeypatch):
    monkeypatch.setattr(interviews_api, "_BATCH_TURN_RETRY_DELAY_S", 0.0)


async def test_transient_exhaustion_is_retried_once_and_recorded() -> None:
    engine = _Engine([_exhausted()])
    entry: dict = {}
    await interviews_api._ask_with_one_retry(
        engine, "conv_1", "Q1", entry, owner_id="batch-owner", deadline_at=asyncio.get_running_loop().time() + 1,
    )
    assert engine.asked == ["Q1", "Q1"]
    assert entry["retried_turns"] == 1


async def test_second_exhaustion_propagates_so_the_interview_fails_honestly() -> None:
    engine = _Engine([_exhausted(), _exhausted()])
    entry: dict = {}
    with pytest.raises(AllCandidatesFailed):
        await interviews_api._ask_with_one_retry(
            engine, "conv_1", "Q1", entry, owner_id="batch-owner", deadline_at=asyncio.get_running_loop().time() + 1,
        )
    assert engine.asked == ["Q1", "Q1"] and entry["retried_turns"] == 1


async def test_other_errors_are_not_retried() -> None:
    engine = _Engine([RuntimeError("bug")])
    entry: dict = {}
    with pytest.raises(RuntimeError):
        await interviews_api._ask_with_one_retry(
            engine, "conv_1", "Q1", entry, owner_id="batch-owner", deadline_at=asyncio.get_running_loop().time() + 1,
        )
    assert engine.asked == ["Q1"] and "retried_turns" not in entry
