# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Yanru Xiao and Yifei Cai
"""Checks against user-supplied pinned upstream sources and frozen oracles.

Independent oracles: message hashes frozen in the v0.2.0 reference payloads,
model-visible input hashes in the Tax study archive, golden outputs of the
pre-API CLI, files read directly from the upstream checkout, and per-item
native ConditionalQA functions aggregated by the test itself.
"""
import ast
from decimal import Decimal
import json
import math
from pathlib import Path
import shutil
import tarfile
import tempfile
import unittest

import bar_policy as bp
from bar_policy import _core

from _support import canonical, env_path, jsonl, require, sha256, tax_study


def golden(name):
    results = env_path("BAR_TEST_BASELINE_RESULTS")
    if results is None or not (results / name).exists():
        raise unittest.SkipTest(f"baseline result {name} not available")
    return results / name


class _Cached:
    _cache = {}

    @classmethod
    def dataset(cls, *args, **kwargs):
        key = (args, tuple(sorted(kwargs.items())))
        if key not in cls._cache:
            cls._cache[key] = bp.load_dataset(*args, source=require("BAR_TEST_RULEARENA"), **kwargs)
        return cls._cache[key]


def check_segments(test, example):
    messages = example.messages
    test.assertEqual([m["role"] for m in messages], ["system", "user"])
    for index, message in enumerate(messages):
        joined = "".join(s.text for s in example.segments if s.message_index == index)
        test.assertEqual(joined, message["content"])
    test.assertEqual(set(example.model_input()), {"messages"})
    test.assertTrue(example.question)


