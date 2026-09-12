"""Cross-route persona consistency — the research question's missing metric.

Question: does a synthetic persona's identity survive being served by
DIFFERENT providers/models? The system's routing is only useful if the
persona signal dominates the provider signal. This module measures that:

- identity_fact_retention — share of probed identity facts (name, age,
  occupation, location) restated correctly in the answer, per route;
- numeric_divergence — |claimed monthly BDT amount − persona budget| where a
  money probe was asked (monthly-normalised by the interview engine's rate
  extractor when importable, a local regex otherwise);
- cross_route_agreement — mean pairwise cosine (HashEmbedding) between answers
  to the SAME question by the SAME persona across DIFFERENT routes, against
  baseline_agreement (DIFFERENT personas, same question); ratio > 1 means the
  persona signal dominates the provider signal;
- contradiction_count — the interview engine's numeric self-contradiction
  detector over each (persona, route) answer sequence, when importable purely;
- provenance per answer — served_by provider/model, attempts, whether the
  requested route was honoured. Preference is advisory in PoolRouter, so an
  answer served by a fallback route is reported as such, never relabelled.

Everything here is pure and deterministic except the runner, which takes any
``LLMService`` — tests and ``--fake`` runs use FakeAdapter-backed routers.
"""

from __future__ import annotations

import math
import random
import re
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any

from bebshax.llm.adapters.base import AdapterCompletion, RouteCandidate
from bebshax.llm.adapters.embeddings import EmbeddingBackend, HashEmbedding
from bebshax.llm.adapters.fake import FakeAdapter, FakeRoute
from bebshax.llm.failures import LLMError
from bebshax.llm.pools import FREELLMPOOL, OPENROUTER
from bebshax.llm.provenance import ProvenanceRecord
from bebshax.llm.router import PoolRouter
from bebshax.llm.service import LLMService
from bebshax.llm.types import ChatMessage, LLMRequest, TaskType

REPORT_KIND = "cross_route_persona_consistency"

try:  # optional: reuse the interview engine's extractors when importable
    from bebshax.interview.engine import InterviewEngine as _InterviewEngine
    from bebshax.interview.engine import _extract_money_rates as _engine_money_rates
except Exception:  # pragma: no cover - engine import is heavy, keep metrics usable without it
    _InterviewEngine = None
    _engine_money_rates = None


# ------------------------------------------------------------------ inputs ---


@dataclass(frozen=True)
class PersonaFacts:
    persona_id: str
    name: str
    age: int
    occupation: str
    location: str
    monthly_budget_bdt: float | None = None

    def identity_card(self) -> str:
        budget = (
            f"Monthly budget for apps/services: {self.monthly_budget_bdt:.0f} BDT"
            if self.monthly_budget_bdt is not None
            else "Monthly budget for apps/services: not stated"
        )
        return (
            "IDENTITY (immutable — never contradict it):\n"
            f"Name: {self.name}\n"
            f"Age: {self.age}\n"
            f"Occupation: {self.occupation}\n"
            f"Location: {self.location}\n"
            f"{budget}\n"
            "Answer every question in the first person as this person, in 2-4 sentences, "
            "restating the relevant identity facts when asked about yourself."
        )


@dataclass(frozen=True)
class Route:
    provider: str | None
    model: str | None

    @property
    def label(self) -> str:
        return f"{self.provider or '*'}/{self.model or '*'}"

    @classmethod
    def parse(cls, spec: str) -> "Route":
        """'provider/model' — either side may be '*' (or empty) for 'any'."""
        provider, sep, model = spec.strip().partition("/")
        if not sep:
            raise ValueError(f"route must look like provider/model, got {spec!r}")
        return cls(
            None if provider in ("", "*") else provider,
            None if model in ("", "*") else model,
        )


@dataclass(frozen=True)
class Question:
    id: str
    text: str
    probes: tuple[str, ...] = ()  # subset of PROBES


PROBES = ("name", "age", "occupation", "location")

