"""Local-model membership is synthetic provenance, never observed study evidence."""

import json

import pytest

from bebshax.personas.ml_adapter import MLPersonaAdapter


_ROLES = [
    {
        "id": "role_primary",
        "role": "PRIMARY USER",
        "description": "Meal planning customer",
        "count": 1,
        "selected": True,
    }
]


@pytest.mark.parametrize("ml_api_app", ["missing"], indirect=True)
def test_missing_local_model_is_an_explicit_503_never_a_skeleton_persona(ml_api_app, ml_auth_headers):
    ml_api_app.app.state.llm_router = None
    response = ml_api_app.post(
        "/api/study/generate-personas",
        json={"study_prompt": "Food delivery and meal planning", "roles": _ROLES},
        headers=ml_auth_headers,
    )
    assert response.status_code == 503
    assert response.json()["error_code"] == "ml_persona_unavailable"
    assert response.json()["request_id"]
    assert ml_api_app.app.state.ml_test_llm.calls == []


def test_zero_grounding_without_evidence_is_labeled_as_synthetic_proxy(ml_api_app, ml_auth_headers):
    response = ml_api_app.post(
        "/api/study/generate-personas",
        json={"study_prompt": "Food delivery and meal planning", "roles": _ROLES},
        headers=ml_auth_headers,
    )
    assert response.status_code == 200, response.text
    result = response.json()
    assert len(result["personas"]) == 1 and result["failed_roles"] == []
    persona = result["personas"][0]
    assert persona["grounding_ratio"] == 0.0
    assert persona["grounding_basis"] == "synthetic_training_proxy"
    assert persona["evidence_claim_count"] == 0
    assert persona["generation_model"].startswith("bebshax-persona-ml/")
    assert ml_api_app.app.state.ml_test_llm.calls == []


def test_all_study_claims_inform_selection_without_becoming_observed_persona_facts(
    ml_api_app, ml_auth_headers, ml_study, monkeypatch,
):
    contexts = []
    original_generate = MLPersonaAdapter.generate

    async def capture(adapter, context, *args, **kwargs):
        contexts.append(context)
        return await original_generate(adapter, context, *args, **kwargs)

    monkeypatch.setattr(MLPersonaAdapter, "generate", capture)
    response = ml_api_app.post(
        "/api/study/generate-personas",
        json={"study_id": ml_study, "study_prompt": "Food delivery and meal planning", "roles": _ROLES},
        headers=ml_auth_headers,
    )
    assert response.status_code == 200, response.text
    research = json.dumps(contexts[0].research)
    for index in range(7):
        assert f"Meal planning research claim {index}" in research
    persona = response.json()["personas"][0]
    assert persona["evidence_claim_count"] == 7
    assert persona["grounding_ratio"] == persona["confidence"] == 0.0
    assert persona["grounding_basis"] == "synthetic_training_proxy"
    assert persona["evidence_citations"] == []
    assert all(
        attribute["provenance_class"] == "SYNTHETIC" and attribute["evidence_ids"] == [] and attribute["evidence"] is None
        for attribute in persona["attributes"]
    )
    assert ml_api_app.app.state.ml_test_llm.calls == []


def test_llm_self_declared_observed_claims_cannot_replace_local_personas(ml_api_app, ml_auth_headers, ml_study):
    adapter = ml_api_app.app.state.ml_test_llm
    for route in adapter._routes.values():
        route.reply = json.dumps({"personas": [{
            "name": "Forbidden LLM Persona", "attributes": [{
                "category": "Goals", "title": "Unverified goal", "provenance_class": "OBSERVED", "evidence": ["C1"],
            }],
        }]})
    response = ml_api_app.post(
        "/api/study/generate-personas",
        json={"study_id": ml_study, "study_prompt": "Food delivery and meal planning", "roles": _ROLES},
        headers=ml_auth_headers,
    )
    assert response.status_code == 200, response.text
    persona = response.json()["personas"][0]
    assert persona["grounding_ratio"] == 0.0
    assert persona["grounding_basis"] == "synthetic_training_proxy"
    assert persona["name"] != "Forbidden LLM Persona"
    assert all(attribute["provenance_class"] == "SYNTHETIC" for attribute in persona["attributes"])
    assert adapter.requests == []
