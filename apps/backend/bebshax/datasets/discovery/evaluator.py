"""Dataset Evaluator & Diversity Ranker for BebshaX.

Deterministic, explainable scoring computed from what the source published and
from THIS study's text — no fixed geography, no domain keyword bonuses, no
credit for being a catalogue entry:

- Relevance: lexical overlap between the study (idea + requirements + queries)
  and the candidate's title/description/tags/variables, plus requirement-variable
  coverage. Unrelated datasets score near 0.
- Quality: direct download available, tabular format, licence stated, size
  known and importable, recency, record count when known.
- Selection: top candidates above both thresholds, one per category first.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from bebshax.datasets.discovery.base_adapter import DatasetCandidateData, DatasetEvaluationResult
from bebshax.datasets.discovery.downloader import MAX_DOWNLOAD_BYTES, looks_downloadable
from bebshax.research.planner import DatasetRequirementSpec
from bebshax.research.search_provider import lexical_relevance, query_tokens

RELEVANCE_SELECT_THRESHOLD = 0.30
QUALITY_SELECT_THRESHOLD = 0.55
_IMPORTABLE_FORMATS = {"csv", "tsv", "json", "jsonl", "xlsx"}


class DatasetEvaluator:
    """Evaluates, scores, and selects dataset candidates."""

    def __init__(self, max_auto_select: int = 4) -> None:
        self.max_auto_select = max_auto_select

    @staticmethod
    def _study_text(idea: str, requirements: list[DatasetRequirementSpec], queries: Optional[list[str]]) -> str:
        parts = [idea, " ".join(queries or [])]
        for req in requirements:
            parts.append(req.category.replace("_", " "))
            parts.append(req.description)
            parts.append(" ".join(req.target_variables))
            parts.append(req.geographic_scope)
            parts.append(req.population_scope)
        return " ".join(p for p in parts if p)

    def calculate_relevance_score(
        self,
        candidate: DatasetCandidateData,
        idea: str,
        requirements: list[DatasetRequirementSpec],
        queries: Optional[list[str]] = None,
    ) -> tuple[float, list[str]]:
        """0–1 relevance computed from token overlap with the study; reasons list what matched."""
        reasons: list[str] = []
        candidate_text = " ".join(
            [candidate.name, candidate.description, " ".join(candidate.tags), " ".join(candidate.relevant_variables),
             candidate.geographic_coverage, candidate.population_coverage, candidate.category.replace("_", " ")]
        )
        study_text = self._study_text(idea, requirements, queries)

        # Two directions: how much of the candidate's own vocabulary the study
        # shares (precision) and how much of the study's key vocabulary the
        # candidate covers (recall). Titles matter more than long notes.
        title_hit = lexical_relevance(candidate.name, study_text)
        body_hit = lexical_relevance(candidate_text, study_text)
        study_cov = lexical_relevance(study_text, candidate_text)
        score = 0.45 * title_hit + 0.30 * body_hit + 0.25 * study_cov

        shared = sorted(query_tokens(candidate.name + " " + " ".join(candidate.tags)) & query_tokens(study_text))
        if shared:
            reasons.append(f"Shares study vocabulary: {', '.join(shared[:6])}")

        matching_vars = 0
        for req in requirements:
            for tv in req.target_variables:
                tv_l = tv.lower()
                if any(tv_l in rv.lower() or rv.lower() in tv_l for rv in candidate.relevant_variables if rv):
                    matching_vars += 1
        if matching_vars:
            score += min(0.15, 0.05 * matching_vars)
            reasons.append(f"Covers {matching_vars} variable(s) named in the research plan")

        geo_terms = query_tokens(" ".join(r.geographic_scope for r in requirements))
        if geo_terms and geo_terms & query_tokens(candidate.geographic_coverage + " " + candidate.name):
            score += 0.10
            reasons.append(f"Geography matches the plan ({candidate.geographic_coverage or candidate.name})")

        if candidate.category == "macro_context":
            reasons.append("Macro context for the target market (not a topical dataset)")

        if not reasons:
            reasons.append("No vocabulary shared with the study — kept for manual review only")
        return max(0.0, min(1.0, round(score, 3))), reasons

    def calculate_quality_score(self, candidate: DatasetCandidateData) -> tuple[float, list[str]]:
        """0–1 quality from published attributes; reasons list what was actually present."""
        score = 0.0
        reasons: list[str] = []

        if looks_downloadable(candidate.download_url) or candidate.raw_data_content:
            score += 0.30
            reasons.append("Direct download available for automated import")
        else:
            reasons.append("Listing only — no direct resource URL published")

        if candidate.format.lower() in _IMPORTABLE_FORMATS:
            score += 0.15
            reasons.append(f"Tabular format ({candidate.format.upper()})")

        if candidate.license.strip():
            score += 0.15
            reasons.append(f"Licence stated: {candidate.license}")
        else:
            reasons.append("No licence published")

        if candidate.size_bytes is not None:
            if candidate.size_bytes <= MAX_DOWNLOAD_BYTES:
                score += 0.15
                reasons.append(f"Size known ({candidate.size_bytes:,} bytes) and within the import ceiling")
            else:
                reasons.append(f"Too large to import automatically ({candidate.size_bytes:,} bytes)")

        if candidate.sample_rows:
            score += 0.10 if candidate.sample_rows >= 100 else 0.05
            reasons.append(f"{candidate.sample_rows:,} records reported")

        if candidate.modified_at:
            try:
                modified = datetime.fromisoformat(candidate.modified_at.replace("Z", "+00:00"))
                if modified.tzinfo is None:
                    modified = modified.replace(tzinfo=timezone.utc)
                age_days = (datetime.now(timezone.utc) - modified).days
                if age_days <= 3 * 365:
                    score += 0.15
                    reasons.append(f"Updated within the last three years ({modified.date().isoformat()})")
                else:
                    score += 0.05
                    reasons.append(f"Last updated {modified.date().isoformat()}")
            except ValueError:
                pass
        elif candidate.source.startswith("World Bank"):
            score += 0.15
            reasons.append("Official statistical series fetched live")

        return max(0.0, min(1.0, round(score, 3))), reasons

    def evaluate_candidates(
        self,
        candidates: list[DatasetCandidateData],
        idea: str,
        requirements: list[DatasetRequirementSpec],
        queries: Optional[list[str]] = None,
    ) -> list[DatasetEvaluationResult]:
        """Score every candidate and auto-select the strongest, category-diverse ones."""
        evaluated: list[DatasetEvaluationResult] = []
        for cand in candidates:
            rel_score, rel_reasons = self.calculate_relevance_score(cand, idea, requirements, queries)
            qual_score, qual_reasons = self.calculate_quality_score(cand)
            evaluated.append(
                DatasetEvaluationResult(
                    candidate=cand,
                    relevance_score=rel_score,
                    quality_score=qual_score,
                    is_selected=False,
                    selection_status="discovered",
                    selection_reason=" • " + "\n• ".join(rel_reasons + qual_reasons),
                    evaluation_details={
                        "relevance_reasons": rel_reasons,
                        "quality_reasons": qual_reasons,
                        "composite_score": round((rel_score * 0.6) + (qual_score * 0.4), 3),
                        "scoring": "lexical_overlap+published_attributes",
                    },
                )
            )

        evaluated.sort(key=lambda x: x.evaluation_details["composite_score"], reverse=True)

        selected_categories: set[str] = set()
        selected = 0
        for res in evaluated:  # pass 1: best per category
            if selected >= self.max_auto_select:
                break
            if (
                res.relevance_score >= RELEVANCE_SELECT_THRESHOLD
                and res.quality_score >= QUALITY_SELECT_THRESHOLD
                and res.candidate.category not in selected_categories
            ):
                res.is_selected, res.selection_status = True, "selected"
                selected_categories.add(res.candidate.category)
                selected += 1
        for res in evaluated:  # pass 2: fill remaining slots
            if selected >= self.max_auto_select:
                break
            if not res.is_selected and res.relevance_score >= RELEVANCE_SELECT_THRESHOLD and res.quality_score >= QUALITY_SELECT_THRESHOLD:
                res.is_selected, res.selection_status = True, "selected"
                selected += 1
        return evaluated
