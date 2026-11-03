# RuleArena Airline prompt errata

Corrects the native example's item-cost summary and textual-policy transcription
against the unchanged Markdown policy. It fixes the item 2/3 fee swap, later-bag
headings, the 70–100 lb heading, and five Haiti clauses with an extra Cuba suffix.
The example remains $750 in baggage fees and $1,198 including the ticket.

Use `scripts/bar.py prepare rulearena-airline-prompt-errata` with the pinned
RuleArena source and a new output directory. The output contains two revised
files, the upstream license and a receipt. These are overlay files, not a complete runnable checkout.
Apply them only to a separate copy of the same pinned upstream source.

Across 300 cases and four Markdown/textual × zero/one-shot variants, 900 prompts
change. Markdown zero-shot, case facts, numeric fee cells, reference amounts,
calculator, and scoring code remain unchanged. New predictions are needed for
modified prompts; no performance improvement is claimed. The unstated allocation
objective is handled by the separate `rulearena-airline-objective` component.

The textual policy still renders nine Markdown Premium Economy dash cells as
explicit `$0` clauses, consistent with the native calculator's interpretation.
This erratum deliberately leaves that interpretation unchanged. In the four
affected native PE cases, the textual input therefore states information that
the Markdown table leaves ambiguous; the two policy variants are not fully
equivalent.

Both this component and the scoring patch modify `airline/auto_test.py`. Their
prepared outputs are independent overlays: do not overwrite one with the other
or apply one patch to the other's changed file. Compose only after separately
verifying the combined result.
