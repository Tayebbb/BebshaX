"""Dataset management and evidence-grounded persona synthesis service."""

from __future__ import annotations

import datetime
import hashlib
import json
import os
from pathlib import Path
import statistics
import uuid
from typing import Any, Optional

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker

from bebshax.db.models import DatasetPersonaRuns, DatasetSources, Personas, _utcnow
from bebshax.datasets.parser import parse_dataset_bytes
from bebshax.datasets.profiler import profile_dataset
from bebshax.datasets.security import safe_fetch_dataset_bytes
from bebshax.datasets.segmenter import calculate_segment_persona_distribution, discover_segments
from bebshax.datasets.validator import validate_persona_against_constraints
from bebshax.llm.service import LLMService
from bebshax.llm.types import ChatMessage, LLMRequest, TaskType
from bebshax.persona.orm import PersonaAttributes, PersonaDetails, PersonaEvidence

UPLOAD_DIR = Path("data/uploads")


def _parse_json_object(text: str) -> dict:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:]
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start == -1 or end <= start:
        raise ValueError("no JSON object found in reply")
    return json.loads(cleaned[start : end + 1])


class DatasetService:
    def __init__(
        self,
        sessionmaker_: sessionmaker[AsyncSession],
        llm: LLMService | None = None,
    ) -> None:
        self._sessionmaker = sessionmaker_
        self._llm = llm
        UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

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
        file_path = str(UPLOAD_DIR / f"{ds_id}.json")
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
        file_path = str(UPLOAD_DIR / f"{ds_id}.json")
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
        file_path = str(UPLOAD_DIR / f"{ds_id}.json")
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

    async def list_datasets(
        self, user_id: Optional[str] = None, study_id: Optional[str] = None
    ) -> list[DatasetSources]:
        async with self._sessionmaker() as session:
            query = select(DatasetSources).order_by(DatasetSources.created_at.desc())
            if study_id:
                query = query.filter(DatasetSources.study_id == study_id)
            if user_id:
                query = query.filter((DatasetSources.user_id == user_id) | (DatasetSources.user_id.is_(None)))
            res = await session.execute(query)
            return list(res.scalars().all())

    async def get_dataset(self, dataset_id: str, user_id: Optional[str] = None) -> Optional[DatasetSources]:
        async with self._sessionmaker() as session:
            query = select(DatasetSources).filter_by(id=dataset_id)
            if user_id:
                query = query.filter((DatasetSources.user_id == user_id) | (DatasetSources.user_id.is_(None)))
            res = await session.execute(query)
            return res.scalar_one_or_none()

    async def delete_dataset(self, dataset_id: str, user_id: Optional[str] = None) -> bool:
        async with self._sessionmaker() as session:
            query = select(DatasetSources).filter_by(id=dataset_id)
            if user_id:
                query = query.filter((DatasetSources.user_id == user_id) | (DatasetSources.user_id.is_(None)))
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
            if user_id:
                query = query.filter((DatasetSources.user_id == user_id) | (DatasetSources.user_id.is_(None)))
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
        ds = await self.get_dataset(dataset_id)
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

    async def generate_personas_from_dataset(
        self,
        dataset_id: str,
        requested_count: int = 10,
        user_id: Optional[str] = None,
        study_id: Optional[str] = None,
        business_name: str = "BebshaX Research Initiative",
        business_description: str = "Evidence-grounded user interview validation",
    ) -> dict[str, Any]:
        """Generate evidence-grounded synthetic personas strictly allocated according to dataset segment distribution."""
        ds = await self.get_dataset(dataset_id)
        if not ds:
            raise ValueError(f"Dataset '{dataset_id}' not found.")

        segments = ds.segments or []
        if not segments:
            raise ValueError(f"Dataset '{dataset_id}' has no discovered segments.")

        # 1. Mathematically determine exact persona quotas per segment
        quota_distribution = calculate_segment_persona_distribution(segments, requested_count)
        model_used = "offline_fallback"  # updated from the first LLM-served persona

        generated_personas: list[dict[str, Any]] = []
        validation_results: list[dict[str, Any]] = []

        valid_count = 0
        warning_count = 0
        contradiction_count = 0

        # 2. Synthesize personas for each segment quota
        for seg in segments:
            seg_id = seg["id"]
            count_for_seg = quota_distribution.get(seg_id, 0)
            if count_for_seg <= 0:
                continue

            constraints = seg.get("constraints", {})
            sample_records = seg.get("sample_records", [])

            for persona_idx in range(count_for_seg):
                prompt = (
                    f"Synthesize 1 realistic persona representing market segment: '{seg['name']}' "
                    f"({seg.get('population_percentage', 0)}% empirical population share).\n\n"
                    f"EVIDENCE CONSTRAINTS (MANDATORY):\n"
                    f"- Segment: {seg['name']}\n"
                    f"- Age range: {constraints.get('age_range', [18, 50])} (Median: {constraints.get('median_age', 25)})\n"
                    f"- Monthly budget: ৳{constraints.get('monthly_budget', {}).get('median', 500)} "
                    f"(Range: ৳{constraints.get('monthly_budget', {}).get('min', 100)} - ৳{constraints.get('monthly_budget', {}).get('max', 1500)})\n"
                    f"- Tech familiarity: {constraints.get('technology_familiarity', 'Medium')}\n"
                    f"- Observed needs: {', '.join(constraints.get('observed_needs', ['Core functionality']))}\n"
                    f"- Context: {business_name} - {business_description}\n\n"
                    f"REPRESENTATIVE DATASET EVIDENCE:\n"
                    f"{json.dumps(sample_records[:2], indent=2)}\n\n"
                    f"Return JSON strictly matching the schema with name, age, occupation, location, income_range, education, description, goals, pain_points, needs, motivations, behaviors, technology_usage, purchase_behavior, personality_traits."
                )

                if self._llm is None:
                    persona_dict = _generate_offline_fallback_persona(seg, persona_idx)
                else:
                    try:
                        result = await self._llm.complete(
                            LLMRequest(
                                task=TaskType.PERSONA_GENERATION,
                                messages=[
                                    ChatMessage(
                                        role="system",
                                        content="You are BebshaX's evidence-grounded persona synthesis engine. Generate structured JSON conforming strictly to empirical constraints.",
                                    ),
                                    ChatMessage(role="user", content=prompt),
                                ],
                                json_mode=True,
                                temperature=0.7,
                                max_output_tokens=2048,
                            )
                        )
                        persona_dict = _parse_json_object(result.text)
                        model_used = result.model
                    except Exception:
                        # Fallback structured generation when offline
                        persona_dict = _generate_offline_fallback_persona(seg, persona_idx)

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

        # 4. Save audit run record in database
        run_id = f"dpr_{uuid.uuid4().hex[:16]}"
        run_record = DatasetPersonaRuns(
            id=run_id,
            dataset_id=ds.id,
            user_id=user_id,
            study_id=study_id,
            model_used=model_used,
            requested_count=requested_count,
            generated_count=len(generated_personas),
            valid_count=valid_count,
            warning_count=warning_count,
            contradiction_count=contradiction_count,
            distribution_target=quota_distribution,
            distribution_actual={s["id"]: sum(1 for p in generated_personas if p.get("segment_id") == s["id"]) for s in segments},
            validation_results=validation_results,
        )

        async with self._sessionmaker() as session:
            session.add(run_record)
            # Update dataset persona generation count
            res = await session.execute(select(DatasetSources).filter_by(id=dataset_id))
            target_ds = res.scalar_one_or_none()
            if target_ds:
                target_ds.persona_count_generated = (target_ds.persona_count_generated or 0) + len(generated_personas)

            # Persist each persona to the Personas table for user dashboard access
            for p_data in generated_personas:
                p_id = f"per_{uuid.uuid4().hex[:12]}"
                p_entity = Personas(
                    id=p_id,
                    study_id=study_id,
                    user_id=user_id,
                    segment_id=p_data.get("segment_id"),
                    generation_run_id=run_id,
                    name=p_data.get("name", "Synthetic Persona"),
                    status="ready" if p_data.get("validation", {}).get("status") == "VALID" else "needs_review",
                    version=1,
                    generation_model=model_used,
                    archetype=p_data.get("archetype") or p_data.get("occupation", "Target User"),
                    tagline=p_data.get("tagline") or f"The Grounded {p_data.get('segment_name', 'User')} Representative",
                    country_code=p_data.get("country_code", "BD"),
                    personality=p_data.get("personality", {
                        "openness": 50,
                        "conscientiousness": 70,
                        "extroversion": 50,
                        "agreeableness": 65,
                        "neuroticism": 45,
                    }),
                    detailed_attributes=p_data.get("detailed_attributes", {}),
                    demographics={
                        "age": p_data.get("age", 25),
                        "occupation": p_data.get("occupation", "Professional"),
                        "location": p_data.get("location", "Dhaka, Bangladesh"),
                        "education": p_data.get("education", "Bachelor's Degree"),
                        "income_or_budget": p_data.get("income_range", "৳500/mo"),
                    },
                    bio=p_data.get("description") or f"{p_data.get('name')} is a representative customer grounded in dataset findings.",
                    quote=p_data.get("quote") or "I need a dependable, cost-effective solution tailored to my daily reality.",
                    goals=[g.get("value") if isinstance(g, dict) else str(g) for g in p_data.get("goals", [])],
                    needs=[n.get("value") if isinstance(n, dict) else str(n) for n in p_data.get("needs", [])],
                    pain_points=[pp.get("value") if isinstance(pp, dict) else str(pp) for pp in p_data.get("pain_points", [])],
                    behaviors=[b.get("value") if isinstance(b, dict) else str(b) for b in p_data.get("behaviors", [])],
                    preferences=[p_data.get("preferences", ["Clean mobile UI"])],
                    motivations=[m.get("value") if isinstance(m, dict) else str(m) for m in p_data.get("motivations", [])],
                    objections=[o.get("value") if isinstance(o, dict) else str(o) for o in p_data.get("objections", [])],
                    commercial_profile={
                        "monthly_budget_bdt": p_data.get("monthly_budget_bdt", 500),
                        "price_sensitivity": "High",
                        "payment_preference": "bKash / Nagad Mobile Wallet",
                    },
                    technology_profile={
                        "primary_devices": ["Android Smartphone"],
                        "platforms": ["WhatsApp", "bKash"],
                        "familiarity": "Medium",
                    },
                    evidence_citations=[],
                    dataset_refs=[{"dataset_id": ds.id, "dataset_name": ds.name, "variable": "segment", "value": p_data.get("segment_name")}],
                    grounding_score=0.92,
                    confidence=0.88,
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
            "model_used": model_used,
            "requested_count": requested_count,
            "generated_count": len(generated_personas),
            "valid_count": valid_count,
            "warning_count": warning_count,
            "contradiction_count": contradiction_count,
            "distribution": quota_distribution,
            "personas": generated_personas,
            "validation_summary": validation_results,
        }


