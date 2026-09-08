"""Dataset management and evidence-grounded persona synthesis service."""

from __future__ import annotations

import hashlib
import json
import math
import os
from collections.abc import Mapping
from pathlib import Path
import uuid
from typing import Any, Optional

from sqlalchemy import false as sa_false, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker

from bebshax.config import get_settings
from bebshax.api.errors import APIError
from bebshax.db.models import DatasetPersonaRuns, DatasetSources, EvidenceClaims, Personas, Studies, _utcnow
from bebshax.datasets.parser import parse_dataset_bytes
from bebshax.datasets.profiler import profile_dataset
from bebshax.datasets.security import safe_fetch_dataset_bytes
from bebshax.datasets.segmenter import calculate_segment_persona_distribution, discover_segments
from bebshax.datasets.validator import _numeric_constraint, validate_persona_against_constraints
from bebshax.llm.json_utils import parse_llm_json
from bebshax.llm.prompt_safety import UNTRUSTED_RULE, untrusted_block
from bebshax.llm.service import LLMService
from bebshax.llm.types import ChatMessage, LLMRequest, TaskType
from bebshax.persona.conflicts import contested_slots, shares_content_token
from bebshax.personas.ml_adapter import MLPersonaAdapter, build_business_context, to_generated_persona, to_persona_draft
from bebshax.tenancy import PUBLIC_OWNER_IDS
from bebshax.utils.explicit_failures import LLMUnavailable, UnusableModelOutput

DATASET_PERSONA_UNPARSEABLE = "dataset_persona_unparseable"
_PERSONA_MAX_ATTEMPTS = 2

_CLAIM_GROUPS = (
    "goals",
    "pain_points",
    "needs",
    "motivations",
    "behaviors",
    "technology_usage",
    "purchase_behavior",
    "personality_traits",
)


def _upload_dir() -> Path:
    """Configured upload root (BEBSHAX_UPLOAD_DIR / BEBSHAX_DATA_DIR), resolved at call time."""
    return get_settings().upload_dir_path


def _parse_json_object(text: str) -> dict:
    parsed = parse_llm_json(text)
    if not isinstance(parsed, dict):
        raise ValueError("no JSON object found in reply")
    return parsed


def _stated_only(values: dict[str, Any]) -> dict[str, Any]:
    """Drop keys the model never stated — an absent fact must stay absent."""
    return {k: v for k, v in values.items() if v not in (None, "", [], {})}


def record_evidence_id(record: dict[str, Any]) -> str:
    """Stable, content-derived id for a dataset row shown to the model."""
    digest = hashlib.sha256(
        json.dumps(record, sort_keys=True, default=str, ensure_ascii=False).encode("utf-8")
    ).hexdigest()
    return f"rec_{digest[:12]}"


def coerce_claim_provenance(
    persona: dict[str, Any], known_ids: set[str] | Mapping[str, Any]
) -> dict[str, Any]:
    """Enforce provenance on a dataset-persona dict IN PLACE, applying the SAME
    OBSERVED standard as persona.schema.coerce_provenance:

    - unknown ids are stripped; a self-declared OBSERVED with nothing verifiable
      becomes INFERRED; unknown labels become SYNTHETIC;
    - when ``known_ids`` maps id → record, a valid citation must also share a
      content token with a cited record (else INFERRED, ``citation_only``) and
      the cited records must not disagree on an identity/asserted numeric slot
      (else INFERRED, ``contested_evidence`` + ``contested:<slot>`` warning).
    A bare id set (no record texts) keeps the legacy id-only check."""
    texts: dict[str, str] = {}
    if isinstance(known_ids, Mapping):
        texts = {
            eid: json.dumps(rec, ensure_ascii=False, default=str, sort_keys=True)
            for eid, rec in known_ids.items()
        }
    ids = set(known_ids)
    warnings: list[str] = list(persona.get("warnings") or [])
    for group in _CLAIM_GROUPS:
        claims = persona.get(group)
        if not isinstance(claims, list):
            continue
        coerced: list[Any] = []
        for claim in claims:
            if not isinstance(claim, dict):
                coerced.append({"value": str(claim), "provenance": "SYNTHETIC", "evidence_ids": []})
                continue
            cited = claim.get("evidence_ids") or []
            valid_ids = [eid for eid in cited if isinstance(eid, str) and eid in ids]
            label = str(claim.get("provenance", "")).strip().upper()
            basis: str | None = None
            if valid_ids:
                provenance = "OBSERVED"
                cited_texts = [texts[eid] for eid in valid_ids if eid in texts]
                if cited_texts:
                    value = str(claim.get("value", ""))
                    contested = (
                        contested_slots(cited_texts, claim_text=value) if len(cited_texts) >= 2 else []
                    )
                    if contested:
                        provenance, basis = "INFERRED", "contested_evidence"
                        for slot in contested:
                            if f"contested:{slot}" not in warnings:
                                warnings.append(f"contested:{slot}")
                    elif not shares_content_token(value, cited_texts):
                        provenance, basis = "INFERRED", "citation_only"
            elif label in ("OBSERVED", "INFERRED"):
                provenance = "INFERRED"
            else:
                provenance = "SYNTHETIC"
            out = {**claim, "provenance": provenance, "evidence_ids": valid_ids}
            if basis:
                out["grounding_basis"] = basis
            coerced.append(out)
        persona[group] = coerced
    if warnings:
        persona["warnings"] = warnings
    return persona


