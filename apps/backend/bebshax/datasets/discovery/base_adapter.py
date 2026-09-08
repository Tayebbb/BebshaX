"""Base adapter and data structures for Dataset Discovery in BebshaX.

Every candidate describes a dataset that exists at a real, keyless public URL.
Attributes are what the source reports — unknown values stay ``None`` rather
than being filled with plausible numbers.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Optional
from pydantic import BaseModel, Field

from bebshax.research.planner import DatasetRequirementSpec


class DatasetCandidateData(BaseModel):
    source: str = Field(..., description="Name of the public data portal or repository (e.g. World Bank Open Data, HDX)")
    external_id: str = Field(..., description="Unique ID within the source repository")
    name: str = Field(..., description="Official title of the dataset")
    description: str = Field("", description="Summary of dataset contents as published by the source")
    url: str = Field(..., description="Public URL of the dataset listing")
    download_url: Optional[str] = Field(None, description="Direct download endpoint for automated ingestion (None = listing only)")
    publisher: str = Field(..., description="Issuing authority, government body, or organization")
    license: str = Field("", description="License or usage terms as published")
    license_url: Optional[str] = Field(None, description="License terms URL")
    format: str = Field("csv", description="File format (csv, json, jsonl, tsv, xlsx)")
    size_bytes: Optional[int] = Field(default=None, description="Byte size reported by the source, if any")
    sample_rows: Optional[int] = Field(default=None, description="Record count when known (e.g. after a live fetch)")
    sample_columns: Optional[int] = Field(default=None, description="Variable count when known")
    geographic_coverage: str = Field("", description="Geographic scope as published")
    population_coverage: str = Field("", description="Target population group as published")
    relevant_variables: list[str] = Field(default_factory=list, description="Variables/tags reported by the source")
    category: str = Field("general", description="Primary dataset category")
    tags: list[str] = Field(default_factory=list, description="Source tags/keywords")
    modified_at: Optional[str] = Field(None, description="Last-modified timestamp reported by the source (ISO 8601)")
    is_sample: bool = Field(
        False,
        description="Always False for live sources; kept so clients can still render a sample badge if a test corpus is wired",
    )
    raw_data_content: Optional[str] = Field(None, description="Tabular content already fetched from the source (e.g. API series)")


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
        *,
        countries: Optional[list[str]] = None,
    ) -> list[DatasetCandidateData]:
        """Search the repository for candidates matching the study's queries and
        requirements. ``countries`` are ISO-3166 alpha-3 codes of the study's
        target market (from the research plan); adapters that are country-bound
        return nothing when it is empty instead of assuming a country."""
        pass
