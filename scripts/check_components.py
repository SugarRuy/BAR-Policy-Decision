#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Yanru Xiao and Yifei Cai
"""Offline scientific and packaging checks using separately obtained sources.

Use --fetch-sources DIR to obtain only the pinned files from official source
repositories. The check itself makes no network requests or model calls.
"""
import argparse
import ast
from collections import Counter
import contextlib
import copy
import csv
import hashlib
import importlib.util
import io
import json
import math
from pathlib import Path
import re
import shutil
import sys
import tempfile
from types import SimpleNamespace
import typing
import urllib.request

sys.dont_write_bytecode = True
import numpy as np
import pydantic
import pandas as pd
import bar

ROOT = Path(__file__).resolve().parents[1]
METRICS = ("EM", "EM_with_conditions", "F1", "F1_with_conditions")
GROUPS = ("total", "yesno", "extractive", "conditional")
TAX_FUNCTIONS = {
    "standard_deduction", "itemized_deduction", "tax_table", "calc_tax",
    "qualified_dividends_and_capital_gain_tax_worksheet", "credit_limit_worksheet",
    "earned_income_worksheet", "compute_child_and_dependent_credits",
    "compute_education_credits", "compute_answer",
}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    exec(compile(path.read_bytes(), str(path), "exec"), module.__dict__)
    return module


def quiet(function, *args):
    with contextlib.redirect_stdout(io.StringIO()):
        return function(*args)


def manifest(identifier):
    return bar._core.component_manifest(ROOT, identifier)


def snapshots(directory, fetch=False):
    """Build a source-root map and verify every downloaded/input file."""
    roots, pins = {}, {}
    for entry in bar.catalog():
        identifier = entry["id"]
        spec = manifest(identifier)
        for pin in spec["source_files"]:
            key = (identifier, pin["repository"])
            root = directory / f"{identifier}-{pin['repository']}"
            roots[key] = root
            path = bar.child(root, pin["path"])
            if fetch and not path.exists():
                path.parent.mkdir(parents=True, exist_ok=True)
                with urllib.request.urlopen(pin["url"], timeout=60) as response:
                    data = response.read()
                require(bar.digest(data) == pin["sha256"], f"Download hash mismatch: {pin['url']}")
                with path.open("xb") as stream:
                    stream.write(data)
            require(path.is_file() and sha(path) == pin["sha256"],
                    f"Pinned source mismatch/missing: {path}")
            pins[str(path.relative_to(directory))] = pin["sha256"]
    return roots, pins


def calculator(source, program):
    namespace = {"np": np, "Union": typing.Union}
    declarations = source / "tax/structured_forms.py"
    exec(compile(declarations.read_bytes(), str(declarations), "exec"), namespace)
    nodes = [node for node in ast.parse(program.read_text()).body
             if isinstance(node, ast.FunctionDef) and node.name in TAX_FUNCTIONS]
    require({n.name for n in nodes} == TAX_FUNCTIONS, "Tax function inventory")
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(program), "exec"), namespace)
    return namespace, nodes


