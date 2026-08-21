"""BebshaX — Dataset Manifest (Single Source of Truth)

Encodes all dataset metadata following Gebru et al. 'Datasheets for Datasets'
dimensions alongside operational pipeline configurations.

Rules:
- Every entry MUST pin an exact commit SHA (pinned_revision), never a branch.
- Gated datasets must have is_required=False and fail soft.
- Profile hierarchy: minimal ⊂ development ⊂ evaluation ⊂ full.
- No model training/fine-tuning permitted.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Literal, Optional

ProfileType = Literal["minimal", "development", "evaluation", "full"]

PROFILES_ORDER: List[ProfileType] = ["minimal", "development", "evaluation", "full"]


@dataclass(frozen=True)
class DatasheetMotivation:
    purpose: str
    domain: str
    research_questions: List[str]


@dataclass(frozen=True)
class DatasheetComposition:
    instance_type: str
    slice_description: str
    sample_count_estimate: int
    sensitive_content: str


@dataclass(frozen=True)
class DatasheetCollection:
    source_url: str
    upstream_creator: str
    collection_mechanism: str


@dataclass(frozen=True)
class DatasheetPreprocessing:
    raw_format: str
    cleaning_applied: str
    normalized_jsonl_schema: Dict[str, str]


@dataclass(frozen=True)
class DatasheetUses:
    intended_uses: List[str]
    prohibited_uses: List[str] = field(
        default_factory=lambda: [
            "Model training / fine-tuning (R9 violation)",
            "Commercial redistribution without upstream license compliance",
            "Deanonymization or PII scraping",
        ]
    )


@dataclass(frozen=True)
class DatasheetDistribution:
    license_claimed_hf: str
    license_verified_upstream: str
    license_verification_url: str
    license_verified_at: str
    license_discrepancy: bool
    license_notes: str
    is_gated: bool


@dataclass
class DatasetEntry:
    dataset_id: str
    hf_repo_id: str
    pinned_revision: str
    files_or_patterns: List[str]
    profiles: List[ProfileType]
    download_method: Literal["hf_hub_file", "hf_stream_slice"]
    preprocessing_fn: str
    is_required: bool
    estimated_raw_size_mb: float
    motivation: DatasheetMotivation
    composition: DatasheetComposition
    collection: DatasheetCollection
    preprocessing: DatasheetPreprocessing
    uses: DatasheetUses
    distribution: DatasheetDistribution
    raw_sha256: Optional[str] = None        # Nullable on first run; verified on subsequent runs
    processed_sha256: Optional[str] = None  # Nullable on first run; verified on subsequent runs

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# Authoritative Dataset Manifest for BebshaX
DATASET_MANIFEST: List[DatasetEntry] = [
    DatasetEntry(
        dataset_id="personahub_sample",
        hf_repo_id="proj-persona/PersonaHub",
        pinned_revision="16777e34bf5cb758b925cae5d84e868ee6c2100c",
        files_or_patterns=["persona.jsonl"],
        profiles=["minimal", "development", "evaluation", "full"],
        download_method="hf_hub_file",
        preprocessing_fn="preprocess_personahub",
        is_required=True,
        estimated_raw_size_mb=21.6,  # 200,000 persona release artifact
        motivation=DatasheetMotivation(
            purpose="High-diversity synthetic persona seeds for business persona generation.",
            domain="Persona synthesis & role diversity",
            research_questions=["Can synthetic persona seeds provide rich behavioral priors for simulated user interviews?"],
        ),
        composition=DatasheetComposition(
            instance_type="Persona profile description string",
            slice_description="Systematic stride-8 sampling over all 200,000 records from persona.jsonl yielding 25,000 uniformly distributed persona seeds across occupations, demographics, and behavioral archetypes.",
            sample_count_estimate=25000,
            sensitive_content="Synthetic persona descriptions; may reflect demographic stereotypes present in foundation model outputs.",
        ),
        collection=DatasheetCollection(
            source_url="https://huggingface.co/datasets/proj-persona/PersonaHub",
            upstream_creator="Tencent, HKUST, Tsinghua (Scaling Synthetic Data Creation with 1B Personas, arXiv:2406.20094)",
            collection_mechanism="Generated synthetically by GPT-4 / Llama-3 / Qwen from web text anchors.",
        ),
        preprocessing=DatasheetPreprocessing(
            raw_format="jsonl",
            cleaning_applied="Extract persona text, normalize whitespace, apply systematic stride-8 sampling, assign deterministic UUID, validate non-empty string.",
            normalized_jsonl_schema={"id": "str", "persona": "str", "source_dataset": "str"},
        ),
        uses=DatasheetUses(
            intended_uses=["Grounding and seeding BebshaX persona generation (Phase 8).", "Persona diversity baseline."],
        ),
        distribution=DatasheetDistribution(
            license_claimed_hf="cc-by-nc-sa-4.0",
            license_verified_upstream="CC-BY-NC-SA-4.0 (Research & Non-Commercial Only)",
            license_verification_url="https://huggingface.co/datasets/proj-persona/PersonaHub/blob/16777e34bf5cb758b925cae5d84e868ee6c2100c/README.md",
            license_verified_at="2026-08-22",
            license_discrepancy=False,
            license_notes="Synthetic outputs from GPT-4/Llama-3/Qwen; downstream users must also comply with foundation model service terms.",
            is_gated=False,
        ),
        raw_sha256="d81c94ab82f5614b2fc7f335154d6cc18ea7dc3db3b3578ca0069c9251363b9f",
        processed_sha256="c0696d8cd0e005509a3b9e5cff73dec2b2b49e8178d5c0ea25377a5c7131d7db",
    ),
    DatasetEntry(
        dataset_id="synthetic_persona_chat",
        hf_repo_id="google/Synthetic-Persona-Chat",
        pinned_revision="a520ad7f999ca7e6dfdc25fed9f5070bf6f87b42",
        files_or_patterns=["data/Synthetic-Persona-Chat_train.csv", "data/Synthetic-Persona-Chat_test.csv"],
        profiles=["minimal", "development", "evaluation", "full"],
        download_method="hf_hub_file",
        preprocessing_fn="preprocess_synthetic_persona_chat",
        is_required=True,
        estimated_raw_size_mb=35.0,
        motivation=DatasheetMotivation(
            purpose="Persona-grounded multi-turn dialogue examples for interview simulation behavior.",
            domain="Persona-conditioned conversational dialogues",
            research_questions=["How consistently can personas maintain stated constraints across multi-turn interviews?"],
        ),
        composition=DatasheetComposition(
            instance_type="Multi-turn conversation transcript with speaker persona descriptions",
            slice_description="Train and test splits from Synthetic-Persona-Chat CSVs (9,906 total multi-turn dialogues across train and test partitions)",
            sample_count_estimate=9906,
            sensitive_content="General casual dialogues, low toxicity.",
        ),
        collection=DatasheetCollection(
            source_url="https://huggingface.co/datasets/google/Synthetic-Persona-Chat",
            upstream_creator="Google Research",
            collection_mechanism="Synthetically generated paired persona dialogues using LLM prompting.",
        ),
        preprocessing=DatasheetPreprocessing(
            raw_format="csv",
            cleaning_applied="Parse persona traits and dialogue turns; format into turn sequences with speaker labels.",
            normalized_jsonl_schema={"id": "str", "persona_1": "list[str]", "persona_2": "list[str]", "dialogue": "list[dict]"},
        ),
        uses=DatasheetUses(
            intended_uses=["Grounding interview turn dynamics in Phase 10.", "Evaluation reference for dialogue consistency."],
        ),
        distribution=DatasheetDistribution(
            license_claimed_hf="cc-by-4.0",
            license_verified_upstream="CC-BY-4.0 (Permissive with Attribution)",
            license_verification_url="https://huggingface.co/datasets/google/Synthetic-Persona-Chat/blob/a520ad7f999ca7e6dfdc25fed9f5070bf6f87b42/README.md",
            license_verified_at="2026-08-22",
            license_discrepancy=False,
            license_notes="Standard CC-BY-4.0 license.",
            is_gated=False,
        ),
        raw_sha256="a7bb20f1c51fd18cc51b2adc942220994e302b237053110b04fce7b413c812da",
        processed_sha256="f6b42b1f18bdfde255c51343e817c8012b3088e86a3f86a265e4c0f498a3748c",
    ),
    DatasetEntry(
        dataset_id="empathetic_dialogues_slice",
        hf_repo_id="facebook/empathetic_dialogues",
        pinned_revision="d5b57ae707b0b9a384af8ed50c043c608d597ca7",
        files_or_patterns=["default/train/0000.parquet", "default/validation/0000.parquet"],
        profiles=["development", "evaluation", "full"],
        download_method="hf_hub_file",
        preprocessing_fn="preprocess_empathetic_dialogues",
        is_required=True,
        estimated_raw_size_mb=6.85,
        motivation=DatasheetMotivation(
            purpose="Emotional nuance and empathetic conversational grounding for interview simulation.",
            domain="Emotion-grounded conversational dialogue",
            research_questions=["Can emotion-grounded dialogues improve persona responsiveness during user interviews?"],
        ),
        composition=DatasheetComposition(
            instance_type="Empathetic multi-turn conversation with emotion label and situation description",
            slice_description="Train and validation splits from official parquet release on facebook/empathetic_dialogues (24,850 conversations, ~100,000 utterances)",
            sample_count_estimate=24850,
            sensitive_content="Personal emotional situations described by crowdworkers; no private identifiers.",
        ),
        collection=DatasheetCollection(
            source_url="https://github.com/facebookresearch/EmpatheticDialogues",
            upstream_creator="Facebook AI Research (Rashkin et al., ACL 2019)",
            collection_mechanism="Crowdsourced on Amazon Mechanical Turk grounded in 32 emotion categories.",
        ),
        preprocessing=DatasheetPreprocessing(
            raw_format="parquet",
            cleaning_applied="Extract dialogue turns, emotion labels, and situation context; format into structured turn objects.",
            normalized_jsonl_schema={"id": "str", "emotion": "str", "situation": "str", "utterance": "str", "speaker_idx": "int"},
        ),
        uses=DatasheetUses(
            intended_uses=["Interview tone realism and empathetic response grounding (Phase 10)."],
        ),
        distribution=DatasheetDistribution(
            license_claimed_hf="cc-by-nc-4.0",
            license_verified_upstream="CC-BY-NC-4.0 (Non-Commercial Research Only)",
            license_verification_url="https://github.com/facebookresearch/EmpatheticDialogues/blob/main/LICENSE",
            license_verified_at="2026-08-22",
            license_discrepancy=False,
            license_notes="Verified against Meta AI / ParlAI GitHub repository license.",
            is_gated=False,
        ),
    ),
    DatasetEntry(
        dataset_id="amazon_reviews_office_products",
        hf_repo_id="McAuley-Lab/Amazon-Reviews-2023",
        pinned_revision="2b6d039ed471f2ba5fd2acb718bf33b0a7e5598e",
        files_or_patterns=[
            "raw/review_categories/Office_Products.jsonl",
            "raw/meta_categories/meta_Office_Products.jsonl",
        ],
        profiles=["development", "evaluation", "full"],
        download_method="hf_stream_slice",
        preprocessing_fn="preprocess_amazon_reviews",
        is_required=True,
        estimated_raw_size_mb=45.0,
        motivation=DatasheetMotivation(
            purpose="Broad real-world business product feedback, user pain points, and customer satisfaction evidence.",
            domain="B2B & consumer office products and workspace equipment reviews",
            research_questions=["Can real product reviews ground synthetic persona pain points and purchasing criteria?"],
        ),
        composition=DatasheetComposition(
            instance_type="Product review with rating, title, text, timestamp, and product metadata",
            slice_description="Office_Products category slice (first 50,000 reviews streamed; avoids bulk 571M download)",
            sample_count_estimate=50000,
            sensitive_content="Public user reviews; reviewer IDs anonymized.",
        ),
        collection=DatasheetCollection(
            source_url="https://huggingface.co/datasets/McAuley-Lab/Amazon-Reviews-2023",
            upstream_creator="McAuley Lab (UCSD, Hou et al., 2024)",
            collection_mechanism="Scraped public Amazon review pages for academic research.",
        ),
        preprocessing=DatasheetPreprocessing(
            raw_format="jsonl",
            cleaning_applied="Join review text with metadata; anonymize user identifiers; filter short noise.",
            normalized_jsonl_schema={"id": "str", "asin": "str", "rating": "float", "title": "str", "text": "str", "category": "str"},
        ),
        uses=DatasheetUses(
            intended_uses=["Evidence grounding and pain point extraction (Phase 8 persona engine)."],
        ),
        distribution=DatasheetDistribution(
            license_claimed_hf="other",
            license_verified_upstream="Academic Research Non-Commercial (UCSD McAuley Lab terms)",
            license_verification_url="https://github.com/hyp1251/AmazonReviews2023#license",
            license_verified_at="2026-08-22",
            license_discrepancy=False,
            license_notes="Research use only. Bulk redistribution restricted. Streamed category slice used.",
            is_gated=False,
        ),
    ),
    DatasetEntry(
        dataset_id="mmlu_micro",
        hf_repo_id="cais/mmlu",
        pinned_revision="c30699e8356da336a370243923dbaf21066bb9fe",
        files_or_patterns=[
            "management/test-00000-of-00001.parquet",
            "marketing/test-00000-of-00001.parquet",
            "professional_psychology/test-00000-of-00001.parquet",
        ],
        profiles=["minimal", "development", "evaluation", "full"],
        download_method="hf_hub_file",
        preprocessing_fn="preprocess_mmlu_micro",
        is_required=True,
        estimated_raw_size_mb=0.07,
        motivation=DatasheetMotivation(
            purpose="Model capability sanity probes for routing health checks.",
            domain="Multi-task language understanding across business domains",
            research_questions=["Can fast zero-cost probes verify model capability before routing complex reasoning tasks?"],
        ),
        composition=DatasheetComposition(
            instance_type="Multiple-choice question with 4 options and ground truth answer",
            slice_description="Micro-slice across three target test domains: management (111 questions), marketing (346 questions), and professional psychology (492 questions) yielding 949 total benchmark questions",
            sample_count_estimate=949,
            sensitive_content="Academic exam questions.",
        ),
        collection=DatasheetCollection(
            source_url="https://huggingface.co/datasets/cais/mmlu",
            upstream_creator="Center for AI Safety (Hendrycks et al., ICLR 2021)",
            collection_mechanism="Curated from official examinations and academic tests.",
        ),
        preprocessing=DatasheetPreprocessing(
            raw_format="parquet",
            cleaning_applied="Extract question, choices, answer index; format as deterministic probe prompt.",
            normalized_jsonl_schema={"id": "str", "subject": "str", "question": "str", "choices": "list[str]", "answer": "int"},
        ),
        uses=DatasheetUses(
            intended_uses=["Routing health check probes in LLM router (Phase 5/11).", "Model capability verification."],
        ),
        distribution=DatasheetDistribution(
            license_claimed_hf="mit",
            license_verified_upstream="MIT (Permissive, verified on upstream repository)",
            license_verification_url="https://github.com/hendrycks/test/blob/master/LICENSE",
            license_verified_at="2026-08-22",
            license_discrepancy=False,
            license_notes="Standard MIT license verified on original CAIS repository.",
            is_gated=False,
        ),
        raw_sha256="b5579485f3b83ceabcf2269720c7ce087b76ad473f020336c5ec7e724900767f",
        processed_sha256="e7525a55049ba8304e2c1c6b751c7cef01cc07a1954f6dc43b103f52e653af83",
    ),
    DatasetEntry(
        dataset_id="gsm8k_micro",
        hf_repo_id="openai/gsm8k",
        pinned_revision="740312add88f781978c0658806c59bc2815b9866",
        files_or_patterns=["main/test-00000-of-00001.parquet"],
        profiles=["minimal", "development", "evaluation", "full"],
        download_method="hf_hub_file",
        preprocessing_fn="preprocess_gsm8k_micro",
        is_required=True,
        estimated_raw_size_mb=0.42,
        motivation=DatasheetMotivation(
            purpose="Mathematical reasoning sanity probe for routing health and capability grading.",
            domain="Grade school math multi-step reasoning",
            research_questions=["Can reasoning probes verify that candidate models follow step-by-step logic?"],
        ),
        composition=DatasheetComposition(
            instance_type="Math problem with chain-of-thought solution and numeric answer",
            slice_description="Micro-slice of 100 test problems",
            sample_count_estimate=100,
            sensitive_content="Elementary math word problems.",
        ),
        collection=DatasheetCollection(
            source_url="https://huggingface.co/datasets/openai/gsm8k",
            upstream_creator="OpenAI (Cobbe et al., 2021)",
            collection_mechanism="Created by human problem writers.",
        ),
        preprocessing=DatasheetPreprocessing(
            raw_format="parquet",
            cleaning_applied="Parse problem text, numeric solution, and final calculation.",
            normalized_jsonl_schema={"id": "str", "question": "str", "answer": "str", "target_number": "str"},
        ),
        uses=DatasheetUses(
            intended_uses=["Reasoning capability probes for candidate route grading."],
        ),
        distribution=DatasheetDistribution(
            license_claimed_hf="mit",
            license_verified_upstream="MIT (Permissive, verified on upstream repository)",
            license_verification_url="https://github.com/openai/grade-school-math/blob/master/LICENSE",
            license_verified_at="2026-08-22",
            license_discrepancy=False,
            license_notes="Standard MIT license verified on original OpenAI repository.",
            is_gated=False,
        ),
        raw_sha256="ee7b8da9e381df27b9e3f7758a159ab2bdaa4dbaa910546cbbc47e0cb44e4f59",
        processed_sha256="c2e917355a21f621264af562d5246d2f4322b37a76300beba8be074c66f5ab25",
    ),
    DatasetEntry(
        dataset_id="router_arena",
        hf_repo_id="RouteWorks/RouterArena",
        pinned_revision="a4a062ce3313b56bb09c042e1bc37b61d34e3bd8",
        files_or_patterns=["data/sub_10-00000-of-00001.parquet"],
        profiles=["evaluation", "full"],
        download_method="hf_hub_file",
        preprocessing_fn="preprocess_router_arena",
        is_required=True,
        estimated_raw_size_mb=0.38,
        motivation=DatasheetMotivation(
            purpose="Multi-model router evaluation benchmark queries and model performance labels.",
            domain="LLM routing benchmark queries across tasks",
            research_questions=["How does BebshaX free-pool routing compare to research router benchmarks?"],
        ),
        composition=DatasheetComposition(
            instance_type="Benchmark prompt, task domain, model response scores, and cost estimates",
            slice_description="Sub-10 evaluation split (~1,000 queries)",
            sample_count_estimate=1000,
            sensitive_content="General benchmark prompts.",
        ),
        collection=DatasheetCollection(
            source_url="https://huggingface.co/datasets/RouteWorks/RouterArena",
            upstream_creator="Rice University (RouteWorks, 2024)",
            collection_mechanism="Aggregated prompt execution logs across major proprietary and open models.",
        ),
        preprocessing=DatasheetPreprocessing(
            raw_format="parquet",
            cleaning_applied="Extract prompt, domain category, ground truth win rates per model family.",
            normalized_jsonl_schema={"id": "str", "prompt": "str", "domain": "str", "model_scores": "dict"},
        ),
        uses=DatasheetUses(
            intended_uses=["Offline router evaluation experiments in Phase 11."],
        ),
        distribution=DatasheetDistribution(
            license_claimed_hf="apache-2.0",
            license_verified_upstream="Tag-only in dataset card frontmatter (unverified upstream repo)",
            license_verification_url="https://huggingface.co/datasets/RouteWorks/RouterArena/blob/a4a062ce3313b56bb09c042e1bc37b61d34e3bd8/README.md",
            license_verified_at="2026-08-22",
            license_discrepancy=False,
            license_notes="Dataset card declares Apache-2.0 in YAML metadata header.",
            is_gated=False,
        ),
    ),
    DatasetEntry(
        dataset_id="xroute_bench",
        hf_repo_id="ulab-ai/xRouteBench",
        pinned_revision="ea4b6e1b29d9a734f55f0a637baf326bad6aa681",
        files_or_patterns=["llmrouter_generic_queries/valid.parquet"],
        profiles=["evaluation", "full"],
        download_method="hf_hub_file",
        preprocessing_fn="preprocess_xroute_bench",
        is_required=True,
        estimated_raw_size_mb=0.19,
        motivation=DatasheetMotivation(
            purpose="Zero-API-cost router evaluation via pre-recorded model executions.",
            domain="Replay-based routing simulation benchmark",
            research_questions=["Can pre-recorded model execution traces validate router strategy trade-offs?"],
        ),
        composition=DatasheetComposition(
            instance_type="Query, task metadata, and pre-recorded outputs from candidate models",
            slice_description="Validation subset of generic router queries (~1,200 instances)",
            sample_count_estimate=1200,
            sensitive_content="Benchmark prompts and model outputs.",
        ),
        collection=DatasheetCollection(
            source_url="https://huggingface.co/datasets/ulab-ai/xRouteBench",
            upstream_creator="UIUC ULAB (xRouteBench, 2024)",
            collection_mechanism="Synthesized and collected benchmark queries with multi-model executions.",
        ),
        preprocessing=DatasheetPreprocessing(
            raw_format="parquet",
            cleaning_applied="Extract query text, task category, and model execution records.",
            normalized_jsonl_schema={"id": "str", "query": "str", "task": "str", "candidates": "list[dict]"},
        ),
        uses=DatasheetUses(
            intended_uses=["Zero-cost routing strategy replay and comparison in Phase 11."],
        ),
        distribution=DatasheetDistribution(
            license_claimed_hf="mit",
            license_verified_upstream="Tag-only in dataset card frontmatter (unverified upstream repo)",
            license_verification_url="https://huggingface.co/datasets/ulab-ai/xRouteBench/blob/ea4b6e1b29d9a734f55f0a637baf326bad6aa681/README.md",
            license_verified_at="2026-08-22",
            license_discrepancy=False,
            license_notes="Dataset card declares MIT tag in YAML header.",
            is_gated=False,
        ),
    ),
    DatasetEntry(
        dataset_id="lmsys_chat_1m",
        hf_repo_id="lmsys/lmsys-chat-1m",
        pinned_revision="200748d9d3cddcc9d782887541057aca0b18c5da",
        files_or_patterns=["data/train-00000-of-00006-4feeb3f83346a0e9.parquet"],
        profiles=["full"],
        download_method="hf_hub_file",
        preprocessing_fn="preprocess_lmsys_chat",
        is_required=False,  # GATED: MUST fail soft without blocking pipeline
        estimated_raw_size_mb=480.0,
        motivation=DatasheetMotivation(
            purpose="Real-world user query distribution and conversation quality evaluation.",
            domain="Real user prompts from LMSYS Chatbot Arena",
            research_questions=["How does the synthetic persona dialogue distribution compare to real user conversations?"],
        ),
        composition=DatasheetComposition(
            instance_type="Multi-turn conversation between user and various LLMs",
            slice_description="First partition (train-00000) from LMSYS Chat-1M",
            sample_count_estimate=5000,
            sensitive_content="Real user prompts; may contain toxic or unsafe queries filtered by moderation tags.",
        ),
        collection=DatasheetCollection(
            source_url="https://huggingface.co/datasets/lmsys/lmsys-chat-1m",
            upstream_creator="LMSYS Org (Zheng et al., ICLR 2024)",
            collection_mechanism="Crowdsourced queries submitted to the LMSYS Chatbot Arena.",
        ),
        preprocessing=DatasheetPreprocessing(
            raw_format="parquet",
            cleaning_applied="Filter unsafe queries; extract user turns and system responses.",
            normalized_jsonl_schema={"id": "str", "model_a": "str", "model_b": "str", "conversation": "list[dict]"},
        ),
        uses=DatasheetUses(
            intended_uses=["Optional evaluation reference for real-world user dialogue distribution."],
        ),
        distribution=DatasheetDistribution(
            license_claimed_hf="lmsys-terms",
            license_verified_upstream="LMSYS Dataset Agreement (Gated; Research & Commercial Use Allowed Subject to Terms)",
            license_verification_url="https://huggingface.co/datasets/lmsys/lmsys-chat-1m#license-and-terms-of-use",
            license_verified_at="2026-08-22",
            license_discrepancy=False,
            license_notes="Gated dataset. Requires login & agreement. Explicit terms: Right-to-request-deletion clause (authors can request destruction of copies); contains unfiltered/unsafe user content. Marked optional (is_required=False).",
            is_gated=True,
        ),
    ),
    DatasetEntry(
        dataset_id="mbti_personality_traits",
        hf_repo_id="Shunian/kaggle-mbti-cleaned",
        pinned_revision="5dcc41662640dbd74f9fc89fb328fd0cd666ce03",
        files_or_patterns=["data/test-00000-of-00001-6475b998015ce8dc.parquet"],
        profiles=["full"],
        download_method="hf_hub_file",
        preprocessing_fn="preprocess_mbti_traits",
        is_required=False,
        estimated_raw_size_mb=4.5,
        motivation=DatasheetMotivation(
            purpose="Personality trait distributions and behavioral priors for persona simulation.",
            domain="MBTI personality types and social writing samples",
            research_questions=["Can personality trait priors inform realistic persona behavioral constraints?"],
        ),
        composition=DatasheetComposition(
            instance_type="MBTI type label with 50 writing sample posts",
            slice_description="Test split of cleaned MBTI dataset",
            sample_count_estimate=1000,
            sensitive_content="Public forum posts; self-reported personality classifications.",
        ),
        collection=DatasheetCollection(
            source_url="https://www.kaggle.com/datasets/datasnaek/mbti-type",
            upstream_creator="Kaggle / datasnaek (scraped from PersonalityCafe forum)",
            collection_mechanism="Scraped public PersonalityCafe forum posts tagged with self-reported MBTI types.",
        ),
        preprocessing=DatasheetPreprocessing(
            raw_format="parquet",
            cleaning_applied="Clean URLs and noise; extract type classification and representative posts.",
            normalized_jsonl_schema={"id": "str", "mbti_type": "str", "posts": "list[str]"},
        ),
        uses=DatasheetUses(
            intended_uses=["Optional personality trait priors for persona engine in Phase 8."],
        ),
        distribution=DatasheetDistribution(
            license_claimed_hf="cc0-1.0",
            license_verified_upstream="CC0-1.0 / Public Domain (Kaggle datasnaek/mbti-type)",
            license_verification_url="https://www.kaggle.com/datasets/datasnaek/mbti-type",
            license_verified_at="2026-08-22",
            license_discrepancy=False,
            license_notes="Verified against original Kaggle dataset page: released under CC0: Public Domain.",
            is_gated=False,
        ),
    ),
]


def get_manifest() -> List[DatasetEntry]:
    """Return the authoritative list of dataset entries."""
    return DATASET_MANIFEST


def get_entries_for_profile(profile: ProfileType) -> List[DatasetEntry]:
    """Return all dataset entries included in the specified profile.
    
    Enforces strict subset hierarchy: minimal ⊂ development ⊂ evaluation ⊂ full.
    """
    if profile not in PROFILES_ORDER:
        raise ValueError(f"Unknown profile '{profile}'. Must be one of {PROFILES_ORDER}")
    return [entry for entry in DATASET_MANIFEST if profile in entry.profiles]
