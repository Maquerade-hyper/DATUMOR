# M4.3 ? Consistency Analysis

## Purpose
Identify structural defects, entity representation differences,
relationship disagreements and potentially opposing semantic statements
across DUKR documents.

## Public interface
`analyze_consistency(dukr_documents)`

## Analysis categories

### Structural
Uses the DUKR integrity validator to report unresolved graph references,
invalid content reconstruction, checksum errors and related structural
problems.

### Entity
Groups entities by entity type and normalized value across distinct sources.
Different display forms are reported as representation variance, not as
proof of conflicting real-world identity.

### Relationship
Groups relationships by normalized subject identity and predicate.
Different objects across distinct sources produce a review finding.
Temporal, contextual and multi-valued explanations remain possible.

### Semantic
Uses deterministic lexical polarity matching to identify potentially
opposing statements across distinct sources. Temporal markers lower
severity but do not automatically resolve a disagreement.

## Output
The report contains:
- Finding IDs and categories.
- Severity and confidence.
- Source references.
- Original evidence and source offsets.
- Review requirement and unresolved status.
- Category and severity counts.
- Explicit warning that no automatic correction occurs.

## Important limitations
This is deterministic consistency screening, not full entity resolution
or natural-language contradiction reasoning. It cannot reliably establish
that two differently named entities refer to the same real-world object.
Lexical negation and temporal matching can produce false positives and
false negatives. Findings require human or downstream verification.

## Testing
`python -m pytest tests/unit/test_consistency_analysis.py -q`
