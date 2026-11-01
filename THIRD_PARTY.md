# Third-party terms and file-level distribution decisions

BAR-original code is MIT under the repository's root license. That license does
not replace third-party notices or grant rights to upstream datasets. This
document covers the three component exports and the accompanying study and
audit records. It does not grant a new license to upstream material.

| Files | Terms and attribution | Distribution decision |
| --- | --- | --- |
| `scripts/bar.py`, `scripts/check_components.py`, `components/legalbench-sara-numeric/evaluator.py` | BAR-original code, MIT; Yanru Xiao and Yifei Cai (2026) | Included. The SARA evaluator independently implements the stated parsing/math contract. |
| Component manifests, component documentation and SARA synthetic conformance vectors | BAR-original metadata/documentation; native source identities preserved | Included. SARA fixtures contain synthetic amounts and native IDs/diagnostic counts, not native labels or source text. |
| `components/rulearena-tax/line22.patch`, `labels.json`, `corrections.json`, `reference_pairs.jsonl` | RuleArena upstream MIT notice, copyright (c) 2024 Ruiwen Zhou, plus BAR's scoped revision | Included with `components/rulearena-tax/UPSTREAM-LICENSE`. All 300 source-bound reference pairs and 27 changes retain IDs, pins and dependency flags. Raw case/prompt files are obtained separately. |
| `components/conditionalqa-scoring/denominator.patch` | Upstream BSD-2-Clause notice, copyright (c) 2017 Bhuwan Dhingra, plus BAR's aggregation revision | Included with the unmodified `components/conditionalqa-scoring/UPSTREAM-LICENSE`. Notice also accompanies prepared output. |
| LegalBench `evaluation.py`, its source-context patch, and source-input restoration text | File-level source redistribution terms unresolved at the pinned revision | Excluded. The release does not contain the former `evaluation.py.patch` or full upstream module. Users supply their own pinned source for optional in-memory adaptation. |
| SARA statutes, cases, prompts and labels | The pinned LegalBench SARA task README says MIT for that task. This does not establish a license for all LegalBench code or independently settle the original SARA archive's terms. | Excluded; fetched by users from the pinned official source. No original SARA labels are repaired or relicensed. |
| ConditionalQA raw documents, references and labels | Dataset terms are separate from evaluator code. The project website's CC BY-SA 4.0 notice differs from the repository's BSD notice, as recorded in upstream issue 3. | Excluded. The code export does not resolve or override the dataset-license discrepancy. |
| `scripts/reproduce_results.py`, `scripts/check_audit_records.py`, study manifests and audit indexes | BAR-original code and annotations | Included under MIT, with source identities and evidence boundaries. |
| Saved model-response archives attached to `v0.1.0` | Responses generated for this study, with original model/configuration and input hashes retained | Included as experimental records. Original upstream prompts, documents, SARA labels, CQA labels and the eight external control files are not bundled. The archives do not relicense any source text a response quotes. |
| OpenExempt study numerical inputs and target calculations | BAR's amended-task records; upstream asset identity retained | Included for the 69-case numerical experiment, without native policy/source files or a replacement native answer key. |
| `evidence/tac-budget/` and other compact audit records | Constructed messages, recorded observations and BAR annotations | Included without upstream evaluator source, database dumps, login responses or credentials. Upstream code is identified by fixed revision and file hashes. |

The exact upstream revisions and official notice URLs are recorded below and
in each component manifest. Notice bytes were compared with the frozen local
copies and the same fixed official repository revisions on 2026-11-01.

- RuleArena: `SkyRiver-2000/RuleArena@59f60f6b4eb93a9b6d187ec781349d4f15618903`,
  `LICENSE`, SHA-256 `092b7bdd17849a625533c288b1bbb03a95bb5dfd9324f4aa4990222fa2bf950f`.
- ConditionalQA: `haitian-sun/ConditionalQA@77bd295952daf415548b3244db10880d3d55cfe0`,
  upstream filename `LISCENSE`, SHA-256
  `62a47f90ddb8fda1bbf1e731a5861d827c109a3570b86b371f9d927cbc75aa14`.
- LegalBench: `HazyResearch/legalbench@b46bf4ffae90524b2b72aaa30e7745fe9db64481`.
  The fixed tree has no root code-license file; the task README's notice is
  scoped to SARA data and is not used as permission to export source context.

Official sources only:

```text
https://raw.githubusercontent.com/SkyRiver-2000/RuleArena/59f60f6b4eb93a9b6d187ec781349d4f15618903/LICENSE
https://raw.githubusercontent.com/haitian-sun/ConditionalQA/77bd295952daf415548b3244db10880d3d55cfe0/LISCENSE
https://github.com/haitian-sun/ConditionalQA/issues/3
https://haitian-sun.github.io/conditionalqa/
https://github.com/HazyResearch/legalbench/tree/b46bf4ffae90524b2b72aaa30e7745fe9db64481
https://raw.githubusercontent.com/HazyResearch/legalbench/b46bf4ffae90524b2b72aaa30e7745fe9db64481/tasks/sara_numeric/README.md
```