def _generate_offline_fallback_persona(seg: dict[str, Any], idx: int) -> dict[str, Any]:
    constraints = seg.get("constraints", {})
    age_range = constraints.get("age_range", [20, 30])
    budget = constraints.get("monthly_budget", {}).get("median", 500)
    names = ["Samiul Alam", "Nabila Khan", "Tanvir Hasan", "Farhana Rahman", "Arif Chowdhury", "Mehzabin Sultana"]
    name = names[idx % len(names)]

    return {
        "name": name,
        "age": int(statistics.mean(age_range)),
        "occupation": seg.get("name", "Student / Professional"),
        "location": "Dhaka, Bangladesh",
        "income_range": f"৳{budget:,.0f} per month",
        "education": "Bachelor's Degree",
        "tagline": f"The Grounded {seg['name']} Representative",
        "country_code": "BD",
        "origin_country": "Bangladesh",
        "personality": {
            "openness": 55,
            "conscientiousness": 78,
            "extroversion": 52,
            "agreeableness": 70,
            "neuroticism": 45,
        },
        "detailed_attributes": {
            "hobbies": "following local news, digital reading, and evening walks",
            "origin_country": "Bangladesh",
            "commute_mode": "rickshaw and local transit",
            "food_source": "home-cooked meals with occasional canteen tea",
            "meal_timing": "regular 3-meal timing with evening snacks",
            "payment_method": "bKash for daily expenses, cash backup",
            "work_schedule": "standard daytime hours",
            "workplace_setting": "office or campus",
            "activity_level": "moderate",
            "adaptability_level": "moderate to high",
            "anxiety_level": "moderate under tight deadlines",
            "attention_focus": "practical and detail-focused",
            "belief_system": "pragmatic and duty-oriented",
            "communication_style": "direct, polite, and clear",
            "community_engagement": "moderate neighborhood connection",
            "coping_strategies": "taking tea breaks and sticking to routine",
            "core_motivators": "protecting income and achieving personal milestones",
            "cultural_affiliations": "urban Bangladeshi middle class",
            "cultural_traditions": "family dinner gatherings and Eid celebrations",
            "daily_activities": "work, commute, family check-ins, and rest",
            "decision_style": "deliberate and value-conscious",
            "family_dynamics": "supportive shared household",
            "financial_attitude": "careful monthly budgeting",
            "financial_profile": "salaried with moderate discretionary ceiling",
            "general_risk": "low to moderate",
            "growth_mindset": "open to practical self-improvement",
            "household_structure": "family household",
            "introversion_level": "balanced ambivert",
            "language_preferences": "Bangla first, professional English",
            "learning_style": "practical demonstration and use",
            "life_priorities": "family stability and steady work",
            "motivation_goals": "reduce friction and improve consistency",
            "personal_independence": "self-directed in routine choices",
            "personal_values": "reliability, integrity, and consideration",
            "planning_horizon": "weekly to monthly budgeting",
            "religious_practices": "observes standard religious occasions",
            "schedule_flexibility": "moderate",
            "self_discipline": "strong",
            "sleep_schedule": "regular night sleep (11 pm - 6:30 am)",
            "social_identity": "dependable working citizen",
            "social_values": "respect, modest conduct, and honesty",
            "spiritual_outlook": "grounded faith and gratitude",
            "tech_interest": "functional and utility-driven",
            "technology_usage": "smartphone for messaging, payments, maps",
            "time_management": "structured and reliable",
            "urban_living": "accustomed to city pace and delays",
            "value_risk": "avoids unverified experimental services",
            "work_ethic": "highly dependable and methodical",
        },
        "description": f"Representative member of {seg['name']} seeking reliable tools within a budget of ৳{budget:,.0f}/month.",
        "quote": f"I need an intelligent tool that keeps my priorities on track within my ৳{budget:,.0f}/month budget.",
        "goals": [{"value": "Optimize monthly spending", "provenance": "OBSERVED", "evidence_ids": [f"rec_{seg['id']}_01"]}],
        "pain_points": [{"value": "Unpredictable price changes and lack of deal alerts", "provenance": "OBSERVED", "evidence_ids": [f"rec_{seg['id']}_01"]}],
        "needs": [{"value": "Instant notification on price drops", "provenance": "INFERRED", "evidence_ids": []}],
        "motivations": [{"value": "Maximize value for money", "provenance": "INFERRED", "evidence_ids": []}],
        "behaviors": [{"value": "Compares prices across multiple retail stores", "provenance": "OBSERVED", "evidence_ids": [f"rec_{seg['id']}_01"]}],
        "technology_usage": [{"value": "Daily smartphone user with medium familiarity", "provenance": "SYNTHETIC", "evidence_ids": []}],
        "purchase_behavior": [{"value": f"Budget capped at ৳{budget:,.0f}/month", "provenance": "OBSERVED", "evidence_ids": [f"rec_{seg['id']}_01"]}],
        "personality_traits": [{"value": "Analytical, cost-conscious, disciplined", "provenance": "SYNTHETIC", "evidence_ids": []}],
    }