def tax(source, work):
    destination = work / "tax-revised"
    # Preserve the published T1-only scientific controls. T2 is checked below
    # using its independently recomputed SE arithmetic and all downstream fields.
    quiet(lambda *args: bar.prepare(*args, release="0.2.0"), "rulearena-tax", source, destination)
    old, _ = calculator(source, source / "tax/micro_evaluation.py")
    new, nodes = calculator(source, destination / "tax/micro_evaluation.py")
    expected = bar.read_json(ROOT / "components/rulearena-tax/labels.json")["records"]
    pairs = [json.loads(line) for line in
             (ROOT / "components/rulearena-tax/reference_pairs.jsonl").read_text().splitlines()]
    require(pairs == expected, "Tax reference-pair export differs from the frozen labels")
    by_id = {r["case_id"]: r for r in expected}
    require(len(by_id) == len(expected) == 300, "Tax reference IDs")
    # Outside compute_answer, all source AST nodes must be unchanged.
    trees = [ast.parse(path.read_text()) for path in
             (source / "tax/micro_evaluation.py", destination / "tax/micro_evaluation.py")]
    other = [[ast.dump(n) for n in tree.body
              if not isinstance(n, ast.FunctionDef) or n.name != "compute_answer"] for tree in trees]
    require(other[0] == other[1], "Tax unrelated code or native grading changed")
    records, branches = [], Counter()
    for level in range(3):
        cases = bar.read_json(source / f"tax/synthesized_problems/comp_{level}.json")
        for index, case in enumerate(cases):
            identifier = f"tax/comp_{level}/{index}"
            a, before = old["compute_answer"](old["TaxPayer"](**copy.deepcopy(case["pydantic"])))
            b, after = new["compute_answer"](new["TaxPayer"](**copy.deepcopy(case["pydantic"])))
            delta = before.f1040_line_18 - before.computed_accumulated_credits
            line22 = delta if delta > 0 else 0
            independent = line22 + before.computed_other_taxes - before.total_payments
            require(math.isclose(b, independent, rel_tol=0, abs_tol=1e-9), identifier)
            require(after.computed_taxes_after_credits == line22, identifier)
            changed = {k for k, value in before.model_dump().items() if after.model_dump()[k] != value}
            require(changed <= {"computed_taxes_after_credits", "computed_total_tax",
                                "computed_amount_owed_or_overpaid"}, identifier)
            reference = by_id[identifier]
            require(a == reference["original_signed_answer"] and
                    b == reference["line22_repaired_signed_answer"], identifier)
            require((a != b) == reference["changed"], identifier)
            if a != b:
                require(not np.isclose(b, a), "Tax native grader unexpectedly accepts changed reference")
            branches["negative" if delta < 0 else "positive" if delta > 0 else "zero"] += 1
            records.append({"case_id": identifier, "original": float(a), "revised": float(b),
                            "changed": bool(a != b)})
    require(len(records) == 300 and sum(r["changed"] for r in records) == 27, "Tax replay count")
    assignments = [n for n in ast.walk(next(n for n in nodes if n.name == "compute_answer"))
                   if isinstance(n, ast.Assign) and any(isinstance(t, ast.Attribute)
                   and t.attr == "computed_taxes_after_credits" for t in n.targets)]
    require(len(assignments) == 1, "Tax assignment inventory")
    boundaries = []
    for line18, line21 in ((0, 0), (100, 100), (100, 100.01), (100, 99.99), (0, 1), (1, 0)):
        obj = SimpleNamespace(f1040_line_18=line18, computed_accumulated_credits=line21)
        exec(compile(ast.Module(body=assignments, type_ignores=[]), "<floor-control>", "exec"),
             {"tax_payer": obj})
        require(obj.computed_taxes_after_credits == (line18 - line21 if line18 > line21 else 0),
                "Tax floor boundary")
        boundaries.append([line18, line21, obj.computed_taxes_after_credits])
    dataset = work / "tax-data"
    quiet(lambda *args: bar.dataset(*args, release="0.2.0"), "rulearena-tax", source, dataset)
    rows = [json.loads(line) for line in (dataset / "data.jsonl").read_text().splitlines()]
    # Compare reconstructed inputs with a separately extracted native renderer.
    namespace = {"args": SimpleNamespace(distractor=False, textual=False)}
    for relative in ("tax/prompt.py", "tax/auto_test.py"):
        tree = ast.parse((source / relative).read_text())
        literals = []
        for node in tree.body:
            if isinstance(node, ast.Assign):
                try:
                    ast.literal_eval(node.value)
                    literals.append(node)
                except (ValueError, TypeError):
                    pass
        exec(compile(ast.Module(body=literals, type_ignores=[]), "<native-literals>", "exec"), namespace)
        if relative.endswith("auto_test.py"):
            renderer = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "build_prompt"]
            exec(compile(ast.Module(body=renderer, type_ignores=[]), "<native-renderer>", "exec"), namespace)
    for row in rows:
        case = bar.read_json(source / row["source_file"])[row["source_index"]]
        require(row["native_case"] == case, "Tax input changed")
        prompt = namespace["build_prompt"](copy.deepcopy(case["dict"])).replace("$example", "")
        require(row["messages"] == [
            {"role": "system", "content": namespace["system_prompt"]},
            {"role": "user", "content": prompt}], "Tax native prompt changed")
        require(row["remaining_dependencies"] == by_id[row["id"]]["other_unresolved_dependencies"],
                "Tax dependency flags changed")
    require(len(rows) == 300 and len({r["id"] for r in rows}) == 300, "Tax dataset coverage")
    import check_tax_t2
    t2 = quiet(check_tax_t2.check, source)
    return {"replayed": 300, "changed": 27, "unchanged": 273, "branches": dict(branches),
            "t1_t2_revision": t2["summary"],
            "boundary_controls": boundaries, "native_inputs_preserved": 300,
            "native_grading_ast_unchanged": True, "changed_references_rejected_by_native_grader": 27,
            "dataset_sha256": sha(dataset / "data.jsonl"), "records": records}