QUESTION_BANK: tuple[Question, ...] = (
    Question("q_identity", "Introduce yourself briefly: your name, your age and what you do.", ("name", "age", "occupation")),
    Question("q_location", "Where do you live, and how does that shape a typical day for you?", ("location",)),
    Question("q_budget", "How much could you spend per month, in taka, on an app that plans your study or work schedule?", ("budget",)),
    Question("q_pain", "What is the most frustrating part of organising your week?", ()),
    Question("q_switch", "What would make you stop using such an app after the first month?", ()),
)

# Deterministic Bangladesh-context persona bank for CLI runs (identity facts only).
PERSONA_BANK: tuple[PersonaFacts, ...] = (
    PersonaFacts("cr_nusrat", "Nusrat Jahan", 24, "third-year BBA undergraduate", "Mohammadpur, Dhaka", 300),
    PersonaFacts("cr_tanvir", "Tanvir Ahmed", 27, "junior software developer", "Mirpur, Dhaka", 800),
    PersonaFacts("cr_farzana", "Farzana Akter", 21, "pharmacy student", "Uttara, Dhaka", 250),
    PersonaFacts("cr_rafiqul", "Rafiqul Islam", 34, "coaching-centre teacher", "Khilgaon, Dhaka", 500),
    PersonaFacts("cr_sabrina", "Sabrina Chowdhury", 30, "bank officer", "Banani, Dhaka", 1200),
    PersonaFacts("cr_mehedi", "Mehedi Hasan", 19, "HSC candidate", "Savar, Dhaka", 150),
)


# ------------------------------------------------------------ extraction ---

_AGE_PATTERNS = (
    re.compile(r"\b(\d{2})\s*(?:years?\s*old|-year-old|yrs?\b|years? of age)", re.IGNORECASE),
    re.compile(r"\b(?:I am|I'm|I’m|aged?)\s+(\d{2})\b", re.IGNORECASE),
    re.compile(r"\bage\s*(?:is|:)?\s*(\d{2})\b", re.IGNORECASE),
)
_STOPWORDS = frozenset({"and", "the", "with", "from", "student", "worker", "candidate", "officer"})
_WORD_RE = re.compile(r"[a-z0-9]+")
_LOCAL_MONEY_RE = re.compile(
    r"(?:৳|tk\.?|bdt|taka)\s*(\d[\d,]{0,8})|(\d[\d,]{0,8})\s*(?:৳|tk\b|bdt\b|taka\b)", re.IGNORECASE
)


def extract_age(answer: str) -> int | None:
    for pattern in _AGE_PATTERNS:
        match = pattern.search(answer)
        if match:
            age = int(match.group(1))
            if 16 <= age <= 95:
                return age
    return None


def _keywords(text: str) -> set[str]:
    return {w for w in _WORD_RE.findall(text.lower()) if len(w) >= 4 and w not in _STOPWORDS}


def extract_bdt_amounts(answer: str) -> list[float]:
    """Monthly-normalised BDT amounts via the interview engine when available,
    else raw BDT amounts from a local regex (no period normalisation)."""
    if _engine_money_rates is not None:
        rates = _engine_money_rates(answer.lower(), "BD")
        if rates:
            return [amount for amount, _ in rates]
    amounts: list[float] = []
    for a, b in _LOCAL_MONEY_RE.findall(answer):
        raw = (a or b).replace(",", "")
        if raw.isdigit():
            amounts.append(float(raw))
    return amounts


def fact_retention(facts: PersonaFacts, answer: str, probes: Sequence[str]) -> dict[str, bool]:
    """Per probed identity fact: was it restated correctly? Unprobed facts are absent."""
    lowered = answer.lower()
    checks: dict[str, Callable[[], bool]] = {
        "name": lambda: facts.name.split()[0].lower() in lowered,
        "age": lambda: extract_age(answer) == facts.age,
        "occupation": lambda: bool(_keywords(facts.occupation) & _keywords(answer)),
        "location": lambda: bool(_keywords(facts.location) & _keywords(answer)),
    }
    return {probe: checks[probe]() for probe in probes if probe in checks}


