"""setup_datasets.preprocess_router_arena must read the upstream parquet's real
column casing (``Category``/``Domain``/``Question``); the lower-case lookups it
used produced 809 records with empty prompts and no scores — a degenerate
offline replay that the evaluator then turned into a 100% alignment tautology."""

import json

import fastparquet
import pandas as pd

from scripts.setup_datasets import preprocess_router_arena


def _write_parquet(tmp_path, rows):
    parquet = tmp_path / "sub_10-00000-of-00001.parquet"
    fastparquet.write(str(parquet), pd.DataFrame(rows))
    return parquet


def _records(output):
    return [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_upstream_capitalised_columns_populate_prompt_category_and_domain(tmp_path):
    parquet = _write_parquet(tmp_path, [
        {
            "Category": "02 Library and information sciences",
            "Domain": "0 Computer science, information, and general works",
            "Dataset name": "ArcMMLU",
            "Global Index": "ArcMMLU_98",
            "Context": "",
            "Question": "What was originally called the imitation game?",
            "Options": ["The Turing test", "Lisp"],
            "Answer": "A",
            "Metadata": "{}",
            "Keywords": "",
            "Difficulty": "easy",
        }
    ])
    out = tmp_path / "router_arena.jsonl"
    assert preprocess_router_arena([parquet], out) == 1
    (rec,) = _records(out)
    assert rec["prompt"] == "What was originally called the imitation game?"
    assert rec["category"] == "02 Library and information sciences"
    assert rec["domain"] == "0 Computer science, information, and general works"
    assert rec["source_dataset"] == "ArcMMLU" and rec["difficulty"] == "easy"
    # The pinned slice carries no per-model labels: say so with an empty dict,
    # never a fabricated score.
    assert rec["model_scores"] == {}


def test_lowercase_columns_and_numeric_model_columns_still_work(tmp_path):
    parquet = _write_parquet(tmp_path, [
        {"question": "q1", "category": "coding", "domain": "software",
         "gpt-4o": 0.91, "llama-3.1-70b": 0.85, "Difficulty": "hard"},
    ])
    out = tmp_path / "router_arena.jsonl"
    assert preprocess_router_arena([parquet], out) == 1
    (rec,) = _records(out)
    assert rec["prompt"] == "q1" and rec["category"] == "coding" and rec["domain"] == "software"
    assert rec["model_scores"] == {"gpt-4o": 0.91, "llama-3.1-70b": 0.85}
    assert "difficulty" not in rec["model_scores"]  # text columns are never scores


def test_domain_falls_back_to_category_when_absent(tmp_path):
    parquet = _write_parquet(tmp_path, [{"Question": "q", "Category": "math"}])
    out = tmp_path / "router_arena.jsonl"
    preprocess_router_arena([parquet], out)
    (rec,) = _records(out)
    assert rec["category"] == "math" and rec["domain"] == "math"
