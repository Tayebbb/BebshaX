"""BebshaX — Dataset Setup & Preprocessing Pipeline

One-command, reproducible dataset pipeline with profile support and license audit.

Usage:
    python scripts/setup_datasets.py --profile minimal
    python scripts/setup_datasets.py --profile development
    python scripts/setup_datasets.py --profile evaluation
    python scripts/setup_datasets.py --profile full
    python scripts/setup_datasets.py --verify-only
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import logging
import os
import sys
import uuid
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from huggingface_hub import HfApi, HfFileSystem, hf_hub_download
import fastparquet

# Add project root to path
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from scripts.dataset_manifest import (
    DATASET_MANIFEST,
    DatasetEntry,
    ProfileType,
    PROFILES_ORDER,
    get_entries_for_profile,
    get_manifest,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("bebshax.datasets")

DATA_DIR = REPO_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"
METADATA_DIR = DATA_DIR / "metadata"


def compute_sha256(filepath: Path) -> str:
    """Compute sha256 checksum of a local file."""
    sha256 = hashlib.sha256()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            sha256.update(chunk)
    return sha256.hexdigest()


# ---------------------------------------------------------------------------
# Preprocessing Functions
# ---------------------------------------------------------------------------


def preprocess_personahub(raw_files: List[Path], output_file: Path) -> int:
    """Preprocess PersonaHub 200k persona release with systematic stride-8 sampling."""
    persona_jsonl = raw_files[0]
    count = 0
    stride = 8
    total_written = 0

    with open(persona_jsonl, "r", encoding="utf-8") as in_f, open(output_file, "w", encoding="utf-8") as out_f:
        for line in in_f:
            line = line.strip()
            if not line:
                continue
            count += 1
            if count % stride == 0:
                data = json.loads(line)
                persona_text = data.get("persona", "").strip()
                if persona_text:
                    record = {
                        "id": str(uuid.uuid5(uuid.NAMESPACE_DNS, f"personahub-{count}")),
                        "persona": persona_text,
                        "source_dataset": "proj-persona/PersonaHub",
                        "raw_index": count,
                    }
                    out_f.write(json.dumps(record, ensure_ascii=False) + "\n")
                    total_written += 1

    logger.info("PersonaHub preprocessed: sampled %d personas (stride %d)", total_written, stride)
    return total_written


def preprocess_synthetic_persona_chat(raw_files: List[Path], output_file: Path) -> int:
    """Preprocess Synthetic-Persona-Chat CSVs into turn sequences."""
    total_written = 0

    with open(output_file, "w", encoding="utf-8") as out_f:
        for csv_path in raw_files:
            if not csv_path.exists():
                continue
            with open(csv_path, "r", encoding="utf-8", errors="replace") as in_f:
                reader = csv.DictReader(in_f)
                for i, row in enumerate(reader):
                    user_1_persona = [p.strip() for p in row.get("user 1 personas", "").split("\n") if p.strip()]
                    user_2_persona = [p.strip() for p in row.get("user 2 personas", "").split("\n") if p.strip()]
                    best_talk = row.get("Best Talk", "").strip()

                    dialogue_turns = []
                    if best_talk:
                        raw_turns = best_talk.split("\n")
                        for t in raw_turns:
                            if ":" in t:
                                spk, text = t.split(":", 1)
                                dialogue_turns.append({"speaker": spk.strip(), "text": text.strip()})
                            else:
                                dialogue_turns.append({"speaker": "unknown", "text": t.strip()})

                    record = {
                        "id": str(uuid.uuid5(uuid.NAMESPACE_DNS, f"spc-{csv_path.stem}-{i}")),
                        "persona_1": user_1_persona,
                        "persona_2": user_2_persona,
                        "dialogue": dialogue_turns,
                        "split": csv_path.stem,
                    }
                    out_f.write(json.dumps(record, ensure_ascii=False) + "\n")
                    total_written += 1

    logger.info("Synthetic-Persona-Chat preprocessed: %d conversations", total_written)
    return total_written


def preprocess_empathetic_dialogues(raw_files: List[Path], output_file: Path) -> int:
    """Preprocess EmpatheticDialogues parquet files."""
    total_written = 0

    with open(output_file, "w", encoding="utf-8") as out_f:
        for pf in raw_files:
            if not pf.exists():
                continue
            pfile = fastparquet.ParquetFile(str(pf))
            df = pfile.to_pandas()
            for i, row in df.iterrows():
                record = {
                    "id": str(uuid.uuid5(uuid.NAMESPACE_DNS, f"ed-{pf.stem}-{i}")),
                    "conv_id": str(row.get("conv_id", "")),
                    "speaker_idx": int(row.get("speaker_idx", 0)),
                    "utterance": str(row.get("utterance", "")).strip(),
                    "emotion": str(row.get("context", "")).strip(),
                    "situation": str(row.get("prompt", "")).strip(),
                }
                out_f.write(json.dumps(record, ensure_ascii=False) + "\n")
                total_written += 1

    logger.info("EmpatheticDialogues preprocessed: %d utterance turns", total_written)
    return total_written


def preprocess_amazon_reviews(raw_files: List[Path], output_file: Path) -> int:
    """Preprocess Amazon Reviews Office_Products category jsonl."""
    total_written = 0
    max_reviews = 50000

    review_file = None
    for rf in raw_files:
        if "raw/review_categories" in str(rf).replace("\\", "/") or rf.name == "Office_Products.jsonl":
            review_file = rf
            break
    if not review_file:
        review_file = raw_files[0]

    with open(review_file, "r", encoding="utf-8", errors="replace") as in_f, open(output_file, "w", encoding="utf-8") as out_f:
        for line in in_f:
            if total_written >= max_reviews:
                break
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
            except Exception:
                continue

            text = data.get("text", "").strip()
            if len(text) < 20:  # skip noisy one-word reviews
                continue

            record = {
                "id": str(uuid.uuid5(uuid.NAMESPACE_DNS, f"amz-office-{total_written}")),
                "asin": data.get("asin", ""),
                "rating": float(data.get("rating", 0.0)),
                "title": data.get("title", "").strip(),
                "text": text,
                "category": "Office_Products",
                "timestamp": data.get("timestamp", 0),
            }
            out_f.write(json.dumps(record, ensure_ascii=False) + "\n")
            total_written += 1

    logger.info("Amazon Reviews preprocessed: %d office product reviews", total_written)
    return total_written


def preprocess_mmlu_micro(raw_files: List[Path], output_file: Path) -> int:
    """Preprocess MMLU micro-slice parquets."""
    total_written = 0

    with open(output_file, "w", encoding="utf-8") as out_f:
        for pf in raw_files:
            if not pf.exists():
                continue
            subject = pf.parent.name if pf.parent.name != "mmlu_micro" else pf.stem
            pfile = fastparquet.ParquetFile(str(pf))
            df = pfile.to_pandas()
            for i, row in df.iterrows():
                choices = list(row.get("choices", []))
                record = {
                    "id": str(uuid.uuid5(uuid.NAMESPACE_DNS, f"mmlu-{subject}-{i}")),
                    "subject": subject,
                    "question": str(row.get("question", "")).strip(),
                    "choices": choices,
                    "answer": int(row.get("answer", 0)),
                }
                out_f.write(json.dumps(record, ensure_ascii=False) + "\n")
                total_written += 1

    logger.info("MMLU preprocessed: %d probe questions", total_written)
    return total_written


def preprocess_gsm8k_micro(raw_files: List[Path], output_file: Path) -> int:
    """Preprocess GSM8K test parquet."""
    total_written = 0
    max_probes = 100

    with open(output_file, "w", encoding="utf-8") as out_f:
        for pf in raw_files:
            if not pf.exists():
                continue
            pfile = fastparquet.ParquetFile(str(pf))
            df = pfile.to_pandas()
            for i, row in df.iterrows():
                if total_written >= max_probes:
                    break
                ans = str(row.get("answer", "")).strip()
                target = ans.split("####")[-1].strip() if "####" in ans else ans
                record = {
                    "id": str(uuid.uuid5(uuid.NAMESPACE_DNS, f"gsm8k-{i}")),
                    "question": str(row.get("question", "")).strip(),
                    "answer": ans,
                    "target_number": target,
                }
                out_f.write(json.dumps(record, ensure_ascii=False) + "\n")
                total_written += 1

    logger.info("GSM8K preprocessed: %d math reasoning probes", total_written)
    return total_written


def preprocess_router_arena(raw_files: List[Path], output_file: Path) -> int:
    """Preprocess RouterArena sub_10 parquet."""
    total_written = 0

    with open(output_file, "w", encoding="utf-8") as out_f:
        for pf in raw_files:
            if not pf.exists():
                continue
            pfile = fastparquet.ParquetFile(str(pf))
            df = pfile.to_pandas()
            for i, row in df.iterrows():
                record = {
                    "id": str(uuid.uuid5(uuid.NAMESPACE_DNS, f"router_arena-{i}")),
                    "prompt": str(row.get("prompt", "") or row.get("question", "")).strip(),
                    "domain": str(row.get("category", "") or row.get("domain", "")).strip(),
                    "model_scores": {k: float(v) for k, v in row.items() if k not in ["prompt", "question", "category", "domain"] and isinstance(v, (int, float))},
                }
                out_f.write(json.dumps(record, ensure_ascii=False) + "\n")
                total_written += 1

    logger.info("RouterArena preprocessed: %d benchmark queries", total_written)
    return total_written


def preprocess_xroute_bench(raw_files: List[Path], output_file: Path) -> int:
    """Preprocess xRouteBench valid parquet."""
    total_written = 0

    with open(output_file, "w", encoding="utf-8") as out_f:
        for pf in raw_files:
            if not pf.exists():
                continue
            pfile = fastparquet.ParquetFile(str(pf))
            df = pfile.to_pandas()
            for i, row in df.iterrows():
                record = {
                    "id": str(uuid.uuid5(uuid.NAMESPACE_DNS, f"xroute-{i}")),
                    "query": str(row.get("query", "") or row.get("prompt", "")).strip(),
                    "task": str(row.get("task", "") or row.get("category", "")).strip(),
                    "metadata": {k: str(v) for k, v in row.items() if k not in ["query", "prompt", "task", "category"]},
                }
                out_f.write(json.dumps(record, ensure_ascii=False) + "\n")
                total_written += 1

    logger.info("xRouteBench preprocessed: %d routing simulation queries", total_written)
    return total_written


def preprocess_lmsys_chat(raw_files: List[Path], output_file: Path) -> int:
    """Preprocess LMSYS-Chat-1M partition."""
    total_written = 0
    max_convs = 5000

    with open(output_file, "w", encoding="utf-8") as out_f:
        for pf in raw_files:
            if not pf.exists():
                continue
            pfile = fastparquet.ParquetFile(str(pf))
            df = pfile.to_pandas()
            for i, row in df.iterrows():
                if total_written >= max_convs:
                    break
                record = {
                    "id": str(uuid.uuid5(uuid.NAMESPACE_DNS, f"lmsys-{i}")),
                    "model_a": str(row.get("model_a", "")),
                    "model_b": str(row.get("model_b", "")),
                    "conversation": row.get("conversation", []),
                }
                out_f.write(json.dumps(record, ensure_ascii=False) + "\n")
                total_written += 1

    logger.info("LMSYS-Chat-1M preprocessed: %d conversations", total_written)
    return total_written


def preprocess_mbti_traits(raw_files: List[Path], output_file: Path) -> int:
    """Preprocess MBTI personality traits."""
    total_written = 0

    with open(output_file, "w", encoding="utf-8") as out_f:
        for pf in raw_files:
            if not pf.exists():
                continue
            pfile = fastparquet.ParquetFile(str(pf))
            df = pfile.to_pandas()
            for i, row in df.iterrows():
                raw_posts = str(row.get("posts", "")).split("|||")
                clean_posts = [p.strip() for p in raw_posts if p.strip() and not p.strip().startswith("http")]
                record = {
                    "id": str(uuid.uuid5(uuid.NAMESPACE_DNS, f"mbti-{i}")),
                    "mbti_type": str(row.get("type", "")).strip(),
                    "posts": clean_posts[:15],
                }
                out_f.write(json.dumps(record, ensure_ascii=False) + "\n")
                total_written += 1

    logger.info("MBTI traits preprocessed: %d personality instances", total_written)
    return total_written


PREPROCESSORS: Dict[str, Callable[[List[Path], Path], int]] = {
    "preprocess_personahub": preprocess_personahub,
    "preprocess_synthetic_persona_chat": preprocess_synthetic_persona_chat,
    "preprocess_empathetic_dialogues": preprocess_empathetic_dialogues,
    "preprocess_amazon_reviews": preprocess_amazon_reviews,
    "preprocess_mmlu_micro": preprocess_mmlu_micro,
    "preprocess_gsm8k_micro": preprocess_gsm8k_micro,
    "preprocess_router_arena": preprocess_router_arena,
    "preprocess_xroute_bench": preprocess_xroute_bench,
    "preprocess_lmsys_chat": preprocess_lmsys_chat,
    "preprocess_mbti_traits": preprocess_mbti_traits,
}


# ---------------------------------------------------------------------------
# Pipeline Execution & Verification
# ---------------------------------------------------------------------------


def verify_manifest_online(entries: List[DatasetEntry]) -> bool:
    """Verify live that each dataset revision resolves and all specified files exist."""
    api = HfApi()
    all_ok = True

    print("\n" + "=" * 80)
    print("PRE-FLIGHT VERIFICATION: Resolving Pinned Commit SHAs and Files")
    print("=" * 80)

    for entry in entries:
        try:
            repo_files = api.list_repo_files(
                repo_id=entry.hf_repo_id,
                repo_type="dataset",
                revision=entry.pinned_revision,
            )
            missing = [f for f in entry.files_or_patterns if f not in repo_files]
            if missing:
                print(f"[FAIL] {entry.dataset_id} ({entry.hf_repo_id}@{entry.pinned_revision[:7]}): missing files {missing}")
                all_ok = False
            else:
                print(f"[PASS] {entry.dataset_id:32} -> {entry.hf_repo_id}@{entry.pinned_revision[:7]} ({len(entry.files_or_patterns)} files verified)")
        except Exception as e:
            if entry.distribution.is_gated or not entry.is_required:
                print(f"[WARN] {entry.dataset_id:32} -> Gated/Optional dataset unauthenticated or unavailable ({e}) [FAIL-SOFT]")
            else:
                print(f"[FAIL] {entry.dataset_id:32} -> {entry.hf_repo_id}@{entry.pinned_revision[:7]}: ERROR {e}")
                all_ok = False

    print("=" * 80)
    return all_ok


def download_entry(entry: DatasetEntry, raw_target_dir: Path) -> List[Path]:
    """Download pinned files for a dataset entry."""
    raw_target_dir.mkdir(parents=True, exist_ok=True)
    downloaded_paths = []

    if entry.download_method == "hf_hub_file":
        for rel_path in entry.files_or_patterns:
            local_dest = raw_target_dir / Path(rel_path).name
            if not local_dest.exists():
                logger.info("Downloading %s:%s at revision %s", entry.hf_repo_id, rel_path, entry.pinned_revision[:7])
                downloaded_file = hf_hub_download(
                    repo_id=entry.hf_repo_id,
                    filename=rel_path,
                    revision=entry.pinned_revision,
                    repo_type="dataset",
                    local_dir=str(raw_target_dir),
                )
                downloaded_paths.append(Path(downloaded_file))
            else:
                downloaded_paths.append(local_dest)

    elif entry.download_method == "hf_stream_slice":
        # Stream first N lines / bytes directly from pinned commit
        fs = HfFileSystem()
        for rel_path in entry.files_or_patterns:
            local_dest = raw_target_dir / Path(rel_path).name
            if not local_dest.exists():
                logger.info("Streaming slice for %s:%s at revision %s", entry.hf_repo_id, rel_path, entry.pinned_revision[:7])
                remote_path = f"datasets/{entry.hf_repo_id}@{entry.pinned_revision}/{rel_path}"
                max_lines = 50000
                lines_read = 0
                with fs.open(remote_path, "r", encoding="utf-8", errors="replace") as in_f, open(local_dest, "w", encoding="utf-8") as out_f:
                    for line in in_f:
                        if lines_read >= max_lines:
                            break
                        out_f.write(line)
                        lines_read += 1
                logger.info("Streamed %d lines to %s", lines_read, local_dest)
            downloaded_paths.append(local_dest)

    return downloaded_paths


def process_dataset(entry: DatasetEntry, force: bool = False) -> Tuple[str, Optional[str], Optional[str]]:
    """Process a single dataset entry.
    
    Returns (status, raw_sha256, processed_sha256) where status is 'SKIPPED' | 'PROCESSED' | 'FAILED_SOFT' | 'FAILED'.
    """
    raw_target_dir = RAW_DIR / entry.dataset_id
    processed_file = PROCESSED_DIR / f"{entry.dataset_id}.jsonl"
    metadata_file = METADATA_DIR / f"{entry.dataset_id}.json"

    # Idempotency check: if processed file exists and checksum matches known checksum
    if not force and processed_file.exists() and entry.processed_sha256 is not None:
        current_sha256 = compute_sha256(processed_file)
        if current_sha256 == entry.processed_sha256:
            logger.info("[NO-OP] %s: processed artifact checksum matches (%s)", entry.dataset_id, current_sha256[:8])
            return "SKIPPED", entry.raw_sha256, current_sha256

    try:
        raw_files = download_entry(entry, raw_target_dir)
    except Exception as e:
        if not entry.is_required or entry.distribution.is_gated:
            logger.warning("[FAIL-SOFT] Optional/Gated dataset '%s' failed download: %s. Continuing pipeline.", entry.dataset_id, e)
            return "FAILED_SOFT", None, None
        else:
            logger.error("[ERROR] Required dataset '%s' failed download: %s", entry.dataset_id, e)
            raise

    # Compute raw sha256 of primary raw file
    raw_sha = compute_sha256(raw_files[0]) if raw_files and raw_files[0].exists() else None

    # Preprocessing
    preprocessor = PREPROCESSORS.get(entry.preprocessing_fn)
    if not preprocessor:
        raise ValueError(f"Unknown preprocessing function '{entry.preprocessing_fn}' for dataset {entry.dataset_id}")

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    count = preprocessor(raw_files, processed_file)
    processed_sha = compute_sha256(processed_file)

    # Log checksum verification vs first-run bootstrap
    if entry.processed_sha256 is None:
        logger.info("[FIRST-RUN / UNVERIFIED CHECKSUM] %s: computed raw_sha256=%s, processed_sha256=%s", entry.dataset_id, raw_sha[:8] if raw_sha else "none", processed_sha[:8])
    else:
        if processed_sha == entry.processed_sha256:
            logger.info("[CHECKSUM-VERIFIED] %s: output matches expected checksum (%s)", entry.dataset_id, processed_sha[:8])
        else:
            logger.warning("[CHECKSUM-MISMATCH] %s: expected %s, got %s", entry.dataset_id, entry.processed_sha256[:8], processed_sha[:8])

    # Write per-dataset metadata JSON
    METADATA_DIR.mkdir(parents=True, exist_ok=True)
    meta_dict = entry.to_dict()
    meta_dict["actual_raw_sha256"] = raw_sha
    meta_dict["actual_processed_sha256"] = processed_sha
    meta_dict["processed_record_count"] = count
    meta_dict["processed_size_bytes"] = processed_file.stat().st_size if processed_file.exists() else 0

    with open(metadata_file, "w", encoding="utf-8") as f:
        json.dump(meta_dict, f, indent=2)

    return "PROCESSED", raw_sha, processed_sha


def generate_datasets_md(entries: List[DatasetEntry]) -> None:
    """Generate data/DATASETS.md directly from the manifest."""
    lines = [
        "# BebshaX — Datasets Documentation",
        "",
        "> Single source of truth: `scripts/dataset_manifest.py`. Generated by `scripts/setup_datasets.py`.",
        "> **THIS IS NOT A TRAINING PROJECT.** Datasets serve grounding, diversity, behavioral examples, and evaluation only. Model fine-tuning is strictly prohibited (RULES.md R9).",
        "",
        "## Profile Hierarchy",
        "",
        "Profiles follow a strict subset relationship: `minimal` ⊂ `development` ⊂ `evaluation` ⊂ `full`.",
        "",
        "- **`minimal` (< 1 GB):** Persona seeds, conversation grounding, and health probes (`personahub_sample`, `synthetic_persona_chat`, `mmlu_micro`, `gsm8k_micro`).",
        "- **`development` (< 5 GB):** Minimal + representative business review evidence and empathetic dialogues (`amazon_reviews_office_products`, `empathetic_dialogues_slice`).",
        "- **`evaluation` (< 5 GB):** Development + router benchmark evaluation suites (`router_arena`, `xroute_bench`).",
        "- **`full` (< 10 GB):** Evaluation + optional/gated conversation sets and personality traits (`lmsys_chat_1m`, `mbti_personality_traits`).",
        "",
        "## Dataset Manifest & Gebru Datasheets",
        "",
    ]

    for entry in entries:
        lines.extend([
            f"### `{entry.dataset_id}`",
            "",
            f"- **Hugging Face Repository:** [{entry.hf_repo_id}](https://huggingface.co/datasets/{entry.hf_repo_id})",
            f"- **Pinned Revision (Commit SHA):** `{entry.pinned_revision}`",
            f"- **Profile Membership:** `{', '.join(entry.profiles)}`",
            f"- **Required / Gated:** {'Required' if entry.is_required else 'Optional / Fail-Soft'} (Gated: `{entry.distribution.is_gated}`)",
            f"- **Claimed HF License:** `{entry.distribution.license_claimed_hf}`",
            f"- **Verified Upstream License:** `{entry.distribution.license_verified_upstream}`",
            f"- **License Verification Source:** [{entry.distribution.license_verification_url}]({entry.distribution.license_verification_url}) (Verified: `{entry.distribution.license_verified_at}`)",
            f"- **License Notes:** {entry.distribution.license_notes}",
            f"- **Motivation & Purpose:** {entry.motivation.purpose}",
            f"- **Domain:** {entry.motivation.domain}",
            f"- **Composition:** {entry.composition.slice_description} (~{entry.composition.sample_count_estimate:,} records)",
            f"- **Collection Process:** {entry.collection.collection_mechanism} (Source: {entry.collection.upstream_creator})",
            f"- **Preprocessing Method:** `{entry.preprocessing_fn}` ({entry.preprocessing.cleaning_applied})",
            f"- **Normalized Schema:** `{json.dumps(entry.preprocessing.normalized_jsonl_schema)}`",
            f"- **Prohibited Uses:** {', '.join(entry.uses.prohibited_uses)}",
            "",
            "---",
            "",
        ])

    doc_path = DATA_DIR / "DATASETS.md"
    with open(doc_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    logger.info("Generated %s from manifest", doc_path)


def run_pipeline(profile: ProfileType, verify_only: bool = False, force: bool = False) -> int:
    """Run dataset pipeline for specified profile."""
    entries = get_entries_for_profile(profile)
    logger.info("Running dataset pipeline for profile '%s' (%d datasets)", profile, len(entries))

    # Pre-flight verification check
    online_ok = verify_manifest_online(entries)
    if verify_only:
        print(f"\nVerify-only result for profile '{profile}': {'PASSED' if online_ok else 'FAILED'}")
        return 0 if online_ok else 1

    summary_rows = []
    has_critical_failure = False

    for entry in entries:
        logger.info("--- Processing %s (%s) ---", entry.dataset_id, entry.hf_repo_id)
        try:
            status, raw_sha, proc_sha = process_dataset(entry, force=force)
            summary_rows.append((entry.dataset_id, entry.hf_repo_id, status, proc_sha[:8] if proc_sha else "none"))
        except Exception as e:
            logger.error("Failed processing %s: %s", entry.dataset_id, e)
            summary_rows.append((entry.dataset_id, entry.hf_repo_id, "FAILED", "none"))
            if entry.is_required:
                has_critical_failure = True

    # Generate data/DATASETS.md
    generate_datasets_md(get_manifest())

    # Print summary table
    print("\n" + "=" * 80)
    print(f"DATASET PIPELINE SUMMARY — Profile: {profile}")
    print("=" * 80)
    print(f"{'Dataset ID':32} {'Repository':30} {'Status':12} {'Processed SHA'}")
    print("-" * 80)
    for did, repo, st, psha in summary_rows:
        print(f"{did:32} {repo:30} {st:12} {psha}")
    print("=" * 80)

    if has_critical_failure:
        logger.error("Pipeline failed for required dataset(s).")
        return 1

    logger.info("Dataset pipeline completed successfully for profile '%s'.", profile)
    return 0


def main():
    parser = argparse.ArgumentParser(description="BebshaX Dataset Pipeline")
    parser.add_argument(
        "--profile",
        choices=PROFILES_ORDER,
        default="development",
        help="Dataset profile to setup (default: development)",
    )
    parser.add_argument(
        "--verify-only",
        action="store_true",
        help="Verify pinned commits and file existence without downloading full datasets",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force re-download and re-processing even if checksums match",
    )
    args = parser.parse_args()

    sys.exit(run_pipeline(profile=args.profile, verify_only=args.verify_only, force=args.force))


if __name__ == "__main__":
    main()