def numeric_divergence(facts: PersonaFacts, answer: str) -> float | None:
    """|first claimed monthly BDT amount − persona budget|; None when unmeasurable."""
    if facts.monthly_budget_bdt is None:
        return None
    amounts = extract_bdt_amounts(answer)
    if not amounts:
        return None
    return abs(amounts[0] - facts.monthly_budget_bdt)


def cosine(a: Sequence[float], b: Sequence[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


def mean(values: Sequence[float]) -> float | None:
    return sum(values) / len(values) if values else None


def bootstrap_ci(
    values: Sequence[float], seed: int, n_boot: int = 1000, alpha: float = 0.05
) -> tuple[float, float] | None:
    """Seeded percentile bootstrap of the mean. None for empty input."""
    if not values:
        return None
    rng = random.Random(seed)
    n = len(values)
    means = sorted(sum(values[rng.randrange(n)] for _ in range(n)) / n for _ in range(n_boot))
    lo = means[int(math.floor(alpha / 2 * (n_boot - 1)))]
    hi = means[int(math.ceil((1 - alpha / 2) * (n_boot - 1)))]
    return lo, hi


# ----------------------------------------------------------------- rows ---


@dataclass
class AnswerRow:
    persona_id: str
    question_id: str
    route_requested: str
    repeat: int
    answer: str | None
    success: bool
    served_by_provider: str | None = None
    served_by_model: str | None = None
    route_honoured: bool | None = None
    attempts: int = 0
    latency_ms: float | None = None
    error: str | None = None
    retention: dict[str, bool] = field(default_factory=dict)
    numeric_divergence: float | None = None
    request_id: str | None = None

    @property
    def route_served(self) -> str | None:
        if self.served_by_provider is None:
            return None
        return f"{self.served_by_provider}/{self.served_by_model}"


def agreement_metrics(
    rows: Sequence[AnswerRow], vectors: dict[int, Sequence[float]]
) -> dict[str, Any]:
    """Pairwise cosines: same persona+question across different SERVED routes vs.
    different personas on the same question. ``vectors`` is keyed by row index.

    Pairing uses ``route_served`` (the concrete provider/model that answered),
    never ``route_requested``: preference is advisory in PoolRouter, so two rows
    requested on different routes may have been served by one model — comparing
    them would measure within-model repeatability and call it cross-route.
    When fewer than two distinct routes actually served, the metric is None."""
    served = [(i, r) for i, r in enumerate(rows) if r.success and i in vectors]
    distinct_served = {r.route_served for _, r in served if r.route_served}
    same_persona: list[float] = []
    cross_persona: list[float] = []
    for a in range(len(served)):
        ia, ra = served[a]
        for b in range(a + 1, len(served)):
            ib, rb = served[b]
            if ra.question_id != rb.question_id:
                continue
            sim = cosine(vectors[ia], vectors[ib])
            if ra.persona_id == rb.persona_id:
                if ra.route_served and rb.route_served and ra.route_served != rb.route_served:
                    same_persona.append(sim)
            else:
                cross_persona.append(sim)
    measurable = len(distinct_served) >= 2
    agreement = mean(same_persona) if measurable else None
    baseline = mean(cross_persona)
    ratio = (agreement / baseline) if agreement is not None and baseline else None
    note = None
    if not measurable:
        note = (
            f"cross-route agreement not measurable: only {len(distinct_served)} distinct route(s) "
            f"actually served ({', '.join(sorted(distinct_served)) or 'none'}) — requested routes "
            "that were not honoured are reported per row, never relabelled"
        )
    return {
        "cross_route_agreement": agreement,
        "baseline_agreement": baseline,
        "agreement_ratio": ratio,
        "n_same_persona_pairs": len(same_persona) if measurable else 0,
        "n_cross_persona_pairs": len(cross_persona),
        "distinct_served_routes": sorted(distinct_served),
        "agreement_note": note,
        "_same_persona_values": same_persona if measurable else [],
        "_cross_persona_values": cross_persona,
    }


def contradiction_count(
    personas: Sequence[PersonaFacts], rows: Sequence[AnswerRow], questions: Sequence[Question]
) -> tuple[int | None, str]:
    """Interview-engine numeric self-contradiction detector over each
    (persona, route, repeat) answer sequence. None with a note when the engine
    is not importable or its method stopped being pure."""
    if _InterviewEngine is None:
        return None, "skipped: bebshax.interview.engine not importable"
    detect = getattr(_InterviewEngine, "_detect_contradiction", None)
    if detect is None:
        return None, "skipped: InterviewEngine._detect_contradiction not found"
    by_id = {p.persona_id: p for p in personas}
    q_text = {q.id: q.text for q in questions}
    sequences: dict[tuple[str, str, int], list[AnswerRow]] = {}
    for row in rows:
        if row.success and row.answer:
            sequences.setdefault((row.persona_id, row.route_requested, row.repeat), []).append(row)
    count = 0
    try:
        for (pid, _route, _rep), seq in sequences.items():
            facts = by_id[pid]
            stub = SimpleNamespace(
                commercial_profile=(
                    {"monthly_budget_bdt": facts.monthly_budget_bdt}
                    if facts.monthly_budget_bdt is not None
                    else {}
                ),
                country_code="BD",
            )
            prior: list[str] = []
            for row in seq:
                # unbound call: the detector reads only its arguments, never `self`
                found, *_ = detect(None, stub, q_text.get(row.question_id, ""), row.answer or "", prior)
                count += 1 if found else 0
                prior.append(row.answer or "")
    except (AttributeError, TypeError) as exc:
        return None, f"skipped: detector no longer pure ({exc!r})"
    return count, "InterviewEngine._detect_contradiction over each (persona, route, repeat) sequence"


# --------------------------------------------------------------- report ---


@dataclass
class CrossRouteReport:
    generated_at: str
    seed: int
    n_personas: int
    n_questions: int
    n_routes: int
    n_repeats: int
    n_rows: int
    n_served: int
    n_failed: int
    rows: list[dict[str, Any]]
    per_route: dict[str, dict[str, Any]]
    identity_fact_retention: float | None
    identity_fact_retention_ci95: tuple[float, float] | None
    n_probed_facts: int
    numeric_divergence_mean_bdt: float | None
    n_numeric_probes: int
    cross_route_agreement: float | None
    cross_route_agreement_ci95: tuple[float, float] | None
    baseline_agreement: float | None
    baseline_agreement_ci95: tuple[float, float] | None
    agreement_ratio: float | None
    n_same_persona_pairs: int
    n_cross_persona_pairs: int
    contradiction_count: int | None
    contradiction_note: str
    embedding_space: str
    notes: list[str]
    kind: str = REPORT_KIND
    simulated: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _route_aggregate(rows: Sequence[AnswerRow]) -> dict[str, Any]:
    probed = [v for r in rows if r.success for v in r.retention.values()]
    divergences = [r.numeric_divergence for r in rows if r.success and r.numeric_divergence is not None]
    served_routes: dict[str, int] = {}
    for r in rows:
        if r.route_served:
            served_routes[r.route_served] = served_routes.get(r.route_served, 0) + 1
    return {
        "identity_fact_retention": mean([1.0 if v else 0.0 for v in probed]),
        "n_probed_facts": len(probed),
        "numeric_divergence_mean_bdt": mean(divergences),
        "n_numeric_probes": len(divergences),
        "served": sum(1 for r in rows if r.success),
        "failed": sum(1 for r in rows if not r.success),
        "route_honoured": sum(1 for r in rows if r.route_honoured),
        "served_routes": served_routes,
        "mean_attempts": mean([float(r.attempts) for r in rows]),
    }


async def compute_report(
    personas: Sequence[PersonaFacts],
    questions: Sequence[Question],
    routes: Sequence[Route],
    rows: Sequence[AnswerRow],
    *,
    repeats: int = 1,
    seed: int = 42,
    embedder: EmbeddingBackend | None = None,
    simulated: bool = False,
    notes: Sequence[str] = (),
) -> CrossRouteReport:
    embedder = embedder or HashEmbedding()
    served_idx = [i for i, r in enumerate(rows) if r.success and r.answer]
    vectors: dict[int, Sequence[float]] = {}
    if served_idx:
        embedded = await embedder.embed([rows[i].answer or "" for i in served_idx])
        vectors = dict(zip(served_idx, embedded))
    agree = agreement_metrics(rows, vectors)

    probed = [1.0 if v else 0.0 for r in rows if r.success for v in r.retention.values()]
    divergences = [r.numeric_divergence for r in rows if r.success and r.numeric_divergence is not None]
    contradictions, contradiction_note = contradiction_count(personas, rows, questions)
    report_notes = list(notes)
    if agree["agreement_note"]:
        report_notes.append(agree["agreement_note"])
    if agree["distinct_served_routes"]:
        report_notes.append("routes that actually served: " + ", ".join(agree["distinct_served_routes"]))

    per_route = {
        route.label: _route_aggregate([r for r in rows if r.route_requested == route.label])
        for route in routes
    }
    return CrossRouteReport(
        generated_at=datetime.now(timezone.utc).isoformat(),
        seed=seed,
        n_personas=len(personas),
        n_questions=len(questions),
        n_routes=len(routes),
        n_repeats=repeats,
        n_rows=len(rows),
        n_served=sum(1 for r in rows if r.success),
        n_failed=sum(1 for r in rows if not r.success),
        rows=[{**asdict(r), "route_served": r.route_served} for r in rows],
        per_route=per_route,
        identity_fact_retention=mean(probed),
        identity_fact_retention_ci95=bootstrap_ci(probed, seed),
        n_probed_facts=len(probed),
        numeric_divergence_mean_bdt=mean(divergences),
        n_numeric_probes=len(divergences),
        cross_route_agreement=agree["cross_route_agreement"],
        cross_route_agreement_ci95=bootstrap_ci(agree["_same_persona_values"], seed + 1),
        baseline_agreement=agree["baseline_agreement"],
        baseline_agreement_ci95=bootstrap_ci(agree["_cross_persona_values"], seed + 2),
        agreement_ratio=agree["agreement_ratio"],
        n_same_persona_pairs=agree["n_same_persona_pairs"],
        n_cross_persona_pairs=agree["n_cross_persona_pairs"],
        contradiction_count=contradictions,
        contradiction_note=contradiction_note,
        embedding_space=embedder.space,
        notes=report_notes,
        simulated=simulated,
    )


# --------------------------------------------------------------- runner ---


async def run_cross_route_eval(
    llm: LLMService,
    personas: Sequence[PersonaFacts],
    questions: Sequence[Question],
    routes: Sequence[Route],
    *,
    repeats: int = 1,
    seed: int = 42,
    task: TaskType = TaskType.PERSONA_INTERVIEW,
    embedder: EmbeddingBackend | None = None,
    simulated: bool = False,
    notes: Sequence[str] = (),
) -> CrossRouteReport:
    """K personas × Q questions × M routes × repeats through ``llm.complete``.

    Each question is asked single-turn under the persona's identity card so a
    route's effect is isolated; the requested route is a PoolRouter preference,
    and the row records what actually served. Failures are rows too."""
    rows: list[AnswerRow] = []
    for persona in personas:
        card = persona.identity_card()
        for route in routes:
            for repeat in range(1, repeats + 1):
                for question in questions:
                    request = LLMRequest(
                        task=task,
                        messages=[
                            ChatMessage(role="system", content=card),
                            ChatMessage(role="user", content=question.text),
                        ],
                        persona_id=persona.persona_id,
                        preferred_provider=route.provider,
                        preferred_model=route.model,
                        temperature=0.0,
                        max_output_tokens=300,
                    )
                    row = AnswerRow(
                        persona_id=persona.persona_id,
                        question_id=question.id,
                        route_requested=route.label,
                        repeat=repeat,
                        answer=None,
                        success=False,
                        request_id=request.request_id,
                    )
                    try:
                        result = await llm.complete(request)
                    except LLMError as exc:
                        row.error = f"{type(exc).__name__}: {exc}"
                        prov = getattr(exc, "provenance", None)
                        if prov is not None:
                            row.attempts = len(prov.attempts)
                            row.latency_ms = prov.total_latency_ms
                        rows.append(row)
                        continue
                    prov = result.provenance
                    row.answer = result.text
                    row.success = True
                    row.served_by_provider = prov.served_by_provider
                    row.served_by_model = prov.served_by_model
                    # A virtual routing candidate (e.g. freellmpool/auto) is honoured
                    # when it produced the answer, whichever concrete provider it chose.
                    via = next((a.via for a in reversed(prov.attempts) if a.success and a.via), None)
                    via_provider, _, via_model = (via or "").partition("/")
                    row.route_honoured = (
                        (
                            route.provider is None
                            or prov.served_by_provider == route.provider
                            or via_provider == route.provider
                        )
                        and (
                            route.model is None
                            or prov.served_by_model == route.model
                            or via_model == route.model
                        )
                    )
                    row.attempts = len(prov.attempts)
                    row.latency_ms = prov.total_latency_ms
                    row.retention = fact_retention(persona, result.text, question.probes)
                    if "budget" in question.probes:
                        row.numeric_divergence = numeric_divergence(persona, result.text)
                    rows.append(row)
    return await compute_report(
        personas, questions, routes, rows,
        repeats=repeats, seed=seed, embedder=embedder, simulated=simulated, notes=notes,
    )


# ----------------------------------------------------- scripted adapter ---

_CARD_FIELD_RE = re.compile(r"^(Name|Age|Occupation|Location|Monthly budget for apps/services): (.+)$", re.MULTILINE)


class ScriptedRouteAdapter(FakeAdapter):
    """FakeAdapter whose reply is composed deterministically from the identity
    card in the request: persona-dependent, lightly route-flavoured. This is
    the offline pipeline check for ``--fake`` runs — it proves the harness,
    never a model."""

    @staticmethod
    def _facts(request: LLMRequest) -> dict[str, str]:
        system = next((m.content for m in request.messages if m.role == "system"), "")
        return {k: v.strip() for k, v in _CARD_FIELD_RE.findall(system)}

    def script(self, candidate: RouteCandidate, request: LLMRequest) -> str:
        f = self._facts(request)
        question = next((m.content for m in reversed(request.messages) if m.role == "user"), "").lower()
        name, age = f.get("Name", "someone"), f.get("Age", "??")
        occupation, location = f.get("Occupation", "a worker"), f.get("Location", "Dhaka")
        budget_field = f.get("Monthly budget for apps/services", "")
        budget = re.search(r"(\d+)", budget_field)
        flavour = f"(voice: {candidate.model})"
        if "taka" in question or "spend" in question:
            if budget:
                return (
                    f"Honestly, around ৳{budget.group(1)} per month is what I could spare for it — "
                    f"about what I pay for mobile data. {flavour}"
                )
            return f"I have not put a number on it; it depends on the month. {flavour}"
        if "yourself" in question or "your name" in question:
            return f"I'm {name}, {age} years old, and I'm a {occupation} here in {location}. {flavour}"
        if "live" in question:
            return f"I live in {location}; as a {occupation} my day is shaped by commuting there. {flavour}"
        return f"As a {occupation} in {location}, the hardest part is keeping every commitment in one place. {flavour}"

    async def complete(self, candidate: RouteCandidate, request: LLMRequest) -> AdapterCompletion:
        route = self._routes[(candidate.provider, candidate.model)]
        route.replies = [self.script(candidate, request)]  # scripted failures still fire first
        return await super().complete(candidate, request)


def scripted_router(
    routes: Sequence[Route], on_provenance: Callable[[ProvenanceRecord], None] | None = None
) -> PoolRouter:
    """Throwaway PoolRouter serving every requested route from one scripted adapter."""
    fake_routes = [
        FakeRoute(RouteCandidate(provider=r.provider or "fake", model=r.model or "scripted"))
        for r in routes
    ]
    adapters = {
        OPENROUTER: FakeAdapter([]),
        FREELLMPOOL: ScriptedRouteAdapter(fake_routes),
    }
    return PoolRouter(adapters, on_provenance=on_provenance)


# ------------------------------------------------------------- markdown ---


def _fmt(value: float | None, digits: int = 3) -> str:
    return "not measured" if value is None else f"{value:.{digits}f}"


def _fmt_ci(ci: tuple[float, float] | None) -> str:
    return "n/a" if ci is None else f"[{ci[0]:.3f}, {ci[1]:.3f}]"


def to_markdown(report: CrossRouteReport) -> str:
    lines = [
        f"# Cross-route persona consistency — {report.generated_at}",
        "",
        f"**Kind:** `{report.kind}`  **Simulated:** `{report.simulated}`  **Seed:** `{report.seed}`",
        "",
        f"n = {report.n_personas} personas × {report.n_questions} questions × {report.n_routes} routes "
        f"× {report.n_repeats} repeats = {report.n_rows} rows ({report.n_served} served, {report.n_failed} failed)",
        "",
        "| Metric | Value | 95% CI (bootstrap) | n |",
        "|---|---|---|---|",
        f"| identity_fact_retention | {_fmt(report.identity_fact_retention)} | {_fmt_ci(report.identity_fact_retention_ci95)} | {report.n_probed_facts} facts |",
        f"| numeric_divergence_mean_bdt | {_fmt(report.numeric_divergence_mean_bdt, 1)} | n/a | {report.n_numeric_probes} probes |",
        f"| cross_route_agreement | {_fmt(report.cross_route_agreement)} | {_fmt_ci(report.cross_route_agreement_ci95)} | {report.n_same_persona_pairs} pairs |",
        f"| baseline_agreement | {_fmt(report.baseline_agreement)} | {_fmt_ci(report.baseline_agreement_ci95)} | {report.n_cross_persona_pairs} pairs |",
        f"| agreement_ratio (>1 ⇒ persona signal dominates) | {_fmt(report.agreement_ratio)} | n/a | — |",
        f"| contradiction_count | {report.contradiction_count if report.contradiction_count is not None else 'not measured'} | n/a | {report.contradiction_note} |",
        "",
        "## Per requested route",
        "",
        "| Route | retention | divergence (BDT) | served | failed | honoured | served by |",
        "|---|---|---|---|---|---|---|",
    ]
    for label, agg in report.per_route.items():
        served_by = ", ".join(f"{k}×{v}" for k, v in agg["served_routes"].items()) or "—"
        lines.append(
            f"| `{label}` | {_fmt(agg['identity_fact_retention'])} | {_fmt(agg['numeric_divergence_mean_bdt'], 1)} "
            f"| {agg['served']} | {agg['failed']} | {agg['route_honoured']} | {served_by} |"
        )
    if report.notes:
        lines.extend(["", "## Notes", ""] + [f"- {n}" for n in report.notes])
    lines.append("")
    return "\n".join(lines)


__all__ = [
    "PERSONA_BANK",
    "PROBES",
    "QUESTION_BANK",
    "REPORT_KIND",
    "AnswerRow",
    "CrossRouteReport",
    "PersonaFacts",
    "Question",
    "Route",
    "ScriptedRouteAdapter",
    "agreement_metrics",
    "bootstrap_ci",
    "compute_report",
    "contradiction_count",
    "cosine",
    "extract_age",
    "extract_bdt_amounts",
    "fact_retention",
    "numeric_divergence",
    "run_cross_route_eval",
    "scripted_router",
    "to_markdown",
]
