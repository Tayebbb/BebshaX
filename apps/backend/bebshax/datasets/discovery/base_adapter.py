"""Base adapter and data structures for Dataset Discovery in BebshaX."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Optional
from pydantic import BaseModel, Field

from bebshax.research.planner import DatasetRequirementSpec


class DatasetCandidateData(BaseModel):
    source: str = Field(..., description="Name of the public data portal or repository (e.g., BBS Open Data, World Bank, Kaggle)")
    external_id: str = Field(..., description="Unique ID within the source repository")
    name: str = Field(..., description="Official title of the dataset")
    description: str = Field(..., description="Summary of dataset contents and collection methodology")
    url: str = Field(..., description="Verified public URL of the dataset listing")
    download_url: Optional[str] = Field(None, description="Direct or simulated download endpoint for automated ingestion")
    publisher: str = Field(..., description="Issuing authority, government body, or organization")
    license: str = Field("Open Access / Public Domain", description="License or usage terms")
    license_url: Optional[str] = Field(None, description="License terms URL")
    format: str = Field("csv", description="File format (csv, json, xlsx, tsv)")
    size_bytes: int = Field(default=102400, description="Approximate byte size")
    sample_rows: int = Field(default=1000, description="Total record count")
    sample_columns: int = Field(default=10, description="Total variable count")
    geographic_coverage: str = Field("Bangladesh", description="Geographic scope of the data")
    population_coverage: str = Field("National Population", description="Target population group covered")
    relevant_variables: list[str] = Field(default_factory=list, description="Variables matching the research requirements")
    category: str = Field("general", description="Primary dataset category")
    is_sample: bool = Field(
        False,
        description="True when the candidate comes from the BebshaX illustrative sample catalog rather than a live source fetch",
    )
    raw_data_content: Optional[str] = Field(None, description="Structured CSV content string for automated import")


class DatasetEvaluationResult(BaseModel):
    candidate: DatasetCandidateData
    relevance_score: float
    quality_score: float
    is_selected: bool
    selection_status: str  # "selected", "discovered", "rejected_by_user", "import_failed", "imported"
    selection_reason: str
    evaluation_details: dict[str, Any]


class DatasetSourceAdapter(ABC):
    """Abstract interface for public dataset discovery sources."""

    @property
    @abstractmethod
    def source_name(self) -> str:
        """Name of the data source provider."""
        pass

    @abstractmethod
    async def search(
        self,
        queries: list[str],
        requirements: list[DatasetRequirementSpec],
    ) -> list[DatasetCandidateData]:
        """Search repository for dataset candidates matching research requirements."""
        pass
