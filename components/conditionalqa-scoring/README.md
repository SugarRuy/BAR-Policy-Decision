# conditionalqa-scoring

Preserve the existing full-reference denominator correction and explicit null convention for undefined categories.

Distribution: BSD-2-Clause for evaluator patch; dataset terms separate.

See [component use and verification](../../docs/COMPONENTS.md) and [exact source bindings](component.json).

- Per-question scoring and all reference labels remain unchanged.
- Explicit [] and a missing prediction are distinct inputs.
- Duplicate IDs and malformed answers retain upstream behavior.
- No raw documents, references or dataset license grant are distributed.
