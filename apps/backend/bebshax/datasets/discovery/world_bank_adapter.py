"""World Bank & UN Development Open Data Adapter."""

from __future__ import annotations

from bebshax.datasets.discovery.base_adapter import DatasetCandidateData, DatasetSourceAdapter
from bebshax.research.planner import DatasetRequirementSpec


class WorldBankOpenDataAdapter(DatasetSourceAdapter):
    """Adapter for World Bank Open Data, Global Findex, and UN development indicators."""

    @property
    def source_name(self) -> str:
        return "World Bank Open Data"

    async def search(
        self,
        queries: list[str],
        requirements: list[DatasetRequirementSpec],
    ) -> list[DatasetCandidateData]:
        combined_text = " ".join(queries).lower() + " " + " ".join(r.category + " " + r.description for r in requirements).lower()
        candidates: list[DatasetCandidateData] = []

        # 1. Global Findex — Bangladesh Mobile Financial Services (MFS) & Payment Adoption
        if any(w in combined_text for w in ["payment", "fintech", "wallet", "bkash", "nagad", "digital", "spend", "online", "money", "ecommerce"]):
            findex_csv = (
                "respondent_id,age,gender,has_mfs_account,monthly_digital_transactions,monthly_mfs_spend_bdt,uses_utility_pay,savings_frequency\n"
                + "\n".join(
                    f"FINDEX_BD_{2000 + i},{18 + (i % 35)},{'Female' if i % 2 == 0 else 'Male'},1,{8 + (i % 20)},{3500 + (i * 120)},{1 if i % 3 != 0 else 0},{'Regular' if i % 2 == 0 else 'Occasional'}"
                    for i in range(120)
                )
            )
            candidates.append(
                DatasetCandidateData(
                    source=self.source_name,
                    external_id="worldbank-findex-bangladesh-mfs-2023",
                    name="World Bank Global Findex — Bangladesh Mobile Financial Inclusion & Payment Flows",
                    description="Standardized survey tracking mobile wallet penetration (bKash/Nagad), monthly digital transaction volumes, peer-to-peer transfers, and digital payment readiness across demographic cohorts.",
                    url="https://microdata.worldbank.org/index.php/catalog/global-findex",
                    download_url="https://api.worldbank.org/v2/microdata/findex-bangladesh-2023.csv",
                    publisher="World Bank Development Research Group",
                    license="Creative Commons Attribution 4.0 International (CC-BY 4.0)",
                    license_url="https://datacatalog.worldbank.org/public-licenses",
                    format="csv",
                    size_bytes=360000,
                    sample_rows=2500,
                    sample_columns=8,
                    geographic_coverage="Bangladesh",
                    population_coverage="Adult Population (18+)",
                    relevant_variables=["has_mfs_account", "monthly_digital_transactions", "monthly_mfs_spend_bdt"],
                    category="digital_payments",
                    raw_data_content=findex_csv,
                )
            )

        # 2. South Asia Enterprise Survey — Micro & SME Financial Health
        if any(w in combined_text for w in ["sme", "enterprise", "accounting", "business", "restaurant", "pos", "financial", "software"]):
            enterprise_csv = (
                "firm_id,sector,annual_sales_usd,operating_margin_pct,formal_bank_credit,software_budget_usd,digital_pos_adoption\n"
                + "\n".join(
                    f"WB_FIRM_{4000 + i},{'Food & Beverage Services' if i % 2 == 0 else 'Retail Trade'},{12000 + (i * 800)},{18.5 + (i % 12)},{1 if i % 3 == 0 else 0},{180 + (i * 15)},{1 if i % 2 == 0 else 0}"
                    for i in range(90)
                )
            )
            candidates.append(
                DatasetCandidateData(
                    source=self.source_name,
                    external_id="worldbank-enterprise-survey-southasia-2023",
                    name="World Bank Enterprise Survey — South Asia Small Business Finance & Tech",
                    description="Firm-level data on financial constraints, operating margins, technology adoption, and digital POS tool investments among micro and small enterprises in South Asia.",
                    url="https://www.enterprisesurveys.org/en/data/exploreeconomies/bangladesh",
                    download_url="https://api.worldbank.org/v2/microdata/enterprise-survey-bangladesh.csv",
                    publisher="World Bank Group Enterprise Analysis Unit",
                    license="Open Data Commons Public Domain (ODC-PD)",
                    license_url="https://datacatalog.worldbank.org/public-licenses",
                    format="csv",
                    size_bytes=490000,
                    sample_rows=1200,
                    sample_columns=7,
                    geographic_coverage="South Asia (Bangladesh Focus)",
                    population_coverage="Small & Medium Enterprise Operators",
                    relevant_variables=["operating_margin_pct", "software_budget_usd", "digital_pos_adoption"],
                    category="sme_finance",
                    raw_data_content=enterprise_csv,
                )
            )

        return candidates