def sara(source, data, work):
    destination = work / "sara-revised"
    quiet(bar.prepare, "legalbench-sara-numeric", source, destination)
    module = load(destination / "evaluation.py", "bar_numeric")
    new = module.evaluate_sara_numeric_acc
    namespace = {"re": re, "np": np, "List": typing.List}
    nodes = [n for n in ast.parse((source / "evaluation.py").read_text()).body
             if isinstance(n, ast.FunctionDef) and n.name == "evaluate_sara_numeric_acc"]
    require(len(nodes) == 1, "SARA native function inventory")
    exec(compile(ast.Module(body=nodes, type_ignores=[]), "<native-sara>", "exec"), namespace)
    old = namespace["evaluate_sara_numeric_acc"]
    echoes, all_answers = {}, []
    for split, count in (("train", 4), ("test", 96)):
        with (data / f"data/sara_numeric/{split}.tsv").open() as stream:
            rows = list(csv.DictReader(stream, delimiter="\t"))
        require(len(rows) == count and len({r["case id"] for r in rows}) == count, "SARA row IDs")
        answers = [r["answer"] for r in rows]
        require(new(answers, answers) == 1, "SARA batch echo")
        require(all(new([a], [a]) == 1 for a in answers), "SARA singleton echoes")
        echoes[split] = {
            "count": count, "original_accepts": sum(int(old([a], [a])) for a in answers),
            "revised_accepts": count, "case_ids": [r["case id"] for r in rows],
        }
        all_answers.extend(answers)
    controls = [
        ("$1,234.00", "$1234", 1), ("-$1,234.00", "$1234", 0),
        ("$12.50", "$1250", 0), ("$1250", "$1250", 1),
        ("0", "$0", 1), ("$0.00", "$0", 1), ("no answer", "$0", 0),
        ("", "$0", 0), ("0.01", "$0", 0), ("-0.01", "$0", 0),
        ("-$100.00", "-100", 1),
    ]
    for prediction, reference, expected in controls:
        require(new([prediction], [reference]) == expected, f"SARA format: {prediction!r}")
    tolerance = []
    for reference in (1, 10, 100, 1234, 100000, -100):
        for ratio in (0, .89999, .9, .90001, 1, 1.09999, 1.1, 1.10001, 2):
            text = format((reference + .1) * ratio, ".12f")
            expected = int(abs(float(text) / (reference + .1) - 1) < .1)
            require(new([text], [str(reference)]) == expected, "SARA native nonzero tolerance")
            tolerance.append({"prediction": text, "reference": str(reference), "expected": expected})
    for predictions, answers in (([], []), ([], ["$1"]), (["1", "2"], ["$1"])):
        rejects(lambda: new(predictions, answers), "SARA empty/mismatched population")
    # The public fixture contains synthetic amounts and diagnostic scores only.
    fixture = bar.read_json(ROOT / "components/legalbench-sara-numeric/conformance.json")
    require(fixture["frozen_corrected_scorer_sha256"] ==
            manifest("legalbench-sara-numeric")["frozen_corrected_scorer_sha256"], "SARA oracle binding")
    for vector in fixture["vectors"]:
        require(float(new(vector["predictions"], vector["references"])) == vector["score"],
                "BAR implementation differs from frozen corrected scorer")
    for split in ("train", "test"):
        require(echoes[split] == fixture["label_echo_diagnostic"][split], "Frozen SARA echo mismatch")
    # Exercise the actual adapter with the real pinned module, not a mock.
    native = load(source / "evaluation.py", "native_legalbench")
    adapted = module.load_upstream_evaluator(source / "evaluation.py")
    require(adapted.evaluate("sara_numeric", all_answers, all_answers) == 1, "SARA native dispatcher")
    require(isinstance(adapted.evaluate_sara_numeric_acc(all_answers, all_answers), np.float64),
            "SARA return type changed")
    unchanged = []
    for name, value in native.__dict__.items():
        if callable(value) and getattr(value, "__module__", None) == native.__name__ and name != "evaluate_sara_numeric_acc":
            require(value.__code__.co_code == getattr(adapted, name).__code__.co_code,
                    f"Non-SARA API changed: {name}")
            unchanged.append(name)
    require(unchanged and adapted.normalize("The TAX amount", False) ==
            native.normalize("The TAX amount", False), "Non-SARA normalization changed")
    return {"label_echo_not_model_accuracy": echoes, "performance_scope": "96 test rows",
            "format_and_zero_controls": len(controls), "native_tolerance_checks": len(tolerance),
            "frozen_corrected_scorer_conformance_vectors": len(fixture["vectors"]),
            "other_native_functions_unchanged": unchanged, "native_dispatcher_preserved": True,
            "labels_changed": False}


