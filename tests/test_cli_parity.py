# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Yanru Xiao and Yifei Cai
"""Pre-API CLI versus refactored CLI, ``bar-policy`` command and Python API."""
import filecmp
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest

import bar_policy as bp

from _support import checkout, env_path, require

DATASETS = ("rulearena-tax", "rulearena-airline-objective", "rulearena-nba-location-errata")
PATCHES = ("rulearena-tax", "legalbench-sara-numeric", "conditionalqa-scoring",
           "rulearena-airline-prompt-errata", "rulearena-airline-scoring",
           "rulearena-nba-location-errata")


def sources():
    return {"rulearena": require("BAR_TEST_RULEARENA"),
            "legalbench": require("BAR_TEST_LEGALBENCH"),
            "conditionalqa": require("BAR_TEST_CONDITIONALQA")}


def source_for(identifier):
    roots = sources()
    if identifier.startswith("legalbench"):
        return roots["legalbench"]
    if identifier.startswith("conditionalqa"):
        return roots["conditionalqa"]
    return roots["rulearena"]


def same_tree(left, right):
    comparison = filecmp.dircmp(left, right, ignore=["__pycache__"])
    if comparison.left_only or comparison.right_only or comparison.funny_files:
        return False
    _, mismatch, errors = filecmp.cmpfiles(left, right, comparison.common_files, shallow=False)
    return not mismatch and not errors and all(
        same_tree(Path(left) / d, Path(right) / d) for d in comparison.common_dirs)


class CLIParity(unittest.TestCase):
    def setUp(self):
        self.baseline = require("BAR_TEST_BASELINE")
        self.tmp = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.runners = {"baseline": [sys.executable, "-B", str(self.baseline / "scripts/bar.py")],
                        "console": [sys.executable, "-m", "bar_policy.cli"]}
        if checkout():
            self.runners["checkout"] = [sys.executable, "-B", str(checkout() / "scripts/bar.py")]

    def run_all(self, *args, output=None):
        results = {}
        for name, command in self.runners.items():
            argv = list(args)
            if name != "baseline":
                argv += ["--release", "0.2.0"]
            if output:
                argv += ["--output", str(self.tmp / name / output)]
                (self.tmp / name).mkdir(exist_ok=True)
            done = subprocess.run(command + argv, capture_output=True, text=True,
                                  cwd=self.tmp, env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
            text = (done.stdout + done.stderr).replace(str(self.tmp / name), "OUT")
            # Only the inventory size differs: the current inventory adds package code.
            text = re.sub(r"Verified \d+ packaged files", "Verified N packaged files", text)
            results[name] = (done.returncode, text)
        return results

    def assertAllEqual(self, results):
        expected = results["baseline"]
        for name, value in results.items():
            self.assertEqual(value, expected, name)

    def test_list_and_errors(self):
        self.assertAllEqual(self.run_all("list"))
        self.assertAllEqual(self.run_all("dataset", "conditionalqa-scoring", "--source",
                                         str(source_for("conditionalqa")), output="x"))
        self.assertAllEqual(self.run_all("prepare", "unknown", "--source",
                                         str(source_for("rulearena")), output="x"))
        self.assertAllEqual(self.run_all("prepare", "rulearena-airline-objective", "--source",
                                         str(source_for("rulearena")), output="x"))
        self.assertAllEqual(self.run_all("dataset", "rulearena-tax", "--source",
                                         str(source_for("conditionalqa")), output="x"))
        self.assertAllEqual(self.run_all("dataset", "rulearena-tax", "--source",
                                         "/nonexistent", output="x"))

    def test_dataset_and_prepare_outputs(self):
        for command, identifiers in (("dataset", DATASETS), ("prepare", PATCHES)):
            for identifier in identifiers:
                with self.subTest(command=command, identifier=identifier):
                    out = f"{command}-{identifier}"
                    results = self.run_all(command, identifier, "--source",
                                           str(source_for(identifier)), output=out)
                    self.assertEqual(results["baseline"][0], 0, results["baseline"][1])
                    self.assertAllEqual(results)
                    for name in self.runners:
                        self.assertTrue(same_tree(self.tmp / "baseline" / out, self.tmp / name / out),
                                        name)
                    api = self.tmp / "api" / out
                    api.parent.mkdir(exist_ok=True)
                    if command == "dataset":
                        bp.write_component_dataset(identifier, source_for(identifier), api,
                                                   release="0.2.0")
                    else:
                        bp.prepare_component(identifier, source_for(identifier), api,
                                             release="0.2.0")
                    self.assertTrue(same_tree(self.tmp / "baseline" / out, api))
                    golden = env_path("BAR_TEST_BASELINE_RESULTS")
                    stored = (golden / (identifier + ("-prepared" if command == "prepare" else ""))
                              if golden else None)
                    if stored is not None and stored.is_dir():
                        self.assertTrue(same_tree(stored, api), stored)

    def test_existing_output_is_preserved(self):
        target = self.tmp / "existing"
        target.mkdir()
        (target / "sentinel").write_text("keep")
        with self.assertRaises(bp.ConfigurationError):
            bp.prepare_component("rulearena-tax", source_for("rulearena"), target)
        with self.assertRaises(bp.ConfigurationError):
            bp.write_component_dataset("rulearena-tax", source_for("rulearena"), target)
        self.assertEqual([p.name for p in target.iterdir()], ["sentinel"])


if __name__ == "__main__":
    unittest.main()
