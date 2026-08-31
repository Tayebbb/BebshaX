"""Persona generation pipeline (brief §15).

Failure discipline:
- transport/JSON-mode failures are INFRASTRUCTURE and already handled inside
  LLMService (retry/fallback) — this module never re-implements them;
- schema-invalid or contradiction-carrying output is a CONTENT problem and
  gets exactly ONE refinement round (PERSONA_REFINEMENT), then an explicit
  PersonaGenerationFailed. No silent degradation, ever (R2).
"""

from __future__ import annotations

import json
import uuid

from pydantic import ValidationError

from bebshax.llm import ChatMessage, LLMRequest, LLMService, TaskType
from bebshax.llm.json_utils import parse_llm_json
from bebshax.persona.consistency import ConsistencyViolation, check_consistency
from bebshax.persona.evidence import EvidenceStore
from bebshax.persona.schema import (
    EvidenceItem,
    GeneratedPersona,
    PersonaProfile,
    coerce_provenance,
)


class PersonaGenerationFailed(Exception):
    def __init__(self, reason: str, violations: list[ConsistencyViolation] | None = None) -> None:
        self.reason = reason
        self.violations = violations or []
        detail = "; ".join(v.message for v in self.violations)
        super().__init__(f"{reason}{': ' + detail if detail else ''}")


_SYSTEM_PROMPT = """You are BebshaX's persona synthesis engine. Create ONE realistic customer \
persona for the business described by the user.

Reply with STRICT JSON only — no markdown fences, no commentary. Schema:
{
  "name": str, "age": int, "occupation": str, "location": str,
  "income_range": str, "education": str, "description": str (2-3 sentences),
  "goals": [claim], "pain_points": [claim], "needs": [claim],
  "motivations": [claim], "behaviors": [claim], "technology_usage": [claim],
  "purchase_behavior": [claim], "personality_traits": [claim]
}
Each claim is: {"value": str, "provenance": "OBSERVED"|"INFERRED"|"SYNTHETIC", "evidence_ids": [str]}

Provenance rules (mandatory, will be machine-verified):
- OBSERVED: the claim is directly supported by an evidence item — cite its id(s) in evidence_ids.
- INFERRED: reasonably deduced from the business context or evidence themes; evidence_ids empty.
- SYNTHETIC: plausible invention to complete the persona; evidence_ids empty.
Never fabricate evidence ids. goals and pain_points need at least 2 claims each; \
give at least 1 claim in every other group. Make the persona specific and internally consistent \
(age vs occupation, income vs spending)."""

_SEED_BLOCK = """DIVERSITY SEED — a random persona sketch for perspective only. Do NOT copy its \
identity, name, or occupation; use it to avoid generating a generic/stereotypical persona:
{seed}"""


def _extract_json(text: str) -> dict:
    parsed = parse_llm_json(text)
    if not isinstance(parsed, dict):
        raise ValueError("no JSON object found in reply")
    return parsed


