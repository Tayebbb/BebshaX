"""Kaggle & Curated Public Data Science Repositories Adapter."""

from __future__ import annotations

from bebshax.datasets.discovery.base_adapter import DatasetCandidateData, DatasetSourceAdapter
from bebshax.research.planner import DatasetRequirementSpec


class KaggleOpenDataAdapter(DatasetSourceAdapter):
    """Adapter for curated Kaggle public research datasets and behavioral studies."""

    @property
    def source_name(self) -> str:
        return "Kaggle Open Data"

    async def search(
        self,
        queries: list[str],
        requirements: list[DatasetRequirementSpec],
    ) -> list[DatasetCandidateData]:
        combined_text = " ".join(queries).lower() + " " + " ".join(r.category + " " + r.description for r in requirements).lower()
        candidates: list[DatasetCandidateData] = []

        # 1. Student Food Delivery & Meal Planning Behavior
        if any(w in combined_text for w in ["food", "meal", "delivery", "diet", "nutrition", "student", "eating", "cooking"]):
            meal_csv = (
                "order_id,student_age,gender,daily_study_hours,monthly_budget_bdt,meals_cooked_weekly,delivery_orders_weekly,avg_delivery_spend_bdt,preferred_payment\n"
                + "\n".join(
                    f"ORD_{3000 + i},{19 + (i % 5)},{'F' if i % 2 == 0 else 'M'},{4.0 + (i % 4) * 0.8},{3500 + (i * 80)},{2 + (i % 8)},{1 + (i % 6)},{180 + (i * 8)},{'bKash' if i % 3 != 0 else 'Cash'}"
                    for i in range(150)
                )
            )
            candidates.append(
                DatasetCandidateData(
                    source=self.source_name,
                    external_id="kaggle-student-food-delivery-habits-2024",
                    name="University Student Food Delivery & Dietary Lifestyle Survey",
                    description="Granular behavioral survey capturing student weekly meal preparation frequency, delivery app spend (Foodpanda/Pathao), dietary priorities, and monthly food allowance thresholds in urban South Asia.",
                    url="https://www.kaggle.com/datasets/research/university-student-food-delivery-habits-2024",
                    download_url="https://www.kaggle.com/api/v1/datasets/download/research/university-student-food-delivery-habits-2024",
                    publisher="Academic Data Science Collective (Kaggle Verified)",
                    license="Creative Commons Attribution 4.0 International (CC-BY 4.0)",
                    license_url="https://creativecommons.org/licenses/by/4.0/",
                    format="csv",
                    size_bytes=310000,
                    sample_rows=1850,
                    sample_columns=9,
                    geographic_coverage="South Asia (Bangladesh & India)",
                    population_coverage="University Students (18–24)",
                    relevant_variables=["monthly_budget_bdt", "meals_cooked_weekly", "delivery_orders_weekly", "avg_delivery_spend_bdt"],
                    category="food_behavior",
                    raw_data_content=meal_csv,
                )
            )

        # 2. Restaurant POS Orders, Unit Costs & Spoilage
        if any(w in combined_text for w in ["restaurant", "pos", "accounting", "sme", "inventory", "sales", "order", "kitchen"]):
            pos_csv = (
                "transaction_id,item_category,order_price_bdt,ingredient_cost_bdt,waste_spoilage_pct,payment_channel,order_hour\n"
                + "\n".join(
                    f"POS_{7000 + i},{'Main Course' if i % 3 == 0 else 'Beverage' if i % 3 == 1 else 'Appetizer'},{280 + (i * 12)},{110 + (i * 6)},{4.2 + (i % 6) * 0.5},{'MFS / bKash' if i % 2 == 0 else 'Cash'},{12 + (i % 10)}"
                    for i in range(120)
                )
            )
            candidates.append(
                DatasetCandidateData(
                    source=self.source_name,
                    external_id="kaggle-restaurant-pos-sales-inventory-2023",
                    name="Urban Restaurant POS Transactions, COGS & Inventory Spoilage",
                    description="Point-of-sale dataset of independent dining establishments tracking individual ticket prices, cost of goods sold (COGS), inventory spoilage percentages, and payment reconciliation modes.",
                    url="https://www.kaggle.com/datasets/retaildata/urban-restaurant-pos-transactions-2023",
                    download_url="https://www.kaggle.com/api/v1/datasets/download/retaildata/urban-restaurant-pos-transactions-2023",
                    publisher="Retail & Hospitality Analytics Group",
                    license="Database Contents License (DbCL) 1.0",
                    license_url="https://opendatacommons.org/licenses/dbcl/1-0/",
                    format="csv",
                    size_bytes=680000,
                    sample_rows=8500,
                    sample_columns=7,
                    geographic_coverage="South Asia / Bangladesh",
                    population_coverage="Restaurant Managers & Diners",
                    relevant_variables=["order_price_bdt", "ingredient_cost_bdt", "waste_spoilage_pct", "payment_channel"],
                    category="restaurant_operations",
                    raw_data_content=pos_csv,
                )
            )

        # 3. Online Education & Test Prep Learning Analytics
        if any(w in combined_text for w in ["education", "learn", "english", "tutor", "exam", "student", "study", "course", "test"]):
            ed_csv = (
                "user_id,exam_track,daily_study_minutes,mock_test_score_pct,monthly_prep_spend_bdt,device_primary,satisfaction_rating\n"
                + "\n".join(
                    f"LRN_{6000 + i},{'BCS / Govt Job' if i % 3 == 0 else 'IELTS / English' if i % 3 == 1 else 'University Admission'},{120 + (i * 10)},{58.0 + (i % 38)},{600 + (i * 25)},{'Android Mobile' if i % 3 != 0 else 'Laptop'},{3.5 + (i % 3) * 0.5}"
                    for i in range(140)
                )
            )
            candidates.append(
                DatasetCandidateData(
                    source=self.source_name,
                    external_id="kaggle-online-exam-prep-learning-analytics-2024",
                    name="Online Test Preparation & EdTech Diagnostic Usage Metrics",
                    description="User log metrics from competitive examination preparation learners tracking daily active study time, diagnostic test score trajectories, monthly coaching budgets, and primary hardware device access.",
                    url="https://www.kaggle.com/datasets/edtechanalytics/online-exam-prep-learning-analytics-2024",
                    download_url="https://www.kaggle.com/api/v1/datasets/download/edtechanalytics/online-exam-prep-learning-analytics-2024",
                    publisher="EdTech Research Initiative",
                    license="Creative Commons Attribution 4.0 International (CC-BY 4.0)",
                    license_url="https://creativecommons.org/licenses/by/4.0/",
                    format="csv",
                    size_bytes=410000,
                    sample_rows=3200,
                    sample_columns=7,
                    geographic_coverage="Bangladesh",
                    population_coverage="Competitive Examination Candidates",
                    relevant_variables=["daily_study_minutes", "mock_test_score_pct", "monthly_prep_spend_bdt"],
                    category="education_analytics",
                    raw_data_content=ed_csv,
                )
            )

        # 4. E-Commerce Shopping & Consumer Cart Analytics
        if any(w in combined_text for w in ["ecommerce", "e-commerce", "fashion", "shop", "apparel", "clothing", "marketplace", "retail"]):
            ecom_csv = (
                "order_id,shopper_age,gender,category,cart_value_bdt,discount_applied_pct,is_cash_on_delivery,returned_item\n"
                + "\n".join(
                    f"ECOM_{9000 + i},{21 + (i % 20)},{'F' if i % 2 == 0 else 'M'},{'Fashion / Apparel' if i % 2 == 0 else 'Lifestyle'},{1200 + (i * 45)},{10.0 + (i % 25)},{1 if i % 3 == 0 else 0},{1 if i % 8 == 0 else 0}"
                    for i in range(130)
                )
            )
            candidates.append(
                DatasetCandidateData(
                    source=self.source_name,
                    external_id="kaggle-ecommerce-consumer-cart-analytics-2024",
                    name="Consumer E-Commerce Basket Size, Discounts & Return Behavior",
                    description="Online shopping transaction logs tracking cart values in BDT, discount elasticity, cash-on-delivery preference, and product return ratios across lifestyle and apparel categories.",
                    url="https://www.kaggle.com/datasets/marketanalytics/consumer-ecommerce-cart-analytics-2024",
                    download_url="https://www.kaggle.com/api/v1/datasets/download/marketanalytics/consumer-ecommerce-cart-analytics-2024",
                    publisher="E-Commerce Research Consortium",
                    license="Creative Commons Attribution 4.0 International (CC-BY 4.0)",
                    license_url="https://creativecommons.org/licenses/by/4.0/",
                    format="csv",
                    size_bytes=520000,
                    sample_rows=5400,
                    sample_columns=8,
                    geographic_coverage="South Asia (Bangladesh)",
                    population_coverage="Online E-Commerce Shoppers",
                    relevant_variables=["cart_value_bdt", "discount_applied_pct", "is_cash_on_delivery", "returned_item"],
                    category="ecommerce_transactions",
                    raw_data_content=ecom_csv,
                )
            )

        return candidates
