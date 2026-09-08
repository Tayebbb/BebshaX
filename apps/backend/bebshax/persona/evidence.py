"""Evidence retrieval over Phase-7 processed datasets.

Deliberately lightweight (owner requirement: quality without weight):
- lazy one-time load per process, hard caps on records and stored text;
- deterministic idf-weighted lexical overlap scoring (~zero dependencies,
  milliseconds over the grounding corpora) — semantic/pgvector retrieval
  arrives with Phase 9 memory and can replace the scorer;
- graceful degradation: missing datasets ⇒ empty evidence ⇒ attributes come
  out SYNTHETIC/INFERRED, never fabricated OBSERVED.

Dataset ROLES are a data table: only real-world corpora may serve as citable
evidence. PersonaHub sketches are synthetic by construction — letting a
persona cite one as OBSERVED would be an invented fact wearing an evidence
badge — so they power diversity seeds only (arXiv:2406.20094 methodology:
a seed diversifies the generation perspective; it is never copied into the
persona identity and never counts as observation).
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from pathlib import Path

from bebshax.config import get_settings
from bebshax.persona.schema import EvidenceItem

_TOKEN_RE = re.compile(r"[a-z0-9]{3,}")
_TEXT_FIELDS = ("persona", "text", "utterance", "review_text", "content", "body", "prompt")

# Dataset → role. Extend the table, never add code branches (conventions).
#   grounding          — real-world records personas may cite as OBSERVED
#   seed               — synthetic diversity sketches (perspective only)
#   probe              — routing/capability checks; never evidence
#   dialogue_examples  — synthetic conversations; never evidence
DATASET_ROLES: dict[str, str] = {
    "amazon_reviews_office_products": "grounding",
    "empathetic_dialogues_slice": "grounding",
    "mbti_personality_traits": "grounding",
    "personahub_sample": "seed",
    "synthetic_persona_chat": "dialogue_examples",
    "lmsys_chat_1m": "dialogue_examples",  # contains LLM-generated turns — never evidence
    "gsm8k_micro": "probe",
    "mmlu_micro": "probe",
    "router_arena": "probe",
    "xroute_bench": "probe",
    "nemotron_personas_usa_ml": "training",
}
# Unknown files are presumed real corpora added for grounding — the safe
# default for the intended extension path (drop a real dataset in, it works).
_DEFAULT_ROLE = "grounding"

MAX_RECORDS_PER_DATASET = 30_000
MAX_STORED_CHARS = 500
# Noise floor: one-liners ("Great!", "Cute, affordable and fast delivery!")
# carry no citable research signal and dilute idf statistics.
MIN_RECORD_CHARS = 50
# Single-token coincidences ("lunch" matching an unrelated utterance about
# lunch) are topical noise — require at least this much query overlap.
MIN_QUERY_OVERLAP = 2
SEED_DATASET = "personahub_sample"


def _tokens(text: str) -> set[str]:
    return set(_TOKEN_RE.findall(text.lower()))


class _Doc:
    __slots__ = ("source", "text", "tokens")

    def __init__(self, source: str, text: str) -> None:
        self.source = source
        self.text = text[:MAX_STORED_CHARS]
        self.tokens = _tokens(self.text)


class EvidenceStore:
    def __init__(self, processed_dir: Path | str | None = None) -> None:
        # None -> configured processed root (BEBSHAX_PROCESSED_DIR / BEBSHAX_DATA_DIR),
        # resolved when the store is built, not at import time.
        self._dir = Path(processed_dir) if processed_dir is not None else get_settings().processed_dir_path
        self._docs: list[_Doc] | None = None
        self._seeds: list[str] | None = None
        self._df: dict[str, int] = {}

    def _read_records(self, path: Path) -> list[str]:
        """Texts from one jsonl file — deduped, noise-filtered, capped."""
        texts: list[str] = []
        seen: set[str] = set()
        with open(path, encoding="utf-8") as f:
            for line in f:
                if len(texts) >= MAX_RECORDS_PER_DATASET:
                    break
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                text = next((str(record[k]).strip() for k in _TEXT_FIELDS if record.get(k)), "")
                if len(text) < MIN_RECORD_CHARS:
                    continue
                # near-exact dedupe: repeated utterances/reviews add no signal
                # and skew idf weights toward their vocabulary
                fingerprint = " ".join(text.lower().split())[:MAX_STORED_CHARS]
                if fingerprint in seen:
                    continue
                seen.add(fingerprint)
                texts.append(text)
        return texts

    def _load(self) -> list[_Doc]:
        if self._docs is not None:
            return self._docs
        docs: list[_Doc] = []
        seeds: list[str] = []
        if self._dir.is_dir():
            for path in sorted(self._dir.glob("*.jsonl")):
                role = DATASET_ROLES.get(path.stem, _DEFAULT_ROLE)
                if role not in ("grounding", "seed"):
                    continue
                texts = self._read_records(path)
                if role == "grounding":
                    docs.extend(_Doc(path.stem, t) for t in texts)
                else:
                    seeds.extend(texts)
        for doc in docs:
            for tok in doc.tokens:
                self._df[tok] = self._df.get(tok, 0) + 1
        self._docs = docs
        self._seeds = seeds
        return docs

    def available_sources(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for doc in self._load():
            counts[doc.source] = counts.get(doc.source, 0) + 1
        return counts

    def retrieve(self, query: str, k: int = 6, per_source_cap: int = 3) -> list[EvidenceItem]:
        docs = self._load()
        if not docs:
            return []
        n_docs = len(docs)
        avg_len = sum(len(d.tokens) for d in docs) / n_docs
        query_tokens = _tokens(query)
        if not query_tokens:
            return []
        # Single-token queries can never clear the overlap floor — let them
        # match on their one token rather than silently returning nothing.
        min_overlap = min(MIN_QUERY_OVERLAP, len(query_tokens))

        scored: list[tuple[float, _Doc]] = []
        for doc in docs:
            overlap = query_tokens & doc.tokens
            if len(overlap) < min_overlap:
                continue
            # BM25-style scoring with tf=1 (set semantics): idf per matched
            # term, saturating length normalization (k1=1.5, b=0.75) — the
            # previous sqrt(len) divisor let 6-token one-liners outrank
            # substantive records on the same matches.
            dl_norm = 1.0 - 0.75 + 0.75 * (len(doc.tokens) / avg_len) if avg_len else 1.0
            score = sum(
                (1.0 + math.log(n_docs / (1 + self._df.get(t, 0)))) * 2.5 / (1.0 + 1.5 * dl_norm)
                for t in overlap
            )
            scored.append((score, doc))
        scored.sort(key=lambda pair: pair[0], reverse=True)

        top_score = scored[0][0] if scored else 1.0
        picked: list[EvidenceItem] = []
        per_source: dict[str, int] = {}
        for score, doc in scored:
            if len(picked) >= k:
                break
            if per_source.get(doc.source, 0) >= per_source_cap:
                continue
            per_source[doc.source] = per_source.get(doc.source, 0) + 1
            picked.append(
                EvidenceItem(
                    source=doc.source,
                    text=doc.text,
                    type="dataset_record",
                    relevance=round(score / top_score, 4) if top_score else 0.0,
                )
            )
        return picked

    def seed_persona(self, key: str) -> str | None:
        """Deterministic diversity seed from the PersonaHub slice."""
        self._load()
        seeds = self._seeds or []
        if not seeds:
            return None
        index = int(hashlib.sha256(key.encode()).hexdigest(), 16) % len(seeds)
        return seeds[index]
