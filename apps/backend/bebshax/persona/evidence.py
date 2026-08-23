"""Evidence retrieval over Phase-7 processed datasets.

Deliberately lightweight (owner requirement: quality without weight):
- lazy one-time load per process, hard caps on records and stored text;
- deterministic idf-weighted lexical overlap scoring (~zero dependencies,
  milliseconds over the 25k-record PersonaHub slice) — semantic/pgvector
  retrieval arrives with Phase 9 memory and can replace the scorer;
- graceful degradation: missing datasets ⇒ empty evidence ⇒ attributes come
  out SYNTHETIC/INFERRED, never fabricated OBSERVED.

PersonaHub seeds follow the dataset's intended persona-driven methodology
(arXiv:2406.20094): a seed diversifies the generation perspective; it is
never copied into the persona identity.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from pathlib import Path

from bebshax.persona.schema import EvidenceItem

_TOKEN_RE = re.compile(r"[a-z0-9]{3,}")
_TEXT_FIELDS = ("persona", "text", "utterance", "review_text", "content", "body", "prompt")

MAX_RECORDS_PER_DATASET = 30_000
MAX_STORED_CHARS = 500
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
    def __init__(self, processed_dir: Path | str = Path("data/processed")) -> None:
        self._dir = Path(processed_dir)
        self._docs: list[_Doc] | None = None
        self._df: dict[str, int] = {}

    def _load(self) -> list[_Doc]:
        if self._docs is not None:
            return self._docs
        docs: list[_Doc] = []
        if self._dir.is_dir():
            for path in sorted(self._dir.glob("*.jsonl")):
                count = 0
                with open(path, encoding="utf-8") as f:
                    for line in f:
                        if count >= MAX_RECORDS_PER_DATASET:
                            break
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            record = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        text = next(
                            (str(record[k]).strip() for k in _TEXT_FIELDS if record.get(k)), ""
                        )
                        if text:
                            docs.append(_Doc(path.stem, text))
                            count += 1
        for doc in docs:
            for tok in doc.tokens:
                self._df[tok] = self._df.get(tok, 0) + 1
        self._docs = docs
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
        query_tokens = _tokens(query)
        if not query_tokens:
            return []

        scored: list[tuple[float, _Doc]] = []
        for doc in docs:
            overlap = query_tokens & doc.tokens
            if not overlap:
                continue
            score = sum(1.0 + math.log(n_docs / (1 + self._df.get(t, 0))) for t in overlap)
            score /= math.sqrt(len(doc.tokens)) or 1.0
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
        seeds = [d for d in self._load() if d.source == SEED_DATASET]
        if not seeds:
            return None
        index = int(hashlib.sha256(key.encode()).hexdigest(), 16) % len(seeds)
        return seeds[index].text
