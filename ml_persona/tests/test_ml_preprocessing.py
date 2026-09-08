"""Offline preprocessing contracts using invented Nemotron-shaped records."""

import json

import pytest

from bebshax_persona_ml.data import prepare_records, split_records

SOURCE = "nvidia/Nemotron-Personas-USA"
REVISION = "fixture-revision-001"
NARRATIVE_FIELDS = (
    "persona",
    "professional_persona",
    "sports_persona",
    "arts_persona",
    "travel_persona",
    "culinary_persona",
    "cultural_background",
    "skills_and_expertise",
    "hobbies_and_interests",
    "career_goals_and_ambitions",
)


@pytest.fixture
def nemotron_rows() -> list[dict[str, object]]:
    return [
        {
            "uuid": "fixture-001",
            "persona": "Alex Example is a university student who struggles with meal costs.",
            "professional_persona": "Alex Example is a university student managing coursework.",
            "sports_persona": "Alex Example plays basketball at a community court.",
            "arts_persona": "Alex Example sketches buildings during study breaks.",
            "travel_persona": "Alex Example faces a limited travel budget.",
            "culinary_persona": "Alex Example cooks shared meals to reduce spending.",
            "cultural_background": "Alex Example takes part in a campus book club.",
            "skills_and_expertise": "Alex Example uses spreadsheets to track meal costs.",
            "hobbies_and_interests": "Alex Example enjoys sketching and community sports.",
            "career_goals_and_ambitions": "Finish a degree while keeping costs manageable.",
            "age": 21,
            "occupation": "student",
            "education_level": "some_college",
            "city": "Test City",
            "state": "CA",
            "country": "USA",
        },
        {
            "uuid": "fixture-002",
            "persona": "Morgan Sample is an electrician who needs predictable work hours.",
            "professional_persona": "Morgan Sample schedules repairs for community centers.",
            "sports_persona": "Morgan Sample practices tennis on weekends.",
            "arts_persona": "Morgan Sample attends community pottery classes.",
            "travel_persona": "Morgan Sample plans short trips around repair appointments.",
            "culinary_persona": "Morgan Sample prepares lunches before work.",
            "cultural_background": "Morgan Sample participates in neighborhood workshops.",
            "skills_and_expertise": "Morgan Sample diagnoses faults in lighting circuits.",
            "hobbies_and_interests": "Morgan Sample enjoys pottery and weekend tennis.",
            "career_goals_and_ambitions": "Improve repair scheduling and keep evenings free.",
            "age": 43,
            "occupation": "electrician",
            "education_level": "vocational_training",
            "city": "Sample Town",
            "state": "WA",
            "country": "USA",
        },
    ]


def test_prepare_records_maps_frozen_typed_profiles_without_truncation(
    nemotron_rows: list[dict[str, object]],
) -> None:
    long_identity = str(nemotron_rows[0]["persona"]) + " " + " ".join(
        f"During study week {week}, Alex records meal costs before attending classes."
        for week in range(1, 101)
    )
    rows = [{**nemotron_rows[0], "persona": long_identity}, nemotron_rows[1]]
    records, stats = prepare_records(rows, source=SOURCE, revision=REVISION)

    assert len(records) == 2
    assert stats["accepted"] == 2
    assert len({record.record_id for record in records}) == 2
    by_occupation = {record.occupation: record for record in records}
    for row in rows:
        record = by_occupation[row["occupation"]]
        assert isinstance(record.record_id, str) and record.record_id
        assert record.source == SOURCE
        assert record.revision == REVISION
        assert type(record.age) is int and record.age == row["age"]
        assert record.education == row["education_level"]
        assert isinstance(record.location, str)
        assert all(str(row[field]) in record.location for field in ("city", "state", "country"))
        assert record.name is None or isinstance(record.name, str)
        assert isinstance(record.description, str)
        assert str(row["persona"]) in record.description
        for field in ("goals", "pain_points", "behaviors"):
            values = getattr(record, field)
            assert isinstance(values, list)
            assert all(isinstance(value, str) for value in values)
        assert isinstance(record.documents, dict)
        assert all(
            isinstance(key, str) and isinstance(value, str)
            for key, value in record.documents.items()
        )
        document_text = "\n".join(record.documents.values())
        assert all(str(row[field]) in document_text for field in NARRATIVE_FIELDS)
        with pytest.raises((AttributeError, TypeError, ValueError)):
            setattr(record, "age", record.age + 1)
        assert record.age == row["age"]