def cqa(source, work):
    destination = work / "cqa-revised"
    quiet(bar.prepare, "conditionalqa-scoring", source, destination)
    original = source / "evaluate.py"
    repaired = destination / "evaluate.py"
    old, new = load(original, "cqa_native"), load(repaired, "cqa_bar")
    other = [{n.name: ast.dump(n) for n in ast.parse(p.read_text()).body
              if isinstance(n, ast.FunctionDef) and n.name != "evaluate"}
             for p in (original, repaired)]
    require(other[0] == other[1], "CQA per-item scoring changed")
    references = bar.read_json(source / "v1_0/dev.json")
    require(len(references) == len({r["id"] for r in references}) == 285, "CQA population")
    predictions = [{"id": r["id"], "answers": copy.deepcopy(r["answers"])} for r in references]
    prediction_file, reference_file = work / "predictions.json", work / "references.json"

    def evaluate(module, rows, refs=references):
        prediction_file.write_text(json.dumps(rows))
        reference_file.write_text(json.dumps(refs))
        return quiet(module.evaluate, str(prediction_file), str(reference_file))

    def independent(rows, refs=references):
        present = {r["id"]: r["answers"] for r in rows}
        groups = {g: [] for g in GROUPS}
        for ref in refs:
            answer = ref["answers"]
            values = (old.compute_metrics(copy.deepcopy(present[ref["id"]]), copy.deepcopy(answer))
                      if ref["id"] in present else (0., 0., 0., 0.))
            groups["total"].append(values)
            if answer:
                groups["yesno" if any(a[0] in ("yes", "no") for a in answer)
                       else "extractive"].append(values)
            if any(a[1] for a in answer):
                groups["conditional"].append(values)
        return {g: {name: sum(v[i] for v in items) / len(items) if items else None
                    for i, name in enumerate(METRICS)} for g, items in groups.items()}

    require(evaluate(old, predictions) == evaluate(new, predictions) == independent(predictions),
            "CQA complete echo changed")
    omissions = []
    for i, record in enumerate(references):
        reduced = predictions[:i] + predictions[i + 1:]
        result = evaluate(new, reduced)
        require(result == independent(reduced), "CQA omission: category/all-four metric mismatch")
        require(all(value == 284 / 285 for value in result["total"].values()),
                "CQA total denominator")
        omissions.append(record["id"])
    expected = (0, 0, .5, 1 / 3)
    for module in (old, new):
        require(tuple(module.compute_metrics([["red blue", ["c1"]]],
                      [["red green", ["c1", "c2"]]])) == expected, "CQA fractional F1")
    mixed = copy.deepcopy(predictions)
    for i, row in enumerate(mixed):
        if i % 5 == 0:
            row["answers"] = [["deliberately unrelated answer", []]]
        elif i % 7 == 0:
            row["answers"] = []
    require(evaluate(old, mixed) == evaluate(new, mixed) == independent(mixed),
            "CQA complete mixed scores")
    mixed_omitted = mixed[:5] + mixed[6:]
    require(evaluate(new, mixed_omitted) == independent(mixed_omitted),
            "CQA mixed omission all-four metrics")
    require(evaluate(new, []) == independent([]), "CQA empty submissions")
    unanswerable = next(r for r in references if not r["answers"])
    empty_answer = [{"id": unanswerable["id"], "answers": []}]
    valid_empty = evaluate(new, empty_answer, [unanswerable])
    absent = evaluate(new, [], [unanswerable])
    require(all(v == 1 for v in valid_empty["total"].values()) and
            all(v == 0 for v in absent["total"].values()), "CQA [] versus absent")
    empty_categories = []
    subsets = [
        [], [unanswerable],
        [r for r in references if r["answers"] and all(a[0] in ("yes", "no") for a in r["answers"])],
        [r for r in references if r["answers"] and not any(a[0] in ("yes", "no") for a in r["answers"])
         and not any(a[1] for a in r["answers"])],
    ]
    for subset in subsets:
        preds = [{"id": r["id"], "answers": copy.deepcopy(r["answers"])} for r in subset]
        result = evaluate(new, preds, subset)
        require(result == independent(preds, subset), "CQA empty-category convention")
        json.dumps(result, allow_nan=False)  # Undefined categories must be JSON null.
        empty_categories.append({"reference_count": len(subset), "metrics": result})
    return {"reference_count": 285, "single_id_omission_checks": 285, "omitted_ids": omissions,
            "all_four_metrics_all_categories_exact": True, "complete_echo_unchanged": True,
            "complete_mixed_scores_unchanged": True, "partial_answer_condition_f1": list(expected),
            "per_item_functions_ast_identical": True, "valid_empty_answer_distinguished": True,
            "empty_category_controls": empty_categories, "labels_changed": False}


