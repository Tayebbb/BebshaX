"""Dataset discovery package for BebshaX."""

from bebshax.datasets.discovery.base_adapter import (
    DatasetCandidateData,
    DatasetEvaluationResult,
    DatasetSourceAdapter,
)
from bebshax.datasets.discovery.bbs_adapter import BBSOpenDataAdapter
from bebshax.datasets.discovery.engine import DatasetDiscoveryEngine
from bebshax.datasets.discovery.evaluator import DatasetEvaluator
from bebshax.datasets.discovery.kaggle_adapter import KaggleOpenDataAdapter
from bebshax.datasets.discovery.world_bank_adapter import WorldBankOpenDataAdapter

__all__ = [
    "DatasetCandidateData",
    "DatasetEvaluationResult",
    "DatasetSourceAdapter",
    "BBSOpenDataAdapter",
    "WorldBankOpenDataAdapter",
    "KaggleOpenDataAdapter",
    "DatasetEvaluator",
    "DatasetDiscoveryEngine",
]