def test_prepare_records_leaves_absent_optional_demographics_unset() -> None:
    rows = [
        {
            "uuid": "fixture-optional-absent",
            "persona": "Alex Example tracks meal costs and plans weekly spending.",
        },
        {
            "uuid": "fixture-optional-null",
            "persona": "Morgan Sample organizes repair projects and keeps a supplies list.",
            "age": None,
            "occupation": None,
            "education_level": None,
            "city": None,
            "state": None,
            "country": None,
        },
    ]
    records, stats = prepare_records(rows, source=SOURCE, revision=REVISION)

    assert len(records) == 2
    assert stats["rejected"] == 0
    for record in records:
        assert record.age is None
        assert record.occupation in (None, "")
        assert record.education in (None, "")
        assert record.location in (None, "")


def test_prepare_records_collapses_exact_duplicate_rows(
    nemotron_rows: list[dict[str, object]],
) -> None:
    unique_records, _ = prepare_records(nemotron_rows, source=SOURCE, revision=REVISION)
    rows = [nemotron_rows[0], dict(nemotron_rows[0]), nemotron_rows[1]]
    records, stats = prepare_records(rows, source=SOURCE, revision=REVISION)

    assert len(records) == 2
    assert {record.record_id for record in records} == {
        record.record_id for record in unique_records
    }
    assert stats["accepted"] == 2
    assert stats["duplicates"] == 1
    assert stats["rejected"] == 0


def test_prepare_records_counts_invalid_rows_and_accepts_age_boundaries(
    nemotron_rows: list[dict[str, object]],
) -> None:
    valid_rows = [
        {**nemotron_rows[0], "uuid": "fixture-age-minimum", "age": 18},
        {**nemotron_rows[1], "uuid": "fixture-age-maximum", "age": 95},
    ]
    invalid_rows = [
        {**nemotron_rows[0], "uuid": "fixture-underage", "age": 17},
        {**nemotron_rows[1], "uuid": "fixture-overage", "age": 96},
        {key: value for key, value in nemotron_rows[0].items() if key != "uuid"},
        {"uuid": "fixture-empty-identity", "age": 21, "persona": ""},
        {"uuid": "fixture-blank-identity", "age": 43, "persona": "   "},
    ]
    records, stats = prepare_records(
        valid_rows + invalid_rows, source=SOURCE, revision=REVISION,
    )

    assert len(records) == 2
    assert {record.age for record in records} == {18, 95}
    assert stats["accepted"] == 2
    assert stats["rejected"] == len(invalid_rows)
    for row in invalid_rows:
        rejected_records, rejection_stats = prepare_records(
            [row], source=SOURCE, revision=REVISION,
        )
        assert rejected_records == []
        assert rejection_stats["rejected"] == 1


def test_prepare_records_excludes_sensitive_metadata_from_profile_fields(
    nemotron_rows: list[dict[str, object]],
) -> None:
    forbidden = {
        "zipcode": "00000",
        "sex": "fixture-sex-marker",
        "religion": "fixture-religion-marker",
        "coordinates": "12.34567, 67.89012",
        "latitude": "12.34567",
        "longitude": "67.89012",
    }
    records, _ = prepare_records(
        [{**nemotron_rows[0], **forbidden}], source=SOURCE, revision=REVISION,
    )

    assert len(records) == 1
    record = records[0]
    assert all(not hasattr(record, field) for field in forbidden)
    profile = {
        field: getattr(record, field)
        for field in (
            "age", "occupation", "education", "location", "name", "description",
            "goals", "pain_points", "behaviors",
        )
    }
    profile_text = json.dumps(profile)
    assert all(value not in profile_text for value in forbidden.values())