class Tax(unittest.TestCase):
    def setUp(self):
        self.source = require("BAR_TEST_RULEARENA")
        self.revised = _Cached.dataset("rulearena-tax", release="0.2.0")
        self.original = _Cached.dataset("rulearena-tax", variant="original", release="0.2.0")

    def test_population_references_and_segments(self):
        labels = bp.load_references("rulearena-tax", release="0.2.0")
        self.assertEqual(len(self.revised), 300)
        self.assertEqual(list(self.revised.ids), [r["case_id"] for r in labels])
        native = {f"tax/synthesized_problems/comp_{i}.json":
                  json.loads((self.source / f"tax/synthesized_problems/comp_{i}.json").read_text())
                  for i in range(3)}
        auto_test = (self.source / "tax/auto_test.py").read_text()
        for example, original, label in zip(self.revised, self.original, labels):
            self.assertEqual(example.reference, label["line22_repaired_signed_answer"])
            self.assertEqual(original.reference, label["original_signed_answer"])
            self.assertEqual(example.references["changed"], label["changed"])
            self.assertEqual(example.messages, original.messages)
            self.assertEqual(example.metadata["remaining_dependencies"],
                             label["other_unresolved_dependencies"])
            record = native[label["source_file"]][label["source_index"]]
            self.assertEqual(example.source_record, record)
            self.assertEqual(sha256(json.dumps(record, sort_keys=True).encode()), label["case_sha256"])
            check_segments(self, example)
            self.assertEqual(len(example.policy), 1)
            self.assertEqual(example.policy, example.case)
            self.assertEqual(example.policy[0].roles, ("policy", "case"))
            self.assertIn(f"Name: {record['dict']['name']}", example.policy[0].text)
            self.assertEqual(example.amendments, ())
            for segment in example.instructions[1:]:
                self.assertIn(segment.text, auto_test)
        self.assertEqual(sum(e.references["changed"] for e in self.revised), 27)
        info = self.revised.info
        self.assertEqual(info["changed_references"], 27)
        self.assertTrue(info["not_complete_ground_truth_certification"])
        self.assertTrue(info["scorer"]["is_repair"])
        self.assertEqual(info["components"][0]["revision"], "line22-only-2")

    def test_frozen_study_input_hashes(self):
        with tarfile.open(tax_study()) as archive:
            inputs = json.load(archive.extractfile("inputs.json"))
        self.assertEqual(set(inputs), set(self.revised.ids))
        for example in self.revised:
            self.assertEqual(sha256(example.messages[1]["content"].encode()),
                             inputs[example.id]["user_text_sha256"])
            self.assertEqual(example.source["case_sha256"], inputs[example.id]["source_record_sha256"])

    def test_baseline_cli_rows(self):
        rows = jsonl(golden("rulearena-tax/data.jsonl"))
        self.assertEqual(len(rows), 300)
        for row, example in zip(rows, self.revised):
            self.assertEqual(row["id"], example.id)
            self.assertEqual(row["messages"], example.messages)
            self.assertEqual(row["revised_reference"], example.reference)
            self.assertEqual(row["original_reference"], self.original[example.id].reference)
            self.assertEqual(row["native_case"], example.source_record)

    def test_batch_scoring_full_denominator(self):
        import_np = None
        try:
            import numpy as import_np
        except ImportError:
            pass
        echo = {e.id: (f"The total tax {'owed' if e.reference >= 0 else 'overpaid'} is "
                       f"${abs(e.reference):,.2f}.") for e in self.revised}
        result = self.revised.score(echo)
        self.assertEqual(result.denominator, 300)
        self.assertEqual(result.missing, ())
        if import_np is not None:
            expected = sum(bool(import_np.isclose(result.items[i].parsed, self.revised[i].reference,
                                                  rtol=1e-5, atol=1e-8)) for i in echo)
            self.assertEqual(result.accepted, expected)
            on_original = self.original.score(echo)
            expected = sum(bool(import_np.isclose(on_original.items[i].parsed,
                                                  self.original[i].reference,
                                                  rtol=1e-5, atol=1e-8)) for i in echo)
            self.assertEqual(on_original.accepted, expected)
            self.assertLess(on_original.accepted, result.accepted)
        first = self.revised.ids[0]
        partial = dict(echo)
        del partial[first]
        with self.assertRaises(bp.MissingResponsesError):
            self.revised.score(partial)
        allowed = self.revised.score(partial, allow_missing=True)
        self.assertEqual((allowed.denominator, allowed.missing), (300, (first,)))
        self.assertIsNone(allowed.items[first])
        self.assertEqual(allowed.accepted, result.accepted - result.items[first].accepted)
        empty = self.revised.score({**echo, first: ""})
        self.assertEqual(empty.missing, ())
        self.assertIsNone(empty.items[first].parsed)
        with self.assertRaises(bp.ResponseError):
            self.revised.score({**echo, "tax/comp_9/0": "x"})
        with self.assertRaises(TypeError):
            self.revised.score({**echo, first: None})
        with self.assertRaises(TypeError):
            self.revised.score(list(echo.values()))

    def test_golden_scores(self):
        cases = json.loads(golden("score-golden.json").read_text())["tax"]
        self.assertGreater(len(cases), 0)
        for case in cases:
            score = bp.score_tax_response(case["response"], case["reference"],
                                          scorer="rulearena-tax-native")
            self.assertEqual((score.parsed, score.accepted), (case["parsed"], case["score"]), case)
            self.assertEqual(self.revised[case["id"]].reference, case["reference"])

    def test_native_mode_reproduces_all_saved_study_responses(self):
        with tarfile.open(tax_study()) as archive:
            responses = json.load(archive.extractfile("responses.json"))
            references = {r["id"]: r for r in
                          json.load(archive.extractfile("references.json"))}
        self.assertEqual(len(responses), 900)
        for response in responses:
            self.assertEqual(sha256(response["raw_text"].encode()),
                             response["raw_text_sha256"])
            for index, key in enumerate(("original", "revised")):
                result = bp.score_tax_response(
                    response["raw_text"], references[response["id"]][key],
                    scorer="rulearena-tax-native")
                self.assertEqual(result.parsed, response["parsed"], response["id"])
                self.assertEqual(result.accepted, response["scores"][index], response["id"])


