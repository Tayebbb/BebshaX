"""Offline unit tests for dataset preprocessing functions using synthetic fixtures."""

import csv
import json
import pandas as pd
import pytest
import fastparquet

from scripts.setup_datasets import (
    preprocess_personahub,
    preprocess_synthetic_persona_chat,
    preprocess_empathetic_dialogues,
    preprocess_amazon_reviews,
    preprocess_mmlu_micro,
    preprocess_gsm8k_micro,
    preprocess_router_arena,
    preprocess_xroute_bench,
)


def test_preprocess_personahub(tmp_path):
    raw_file = tmp_path / "persona.jsonl"
    output_file = tmp_path / "processed_persona.jsonl"

    # Create 20 sample lines
    with open(raw_file, "w", encoding="utf-8") as f:
        for i in range(24):
            f.write(json.dumps({"persona": f"Persona Description #{i+1}"}) + "\n")

    count = preprocess_personahub([raw_file], output_file)
    # With stride=8, 24 lines produce 3 sampled personas (index 8, 16, 24)
    assert count == 3
    assert output_file.exists()

    with open(output_file, "r", encoding="utf-8") as f:
        lines = [json.loads(line) for line in f]
    assert len(lines) == 3
    assert "persona" in lines[0]
    assert "id" in lines[0]
    assert lines[0]["persona"] == "Persona Description #8"


def test_preprocess_synthetic_persona_chat(tmp_path):
    csv_file = tmp_path / "Synthetic-Persona-Chat_train.csv"
    output_file = tmp_path / "processed_spc.jsonl"

    with open(csv_file, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["user 1 personas", "user 2 personas", "Best Talk"])
        writer.writeheader()
        writer.writerow({
            "user 1 personas": "I am a barista.\nI love cats.",
            "user 2 personas": "I am an engineer.\nI like coffee.",
            "Best Talk": "user 1: Hello!\nuser 2: Hi there!",
        })

    count = preprocess_synthetic_persona_chat([csv_file], output_file)
    assert count == 1

    with open(output_file, "r", encoding="utf-8") as f:
        lines = [json.loads(line) for line in f]
    assert len(lines) == 1
    assert lines[0]["persona_1"] == ["I am a barista.", "I love cats."]
    assert len(lines[0]["dialogue"]) == 2
    assert lines[0]["dialogue"][0]["speaker"] == "user 1"


def test_preprocess_empathetic_dialogues(tmp_path):
    parquet_file = tmp_path / "0000.parquet"
    output_file = tmp_path / "processed_ed.jsonl"

    df = pd.DataFrame([
        {"conv_id": "hit:1_conv:1", "speaker_idx": 0, "utterance": "I got promoted today!", "context": "proud", "prompt": "I worked hard for years and finally got promoted."},
        {"conv_id": "hit:1_conv:1", "speaker_idx": 1, "utterance": "Congratulations! That is amazing.", "context": "proud", "prompt": "I worked hard for years and finally got promoted."},
    ])
    fastparquet.write(str(parquet_file), df)

    count = preprocess_empathetic_dialogues([parquet_file], output_file)
    assert count == 2

    with open(output_file, "r", encoding="utf-8") as f:
        lines = [json.loads(line) for line in f]
    assert len(lines) == 2
    assert lines[0]["emotion"] == "proud"
    assert lines[0]["utterance"] == "I got promoted today!"


def test_preprocess_amazon_reviews(tmp_path):
    raw_file = tmp_path / "Office_Products.jsonl"
    output_file = tmp_path / "processed_amz.jsonl"

    with open(raw_file, "w", encoding="utf-8") as f:
        f.write(json.dumps({
            "asin": "B000001",
            "rating": 5.0,
            "title": "Great ergonomic office chair",
            "text": "This chair provides excellent lumbar support for 8-hour workdays. Highly recommended.",
            "timestamp": 1600000000,
        }) + "\n")
        f.write(json.dumps({
            "asin": "B000002",
            "rating": 1.0,
            "title": "Bad",
            "text": "Noise.",  # short, should be filtered
            "timestamp": 1600000001,
        }) + "\n")

    count = preprocess_amazon_reviews([raw_file], output_file)
    assert count == 1

    with open(output_file, "r", encoding="utf-8") as f:
        lines = [json.loads(line) for line in f]
    assert len(lines) == 1
    assert lines[0]["category"] == "Office_Products"
    assert lines[0]["rating"] == 5.0


def test_preprocess_mmlu_micro(tmp_path):
    parquet_file = tmp_path / "management" / "test-00000-of-00001.parquet"
    parquet_file.parent.mkdir(parents=True)
    output_file = tmp_path / "processed_mmlu.jsonl"

    df = pd.DataFrame([
        {"question": "What is the primary role of a scrum master?", "choices": ["Code review", "Facilitate process", "Hire staff", "Write budget"], "answer": 1}
    ])
    fastparquet.write(str(parquet_file), df)

    count = preprocess_mmlu_micro([parquet_file], output_file)
    assert count == 1

    with open(output_file, "r", encoding="utf-8") as f:
        lines = [json.loads(line) for line in f]
    assert len(lines) == 1
    assert lines[0]["answer"] == 1
    assert len(lines[0]["choices"]) == 4


def test_preprocess_gsm8k_micro(tmp_path):
    parquet_file = tmp_path / "test.parquet"
    output_file = tmp_path / "processed_gsm8k.jsonl"

    df = pd.DataFrame([
        {"question": "John has 5 apples and eats 2. How many are left?", "answer": "5 - 2 = 3\n#### 3"}
    ])
    fastparquet.write(str(parquet_file), df)

    count = preprocess_gsm8k_micro([parquet_file], output_file)
    assert count == 1

    with open(output_file, "r", encoding="utf-8") as f:
        lines = [json.loads(line) for line in f]
    assert len(lines) == 1
    assert lines[0]["target_number"] == "3"
