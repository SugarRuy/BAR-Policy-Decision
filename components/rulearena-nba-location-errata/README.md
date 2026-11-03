# RuleArena NBA localization errata

Two field changes in the frozen 216-case release:

| Native case (zero-based index) | Field | Original → revised | Source basis |
|---|---|---|---|
| `comp_1/62` | `problematic_team` | H → Q | Team H does not appear. Q signs and trades with 6% raises; Article VII §5(a)(2) redirects sign-and-trades to the 5% limit in §5(a)(1). |
| `comp_2/4` | `illegal_operation` | C → D | Literal operation D is Team A's signing. With the native salary and transaction-order convention, the over-38 allocation gives a first-year charge of 172,000,000/21, exceeding the first apron by 1,228,000/21. |

`scripts/bar.py prepare rulearena-nba-location-errata` produces corrected copies
of the two affected native JSON files. `scripts/bar.py dataset
rulearena-nba-location-errata` provides all 216 original/revised records with IDs,
hashes and changed-field flags. Both require the fixed source checkout and new
output directories. `errata.json` contains the exact guarded field replacements.

All 216 binary verdicts, case/policy text and rule annotations remain unchanged;
214 complete records are identical. The original substring scorer is unchanged.
Constructed answer probes document how the two target changes affect that
scorer, without claiming a measured model-score effect.

These are supported violating locations, not an exhaustive list. The receiving
team F's separate Room requirement in `comp_1/62` remains unresolved. The
withheld `comp_1/81` issue and rule-attribution vocabulary mismatch are not
resolved by these patches. The resource does not certify all other labels.
