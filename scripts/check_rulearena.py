# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Yanru Xiao and Yifei Cai
"""Offline population and counterexample checks for the added RuleArena components."""
import ast
from collections import Counter
import copy
import csv
import io
import json
import os
from types import SimpleNamespace

import numpy as np
import pandas as pd
import bar
import rulearena
import airline_policy_check as policy


def require(condition, message):
    if not condition:
        raise ValueError(message)


def quiet(function, *args):
    import contextlib
    with contextlib.redirect_stdout(io.StringIO()):
        return function(*args)


def load(path):
    namespace = {"__name__": "bar_checked_module"}
    exec(compile(path.read_bytes(), str(path), "exec"), namespace)
    return namespace


def native_calculator(source):
    path = source / "airline/compute_answer.py"
    # Execute all native definitions, excluding only imports and top-level I/O.
    tree = ast.parse(path.read_text(encoding="utf-8"))
    nodes = [n for n in tree.body if isinstance(n, ast.FunctionDef)]
    namespace = {"np": np, "pd": pd, "List": list, "Dict": dict, "Any": object}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(path), "exec"), namespace)
    tables = [{direction: pd.read_csv(
        source / f"airline/fee_tables/bag_{position}/{direction}.csv", index_col=0)
        for direction in range(2)} for position in range(1, 5)]
    return namespace, tables


def native_scoring_nodes(path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    function = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "eval_query")
    loop = next(n for n in function.body if isinstance(n, ast.While))
    trial = next(n for n in loop.body if isinstance(n, ast.Try))
    # Delimit by semantic neighbors, not source line numbers that patches shift.
    begin = next(i for i, n in enumerate(trial.body)
                 if isinstance(n, ast.Assign) and ast.unparse(n).startswith("response = response.replace"))
    end = next(i for i, n in enumerate(trial.body)
               if isinstance(n, ast.Assign) and ast.unparse(n).startswith("rule_app_checklist, structured_response"))
    return trial.body[begin:end]


def score_branch(path, response, fee, helper=None):
    ns = {"response": response, "fee": fee, "acc": False, "pred": None}
    if helper:
        ns.update({k: helper[k] for k in ("parse_total", "score_total")})
    exec(compile(ast.Module(body=native_scoring_nodes(path), type_ignores=[]), str(path), "exec"), ns)
    return bool(ns["acc"]), ns["pred"]


