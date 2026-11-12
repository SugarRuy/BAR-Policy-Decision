#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Yanru Xiao and Yifei Cai
"""Replay the Tax T1/T2 revision offline using pinned, user-supplied sources.

Requires NumPy and Pydantic for the upstream calculator. No model client,
experiment entrypoint, network request or upstream write is used.
"""
import argparse
import ast
import copy
from decimal import Decimal
import json
import math
from pathlib import Path
import sys
from types import SimpleNamespace
from typing import Union

ROOT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
if (ROOT / "src/bar_policy/_core.py").is_file():
    import bar
else:
    # The installed wheel stores scripts alongside bundled assets and stores
    # Python modules in the package itself.
    from bar_policy import _assets, _core
    ROOT = _assets.root()
    bar = SimpleNamespace(_core=_core, digest=_core.digest, read_json=_core.read_json,
                          verify=_assets.verify)
REVISION = "components/rulearena-tax/revisions/t1-t2-1"
T2 = "T2_unstated_self_employment_threshold"
FUNCTIONS = {
    "standard_deduction", "itemized_deduction", "tax_table", "calc_tax",
    "qualified_dividends_and_capital_gain_tax_worksheet", "credit_limit_worksheet",
    "earned_income_worksheet", "compute_child_and_dependent_credits",
    "compute_education_credits", "compute_answer",
}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def calculator(declarations, program):
    import numpy as np
    namespace = {"np": np, "Union": Union}
    exec(compile(declarations, "<pinned-tax-declarations>", "exec"), namespace)
    nodes = [n for n in ast.parse(program).body
             if isinstance(n, ast.FunctionDef) and n.name in FUNCTIONS]
    require({n.name for n in nodes} == FUNCTIONS, "Tax function inventory changed")
    exec(compile(ast.Module(body=nodes, type_ignores=[]), "<pinned-tax-calculator>", "exec"),
         namespace)
    return namespace


def replay(namespace, record):
    amount, trace = namespace["compute_answer"](
        namespace["TaxPayer"](**copy.deepcopy(record["pydantic"])))
    return float(amount), trace


def expected_program(t1):
    """Only remove the threshold branch; retain every statement in its else."""
    tree = ast.parse(t1)
    compute = next(n for n in tree.body
                   if isinstance(n, ast.FunctionDef) and n.name == "compute_answer")
    matches = []
    for parent in ast.walk(compute):
        for _, value in ast.iter_fields(parent):
            if isinstance(value, list):
                for i, node in enumerate(value):
                    if (isinstance(node, ast.If)
                            and ast.unparse(node.test) == "tax_payer.sche_se_line_4c < 400"):
                        matches.append((value, i, node))
    require(len(matches) == 1, "Expected exactly one T2 branch")
    body, index, node = matches[0]
    body[index:index + 1] = node.orelse
    return ast.dump(tree, include_attributes=False)


def independent_se(record):
    """Decimal arithmetic from model-visible case facts and supplied SE formulas."""
    data = record["dict"]["data"]
    if not record["dict"]["self_employed"]:
        return Decimal(0), Decimal(0), Decimal(0)
    d = lambda key: Decimal(str(data[key]))
    profit = (d("gross_receipts") - d("returns_and_allowances") - d("cost_of_goods_sold")
              + d("other_inc_sched_c") - d("total_expenses") - d("expenses_of_home"))
    adjusted = profit * Decimal("0.9235") if profit > 0 else profit
    wages = d("total_social_security_wages")
    social = (Decimal(0) if wages >= 160200 else
              min(adjusted, Decimal(160200) - wages) * Decimal("0.124"))
    tax = social + adjusted * Decimal("0.029")
    return adjusted, tax, tax * Decimal("0.5")


