import math

from bebshax.llm.adapters.embeddings import CANONICAL_DIM, HashEmbedding, fit_dim
from bebshax.memory.scoring import combined_score, cosine, recency_decay


def test_cosine_basics() -> None:
    assert cosine([1.0, 0.0], [1.0, 0.0]) == 1.0
    assert cosine([1.0, 0.0], [0.0, 1.0]) == 0.0
    assert cosine([1.0, 0.0], [-1.0, 0.0]) == -1.0
    assert cosine([], []) == 0.0
    assert cosine([1.0], [1.0, 2.0]) == 0.0  # dim mismatch → 0, never crashes


def test_recency_decay_halves_at_half_life() -> None:
    assert recency_decay(0) == 1.0
    assert math.isclose(recency_decay(48.0, half_life_hours=48.0), 0.5, rel_tol=1e-9)
    assert recency_decay(480.0) < 0.01


def test_combined_score_weights() -> None:
    # fresh + perfectly relevant + max importance = sum of weights
    assert math.isclose(combined_score(1.0, 0.0, 1.0), 0.60 + 0.25 + 0.15)
    # relevance dominates by default
    relevant_old = combined_score(1.0, 1000.0, 0.0)
    irrelevant_fresh = combined_score(0.0, 0.0, 0.0)
    assert relevant_old > irrelevant_fresh


async def test_hash_embedding_is_deterministic_normalized_and_sized() -> None:
    emb = HashEmbedding()
    [a1], [a2] = await emb.embed(["coffee subscription pricing"]), await emb.embed(
        ["coffee subscription pricing"]
    )
    assert a1 == a2
    assert len(a1) == CANONICAL_DIM
    assert math.isclose(math.sqrt(sum(x * x for x in a1)), 1.0, rel_tol=1e-9)


async def test_hash_embedding_reflects_lexical_similarity() -> None:
    emb = HashEmbedding()
    [coffee_a] = await emb.embed(["the coffee delivery arrived late again"])
    [coffee_b] = await emb.embed(["late coffee delivery frustrates customers"])
    [unrelated] = await emb.embed(["quantum entanglement in superconductors"])
    assert cosine(coffee_a, coffee_b) > cosine(coffee_a, unrelated)


def test_fit_dim_pads_truncates_and_normalizes() -> None:
    padded = fit_dim([3.0, 4.0], dim=4)
    assert len(padded) == 4
    assert math.isclose(math.sqrt(sum(x * x for x in padded)), 1.0)
    truncated = fit_dim([1.0] * 10, dim=4)
    assert len(truncated) == 4