class DatasetService:
    def __init__(
        self,
        sessionmaker_: sessionmaker[AsyncSession],
        llm: LLMService | None = None,
        *, ml_generator: MLPersonaAdapter | None = None,
    ) -> None:
        self._sessionmaker = sessionmaker_
        self._llm = llm
        self._ml_generator = ml_generator
        if self._ml_generator is None and llm is None:
            self._ml_generator = MLPersonaAdapter.from_settings()
        _upload_dir().mkdir(parents=True, exist_ok=True)

    @property
    def sessionmaker(self) -> sessionmaker[AsyncSession]:
        """Session factory this service was built with (falls back to a
        freshly created engine when the app has none wired)."""
        return self._sessionmaker

    async def ingest_from_url(
        self,
        url: str,
        name: str,
        description: Optional[str] = None,
        user_id: Optional[str] = None,
        study_id: Optional[str] = None,
        file_type: Optional[str] = None,
    ) -> DatasetSources:
        """Fetch external dataset URL with SSRF protection, parse, profile, and store metadata."""
        content, ctype = await safe_fetch_dataset_bytes(url)
        content_hash = hashlib.sha256(content).hexdigest()
        columns, rows = parse_dataset_bytes(content, file_type=file_type, content_type=ctype)
        schema_metadata, stats = profile_dataset(columns, rows)
        segments = discover_segments(columns, rows, schema_metadata, stats)

        ds_id = f"ds_{uuid.uuid4().hex[:16]}"
        # Store structured records on disk for fast querying and preview
        file_path = str(_upload_dir() / f"{ds_id}.json")
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(rows, f)

        dataset = DatasetSources(
            id=ds_id,
            user_id=user_id,
            study_id=study_id,
            name=name,
            source_type="url",
            source_url=url,
            file_path=file_path,
            file_type=file_type or "csv",
            description=description,
            status="ready",
            row_count=len(rows),
            column_count=len(columns),
            schema_metadata=schema_metadata,
            statistics=stats,
            segments=segments,
            content_hash=content_hash,
            persona_count_generated=0,
            last_processed_at=_utcnow(),
        )

        async with self._sessionmaker() as session:
            session.add(dataset)
            await session.commit()
            await session.refresh(dataset)

        return dataset

    async def ingest_from_upload(
        self,
        content: bytes,
        original_filename: str,
        name: str,
        description: Optional[str] = None,
        user_id: Optional[str] = None,
        study_id: Optional[str] = None,
        file_type: Optional[str] = None,
    ) -> DatasetSources:
        """Parse uploaded dataset file, profile deterministically, discover segments, and store."""
        content_hash = hashlib.sha256(content).hexdigest()
        columns, rows = parse_dataset_bytes(content, file_type=file_type, filename=original_filename)
        schema_metadata, stats = profile_dataset(columns, rows)
        segments = discover_segments(columns, rows, schema_metadata, stats)

        ds_id = f"ds_{uuid.uuid4().hex[:16]}"
        file_path = str(_upload_dir() / f"{ds_id}.json")
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(rows, f)

        dataset = DatasetSources(
            id=ds_id,
            user_id=user_id,
            study_id=study_id,
            name=name,
            source_type="upload",
            original_file_name=original_filename,
            file_path=file_path,
            file_type=file_type or original_filename.split(".")[-1].lower(),
            description=description,
            status="ready",
            row_count=len(rows),
            column_count=len(columns),
            schema_metadata=schema_metadata,
            statistics=stats,
            segments=segments,
            content_hash=content_hash,
            persona_count_generated=0,
            last_processed_at=_utcnow(),
        )

        async with self._sessionmaker() as session:
            session.add(dataset)
            await session.commit()
            await session.refresh(dataset)

        return dataset

    async def ingest_candidate_dataset(
        self,
        content: bytes,
        name: str,
        source_url: str,
        description: Optional[str] = None,
        user_id: Optional[str] = None,
        study_id: Optional[str] = None,
        file_type: Optional[str] = None,
    ) -> DatasetSources:
        """Parse discovered candidate bytes, profile deterministically, discover segments, and store."""
        content_hash = hashlib.sha256(content).hexdigest()
        columns, rows = parse_dataset_bytes(content, file_type=file_type or "csv")
        schema_metadata, stats = profile_dataset(columns, rows)
        segments = discover_segments(columns, rows, schema_metadata, stats)

        ds_id = f"ds_{uuid.uuid4().hex[:16]}"
        file_path = str(_upload_dir() / f"{ds_id}.json")
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(rows, f)

        dataset = DatasetSources(
            id=ds_id,
            user_id=user_id,
            study_id=study_id,
            name=name,
            source_type="url",
            source_url=source_url,
            file_path=file_path,
            file_type=file_type or "csv",
            description=description,
            status="ready",
            row_count=len(rows),
            column_count=len(columns),
            schema_metadata=schema_metadata,
            statistics=stats,
            segments=segments,
            content_hash=content_hash,
            persona_count_generated=0,
            last_processed_at=_utcnow(),
        )

        async with self._sessionmaker() as session:
            session.add(dataset)
            await session.commit()
            await session.refresh(dataset)

        return dataset

    @staticmethod
    def _tenant_filter(user_id: Optional[str]):
        """Tenant scope for caller-facing queries: unowned (NULL) rows and
        anonymous/system-tenant stamps (PUBLIC_OWNER_IDS — e.g. candidate
        imports stamp "usr_default") are shared; authenticated callers
        additionally see their own rows. Anonymous callers never see another
        tenant's data (B6 stage 3)."""
        shared = DatasetSources.user_id.is_(None) | DatasetSources.user_id.in_(PUBLIC_OWNER_IDS)
        if user_id:
            return (DatasetSources.user_id == user_id) | shared
        return shared

    @staticmethod
    def _tenant_write_filter(user_id: Optional[str]):
        """Tenant scope for DESTRUCTIVE queries. The shared pool is a read
        pool, never a write pool: inheriting `_tenant_filter` here let any
        anonymous visitor (and any signed-in user) delete or overwrite a
        dataset that belongs to someone else. Owner's own token required."""
        if not user_id:
            # Impossible predicate: anonymous callers own nothing.
            return sa_false()
        return DatasetSources.user_id == user_id

    async def list_datasets(
        self, user_id: Optional[str] = None, study_id: Optional[str] = None
    ) -> list[DatasetSources]:
        async with self._sessionmaker() as session:
            query = select(DatasetSources).order_by(DatasetSources.created_at.desc())
            if study_id:
                query = query.filter(DatasetSources.study_id == study_id)
            query = query.filter(self._tenant_filter(user_id))
            res = await session.execute(query)
            return list(res.scalars().all())

    async def _get_dataset_any(self, dataset_id: str) -> Optional[DatasetSources]:
        """Unscoped fetch for internal use AFTER an access check has passed."""
        async with self._sessionmaker() as session:
            return await session.get(DatasetSources, dataset_id)

    async def get_dataset(self, dataset_id: str, user_id: Optional[str] = None) -> Optional[DatasetSources]:
        async with self._sessionmaker() as session:
            query = select(DatasetSources).filter_by(id=dataset_id)
            query = query.filter(self._tenant_filter(user_id))
            res = await session.execute(query)
            return res.scalar_one_or_none()

    async def delete_dataset(self, dataset_id: str, user_id: Optional[str] = None) -> bool:
        async with self._sessionmaker() as session:
            query = select(DatasetSources).filter_by(id=dataset_id)
            query = query.filter(self._tenant_write_filter(user_id))
            res = await session.execute(query)
            ds = res.scalar_one_or_none()
            if not ds:
                return False

            if ds.file_path and os.path.exists(ds.file_path):
                try:
                    os.remove(ds.file_path)
                except OSError:
                    pass

            await session.delete(ds)
            await session.commit()
            return True

    async def refresh_dataset(self, dataset_id: str, user_id: Optional[str] = None) -> tuple[Optional[DatasetSources], bool]:
        """Re-fetch a URL-based dataset, check content-hash, and re-calculate statistics only if changed.

        Returns:
            (dataset: DatasetSources | None, changed: bool)
        """
        async with self._sessionmaker() as session:
            query = select(DatasetSources).filter_by(id=dataset_id)
            query = query.filter(self._tenant_write_filter(user_id))
            res = await session.execute(query)
            ds = res.scalar_one_or_none()
            if not ds or ds.source_type != "url" or not ds.source_url:
                return None, False

            content, ctype = await safe_fetch_dataset_bytes(ds.source_url)
            new_hash = hashlib.sha256(content).hexdigest()

            # If content is completely identical, skip reprocessing
            if ds.content_hash and ds.content_hash == new_hash:
                ds.last_processed_at = _utcnow()
                await session.commit()
                await session.refresh(ds)
                return ds, False

            columns, rows = parse_dataset_bytes(content, file_type=ds.file_type, content_type=ctype)
            schema_metadata, stats = profile_dataset(columns, rows)
            segments = discover_segments(columns, rows, schema_metadata, stats)

            if ds.file_path:
                with open(ds.file_path, "w", encoding="utf-8") as f:
                    json.dump(rows, f)

            ds.row_count = len(rows)
            ds.column_count = len(columns)
            ds.schema_metadata = schema_metadata
            ds.statistics = stats
            ds.segments = segments
            ds.content_hash = new_hash
            ds.last_processed_at = _utcnow()
            ds.status = "ready"
            ds.processing_error = None

            await session.commit()
            await session.refresh(ds)
            return ds, True

    async def get_dataset_preview(
        self, dataset_id: str, offset: int = 0, limit: int = 20, user_id: Optional[str] = None
    ) -> dict[str, Any]:
        """Load paginated preview rows from stored dataset records without loading massive files into client."""
        ds = await self.get_dataset(dataset_id, user_id=user_id)
        if not ds or not ds.file_path or not os.path.exists(ds.file_path):
            return {"columns": [], "rows": [], "total_rows": 0, "offset": offset, "limit": limit}

        with open(ds.file_path, "r", encoding="utf-8") as f:
            records = json.load(f)

        total_rows = len(records)
        columns = list(records[0].keys()) if records else []
        paged_rows = records[offset : offset + limit]

        return {
            "columns": columns,
            "rows": paged_rows,
            "total_rows": total_rows,
            "offset": offset,
            "limit": limit,
        }

    async def query_dataset(
        self, dataset_id: str, filter_col: Optional[str] = None, filter_val: Optional[Any] = None, limit: int = 100
    ) -> dict[str, Any]:
        """Execute deterministic filtering / analysis query on stored dataset records."""
        # Post-verification internal fetch — the API layer already ran the
        # tenant-scoped get_dataset check before calling this.
        ds = await self._get_dataset_any(dataset_id)
        if not ds or not ds.file_path or not os.path.exists(ds.file_path):
            return {"error": "Dataset file not found", "records": [], "count": 0}

        with open(ds.file_path, "r", encoding="utf-8") as f:
            records = json.load(f)

        if filter_col:
            records = [
                r for r in records
                if str(r.get(filter_col, "")).lower() == str(filter_val).lower()
            ]

        return {
            "total_matches": len(records),
            "returned_count": min(len(records), limit),
            "records": records[:limit],
        }

    async def _generate_ml_segment(
        self, dataset: DatasetSources, segment: dict[str, Any], count: int,
        business_name: str, business_description: str, study_context: dict[str, Any],
        claims: list[dict[str, Any]], exclude_ids: set[str], exclude_names: set[str],
    ) -> list[dict[str, Any]]:
        constraints = segment.get("constraints", {}) or {}
        age_stats = _numeric_constraint(constraints, ("age",))
        age_range = constraints.get("age_range")
        if age_range is None and age_stats:
            age_range = [age_stats.get("min"), age_stats.get("max")]
        age_bounds: dict[str, Any] = {}
        if age_range is not None:
            try:
                if not isinstance(age_range, list) or len(age_range) != 2:
                    raise ValueError("Invalid age range")
                age_bounds = {
                    "min_age": math.ceil(age_range[0]) if age_range[0] is not None else None,
                    "max_age": math.floor(age_range[1]) if age_range[1] is not None else None,
                }
            except (TypeError, ValueError, OverflowError) as error:
                raise APIError(422, "The dataset age constraints are unsupported.", error_code="ml_persona_unsupported_context") from error
        context = build_business_context(
            description="\n".join([business_name, business_description, study_context.get("prompt") or ""]),
            target_audience=study_context.get("target_audience") or "",
            price_range=study_context.get("pricing_hypothesis") or "",
            role=segment.get("name") or "",
            research=[json.dumps({
                "study": study_context,
                "dataset": {
                    "id": dataset.id, "name": dataset.name, "description": dataset.description,
                    "content_hash": dataset.content_hash, "schema_metadata": dataset.schema_metadata,
                    "statistics": dataset.statistics,
                },
                "segment": segment,
            }, ensure_ascii=False), *(json.dumps(claim, ensure_ascii=False) for claim in claims)],
            **age_bounds,
        )
        assert self._ml_generator is not None
        selections = await self._ml_generator.generate(
            context, count, exclude_ids=exclude_ids, exclude_names=exclude_names,
        )
        personas: list[dict[str, Any]] = []
        for selection in selections:
            persona = to_generated_persona(selection).model_dump(mode="json")
            draft = to_persona_draft(selection)
            validation = validate_persona_against_constraints(persona, segment)
            validation["warnings"] = list(dict.fromkeys([*validation["warnings"], *draft.validation_warnings]))
            if validation["status"] == "VALID" and validation["warnings"]:
                validation["status"] = "WARNING"
            persona.update({
                "model_used": draft.generation_model,
                "generation_model": draft.generation_model,
                "served_by": draft.generation_model,
                "segment_id": segment["id"],
                "segment_name": segment["name"],
                "validation": validation,
                "warnings": draft.validation_warnings,
                "evidence_citations": [],
                "dataset_refs": [*draft.dataset_refs, {
                    "dataset_id": dataset.id, "dataset_name": dataset.name,
                    "variable": "segment", "value": segment["name"], "usage": "selection_context",
                }],
                "dataset_provenance": {
                    "dataset_id": dataset.id, "dataset_name": dataset.name,
                    "segment_name": segment["name"], "population_share": segment.get("population_share", 0.0),
                },
            })
            personas.append(persona)
        return personas

    async def generate_personas_from_dataset(
        self,
        dataset_id: str,
        requested_count: int = 10,
        user_id: Optional[str] = None,
        study_id: Optional[str] = None,
        business_name: str = "",
        business_description: str = "",
    ) -> dict[str, Any]:
        """Generate evidence-grounded synthetic personas allocated by the dataset's
        observed segment shares.

        Every persona is written by the model from the segment's OBSERVED
        constraints and sample records. There is no offline template: without an
        LLM the call raises ``LLMUnavailable``; a persona whose reply is unusable
        after one retry is recorded as failed (``failed`` list) instead of being
        replaced by a stock character.
        """
        # Post-verification internal fetch (API layer ran the scoped check).
        ds = await self._get_dataset_any(dataset_id)
        if not ds:
            raise ValueError(f"Dataset '{dataset_id}' not found.")

        segments = ds.segments or []
        if not segments:
            raise ValueError(f"Dataset '{dataset_id}' has no discovered segments.")
        if self._llm is None and self._ml_generator is None:
            raise LLMUnavailable("Dataset persona generation")

        study_context: dict[str, Any] = {}
        claims: list[dict[str, Any]] = []
        if self._ml_generator is not None and study_id:
            async with self._sessionmaker() as session:
                study = await session.get(Studies, study_id)
                if study is not None:
                    study_context = {field: getattr(study, field) for field in (
                        "title", "prompt", "goal", "target_audience", "pricing_hypothesis", "copilot_messages", "findings",
                    )}
                claim_rows = (await session.execute(select(EvidenceClaims).where(EvidenceClaims.study_id == study_id))).scalars()
                claims = [{"id": claim.id, "claim_text": claim.claim_text, "category": claim.category} for claim in claim_rows]

        # 1. Mathematically determine exact persona quotas per segment
        quota_distribution = calculate_segment_persona_distribution(segments, requested_count)
        served_by: list[str] = []

        generated_personas: list[dict[str, Any]] = []
        failed: list[dict[str, Any]] = []
        validation_results: list[dict[str, Any]] = []

        valid_count = 0
        warning_count = 0
        contradiction_count = 0
        used_source_ids: set[str] = set()
        used_names: set[str] = set()
        ml_errors: list[APIError] = []

        # 2. Synthesize personas for each segment quota
        for seg in segments:
            seg_id = seg["id"]
            count_for_seg = quota_distribution.get(seg_id, 0)
            if count_for_seg <= 0:
                continue

            if self._ml_generator is not None:
                try:
                    local_personas = await self._generate_ml_segment(
                        ds, seg, count_for_seg, business_name, business_description,
                        study_context, claims, used_source_ids, used_names,
                    )
                except APIError as error:
                    if error.status_code == 503:
                        raise
                    ml_errors.append(error)
                    failed.extend({
                        "segment_id": seg_id, "segment": seg["name"], "index": index,
                        "error_code": error.error_code, "detail": error.detail,
                    } for index in range(count_for_seg))
                    continue
                for persona in local_personas:
                    used_source_ids.add(persona["detailed_attributes"]["ml_provenance"]["record_id"])
                    used_names.add(persona["name"])
                    if persona["served_by"] not in served_by:
                        served_by.append(persona["served_by"])
                    validation = persona["validation"]
                    if validation["status"] == "VALID":
                        valid_count += 1
                    elif validation["status"] == "WARNING":
                        warning_count += 1
                    else:
                        contradiction_count += 1
                    generated_personas.append(persona)
                    validation_results.append({
                        "persona_name": persona["name"], "segment": seg["name"],
                        "status": validation["status"], "violations": validation["violations"],
                        "warnings": validation["warnings"],
                    })
                continue

            constraints = seg.get("constraints", {}) or {}
            sample_records = seg.get("sample_records", [])
            # Only rows the model is actually SHOWN can ground a claim; they get
            # stable content-derived ids so citations are verifiable.
            shown_records = [r for r in sample_records[:2] if isinstance(r, dict)]
            shown_ids = {record_evidence_id(r): r for r in shown_records}
            evidence_lines = "\n".join(
                f"[{rid}] {json.dumps(record, ensure_ascii=False, default=str)}"
                for rid, record in shown_ids.items()
            ) or "(no sample records — do not mark any claim OBSERVED)"

            # Observed constraints only — whatever the dataset actually measured
            # for this group, keyed by its own column names. Nothing is assumed.
            observed_lines = "\n".join(
                f"- {key}: {json.dumps(value, ensure_ascii=False, default=str)}"
                for key, value in constraints.items()
                if key != "rule_description" and value not in (None, "", [], {})
            ) or "- (no per-group statistics beyond the grouping itself)"
            context_line = f"- Context: {business_name} - {business_description}\n" if (business_name or business_description) else ""

            for persona_idx in range(count_for_seg):
                prompt = (
                    f"Synthesize 1 realistic persona representing market segment: '{seg['name']}' "
                    f"({seg.get('population_percentage', 0)}% of the dataset's observed population; "
                    f"grouped by {seg.get('segmentation_feature', 'a dataset column')}).\n\n"
                    f"OBSERVED SEGMENT STATISTICS (MANDATORY — stay inside them; do not assume a country, currency or "
                    f"value the data does not show; if something is unknown, say so in the description):\n"
                    f"{observed_lines}\n"
                    f"- Rule: {constraints.get('rule_description', '')}\n"
                    f"{context_line}\n"
                    f"REPRESENTATIVE DATASET EVIDENCE (cite the bracketed record ids in evidence_ids for OBSERVED claims; "
                    f"never invent ids):\n"
                    + untrusted_block("DATASET_RECORDS", evidence_lines, source=f"dataset.{ds.id}")
                    + "\n\nReturn JSON strictly matching the schema with name, age, occupation, location, income_range, education, "
                    "description, goals, pain_points, needs, motivations, behaviors, technology_usage, purchase_behavior, personality_traits, "
                    "and commercial_profile {monthly_budget: number|null, currency: ISO code|null, price_sensitivity: str|null}. "
                    'Each claim is {"value": str, "provenance": "OBSERVED"|"INFERRED"|"SYNTHETIC", "evidence_ids": [record ids]}.'
                )
                request = LLMRequest(
                    task=TaskType.PERSONA_GENERATION,
                    messages=[
                        ChatMessage(
                            role="system",
                            content=(
                                "You are BebshaX's evidence-grounded persona synthesis engine. Generate structured JSON "
                                "conforming strictly to the observed constraints. " + UNTRUSTED_RULE
                            ),
                        ),
                        ChatMessage(role="user", content=prompt),
                    ],
                    json_mode=True,
                    temperature=0.7,
                    max_output_tokens=2048,
                )

                persona_dict: Optional[dict[str, Any]] = None
                last_model = None
                for attempt in range(1, _PERSONA_MAX_ATTEMPTS + 1):
                    if attempt > 1:
                        request = request.retry_copy()
                    result = await self._llm.complete(request)  # LLMError propagates
                    last_model = f"{result.provider}/{result.model}"
                    try:
                        parsed = _parse_json_object(result.text)
                    except ValueError:
                        parsed = None
                    if isinstance(parsed, dict) and str(parsed.get("name") or "").strip():
                        persona_dict = coerce_claim_provenance(parsed, shown_ids)
                        persona_dict["model_used"] = result.model
                        persona_dict["served_by"] = last_model
                        if last_model not in served_by:
                            served_by.append(last_model)
                        break
                if persona_dict is None:
                    failed.append(
                        {
                            "segment_id": seg_id,
                            "segment": seg["name"],
                            "index": persona_idx,
                            "error_code": DATASET_PERSONA_UNPARSEABLE,
                            "detail": f"The model's persona reply was unusable after {_PERSONA_MAX_ATTEMPTS} attempts.",
                            "served_by": last_model,
                        }
                    )
                    continue

                # 3. Programmatically validate persona against segment constraints
                val = validate_persona_against_constraints(persona_dict, seg)
                persona_dict["segment_id"] = seg_id
                persona_dict["segment_name"] = seg["name"]
                persona_dict["validation"] = val
                persona_dict["dataset_provenance"] = {
                    "dataset_id": ds.id,
                    "dataset_name": ds.name,
                    "segment_name": seg["name"],
                    "population_share": seg.get("population_share", 0.0),
                }

                if val["status"] == "VALID":
                    valid_count += 1
                elif val["status"] == "WARNING":
                    warning_count += 1
                else:
                    contradiction_count += 1

                generated_personas.append(persona_dict)
                validation_results.append({
                    "persona_name": persona_dict.get("name", "Unknown"),
                    "segment": seg["name"],
                    "status": val["status"],
                    "violations": val["violations"],
                    "warnings": val["warnings"],
                })

        if not generated_personas:
            if ml_errors:
                ml_errors[-1].extra["failed"] = failed
                raise ml_errors[-1]
            raise UnusableModelOutput(
                DATASET_PERSONA_UNPARSEABLE,
                f"None of the {requested_count} requested personas could be generated from usable model replies.",
                attempts=_PERSONA_MAX_ATTEMPTS,
                served_by=served_by[-1] if served_by else None,
                extra={"failed": failed},
            )

        # 4. Save audit run record in database
        run_id = f"dpr_{uuid.uuid4().hex[:16]}"
        run_record = DatasetPersonaRuns(
            id=run_id,
            dataset_id=ds.id,
            user_id=user_id,
            study_id=study_id,
            model_used=", ".join(served_by),
            requested_count=requested_count,
            generated_count=len(generated_personas),
            valid_count=valid_count,
            warning_count=warning_count,
            contradiction_count=contradiction_count,
            distribution_target=quota_distribution,
            distribution_actual={s["id"]: sum(1 for p in generated_personas if p.get("segment_id") == s["id"]) for s in segments},
            validation_results=validation_results + [{"failed": f} for f in failed],
        )

        async with self._sessionmaker() as session:
            session.add(run_record)
            # Update dataset persona generation count
            res = await session.execute(select(DatasetSources).filter_by(id=dataset_id))
            target_ds = res.scalar_one_or_none()
            if target_ds:
                target_ds.persona_count_generated = (target_ds.persona_count_generated or 0) + len(generated_personas)

            # Persist each persona to the Personas table for user dashboard access.
            # Only STATED values are stored: a missing age/location/budget stays
            # missing (the identity card renders "not stated"), never a literal
            # the model never produced.
            for p_data in generated_personas:
                p_id = f"per_{uuid.uuid4().hex[:12]}"
                prefs = p_data.get("preferences") or []
                if isinstance(prefs, str):
                    prefs = [prefs]
                commercial = p_data.get("commercial_profile") if isinstance(p_data.get("commercial_profile"), dict) else {}
                p_entity = Personas(
                    id=p_id,
                    study_id=study_id,
                    user_id=user_id,
                    owner_id=user_id or "usr_system_holder",
                    segment_id=p_data.get("segment_id"),
                    generation_run_id=run_id,
                    name=p_data.get("name", "Synthetic Persona"),
                    status="ready" if p_data.get("validation", {}).get("status") == "VALID" else "needs_review",
                    version=1,
                    generation_model=p_data.get("served_by") or p_data.get("model_used"),
                    archetype=p_data.get("archetype") or p_data.get("occupation") or None,
                    tagline=p_data.get("tagline") or None,
                    country_code=p_data.get("country_code") or None,
                    personality=p_data.get("personality") or {},
                    detailed_attributes=p_data.get("detailed_attributes", {}),
                    demographics=_stated_only(
                        {
                            "age": p_data.get("age"),
                            "occupation": p_data.get("occupation"),
                            "location": p_data.get("location"),
                            "education": p_data.get("education"),
                            "income_or_budget": p_data.get("income_range"),
                        }
                    ),
                    bio=p_data.get("description") or None,
                    quote=p_data.get("quote") or None,
                    goals=[g.get("value") if isinstance(g, dict) else str(g) for g in p_data.get("goals", [])],
                    needs=[n.get("value") if isinstance(n, dict) else str(n) for n in p_data.get("needs", [])],
                    pain_points=[pp.get("value") if isinstance(pp, dict) else str(pp) for pp in p_data.get("pain_points", [])],
                    behaviors=[b.get("value") if isinstance(b, dict) else str(b) for b in p_data.get("behaviors", [])],
                    preferences=[str(x) for x in prefs],
                    motivations=[m.get("value") if isinstance(m, dict) else str(m) for m in p_data.get("motivations", [])],
                    objections=[o.get("value") if isinstance(o, dict) else str(o) for o in p_data.get("objections", [])],
                    commercial_profile=_stated_only(
                        {
                            "monthly_budget": commercial.get("monthly_budget") or p_data.get("monthly_budget"),
                            "currency": commercial.get("currency") or p_data.get("currency"),
                            "price_sensitivity": commercial.get("price_sensitivity") or p_data.get("price_sensitivity"),
                            "payment_preference": commercial.get("payment_preference") or p_data.get("payment_preference"),
                        }
                    ),
                    technology_profile=p_data.get("technology_profile") or {},
                    evidence_citations=p_data.get("evidence_citations", []) or [],
                    dataset_refs=p_data.get("dataset_refs") or [{"dataset_id": ds.id, "dataset_name": ds.name, "variable": "segment", "value": p_data.get("segment_name")}],
                    # Honest scores: pass through what validation computed, never constants.
                    grounding_score=float(p_data.get("grounding_score") or 0.0),
                    confidence=float(p_data.get("confidence") or 0.0),
                    validation_warnings=p_data.get("validation", {}).get("warnings", []),
                    is_synthetic=True,
                    created_at=_utcnow(),
                    updated_at=_utcnow(),
                )
                session.add(p_entity)

            await session.commit()

        return {
            "run_id": run_id,
            "dataset_id": ds.id,
            "dataset_name": ds.name,
            "model_used": ", ".join(served_by),
            "served_by": served_by,
            "requested_count": requested_count,
            "generated_count": len(generated_personas),
            "failed_count": len(failed),
            "failed": failed,
            "valid_count": valid_count,
            "warning_count": warning_count,
            "contradiction_count": contradiction_count,
            "distribution": quota_distribution,
            "personas": generated_personas,
            "validation_summary": validation_results,
        }


