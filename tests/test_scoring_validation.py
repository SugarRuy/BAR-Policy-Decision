# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Yanru Xiao and Yifei Cai
"""Post-publication API checks, separate from frozen scoring parity tests."""
import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import bar_policy as bar

from _support import require


class TaxNumeric(unittest.TestCase):
    def test_complete_amounts_with_and_without_grouping(self):
        for amount in (0, 1, 999, 1234, 1234.5, 12345.67, 1000000):
            for verb, sign in (("owed", 1), ("overpaid", -1)):
                for number in (str(amount), f"{amount:,.2f}"):
                    for punctuation in ("", ".", "\n", ";", ",", '"', "'", "`", "}", "”",
                                        "_", "*", "</b>", "—that is all"):
                        text = f"The total tax {verb} is ${number}{punctuation}"
                        with self.subTest(text=text):
                            result = bar.score_tax_response(text, sign * amount)
                            self.assertTrue(result.accepted)
                            self.assertEqual(result.parsed, sign * amount)
                            self.assertEqual(result.scorer, "rulearena-tax-numeric-v1")

    def test_malformed_numbers_are_not_partially_accepted(self):
        for token in ("1,23", "12,34.50", "1,234,56", "1234.56.78",
                      "1234abc", "1234e2", "1,234.56e2", "1,,234",
                      "1..234", "1.,234", "1,234..56", "1_234", "1__234"):
            with self.subTest(token=token):
                result = bar.score_tax_response(f"The total tax owed is ${token}.", 123)
                self.assertIsNone(result.parsed)
                self.assertFalse(result.accepted)

    def test_malformed_first_conclusion_is_not_skipped(self):
        for token in ("1,23", "1234abc", "unknown", ""):
            text = (f"The total tax owed is ${token}. "
                    "Correction: The total tax owed is $999.")
            with self.subTest(token=token):
                result = bar.score_tax_response(text, 999)
                self.assertIsNone(result.parsed)
                self.assertFalse(result.accepted)

    def test_native_unicode_digits_remain_supported(self):
        for scorer in ("rulearena-tax-native", "rulearena-tax-numeric-v1"):
            result = bar.score_tax_response(
                "The total tax owed is $١,٢٣٤.٥٠.", 1234.5, scorer=scorer)
            self.assertEqual(result.parsed, 1234.5)
            self.assertTrue(result.accepted)

    def test_native_compatibility_and_retained_selection(self):
        text = "**The total tax owed is $1234.50.**"
        self.assertEqual(bar.score_tax_response(text, 1234.5).parsed, 1234.5)
        native = bar.score_tax_response(text, 1234.5, scorer="rulearena-tax-native")
        self.assertEqual(native.parsed, 123)
        self.assertFalse(native.accepted)
        for scorer in ("rulearena-tax-native", "rulearena-tax-numeric-v1"):
            text = "The total tax owed is $5. Then The total tax owed is $1,234.50."
            self.assertEqual(bar.score_tax_response(text, 1234.5, scorer=scorer).parsed, 5)
            for amount in ("1,339", "4,555.10"):
                text = (f"The total tax owed is ${amount}, and payments exceed it.\n"
                        "The total tax overpaid is $3,157.")
                self.assertEqual(bar.score_tax_response(text, -3157, scorer=scorer).parsed,
                                 float(amount.replace(",", "")))
        self.assertIsNone(bar.score_tax_response("the total tax owed is $1234.", 1234).parsed)

    def test_scorer_selection_errors_precede_source_access(self):
        for name, scorer in (("rulearena-tax", "typo"),
                             ("rulearena-airline", "rulearena-tax-native")):
            with self.assertRaises(bar.UnsupportedError):
                bar.load_dataset(name, "/nonexistent/source", scorer=scorer)
        with self.assertRaises(bar.UnsupportedError):
            bar.score_tax_response("x", 1, scorer="typo")
        for scorer in (1, True, [], None):
            with self.assertRaises(bar.ConfigurationError):
                bar.score_tax_response("x", 1, scorer=scorer)

    def test_dataset_selection_changes_only_scoring(self):
        source = require("BAR_TEST_RULEARENA")
        current = bar.load_dataset("rulearena-tax", source)
        native = bar.load_dataset("rulearena-tax", source, scorer="rulearena-tax-native")
        self.assertTrue(current.info["scorer"]["is_repair"])
        self.assertFalse(native.info["scorer"]["is_repair"])
        for left, right in zip(current, native):
            self.assertEqual(left.to_dict(True), right.to_dict(True))
            text = (f"The total tax {'owed' if left.reference >= 0 else 'overpaid'} is "
                    f"${abs(left.reference):.2f}.")
            result = left.score(text)
            self.assertEqual(result.scorer, current.scorer)
            self.assertEqual(result.parsed, round(left.reference, 2))
            self.assertEqual(right.score(text).scorer, native.scorer)
        spec = bar.capabilities()["datasets"]["rulearena-tax"]
        self.assertEqual(spec["default_scorer"], current.scorer)
        self.assertIn(native.scorer, spec["scorers"])

    def test_unapplied_airline_errata_does_not_claim_verification(self):
        ds = bar.load_dataset("rulearena-airline", require("BAR_TEST_RULEARENA"),
                              variant="original-input")
        component = next(c for c in ds.info["components"]
                         if c["component"] == "rulearena-airline-prompt-errata")
        self.assertFalse(component["applied"])
        self.assertNotIn("model_visible_effect", component)