def airline(roots, work):
    identifier = "rulearena-airline-objective"
    source = roots[(identifier, "code")]
    dataset = work / "airline-objective-data"
    quiet(bar.dataset, identifier, source, dataset)
    rows = [json.loads(s) for s in (dataset / "data.jsonl").read_text(encoding="utf-8").splitlines()]
    calculator, tables = native_calculator(source)
    policy_text = (source / "airline/reference_rules.txt").read_text(encoding="utf-8")
    policy_tables = policy.markdown_tables(policy_text)
    subsets = 0
    sensitive, listed, pe = [], [], []
    for row in rows:
        case = row["native_case"]
        require(all(sum(b["size"]) > 62 and b["weight"] > 50
                    for b in case["info"]["bag_list"][1:]), "Native checked-item shape")
        answer, _ = calculator["compute_answer"](**copy.deepcopy(case["info"]), check_base_tables=tables)
        independent = policy.allocation_spectrum(case["info"], policy_tables)
        require(answer == independent["minimum"] == row["original_reference"] == row["revised_reference"],
                f"Airline reference mismatch: {row['id']}")
        require(independent["maximum"] == row["allocation_maximum"]
                and independent["source_order_total"] == row["listed_order_reference"], "Allocation bounds")
        require(row["allocation_minimum"] == independent["minimum"]
                and row["reference_changed"] is False, "Unchanged minimum reference fields")
        require(row["allocation_sensitive"] == (independent["minimum"] != independent["maximum"]),
                "Allocation flag")
        if row["allocation_sensitive"]:
            sensitive.append(row["id"])
        if independent["source_order_total"] > independent["minimum"]:
            listed.append(row["id"])
        info = case["info"]
        reached_dash = any("dash" in policy.base_cell(
            policy_tables, i + 1, info["direction"], info["routine"], info["customer_class"])[1]
            for i in range(len(info["bag_list"]) - 1))
        require(reached_dash == row["pe_dash_case"], "PE flag")
        if reached_dash:
            pe.append(row["id"])
        subsets += independent["free_subsets_checked"]
        original, revised = row["original_messages"], row["messages"]
        objective = (bar.ROOT / "components" / identifier / "objective.txt").read_text(encoding="utf-8").strip()
        require(original[0] == revised[0], "System prompt changed")
        require(revised[1]["content"].replace("\n\n" + objective, "", 1) == original[1]["content"],
                "Amendment changed other input content")
    require((len(rows), len(sensitive), len(listed), len(pe), subsets) == (300, 94, 74, 4, 6145),
            "Airline population counts")
    require(not set(sensitive) & set(pe), "PE overlap")

    # Verify the actual distributed prompt patches and every native variant.
    prompt_source = roots[("rulearena-airline-prompt-errata", "code")]
    prepared = work / "airline-prompt-revised"
    quiet(bar.prepare, "rulearena-airline-prompt-errata", prompt_source, prepared)
    old = rulearena.literals((prompt_source / "airline/auto_test.py").read_text(encoding="utf-8"),
                            {"system_prompt", "prompt_template", "example"})
    new = rulearena.literals((prepared / "airline/auto_test.py").read_text(encoding="utf-8"),
                            {"system_prompt", "prompt_template", "example"})
    require(old["system_prompt"] == new["system_prompt"] and old["prompt_template"] == new["prompt_template"],
            "Erratum changed task/system templates")
    require("Item 2: $150" in new["example"] and "Item 3: $200" in new["example"], "Example attribution")
    require("= $750" in new["example"] and "$1,198." in new["example"], "Example totals changed")
    changed = Counter()
    bindings = []
    for textual in (False, True):
        name = "airline/reference_rules_textual.txt" if textual else "airline/reference_rules.txt"
        old_policy = (prompt_source / name).read_text(encoding="utf-8")
        new_policy = (prepared / name).read_text(encoding="utf-8") if textual else old_policy
        for one_shot in (False, True):
            for row in rows:
                rendered = []
                for literals, rules in ((old, old_policy), (new, new_policy)):
                    rendered.append(literals["prompt_template"].replace("$reference_rules", rules)
                                    .replace("$question_prompt", row["native_case"]["prompt"])
                                    .replace("$example_prompt", literals["example"] if one_shot else ""))
                differs = rendered[0] != rendered[1]
                if not textual and not one_shot:
                    require(row["original_messages"] == [
                        {"role": "system", "content": old["system_prompt"]},
                        {"role": "user", "content": rendered[0]}],
                        "Builder differs from independent native prompt assembly")
                require(differs == (textual or one_shot), "Unexpected changed prompt variant")
                changed[str((textual, one_shot))] += differs
                bindings.append({"id": row["id"], "textual": textual, "one_shot": one_shot,
                                 "before": bar.digest(rendered[0].encode()),
                                 "after": bar.digest(rendered[1].encode())})
    require(sum(changed.values()) == 900, "Prompt population")

    # Preserve all non-prompt AST, including native model and scoring functions.
    def non_example(path):
        return [ast.dump(n) for n in ast.parse(path.read_text(encoding="utf-8")).body
                if not (isinstance(n, ast.Assign) and
                        any(isinstance(t, ast.Name) and t.id == "example" for t in n.targets))]
    require(non_example(prompt_source / "airline/auto_test.py")
            == non_example(prepared / "airline/auto_test.py"), "Errata changed executable code")
    return {"cases": 300, "native_and_policy_minima_match": 300,
            "allocation_sensitive_ids": sensitive, "listed_order_above_minimum_ids": listed,
            "pe_dash_ids": pe, "enumerated_subsets": subsets,
            "changed_prompt_variants": dict(changed), "prompt_bindings": bindings,
            "reference_amounts_changed": 0, "model_calls": 0}


