"""Dataset discovery package for BebshaX — live, keyless public sources only."""

from bebshax.datasets.discovery.base_adapter import (
    DatasetCandidateData,
    DatasetEvaluationResult,
    DatasetSourceAdapter,
)
from bebshax.datasets.discovery.ckan_adapter import CKANDatasetAdapter
from bebshax.datasets.discovery.downloader import DatasetDownloadFailed, fetch_resource_bytes
from bebshax.datasets.discovery.engine import DatasetDiscoveryEngine, default_adapters, materialize_candidate
from bebshax.datasets.discovery.evaluator import DatasetEvaluator
from bebshax.datasets.discovery.world_bank_adapter import WorldBankOpenDataAdapter

__all__ = [
    "DatasetCandidateData",
    "DatasetEvaluationResult",
    "DatasetSourceAdapter",
    "CKANDatasetAdapter",
    "DatasetDownloadFailed",
    "WorldBankOpenDataAdapter",
    "DatasetEvaluator",
    "DatasetDiscoveryEngine",
    "default_adapters",
    "fetch_resource_bytes",
    "materialize_candidate",
]