class Airline(unittest.TestCase):
    def setUp(self):
        self.source = require("BAR_TEST_RULEARENA")
        self.revised = _Cached.dataset("rulearena-airline")
        self.original = _Cached.dataset("rulearena-airline", variant="original-input")

    def test_default_is_integrated_revision(self):
        default = _Cached.dataset("rulearena-airline")
        self.assertEqual((default.variant, default.mode), ("revised", "markdown-zero-shot"))
        info = default.info
        self.assertEqual([c["component"] for c in info["components"]],
                         ["rulearena-airline-objective", "rulearena-airline-prompt-errata",
                          "rulearena-airline-scoring"])
        self.assertTrue(all(c["applied"] for c in info["components"]))
        self.assertEqual(len(info["prompt_errata"]["applied_in_memory"]), 2)
        self.assertIn("none in markdown-zero-shot", info["prompt_errata"]["model_visible_effect"])
        self.assertEqual(info["flag_counts"], {"allocation_sensitive": 94,
                                               "listed_order_above_minimum": 74,
                                               "pe_dash_cases": 4, "changed_references": 0})
        self.assertEqual(len(info["amendments"]), 1)
        self.assertTrue(info["not_complete_ground_truth_certification"])
        self.assertEqual(default.scorer, "rulearena-airline-scoring")

    def test_all_messages_match_frozen_hashes(self):
        references = bp.load_references("rulearena-airline-objective")
        objective = bp.get_component("rulearena-airline-objective").read_bytes(
            "components/rulearena-airline-objective/objective.txt").decode().strip()
        policy = (self.source / "airline/reference_rules.txt").read_text()
        native = {}
        for reference, example, original in zip(references, self.revised, self.original):
            self.assertEqual(example.id, reference["id"])
            self.assertEqual(sha256(canonical(example.messages)), reference["revised_messages_sha256"])
            self.assertEqual(sha256(canonical(original.messages)),
                             reference["original_messages_sha256"])
            self.assertEqual(example.reference, reference["revised_reference"])
            self.assertEqual(original.reference, reference["original_reference"])
            for key in ("allocation_sensitive", "pe_dash_case", "allocation_minimum"):
                self.assertEqual(example.metadata[key], reference[key])
            name = reference["source_file"]
            if name not in native:
                native[name] = jsonl(self.source / name)
            record = native[name][reference["source_index"]]
            self.assertEqual(example.source_record, record)
            for item in (example, original):
                check_segments(self, item)
                self.assertEqual([s.text for s in item.policy], [policy])
                self.assertEqual([s.text for s in item.case], [record["prompt"]])
                text = json.dumps(record["info"])
                self.assertNotIn(text, item.messages[1]["content"])
            self.assertEqual([s.text for s in example.amendments], ["\n\n" + objective])
            self.assertEqual(example.amendments[0].origin, "bar")
            self.assertEqual(original.amendments, ())

    def test_baseline_cli_rows(self):
        rows = jsonl(golden("rulearena-airline-objective/data.jsonl"))
        self.assertEqual(len(rows), 300)
        for row, example, original in zip(rows, self.revised, self.original):
            self.assertEqual(row["messages"], example.messages)
            self.assertEqual(row["original_messages"], original.messages)
            self.assertEqual(row["native_case"], example.source_record)

    def test_golden_scores(self):
        cases = json.loads(golden("score-golden.json").read_text())["airline"]
        self.assertGreater(len(cases), 0)
        for case in cases:
            score = bp.score_airline_response(case["response"], case["reference"])
            parsed = None if score.parsed is None else str(score.parsed)
            self.assertEqual((parsed, score.accepted), (case["parsed"], case["score"]), case)
            self.assertEqual(self.revised[case["id"]].reference, case["reference"])

    def test_batch_scoring(self):
        echo = {e.id: f"The total cost is ${e.reference:,}." for e in self.revised}
        self.assertEqual(self.revised.score(echo).accepted, 300)
        self.assertEqual(self.original.score(echo).accepted, 300)