def scoring(roots, work):
    source = roots[("rulearena-airline-scoring", "code")]
    output = work / "airline-scorer-revised"
    quiet(bar.prepare, "rulearena-airline-scoring", source, output)
    original = source / "airline/auto_test.py"
    revised = output / "airline/auto_test.py"
    helper = load(output / "airline/bar_airline_scoring.py")
    # Removing the added import and normalizing only the scoring block must
    # recover the original AST exactly, including the reference/rule checker.
    old_tree, new_tree = ast.parse(original.read_text(encoding="utf-8")), ast.parse(revised.read_text(encoding="utf-8"))
    new_tree.body = [n for n in new_tree.body
                     if not (isinstance(n, ast.ImportFrom) and n.module == "bar_airline_scoring")]
    for tree in (old_tree, new_tree):
        fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "eval_query")
        trial = next(n for n in next(n for n in fn.body if isinstance(n, ast.While)).body
                     if isinstance(n, ast.Try))
        a = next(i for i, n in enumerate(trial.body) if ast.unparse(n).startswith("response = response.replace"))
        b = next(i for i, n in enumerate(trial.body) if ast.unparse(n).startswith("rule_app_checklist, structured_response"))
        trial.body[a:b] = [ast.Pass()]
        resume = next(n for n in tree.body if isinstance(n, ast.If)
                      and ast.unparse(n.test) == "args.start_idx >= 1")
        loop = resume.body[0]
        rule_loop = max(i for i, n in enumerate(loop.body) if isinstance(n, ast.For))
        loop.body[1:rule_loop] = [ast.Pass()]
    require(ast.dump(old_tree) == ast.dump(new_tree), "Scorer patch changed unrelated code")
    fixtures = [
        ("The total cost is $1,198.", 1198, True),
        ("The total cost is $1,198.00", 1198, True),
        ("The total cost is $1,198.00.\n", 1198, True),
        ("The total cost is $11,980 USD", 1198, False),
        ("The total cost is $1198.01.", 1198, False),
        ("The total cost is $1198.01.", "1198.01", True),
        ("The total cost is $0.00.", 0, True),
        ("The total cost is $0.01.", 0, False),
        ("**The total cost is $1,198.00.**", 1198, True),
        ("Reasoning: 44 + 1154.\nThe total cost is $1198.", 1198, True),
        ("The total cost is $-1198.", 1198, False),
        ("The total cost is $1,19,8.", 1198, False),
        ("The total cost is $1.198e3.", 1198, False),
        ("The total cost is $1198 or $999.", 1198, False),
        ("The total cost is $999. The total cost is $1198.", 1198, False),
        ("1198", 1198, False), ("The total cost is $NaN.", 1198, False),
        ("The total cost is $1198.0001.", 1198, False),
        ("The total cost is $1198. A different total is $999.", 1198, False),
        ("The total cost is $1198,50.", "1198.5", False),
        ("The total cost is calculated below. The total cost is $1,198.", 1198, False),
        ("The total cost is: $1,198.", 1198, False),
        ("The total cost is $ 1,198.", 1198, False),
        ('"The total cost is $1,198."', 1198, False),
        ("(The total cost is $1,198.)", 1198, False),
        ("The total cost is $1,198. Thank you.", 1198, False),
    ]
    checks = []
    for response, reference, expected in fixtures:
        before, old_pred = score_branch(original, response, reference)
        after, new_pred = score_branch(revised, response, reference, helper)
        require(after == expected == helper["score_total"](response, reference), "Scoring fixture: " + response)
        checks.append({"response": response, "reference": reference, "expected": expected,
                       "original_score": before, "revised_score": after,
                       "original_parsed": str(old_pred), "revised_parsed": str(new_pred)})
    require(checks[1]["original_score"] is False and checks[3]["original_score"] is True,
            "Native decimal/substr witnesses no longer reproduce")
    require(all(row["original_score"] and not row["revised_score"] for row in checks[-6:]),
            "Documented stricter format cases differ")
    resume_results = []
    native_resume = next(n for n in ast.parse(revised.read_text(encoding="utf-8")).body if isinstance(n, ast.If)
                         and ast.unparse(n.test) == "args.start_idx >= 1")
    resume_code = compile(ast.Module(body=[native_resume], type_ignores=[]),
                          "patched-native-log-replay", "exec")
    logs = work / "native-airline-logs"
    logs.mkdir()
    import contextlib
    for index, row in enumerate(checks):
        # Use the OLD parser result in the log, as in an existing pre-patch run.
        text = (row["response"] + "\n\nGPT Predicted: " + row["original_parsed"]
                + "\nRule Calculated: " + str(row["reference"]) + "\n\nCorrect: control\n")
        (logs / "0.log").write_text(text, encoding="utf-8")
        ns = {"args": SimpleNamespace(start_idx=1), "log_path": str(logs), "os": os,
              "total_acc": 0, "rule_applications": [], "score_saved_log": helper["score_saved_log"]}
        with contextlib.redirect_stdout(io.StringIO()):
            exec(resume_code, ns)
        require(ns["total_acc"] == int(row["expected"]), "Resume/live scoring disagreement")
        resume_results.append({"fixture": index, "expected": row["expected"],
                               "resumed_score": bool(ns["total_acc"])})
    references = [json.loads(s) for s in
                  (bar.ROOT / "components/rulearena-airline-objective/references.jsonl").read_text(encoding="utf-8").splitlines()]
    echoes = 0
    for row in references:
        fee = row["original_reference"]
        for value in (str(fee), f"{fee:,}", f"{fee:.2f}", f"{fee:,.2f}"):
            text = f"The total cost is ${value}."
            require(score_branch(revised, text, fee, helper)[0], "Native reference echo")
            echoes += 1
        require(not score_branch(revised, f"The total cost is ${fee + 1}.", fee, helper)[0],
                "Wrong amount accepted")
    return {"scope": "Unchanged native scoring branch plus installed helper; not a model-driven run",
            "constructed_cases": checks, "reference_amount_echoes": echoes,
            "wrong_amount_controls": 300, "native_log_replays": resume_results,
            "unrelated_ast_preserved": True, "model_calls": 0}


