# legalbench-sara-numeric

Parse signed decimal amounts, retain the exact native nonzero floating-point acceptance formula, special-case exact zero, and explicitly reject unequal or empty reference populations.

Distribution: MIT for BAR code only; no license grant for upstream source/data.

See [component use and verification](../../docs/COMPONENTS.md) and [exact source bindings](component.json).

- First-number extraction is retained. A line-leading minus before an amount is interpreted as a sign even if it could be a Markdown bullet. Unicode minus, European separators, scientific notation and general free-form financial parsing are not certified.
- No reference tax amount is certified by the 100-label echo diagnostic.