class ComponentRows(unittest.TestCase):
    """component_rows must reproduce the pre-API CLI data.jsonl byte for byte."""

    def test_rows_equal_baseline_bytes(self):
        source = require("BAR_TEST_RULEARENA")
        for identifier, encode in (
                ("rulearena-tax", lambda r: (json.dumps(r, ensure_ascii=False, allow_nan=False)
                                             + "\n").encode()),
                ("rulearena-airline-objective", lambda r: canonical(r) + b"\n"),
                ("rulearena-nba-location-errata", lambda r: canonical(r) + b"\n")):
            with self.subTest(identifier=identifier):
                expected = golden(f"{identifier}/data.jsonl").read_bytes()
                rows = bp.component_rows(identifier, source, release="0.2.0")
                self.assertEqual(b"".join(encode(r) for r in rows), expected)

    def test_nba_records(self):
        rows = bp.component_rows("rulearena-nba-location-errata", require("BAR_TEST_RULEARENA"))
        self.assertEqual(len(rows), 216)
        changed = [r for r in rows if r["changed"]]
        self.assertEqual([(r["id"], r["changed_field"]) for r in changed],
                         [("nba/comp_1/62", "problematic_team"), ("nba/comp_2/4", "illegal_operation")])
        for row in rows:
            diff = {k for k in row["original_record"]
                    if row["original_record"][k] != row["revised_record"][k]}
            self.assertEqual(diff, {row["changed_field"]} if row["changed"] else set())


class Patches(unittest.TestCase):
    """In-memory patch application must equal the pinned (GNU patch) results."""

    def test_every_patch(self):
        roots = {"rulearena": require("BAR_TEST_RULEARENA"),
                 "conditionalqa": require("BAR_TEST_CONDITIONALQA")}
        results = env_path("BAR_TEST_BASELINE_RESULTS")
        checked = 0
        # These golden programs belong to the paper's asset release.
        # The new T2 patch has separate full-replay/preparation checks.
        for component in bp.list_components(release="0.2.0"):
            for patch in component.patches():
                root = roots["conditionalqa" if component.id.startswith("conditionalqa")
                             else "rulearena"]
                data = (root / patch["upstream_path"]).read_bytes()
                revised = _core.apply_patch_bytes(data, component.read_bytes(patch["patch"]),
                                                  patch["upstream_path"])
                self.assertEqual(sha256(revised), patch["after_sha256"], patch["patch"])
                prepared = (results / f"{component.id}-prepared" / patch["upstream_path"]
                            if results else None)
                if prepared and prepared.is_file():
                    self.assertEqual(revised, prepared.read_bytes())
                with self.assertRaises(bp.PatchError):
                    _core.apply_patch_bytes(revised, component.read_bytes(patch["patch"]),
                                            patch["upstream_path"])
                checked += 1
        self.assertEqual(checked, 7)