def nba(roots, work):
    source = roots[("rulearena-nba-location-errata", "code")]
    prepared, dataset = work / "nba-revised", work / "nba-data"
    quiet(bar.prepare, "rulearena-nba-location-errata", source, prepared)
    quiet(bar.dataset, "rulearena-nba-location-errata", source, dataset)
    rows = [json.loads(s) for s in (dataset / "data.jsonl").read_text(encoding="utf-8").splitlines()]
    differences = []
    for level in range(3):
        name = f"nba/annotated_problems/comp_{level}.json"
        old = json.loads((source / name).read_text(encoding="utf-8"))
        new = json.loads((prepared / name).read_text(encoding="utf-8")) if (prepared / name).exists() else old
        require(len(old) == len(new), "NBA count changed")
        for index, (a, b) in enumerate(zip(old, new)):
            altered = {k for k in a.keys() | b.keys() if a.get(k) != b.get(k)}
            identifier = f"nba/comp_{level}/{index}"
            if altered:
                differences.append((identifier, sorted(altered)))
            require(a["answer"] == b["answer"], "Binary verdict changed")
            row = next(r for r in rows if r["id"] == identifier)
            require(row["original_record"] == a and row["revised_record"] == b, "Dataset/patch mismatch")
    require(differences == [("nba/comp_1/62", ["problematic_team"]),
                            ("nba/comp_2/4", ["illegal_operation"])], "NBA patch scope")
    # Execute the native terminal target/substring comparison for unchanged
    # inputs with old and revised references; all generated strings are probes.
    source_tree = ast.parse((source / "nba/auto_test.py").read_text(encoding="utf-8"))
    fn = next(n for n in source_tree.body if isinstance(n, ast.FunctionDef) and n.name == "eval_query")
    trial = next(n for n in next(n for n in fn.body if isinstance(n, ast.While)).body
                 if isinstance(n, ast.Try))
    a = next(i for i, n in enumerate(trial.body) if ast.unparse(n).startswith("response = response.replace"))
    b = next(i for i, n in enumerate(trial.body) if isinstance(n, ast.Assign) and ast.unparse(n.targets[0]) == "acc")
    nodes = trial.body[a:b + 1]
    code = compile(ast.Module(body=nodes, type_ignores=[]), "native-nba-scoring", "exec")
    probes = []
    for row in rows:
        if not row["changed"]:
            continue
        revised = row["revised_record"]
        text = (f"Answer: True. Illegal Operation: {revised['illegal_operation']}. "
                f"Problematic Team: {revised['problematic_team']}")
        scores = []
        for case in (row["original_record"], revised):
            ns = {"response": text, "query_dict": case}
            exec(code, ns)
            scores.append(bool(ns["acc"]))
        require(scores == [False, True], "NBA native target control")
        probes.append({"id": row["id"], "response": text, "scores": scores})
    return {"records": len(rows), "changes": differences, "binary_changes": 0,
            "synthetic_native_score_probes": probes, "model_calls": 0}


def guards(roots, work):
    import shutil
    reports = []
    for identifier in ("rulearena-airline-prompt-errata", "rulearena-airline-scoring",
                       "rulearena-nba-location-errata", "rulearena-airline-objective"):
        source = roots[(identifier, "code")]
        bad = work / (identifier + "-bad")
        shutil.copytree(source, bad)
        spec = bar.read_json(bar.ROOT / "components" / identifier / "component.json")
        name = spec["patches"][0]["upstream_path"] if spec["patches"] else "airline/reference_rules.txt"
        (bad / name).write_bytes((bad / name).read_bytes() + b"\n")
        output = work / (identifier + "-reject")
        function = bar.dataset if identifier == "rulearena-airline-objective" else bar.prepare
        try:
            quiet(function, identifier, bad, output)
        except ValueError:
            require(not output.exists(), "Rejected source left published output")
        else:
            raise ValueError("Changed source was accepted")
        reports.append(identifier + ":source_hash")
    return reports


def check(roots, work):
    return {"airline": airline(roots, work), "airline_scoring": scoring(roots, work),
            "nba": nba(roots, work), "rejections": guards(roots, work)}