class PersonaEngine:
    def __init__(
        self,
        llm: LLMService,
        evidence_store: EvidenceStore,
        critic: bool = False,
        evidence_k: int = 6,
    ) -> None:
        self._llm = llm
        self._store = evidence_store
        self._critic = critic
        self._evidence_k = evidence_k

    def _build_messages(
        self,
        business_name: str,
        business_description: str,
        evidence: list[EvidenceItem],
        seed: str | None,
        hints: str | None,
    ) -> list[ChatMessage]:
        parts = [f"BUSINESS: {business_name}\n{business_description}"]
        if evidence:
            lines = "\n".join(f"- [{e.id}] ({e.source}) {e.text}" for e in evidence)
            parts.append(f"EVIDENCE ITEMS (cite ids for OBSERVED claims):\n{lines}")
        else:
            parts.append(
                "EVIDENCE ITEMS: none available — do not mark any claim OBSERVED; "
                "use INFERRED or SYNTHETIC honestly."
            )
        if seed:
            parts.append(_SEED_BLOCK.format(seed=seed))
        if hints:
            parts.append(f"RESEARCHER HINTS: {hints}")
        return [
            ChatMessage(role="system", content=_SYSTEM_PROMPT),
            ChatMessage(role="user", content="\n\n".join(parts)),
        ]

    async def _call(self, task: TaskType, messages: list[ChatMessage], persona_id: str):
        request = LLMRequest(
            task=task,
            messages=messages,
            json_mode=True,
            max_output_tokens=1400,
            temperature=0.8,
            persona_id=persona_id,
        )
        return await self._llm.complete(request)

    @staticmethod
    def _parse(text: str) -> tuple[GeneratedPersona | None, str | None]:
        try:
            return GeneratedPersona.model_validate(_extract_json(text)), None
        except (ValueError, ValidationError) as exc:
            return None, str(exc)[:800]

    async def generate(
        self,
        business_id: str,
        business_name: str,
        business_description: str,
        hints: str | None = None,
    ) -> PersonaProfile:
        persona_id = uuid.uuid4().hex
        evidence = self._store.retrieve(
            f"{business_name} {business_description}", k=self._evidence_k
        )
        seed = self._store.seed_persona(persona_id)
        messages = self._build_messages(
            business_name, business_description, evidence, seed, hints
        )

        result = await self._call(TaskType.PERSONA_GENERATION, messages, persona_id)
        generated, parse_error = self._parse(result.text)
        refinement_used = False

        if generated is None:
            # ONE content-level refinement for schema-invalid output.
            refinement_used = True
            result = await self._call(
                TaskType.PERSONA_REFINEMENT,
                [
                    *messages,
                    ChatMessage(role="assistant", content=result.text),
                    ChatMessage(
                        role="user",
                        content=(
                            "Your JSON was invalid and was rejected by the schema validator:\n"
                            f"{parse_error}\n"
                            "Reply again with corrected STRICT JSON only."
                        ),
                    ),
                ],
                persona_id,
            )
            generated, parse_error = self._parse(result.text)
            if generated is None:
                raise PersonaGenerationFailed(f"schema-invalid after refinement: {parse_error}")

        profile = coerce_provenance(generated, business_id, evidence, result.model)
        profile = profile.model_copy(update={"id": persona_id})

        violations = check_consistency(profile)
        errors = [v for v in violations if v.severity == "error"]
        if errors and not refinement_used:
            refinement_used = True
            result = await self._call(
                TaskType.PERSONA_REFINEMENT,
                [
                    *messages,
                    ChatMessage(role="assistant", content=result.text),
                    ChatMessage(
                        role="user",
                        content=(
                            "Your persona failed deterministic consistency checks:\n"
                            + "\n".join(f"- {v.message}" for v in errors)
                            + "\nFix these contradictions and reply with corrected STRICT JSON only."
                        ),
                    ),
                ],
                persona_id,
            )
            generated, parse_error = self._parse(result.text)
            if generated is None:
                raise PersonaGenerationFailed(f"schema-invalid after refinement: {parse_error}")
            profile = coerce_provenance(generated, business_id, evidence, result.model)
            profile = profile.model_copy(update={"id": persona_id})
            violations = check_consistency(profile)
            errors = [v for v in violations if v.severity == "error"]

        if errors:
            raise PersonaGenerationFailed("consistency errors persist after refinement", errors)

        warnings = [v.message for v in violations if v.severity == "warning"]

        if self._critic:
            warnings.extend(await self._run_critic(profile, persona_id))

        return profile.model_copy(update={"warnings": warnings})

    async def _run_critic(self, profile: PersonaProfile, persona_id: str) -> list[str]:
        """Best-effort CRITIC pass — issues become warnings, never failures."""
        result = await self._call(
            TaskType.CRITIC,
            [
                ChatMessage(
                    role="system",
                    content=(
                        "You are a skeptical persona reviewer. List internal contradictions or "
                        'implausibilities. Reply STRICT JSON: {"issues": [str, ...]} — empty list if none.'
                    ),
                ),
                ChatMessage(
                    role="user", content=json.dumps(profile.to_eval_dict(), ensure_ascii=False)
                ),
            ],
            persona_id,
        )
        try:
            issues = _extract_json(result.text).get("issues", [])
            return [f"critic: {issue}" for issue in issues if isinstance(issue, str)]
        except (ValueError, json.JSONDecodeError):
            return ["critic: output unparseable — review skipped"]