class WrongSources(unittest.TestCase):
    """Changed or missing sources fail, and before any upstream code is executed."""

    def copy(self, root, names):
        tmp = Path(self.enterContext(tempfile.TemporaryDirectory()))
        for name in names:
            (tmp / name).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(root / name, tmp / name)
        return tmp

    def test_rulearena(self):
        source = require("BAR_TEST_RULEARENA")
        names = sorted({p["path"] for c in ("rulearena-tax", "rulearena-airline-objective")
                        for p in bp.get_component(c).source_pins()})
        bad = self.copy(source, names)
        marker = bad / "executed"
        path = bad / "tax/auto_test.py"
        text = path.read_text()
        text = text.replace("def build_prompt(tax_payer: dict):\n",
                            f"def build_prompt(tax_payer: dict):\n    open({str(marker)!r}, 'w')\n", 1)
        path.write_text(text)
        with self.assertRaises(bp.SourceMismatchError) as caught:
            bp.load_dataset("rulearena-tax", bad)
        self.assertIn("tax/auto_test.py", str(caught.exception))
        with self.assertRaises(bp.SourceMismatchError):
            bp.component_rows("rulearena-tax", bad)
        self.assertFalse(marker.exists())
        good = self.copy(source, names)
        (good / "airline/reference_rules.txt").write_text(
            (source / "airline/reference_rules.txt").read_text() + "\n")
        with self.assertRaises(bp.SourceMismatchError):
            bp.load_dataset("rulearena-airline", good)
        (good / "airline/reference_rules.txt").unlink()
        with self.assertRaises(bp.SourceNotFoundError):
            bp.load_dataset("rulearena-airline", good)
        cqa = require("BAR_TEST_CONDITIONALQA")
        with self.assertRaises(bp.SourceNotFoundError):
            bp.load_dataset("rulearena-tax", cqa)

    def test_conditionalqa(self):
        source = require("BAR_TEST_CONDITIONALQA")
        bad = self.copy(source, ["evaluate.py", "v1_0/dev.json"])
        marker = bad / "executed"
        (bad / "evaluate.py").write_text(f"open({str(marker)!r}, 'w')\n"
                                         + (source / "evaluate.py").read_text())
        with self.assertRaises(bp.SourceMismatchError):
            bp.score_conditionalqa([], source=bad)
        self.assertFalse(marker.exists())
        good = self.copy(source, ["evaluate.py", "v1_0/dev.json"])
        (good / "v1_0/dev.json").write_text(json.dumps(json.loads(
            (source / "v1_0/dev.json").read_text())[:3]))
        with self.assertRaises(bp.SourceMismatchError):
            bp.score_conditionalqa([], source=good)
        result = bp.score_conditionalqa([], source=good, allow_unpinned_reference=True)
        self.assertFalse(result.reference_pinned)

    def test_legalbench(self):
        source = require("BAR_TEST_LEGALBENCH")
        bad = self.copy(source, ["evaluation.py"])
        marker = bad / "executed"
        (bad / "evaluation.py").write_text(f"open({str(marker)!r}, 'w')\n"
                                           + (source / "evaluation.py").read_text())
        try:
            import numpy  # noqa: F401
        except ImportError:
            self.skipTest("numpy not installed")
        with self.assertRaises(bp.SourceMismatchError):
            bp.load_legalbench_evaluator(bad / "evaluation.py")
        self.assertFalse(marker.exists())
        with self.assertRaises(bp.SourceNotFoundError):
            bp.load_legalbench_evaluator(bad / "missing.py")


def native_cqa_functions(source):
    """Per-item functions of the UNPATCHED upstream evaluator (aggregation excluded)."""
    text = (source / "evaluate.py").read_text()
    names = {"compute_metrics", "compute_em_f1", "compute_conditions_f1", "compute_answer_f1",
             "get_tokens", "normalize_answer"}
    nodes = [n for n in ast.parse(text).body if isinstance(n, ast.FunctionDef) and n.name in names]
    namespace = {}
    exec("import json, itertools, math, collections, string, re", namespace)
    exec(compile(ast.Module(body=nodes, type_ignores=[]), "native-cqa", "exec"), namespace)
    return namespace["compute_metrics"]


def independent_cqa(compute, predictions, references):
    """Full-denominator aggregation written independently of the BAR patch."""
    predicted = {p["id"]: p["answers"] for p in predictions}
    rows = []
    for reference in references:
        answers = reference["answers"]
        values = (compute(predicted[reference["id"]], answers) if reference["id"] in predicted
                  else (0.0, 0.0, 0.0, 0.0))
        groups = {"total"}
        if answers:
            groups.add("yesno" if any(a[0] in ("yes", "no") for a in answers) else "extractive")
        if any(a[1] for a in answers):
            groups.add("conditional")
        rows.append((values, groups))
    names = ("EM", "EM_with_conditions", "F1", "F1_with_conditions")
    result = {}
    for group in ("total", "yesno", "extractive", "conditional"):
        chosen = [v for v, g in rows if group in g]
        result[group] = {name: (sum(v[i] for v in chosen) / len(chosen) if chosen else None)
                         for i, name in enumerate(names)}
    return result


