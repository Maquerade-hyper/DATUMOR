# M4.1 ? Quality Metrics

## Purpose
Calculate explainable, reproducible quality measurements from a DUKR
representation without modifying source data or knowledge artifacts.

## Public interface
`calculate_quality_metrics(dukr)`

## Quality dimensions
| Dimension | Weight | Measurement |
|---|---:|---|
| Structural integrity | 20% | DUKR validation, graph identifiers and references |
| Content preservation | 20% | Exact context reconstruction and content hash |
| Evidence coverage | 20% | Knowledge artifacts with valid source offsets |
| Provenance completeness | 15% | Source ID, project ID, filename, path and checksum |
| Semantic linkage | 15% | Resolved relationship endpoints and statement entity references |
| Context completeness | 10% | Context units, sentence records, summary and references |

## Scoring
Scores are percentages from 0 to 100. Weighted scores use the configured
dimension weights. Unassessed dimensions are not silently assigned 100:
their weight is excluded from the weighted calculation and the result is
scaled by the assessed weight.

An evidence score is unassessed when there are no entities, relationships
or semantic statements to evaluate.

Dimension status:
- pass: 90?100
- warning: 70?89.99
- fail: below 70
- not_assessed: no measurable denominator

## Output
Metrics schema, DUKR representation ID, evaluation timestamp, overall score
and status, per-dimension scores and details, weights, artifact counts,
warnings and the underlying DUKR validation result.

## Limitations
M4.1 measures structural and traceability properties. It does not yet
determine semantic truth, detect near-duplicates, resolve contradictions,
or certify data as suitable for a particular model or task.

## Testing
`python -m pytest tests/unit/test_quality_metrics.py -q`
