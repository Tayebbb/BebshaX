"""Market segmentation engine for BebshaX.

Provides data-grounded variable selection, deterministic clustering,
LLM-assisted qualitative interpretation, and evidence linking.
"""

from bebshax.segmentation.pre_check import check_segmentation_readiness
from bebshax.segmentation.service import SegmentationEngineService

__all__ = [
    "check_segmentation_readiness",
    "SegmentationEngineService",
]
