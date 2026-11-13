# M5.1 ? Transformation Profiles

## Purpose

Transformation profiles declare the intended shape and processing preferences of a derived AI dataset. They do not execute transformations.

## Built-in profiles

- `general_llm`: instruction and response datasets.
- `coding`: code generation, debugging, and explanation.
- `research`: evidence-grounded question and answer datasets.
- `retrieval`: query and relevant-context pairs.

## Profile configuration

Each profile defines:
- Identity, version, task type, and description.
- Output format and required/optional fields.
- Minimum quality threshold.
- Source metadata and provenance requirements.
- Duplicate-handling preference.
- Normalization preference.
- Chunking preference.
- Optional target model.

## Public functions

- `list_profiles()`
- `get_profile(profile_id)`
- `validate_profile(profile)`
- `create_custom_profile(profile)`

Custom profiles are validated and returned in memory. Persistent profile storage and API endpoints are not part of this implementation step.

## Safety and integrity

- Profiles are returned as independent copies.
- Unknown configuration keys are rejected.
- Invalid thresholds, field overlaps, and chunking settings are rejected.
- Profile creation does not modify DUKR or source datasets.
- Provenance preservation is enabled by default.
- Normalization and chunking are declarations only; execution belongs to later M5 steps.