def test_split_records_is_seeded_identity_disjoint_and_retains_all_ids() -> None:
    activities = (
        "ceramics", "gardening", "woodworking", "photography", "knitting", "baking",
        "calligraphy", "chess", "weaving", "sewing", "printmaking", "bookbinding",
        "coding", "yoga", "cycling", "robotics", "origami", "cooking",
        "sculpture", "painting", "jewelry making", "dancing", "composing", "acting",
    )
    rows = [
        {
            "uuid": f"fixture-split-{index:03d}",
            "persona": (
                f"Fixture Person {index} teaches {activity} and needs affordable workshop supplies."
            ),
            "professional_persona": (
                f"Fixture Person {index} organizes {activity} workshops at a community center."
            ),
            "career_goals_and_ambitions": f"Make {activity} sessions affordable for beginners.",
            "age": 18 + index,
            "occupation": "instructor",
            "education_level": "some_college",
            "city": "Test City",
            "state": "CA",
            "country": "USA",
        }
        for index, activity in enumerate(activities)
    ]
    records, _ = prepare_records(rows, source=SOURCE, revision=REVISION)
    assert len(records) == 24
    assert len({record.record_id for record in records}) == 24
    split_input = records + records[::5]
    splits = split_records(
        split_input, seed=42, validation_fraction=0.15, test_fraction=0.15,
    )
    repeated_splits = split_records(split_input)

    assert set(splits) == {"train", "validation", "test"}
    assert all(isinstance(partition, list) and partition for partition in splits.values())
    assert {key: [record.record_id for record in value] for key, value in splits.items()} == {
        key: [record.record_id for record in value] for key, value in repeated_splits.items()
    }
    split_ids = {key: {record.record_id for record in value} for key, value in splits.items()}
    assert split_ids["train"].isdisjoint(split_ids["validation"])
    assert split_ids["train"].isdisjoint(split_ids["test"])
    assert split_ids["validation"].isdisjoint(split_ids["test"])
    assert set().union(*split_ids.values()) == {record.record_id for record in records}


@pytest.mark.parametrize("identity, expected", [
    ("Jenna Jenkins, a detail-oriented retail professional, plans affordable meals.", "Jenna Jenkins"),
    ("Ann Damron's analytical mind drives her logistics career.", "Ann Damron"),
    ("Juan Thomas builds concrete, crews, and community gatherings.", "Juan Thomas"),
    ("Rafael Martinez blends hands-on skills with curiosity.", "Rafael Martinez"),
])
def test_extracts_source_name_without_rewriting_the_identity(identity: str, expected: str) -> None:
    records, _ = prepare_records(
        [{"uuid": "source-narrative", "persona": identity}], source=SOURCE, revision=REVISION,
    )

    assert records[0].name == expected
    assert records[0].description == identity


def test_split_groups_shared_names_and_format_variants(nemotron_rows: list[dict[str, object]]) -> None:
    rows = [
        {**nemotron_rows[0], "uuid": "alex-alternative", "persona": "Alex Example enjoys affordable cooking."},
        {**nemotron_rows[0], "uuid": "alex-format", "persona": "Alex Example enjoys affordable cooking!"},
        *nemotron_rows,
        {"uuid": "third", "persona": "Jamie Fixture is an artist who needs supplies."},
        {"uuid": "fourth", "persona": "Robin Test is a carpenter who needs tools."},
    ]
    records, _ = prepare_records(rows, source=SOURCE, revision=REVISION)
    splits = split_records(records)

    partitions = {record.record_id: partition for partition, values in splits.items() for record in values}
    alex_ids = [record.record_id for record in records if record.name == "Alex Example"]
    assert len({partitions[record_id] for record_id in alex_ids}) == 1