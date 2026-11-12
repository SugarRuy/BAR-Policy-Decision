# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Yanru Xiao and Yifei Cai
"""Versioned Tax assets, exact historical compatibility and T2 integration."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import bar_policy as bar
from bar_policy import _assets, _core
from _support import require


class VersionedTax(unittest.TestCase):
    def test_release_boundaries_and_references(self):
        current = bar.get_component("rulearena-tax")
        old = bar.get_component("rulearena-tax", release="0.2.0")
        self.assertEqual(current.revision, "t1-t2-1")
        self.assertEqual(old.revision, "line22-only-2")
        self.assertNotEqual(current.manifest_sha256, old.manifest_sha256)
        self.assertEqual(bar.release_info(release="0.2.0")["version"], "0.2.0")
        self.assertEqual(bar.release_info()["version"], "0.3.0")
        original = bar.load_references("rulearena-tax", release="0.2.0")
        revised = bar.load_references("rulearena-tax")
        self.assertEqual(len(original), 300)
        self.assertEqual(len(revised), 300)
        for a, b in zip(original, revised):
            for field in ("case_id", "case_sha256", "source_file", "source_index",
                          "original_signed_answer", "line22_repaired_signed_answer"):
                self.assertEqual(a[field], b[field])
        self.assertEqual(sum(r["changed"] for r in revised), 43)
        self.assertEqual(sum(r["changed_from_line22"] for r in revised), 21)
        self.assertEqual(sum(r["changed"] for r in original), 27)
        with self.assertRaises(bar.ConfigurationError):
            old.read_bytes(current.manifest_path)
        self.assertIn("line-22 floor", bar.capabilities(release="0.2.0")[
            "datasets"]["rulearena-tax"]["variants"]["revised"])

    def test_exact_three_way_inputs_and_references(self):
        source = require("BAR_TEST_RULEARENA")
        new = bar.load_dataset("rulearena-tax", source)
        old = bar.load_dataset("rulearena-tax", source, release="0.2.0")
        native = bar.load_dataset("rulearena-tax", source, variant="original")
        changes = 0
        for a, b, c in zip(old, new, native):
            self.assertEqual(a.messages, b.messages)
            self.assertEqual(b.messages, c.messages)
            self.assertEqual(a.source_record, b.source_record)
            self.assertEqual(a.reference, b.references["previous"])
            self.assertEqual(a.references["original"], c.reference)
            self.assertEqual(c.metadata["remaining_dependencies"],
                             a.metadata["remaining_dependencies"])
            self.assertEqual(c.metadata["resolved_dependencies"], [])
            self.assertEqual(a.score("").scorer, b.score("").scorer)
            changes += a.reference != b.reference
            self.assertEqual(a.reference != b.reference, b.references["changed_from_previous"])
            self.assertEqual(b.metadata["remaining_dependencies"],
                             ["T3_schedule3_line15_default_zero"])
        self.assertEqual(changes, 21)
        self.assertEqual(new.info["reference_kind"], "policy_repaired_signed_answer")
        self.assertEqual(new.info["components"][0]["release"], "0.3.0")
        self.assertEqual(old.info["components"][0]["release"], "0.2.0")
        self.assertIn("T2_unstated_self_employment_threshold",
                      native.info["dependency_definitions"])
        self.assertNotIn("T2_unstated_self_employment_threshold",
                         new.info["dependency_definitions"])

    def test_both_preparation_paths_and_cli_dataset(self):
        source = require("BAR_TEST_RULEARENA")
        with tempfile.TemporaryDirectory() as tmp:
            for release in bar.SUPPORTED_RELEASES:
                output = Path(tmp) / release
                receipt = bar.prepare_component("rulearena-tax", source, output, release=release)
                manifest = bar.get_component("rulearena-tax", release=release).manifest()
                expected = manifest["patches"][0]["after_sha256"]
                self.assertEqual(receipt["files"]["tax/micro_evaluation.py"], expected)
                self.assertEqual(_core.digest((output / "tax/micro_evaluation.py").read_bytes()), expected)
                destination = Path(tmp) / (release + "-rows")
                command = [sys.executable, "-m", "bar_policy.cli", "dataset", "rulearena-tax",
                           "--release", release, "--source", str(source), "--output", str(destination)]
                result = subprocess.run(command, capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                rows = [json.loads(s) for s in (destination / "data.jsonl").read_text().splitlines()]
                self.assertEqual(rows, bar.component_rows("rulearena-tax", source, release=release))
                self.assertEqual(len(rows), 300)

    def test_wrong_source_rejected_for_both_versions(self):
        import shutil
        source = require("BAR_TEST_RULEARENA")
        with tempfile.TemporaryDirectory() as tmp:
            clone = Path(tmp) / "source"
            (clone / "tax").mkdir(parents=True)
            shutil.copyfile(source / "tax/micro_evaluation.py", clone / "tax/micro_evaluation.py")
            with (clone / "tax/micro_evaluation.py").open("a") as stream:
                stream.write("\n# wrong source\n")
            for release in bar.SUPPORTED_RELEASES:
                with self.assertRaises(bar.SourceMismatchError):
                    bar.prepare_component("rulearena-tax", clone, Path(tmp) / release, release=release)
                self.assertFalse((Path(tmp) / release).exists())

    def test_previous_revision_integrity(self):
        import copy
        source = require("BAR_TEST_RULEARENA")
        manifest = bar.get_component("rulearena-tax").manifest()
        spec = copy.deepcopy(manifest["dataset"])
        sources = _core.pinned_sources(source, spec["source_files"])
        spec["changed_from_previous_count"] = 20
        with self.assertRaisesRegex(bar.AssetIntegrityError, "count from previous"):
            _core.tax_rows(_assets.root(), spec, sources)
        spec["changed_from_previous_count"] = 21
        records = json.loads(_assets.path(spec["reference_file"]).read_text())
        records["records"][0]["changed_from_line22"] = not records["records"][0]["changed_from_line22"]
        with tempfile.TemporaryDirectory() as tmp:
            payload = json.dumps(records).encode()
            path = Path(tmp) / "labels.json"
            path.write_bytes(payload)
            spec["reference_file"] = "labels.json"
            spec["reference_sha256"] = _core.digest(payload)
            with self.assertRaisesRegex(bar.AssetIntegrityError, "Previous-reference flag"):
                _core.tax_rows(Path(tmp), spec, sources)

    def test_packaged_scientific_check(self):
        source = require("BAR_TEST_RULEARENA")
        # Use the same inventoried checker shipped in the wheel, outside the
        # source checkout when the installed-wheel suite runs.
        checker = _assets.path("scripts/check_tax_t2.py")
        with tempfile.TemporaryDirectory() as tmp:
            run = subprocess.run(
                [sys.executable, "-B", str(checker), "--source", str(source),
                 "--output", str(Path(tmp) / "checked")],
                capture_output=True, text=True,
                env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
            )
            self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
            result = json.loads((Path(tmp) / "checked/validation.json").read_text())
            self.assertEqual(result["summary"]["original_exact_replay"], 300)
            self.assertEqual(result["summary"]["negative_earnings_affected"], 20)
            self.assertEqual(result["summary"]["negative_other_taxes"], 15)
            self.assertEqual(result["summary"]["negative_total_tax"], 5)
            self.assertEqual(result["summary"]["owed_to_refund_from_line22"], 3)
            self.assertEqual(len(result["boundary_controls"]), 18)


if __name__ == "__main__":
    unittest.main()