def check(source):
    bar.verify()
    legacy = bar.read_json(ROOT / "components/rulearena-tax/component.json")
    current = bar.read_json(ROOT / REVISION / "component.json")
    sources = bar._core.pinned_sources(source, current["source_files"])
    program = sources["tax/micro_evaluation.py"]
    programs = [program]
    for manifest in (legacy, current):
        patch = manifest["patches"][0]
        require(bar.digest(program) == patch["before_sha256"], "Calculator source mismatch")
        revised = bar._core.apply_patch_bytes(program, (ROOT / patch["patch"]).read_bytes(),
                                              patch["upstream_path"])
        require(bar.digest(revised) == patch["after_sha256"], "Calculator patch output mismatch")
        programs.append(revised)
    require(expected_program(programs[1]) ==
            ast.dump(ast.parse(programs[2]), include_attributes=False),
            "Changes beyond the T2 branch in the T1 calculator")
    spaces = [calculator(sources["tax/structured_forms.py"], p) for p in programs]
    old = bar.read_json(ROOT / legacy["dataset"]["reference_file"])["records"]
    new = bar.read_json(ROOT / current["dataset"]["reference_file"])["records"]
    pairs = [json.loads(s) for s in (ROOT / current["dataset"]["reference_pairs"]).read_text().splitlines()]
    require(new == pairs and len(old) == len(new) == 300, "Reference payload population")
    corrections = bar.read_json(ROOT / REVISION / "corrections.json")
    require(corrections == {
        "revision": "t1-t2-1", "comparison_revision": "line22-only-2",
        "changed_count": 21, "records": [r for r in new if r["changed_from_line22"]],
    }, "Corrections do not match the complete T2 change set")
    old_by_id = {r["case_id"]: r for r in old}
    native = {name: json.loads(data) for name, data in sources.items() if name.endswith(".json")}
    actual_rows, _ = bar._core.tax_rows(ROOT, current["dataset"], sources)
    old_rows, _ = bar._core.tax_rows(ROOT, legacy["dataset"], sources)
    require([r["messages"] for r in actual_rows] == [r["messages"] for r in old_rows],
            "Model-visible inputs changed")
    comparisons, fields, changed_ids, marked = [], [], set(), set()
    negative_other_taxes, negative_total_tax = [], []
    for r in new:
        identifier = r["case_id"]
        previous = old_by_id[identifier]
        record = native[r["source_file"]][r["source_index"]]
        values = [replay(ns, record) for ns in spaces]
        (original, _), (t1, before), (revised, after) = values
        require(original == previous["original_signed_answer"] == r["original_signed_answer"],
                f"Original replay: {identifier}")
        require(t1 == previous["line22_repaired_signed_answer"] == r["line22_repaired_signed_answer"],
                f"T1 replay: {identifier}")
        require(revised == r["policy_repaired_signed_answer"], f"T1/T2 replay: {identifier}")
        is_marked = T2 in previous["other_unresolved_dependencies"]
        changed = revised != t1
        if is_marked:
            marked.add(identifier)
        if changed:
            changed_ids.add(identifier)
        if after.computed_other_taxes < 0:
            negative_other_taxes.append(identifier)
        if after.computed_total_tax < 0:
            negative_total_tax.append(identifier)
        require(changed == r["changed_from_line22"] and (original != revised) == r["changed"],
                f"Change flags: {identifier}")
        require(r["other_unresolved_dependencies"] ==
                [d for d in previous["other_unresolved_dependencies"] if d != T2],
                f"Remaining dependencies: {identifier}")
        require(r["resolved_dependencies"] == ([T2] if is_marked else []),
                f"Resolved dependencies: {identifier}")
        adjusted, tax, deduction = independent_se(record)
        for got, expected in ((after.self_employment_tax, tax),
                              (after.self_employment_deductible, deduction)):
            require(math.isclose(got, float(expected), rel_tol=1e-12, abs_tol=1e-9),
                    f"Independent Schedule SE arithmetic: {identifier}")
        require(after.computed_taxes_after_credits ==
                max(0, after.f1040_line_18 - after.computed_accumulated_credits),
                f"T1 zero floor: {identifier}")
        require(after.total_other_payments_and_refundable_credits ==
                after.earned_income_credit + after.computed_additional_child_tax_credit
                + after.computed_american_opportunity_credit + 0,
                f"T3 zero default: {identifier}")
        diff = {k: {"before": before.model_dump().get(k), "after": v}
                for k, v in after.model_dump().items() if v != before.model_dump().get(k)}
        if not is_marked:
            require(not diff, f"Unmarked intermediate changed: {identifier}")
        comparisons.append({
            "case_id": identifier, "case_sha256": r["case_sha256"],
            "original": float(original), "line22_only": float(t1), "t1_t2": float(revised),
            "delta_from_line22": float(revised - t1), "changed_from_line22": changed,
            "changed_from_original": original != revised, "t2_marked": is_marked,
            "adjusted_self_employment_earnings": float(adjusted),
            "self_employment_tax": float(after.self_employment_tax),
            "self_employment_deduction": float(after.self_employment_deductible),
        })
        if changed:
            fields.append({"case_id": identifier, "changed_fields": diff})
    require(changed_ids == marked and len(marked) == 21, "T2 affected population differs")
    # Execute the exact revised SE block at relevant sign/threshold/wage boundaries.
    compute = next(n for n in ast.parse(programs[2]).body
                   if isinstance(n, ast.FunctionDef) and n.name == "compute_answer")
    block = next(n for n in compute.body
                 if isinstance(n, ast.If) and ast.unparse(n.test) == "tax_payer.self_employed")
    controls = []
    for profit in (-100, 0, 100, 399 / .9235, 400 / .9235, 401 / .9235):
        for wages in (160199, 160200, 160201):
            obj = SimpleNamespace(self_employed=True, gross_receipts=profit,
                                  returns_and_allowances=0, cost_of_goods_sold=0,
                                  other_inc_sched_c=0, total_expenses=0, expenses_of_home=0,
                                  total_social_security_wages=wages)
            exec(compile(ast.Module(body=[block], type_ignores=[]), "<SE-boundary>", "exec"),
                 {"tax_payer": obj})
            record = {"dict": {"self_employed": True, "data": vars(obj)}}
            _, expected, _ = independent_se(record)
            require(math.isclose(obj.self_employment_tax, float(expected),
                                 rel_tol=1e-12, abs_tol=1e-9), "Schedule SE boundary")
            controls.append({"net_profit": profit, "social_security_wages": wages,
                             "self_employment_tax": obj.self_employment_tax})
    return {
        "summary": {
            "revision": "t1-t2-1", "records": 300, "original_exact_replay": 300,
            "line22_exact_replay": 300, "revised_exact_replay": 300,
            "changed_from_line22": len(changed_ids), "unchanged_from_line22": 279,
            "changed_from_original": sum(r["changed_from_original"] for r in comparisons),
            "t1_t2_overlap": sum(old_by_id[i]["changed"] for i in changed_ids),
            "negative_earnings_affected": sum(r["t2_marked"] and r["adjusted_self_employment_earnings"] < 0 for r in comparisons),
            "positive_earnings_below_400_affected": sum(r["t2_marked"] and 0 < r["adjusted_self_employment_earnings"] < 400 for r in comparisons),
            "negative_self_employment_tax": sum(r["self_employment_tax"] < 0 for r in comparisons),
            "negative_other_taxes": len(negative_other_taxes),
            "negative_total_tax": len(negative_total_tax),
            "owed_to_refund_from_line22": sum(r["line22_only"] > 0 and r["t1_t2"] < 0 for r in comparisons),
            "native_inputs_unchanged": 300, "unmarked_intermediates_unchanged": 279,
            "changed_ids_equal_t2_flags": True, "only_t2_branch_removed_from_t1": True,
            "remaining_dependency": "T3_schedule3_line15_default_zero",
            "model_calls": 0,
        },
        "source_pins": {name: bar.digest(data) for name, data in sources.items()},
        "boundary_controls": controls,
        "negative_other_tax_case_ids": negative_other_taxes,
        "negative_total_tax_case_ids": negative_total_tax,
        "labels": comparisons, "fields": fields,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    bar._core.check_new_output(ROOT, args.source.resolve(), args.output)
    result = check(args.source)
    # Check shipped evidence against a fresh replay, not just its own checksum.
    for name, key in (("label_differences.jsonl", "labels"), ("field_differences.jsonl", "fields")):
        stored = [json.loads(s) for s in (ROOT / REVISION / name).read_text().splitlines()]
        require(stored == result[key], f"Stored {name} differs from replay")
    require(bar.read_json(ROOT / REVISION / "validation.json") ==
            {k: v for k, v in result.items() if k not in ("labels", "fields")},
            "Stored validation differs from replay")
    args.output.mkdir()
    (args.output / "validation.json").write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")
    print(json.dumps(result["summary"], indent=2))


if __name__ == "__main__":
    main()