def rejects(function, label):
    try:
        quiet(function)
    except (ValueError, OSError):
        return
    raise ValueError(f"Expected rejection: {label}")


def hash_rejections(roots, work):
    checked = []
    for identifier in ("rulearena-tax", "legalbench-sara-numeric", "conditionalqa-scoring"):
        spec = manifest(identifier)
        operation = spec.get("replacement") or spec["patches"][0]
        name = operation["upstream_path"]
        bad = work / ("bad-" + identifier)
        target = bad / name
        target.parent.mkdir(parents=True)
        target.write_bytes((roots[(identifier, "code")] / name).read_bytes() + b"\n# mutation\n")
        output = work / ("rejected-" + identifier)
        rejects(lambda: bar.prepare(identifier, bad, output), "before hash")
        require(not output.exists(), "Rejected prepare left output")
        checked.append(identifier + ":before_hash")
        revised = work / {"rulearena-tax": "tax-revised", "legalbench-sara-numeric": "sara-revised",
                          "conditionalqa-scoring": "cqa-revised"}[identifier]
        rejects(lambda: bar.prepare(identifier, revised, output), "already revised")
        checked.append(identifier + ":already_revised")
    # Deliberately make self-consistent manifest/inventory copies with wrong output
    # hashes, so this checks prepare's after guard rather than inventory alone.
    for identifier in ("rulearena-tax", "legalbench-sara-numeric", "conditionalqa-scoring"):
        package = work / ("bad-after-" + identifier)
        shutil.copytree(ROOT / "components", package / "components", ignore=shutil.ignore_patterns("__pycache__"))
        for relative in [name for name in bar.read_json(ROOT / "inventory.json")["files"]
                         if not name.startswith("components/")] + ["inventory.json"]:
            dst = package / relative
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / relative, dst)
        selected = next(c for c in bar._core.catalog(package) if c["id"] == identifier)
        path = package / selected["manifest"]
        spec = bar.read_json(path)
        (spec.get("replacement") or spec["patches"][0])["after_sha256"] = "0" * 64
        path.write_text(json.dumps(spec))
        inventory = bar.read_json(package / "inventory.json")
        inventory["files"][str(path.relative_to(package))] = {"sha256": sha(path), "bytes": path.stat().st_size}
        (package / "inventory.json").write_text(json.dumps(inventory))
        runner = load(package / "scripts/bar.py", "bad_after")
        output = work / ("reject-after-" + identifier)
        rejects(lambda: runner.prepare(identifier, roots[(identifier, "code")], output), "after hash")
        require(not output.exists(), "Wrong after hash published output")
        checked.append(identifier + ":after_hash")
    existing = work / "existing-output"
    existing.mkdir()
    (existing / "sentinel").write_text("preserve")
    rejects(lambda: bar.prepare("rulearena-tax", roots[("rulearena-tax", "code")], existing),
            "existing output")
    require((existing / "sentinel").read_text() == "preserve", "Existing output changed")
    for path in ("../outside", "/absolute", "dir\\outside"):
        rejects(lambda: bar.child(work, path), "unsafe path")
    # Any altered source input must fail before the native-input dataset is built.
    bad_tax = work / "tax-bad-input"
    shutil.copytree(roots[("rulearena-tax", "code")], bad_tax)
    path = bad_tax / "tax/prompt.py"
    path.write_bytes(path.read_bytes() + b"\n# mutation\n")
    output = work / "rejected-dataset"
    rejects(lambda: bar.dataset("rulearena-tax", bad_tax, output), "input hash")
    require(not output.exists(), "Rejected dataset left output")
    checked += ["existing_output", "unsafe_paths", "tax_native_input_hash"]
    return checked


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sources", type=Path, required=True,
                        help="Pinned snapshot root; see docs/COMPONENTS.md for layout")
    parser.add_argument("--fetch-sources", action="store_true",
                        help="Download missing, pinned files directly from official repositories")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    require(not args.output.exists(), "Preserve existing results; choose a new output file")
    quiet(bar.verify)
    sources = args.sources.resolve()
    roots, pins = snapshots(sources, args.fetch_sources)
    with tempfile.TemporaryDirectory(prefix="bar-components-check-") as tmp:
        work = Path(tmp)
        results = {
            "rulearena_tax": tax(roots[("rulearena-tax", "code")], work),
            "legalbench_sara_numeric": sara(roots[("legalbench-sara-numeric", "code")],
                                          roots[("legalbench-sara-numeric", "data")], work),
            "conditionalqa": cqa(roots[("conditionalqa-scoring", "code")], work),
        }
        import check_rulearena
        results["added_rulearena"] = check_rulearena.check(roots, work)
        results["rejection_checks"] = hash_rejections(roots, work)
    require(pins == {name: sha(sources / name) for name in pins}, "Upstream inputs changed")
    quiet(bar.verify)
    results.update({
        "source_preservation": {"checked_files": len(pins), "all_unchanged": True},
        "source_bindings": pins, "checker_sha256": sha(Path(__file__)),
        "component_inventory_sha256": sha(ROOT / "inventory.json"),
        "script_sha256": {str(p.relative_to(ROOT)): sha(p) for p in
                          sorted((ROOT / "scripts").glob("*.py"))},
        "model_calls": 0,
        "environment": {"python": sys.version.split()[0], "numpy": np.__version__,
                        "pydantic": pydantic.__version__, "pandas": pd.__version__},
    })
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x") as stream:
        json.dump(results, stream, indent=2, allow_nan=False)
        stream.write("\n")
    print(json.dumps({"status": "passed", "components": len(bar.catalog()),
                      "checked_source_files": len(pins), "model_calls": 0,
                      "output": str(args.output)}, indent=2))


if __name__ == "__main__":
    main()