class ConditionalQA(unittest.TestCase):
    def setUp(self):
        self.source = require("BAR_TEST_CONDITIONALQA")
        self.references = json.loads((self.source / "v1_0/dev.json").read_text())

    def assertMetrics(self, actual, expected):
        self.assertEqual(set(actual), set(expected))
        for group in expected:
            for name, value in expected[group].items():
                if value is None:
                    self.assertIsNone(actual[group][name])
                else:
                    self.assertTrue(math.isclose(actual[group][name], value, abs_tol=1e-12))

    def test_golden_files(self):
        cases = json.loads(golden("score-golden.json").read_text())["conditionalqa"]
        compute = native_cqa_functions(self.source)
        results = env_path("BAR_TEST_BASELINE_RESULTS")
        for case in cases:
            with self.subTest(case=case["name"]):
                prediction = results / case["prediction_file"]
                result = bp.score_conditionalqa_file(
                    prediction, source=self.source, reference_file=results / case["reference_file"],
                    allow_unpinned_reference=True)
                self.assertEqual(result.metrics, case["score"])
                pinned = bp.score_conditionalqa_file(prediction, source=self.source)
                self.assertTrue(pinned.reference_pinned)
                self.assertEqual(pinned.metrics, case["score"])
                predictions = json.loads(prediction.read_text())
                self.assertEqual(bp.score_conditionalqa(predictions, source=self.source).metrics,
                                 case["score"])
                self.assertMetrics(result.metrics,
                                   independent_cqa(compute, predictions, self.references))
        by_name = {c["name"]: c["score"] for c in cases}
        if {"all_absent", "all_legal_empty"} <= set(by_name):
            self.assertNotEqual(by_name["all_absent"], by_name["all_legal_empty"])

    def test_constructed_submissions(self):
        compute = native_cqa_functions(self.source)
        refs = self.references
        submissions = {
            "empty": [],
            "every_other": [{"id": r["id"], "answers": r["answers"]} for r in refs[::2]],
            "legal_empty": [{"id": r["id"], "answers": []} for r in refs],
            "mixed": [{"id": r["id"], "answers": ([] if i % 3 else r["answers"])}
                      for i, r in enumerate(refs) if i % 5],
        }
        for name, predictions in submissions.items():
            with self.subTest(name=name):
                result = bp.score_conditionalqa(predictions, source=self.source)
                self.assertMetrics(result.metrics, independent_cqa(compute, predictions, refs))
        # A naive mean over submitted IDs differs from the full-denominator score.
        partial = submissions["every_other"]
        result = bp.score_conditionalqa(partial, source=self.source).metrics["total"]["EM"]
        self.assertAlmostEqual(result, len(partial) / len(refs))

    def test_empty_category_is_none(self):
        subset = [r for r in self.references if r["answers"]
                  and all(a[0] in ("yes", "no") for a in r["answers"])
                  and not any(a[1] for a in r["answers"])][:5]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "refs.json"
            path.write_text(json.dumps(subset))
            result = bp.score_conditionalqa(subset, source=self.source, reference_file=path,
                                            allow_unpinned_reference=True)
        self.assertEqual(result.metrics["total"]["EM"], 1.0)
        self.assertIsNone(result.metrics["extractive"]["EM"])
        self.assertIsNone(result.metrics["conditional"]["F1"])
        json.dumps(result.metrics, allow_nan=False)


class Sara(unittest.TestCase):
    def setUp(self):
        try:
            import numpy  # noqa: F401
        except ImportError:
            self.skipTest("numpy not installed")

    def test_golden_vectors(self):
        cases = json.loads(golden("score-golden.json").read_text())["sara"]
        for case in cases:
            self.assertEqual(float(bp.score_sara_numeric(case["predictions"], case["references"])),
                             case["score"], case)

    def test_label_echo_and_upstream_adapter(self):
        import csv
        source = require("BAR_TEST_LEGALBENCH")
        with (source / "data/sara_numeric/test.tsv").open(newline="") as stream:
            rows = list(csv.DictReader(stream, delimiter="\t"))
        answers = [r["answer"] for r in rows]
        self.assertEqual(len(answers), 96)
        self.assertEqual(bp.score_sara_numeric(answers, answers), 1.0)
        try:
            import sklearn, nltk  # noqa: F401
        except ImportError:
            self.skipTest("LegalBench evaluator dependencies not installed")
        evaluation = bp.load_legalbench_evaluator(source / "evaluation.py")
        self.assertEqual(evaluation.evaluate("sara_numeric", ["$1,234.00"], ["$1234"]), 1.0)
        self.assertEqual(evaluation.evaluate("sara_numeric", answers, answers), 1.0)


if __name__ == "__main__":
    unittest.main()