class ConditionalQAValidation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = require("BAR_TEST_CONDITIONALQA")
        cls.refs = json.loads((cls.source / "v1_0/dev.json").read_text())
        cls.gold = [{"id": r["id"], "answers": r["answers"]} for r in cls.refs]

    def score(self, predictions):
        return bar.score_conditionalqa(predictions, source=self.source)

    def test_invalid_ids_and_shapes_raise(self):
        identifier = self.refs[0]["id"]
        valid = {"id": identifier, "answers": [["yes", []]]}
        cases = [
            [{"id": "unknown-or-wrong-split", "answers": []}],
            [valid, copy.deepcopy(valid)],
            [{"id": identifier}], [{"answers": []}],
            [{"id": 0, "answers": []}], [{"id": "", "answers": []}],
            [{"id": identifier, "answers": ["yes"]}],
            [{"id": identifier, "answers": None}],
            [{"id": identifier, "answers": "yes"}],
            [{"id": identifier, "answers": [["yes"]]}],
            [{"id": identifier, "answers": [["yes", "condition"]]}],
            [{"id": identifier, "answers": [["yes", [1]]]}],
            [{"id": identifier, "answers": [[3, []]]}],
            [{"id": identifier, "answers": [["yes", [], "extra"]]}],
            [None], [1],
        ]
        for predictions in cases:
            with self.subTest(predictions=predictions):
                with self.assertRaises(bar.ResponseError):
                    self.score(predictions)

    def test_file_validation_and_duplicate_json_keys(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "predictions.json"
            for text in (
                "not json", "{}", "null",
                '[{"id":"dev-0","id":"dev-1","answers":[]}]',
                '[{"id":"dev-0","answers":[],"answers":[["yes",[]]]}]',
            ):
                path.write_text(text)
                with self.subTest(text=text), self.assertRaises(bar.ResponseError):
                    bar.score_conditionalqa_file(path, source=self.source)

    def test_non_utf8_files_and_bom_have_clear_errors(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "records.json"
            text = json.dumps(self.gold[:1])
            for encoding in ("utf-16", "utf-32", "utf-8-sig"):
                path.write_bytes(text.encode(encoding))
                with self.subTest(encoding=encoding):
                    with self.assertRaises(bar.ResponseError):
                        bar.score_conditionalqa_file(path, source=self.source)
                    with self.assertRaises(bar.ConfigurationError):
                        bar.score_conditionalqa([], source=self.source, reference_file=path,
                                               allow_unpinned_reference=True)

    def test_real_ascii_locale_keeps_utf8_answers(self):
        code = """
import json, locale, sys
from pathlib import Path
import bar_policy as bar
assert locale.getpreferredencoding(False).lower() not in ('utf-8', 'utf8')
source = Path(sys.argv[1])
gold = json.loads((source / 'v1_0/dev.json').read_text(encoding='utf-8'))
result = bar.score_conditionalqa(gold, source=source)
assert result.metrics['total']['EM'] == 1.0, result.metrics
"""
        env = dict(os.environ, LC_ALL="C", PYTHONUTF8="0", PYTHONCOERCECLOCALE="0")
        result = subprocess.run([sys.executable, "-B", "-c", code, str(self.source)],
                                env=env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_simulated_cp1252_default_keeps_utf8_answers(self):
        # Only simulate the default encoding; all reads still use real files.
        real_open = open

        def cp1252_open(file, mode="r", *args, **kwargs):
            if "b" not in mode:
                kwargs.setdefault("encoding", "cp1252")
            return real_open(file, mode, *args, **kwargs)

        with patch("builtins.open", side_effect=cp1252_open):
            result = self.score(self.gold)
        self.assertEqual(result.metrics["total"]["EM"], 1.0)
        self.assertEqual(result.metrics["total"]["F1"], 1.0)

    def test_empty_missing_and_complete_are_distinct(self):
        empty = self.score([])
        self.assertEqual((empty.denominator, empty.submitted), (285, 0))
        self.assertEqual(empty.missing, tuple(r["id"] for r in self.refs))
        self.assertEqual(empty.empty_answers, ())
        self.assertEqual(empty.metrics["total"]["EM"], 0)
        legal_empty = self.score([{"id": r["id"], "answers": []} for r in self.refs])
        self.assertEqual((legal_empty.denominator, legal_empty.submitted), (285, 285))
        self.assertEqual(legal_empty.missing, ())
        self.assertEqual(legal_empty.empty_answers, empty.missing)
        self.assertEqual(legal_empty.metrics["total"]["EM"],
                         sum(not r["answers"] for r in self.refs) / 285)
        complete = self.score(self.gold)
        self.assertEqual(complete.metrics["total"]["EM"], 1)
        partial = self.score(self.gold[1:])
        self.assertAlmostEqual(partial.metrics["total"]["EM"], 284 / 285)
        self.assertEqual(partial.missing, (self.refs[0]["id"],))
        self.assertEqual(partial.input_validation, "conditionalqa-input-v1")

    def test_both_entrypoints_agree_and_do_not_change_inputs(self):
        predictions = copy.deepcopy(self.gold)
        before = copy.deepcopy(predictions)
        payload = json.dumps(predictions, indent=2).encode()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "predictions.json"
            path.write_bytes(payload)
            result = bar.score_conditionalqa_file(path, source=self.source)
            self.assertEqual(path.read_bytes(), payload)
        self.assertEqual(result.prediction_sha256, hashlib.sha256(payload).hexdigest())
        self.assertEqual(result.metrics, self.score(predictions).metrics)
        self.assertEqual(predictions, before)

    def test_invalid_custom_references_raise_configuration_error(self):
        record = self.gold[0]
        cases = ([], {}, [record, record],
                 [{"id": record["id"], "answers": ["yes"]}])
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "references.json"
            for refs in cases:
                path.write_text(json.dumps(refs))
                with self.subTest(refs=refs), self.assertRaises(bar.ConfigurationError):
                    bar.score_conditionalqa([], source=self.source, reference_file=path,
                                           allow_unpinned_reference=True)


if __name__ == "__main__":
    unittest.main()
