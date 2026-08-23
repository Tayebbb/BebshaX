from bebshax.evaluation.persona_evaluator import REQUIRED_PERSONA_FIELDS
from bebshax.persona.schema import (
    EvidenceItem,
    GeneratedClaim,
    GeneratedPersona,
    ProvenanceClass,
    coerce_provenance,
)


def _generated(**claim_kwargs) -> GeneratedPersona:
    claim = GeneratedClaim(**claim_kwargs)
    filler = GeneratedClaim(value="filler", provenance="SYNTHETIC")
    return GeneratedPersona(
        name="Test",
        age=30,
        occupation="engineer",
        location="Berlin",
        income_range="mid",
        education="MSc",
        description="desc",
        goals=[claim],
        pain_points=[filler],
    )


def test_valid_citation_becomes_observed() -> None:
    ev = EvidenceItem(source="ds", text="users complain about late delivery")
    profile = coerce_provenance(
        _generated(value="hates late delivery", provenance="OBSERVED", evidence_ids=[ev.id]),
        business_id="b1",
        evidence=[ev],
    )
    goal = next(a for a in profile.attributes if a.key == "goal")
    assert goal.provenance_class == ProvenanceClass.OBSERVED
    assert goal.evidence_ids == [ev.id]


def test_bogus_citation_downgrades_to_inferred_and_strips_id() -> None:
    profile = coerce_provenance(
        _generated(value="x", provenance="OBSERVED", evidence_ids=["made-up"]),
        business_id="b1",
        evidence=[],
    )
    goal = next(a for a in profile.attributes if a.key == "goal")
    assert goal.provenance_class == ProvenanceClass.INFERRED
    assert goal.evidence_ids == []


def test_unknown_label_downgrades_to_synthetic() -> None:
    profile = coerce_provenance(
        _generated(value="x", provenance="TOTALLY_TRUE"), business_id="b1", evidence=[]
    )
    goal = next(a for a in profile.attributes if a.key == "goal")
    assert goal.provenance_class == ProvenanceClass.SYNTHETIC


def test_provenance_is_never_upgraded() -> None:
    ev = EvidenceItem(source="ds", text="some evidence")
    profile = coerce_provenance(
        _generated(value="x", provenance="SYNTHETIC", evidence_ids=[ev.id]),
        business_id="b1",
        evidence=[ev],
    )
    # cited valid evidence → OBSERVED is legitimate (citation is the ground truth)
    goal = next(a for a in profile.attributes if a.key == "goal")
    assert goal.provenance_class == ProvenanceClass.OBSERVED


def test_eval_dict_satisfies_phase11_evaluator_contract() -> None:
    profile = coerce_provenance(
        _generated(value="x", provenance="INFERRED"), business_id="b1", evidence=[]
    )
    eval_dict = profile.to_eval_dict()
    for field in REQUIRED_PERSONA_FIELDS:
        assert field in eval_dict and eval_dict[field] is not None, field
    assert all("provenance_class" in a for a in eval_dict["attributes"])
