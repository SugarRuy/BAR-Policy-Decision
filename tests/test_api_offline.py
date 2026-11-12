# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Yanru Xiao and Yifei Cai
"""Checks that need no upstream source: versions, assets, errors and scorers."""
from decimal import Decimal
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

import bar_policy as bp
from bar_policy import _core

from _support import checkout, package_dir


class Versions(unittest.TestCase):
    def test_shared_version_and_historical_releases(self):
        self.assertEqual(bp.ASSET_RELEASE, "0.3.0")
        self.assertEqual(bp.SUPPORTED_RELEASES, ("0.2.0", "0.3.0"))
        self.assertEqual(bp.__version__, bp.ASSET_RELEASE)
        info = bp.release_info()
        self.assertEqual(info["version"], "0.3.0")
        self.assertEqual(len(info["components"]), 7)

    def test_unknown_releases_fail_without_fallback(self):
        for release in ("0.1.0", "0.4.0", "latest", "v0.2.0", "", "0.2"):
            with self.subTest(release=release):
                with self.assertRaises(bp.UnsupportedError):
                    bp.load_dataset("rulearena-tax", "/nonexistent", release=release)
                with self.assertRaises(bp.UnsupportedError):
                    bp.list_components(release=release)
        for release in (0.2, None, ("0.2.0",)):
            with self.assertRaises(bp.ConfigurationError):
                bp.release_info(release=release)

    def test_component_revisions_and_manifests(self):
        tax = bp.get_component("rulearena-tax")
        self.assertEqual(tax.revision, "t1-t2-1")
        self.assertEqual(tax.release, "0.3.0")
        self.assertEqual(tax.source_repository,
                         "SkyRiver-2000/RuleArena@59f60f6b4eb93a9b6d187ec781349d4f15618903")
        self.assertEqual(len(tax.manifest_sha256), 64)
        objective = bp.get_component("rulearena-airline-objective")
        self.assertEqual(objective.revision, "BAR-RuleArena-Airline-objective-v1")
        self.assertIsNone(bp.get_component("conditionalqa-scoring").revision)
        manifest = tax.manifest()
        manifest["id"] = "changed"
        self.assertEqual(tax.manifest()["id"], "rulearena-tax")
        self.assertTrue(all("sha256" in pin for pin in tax.source_pins()))


class Assets(unittest.TestCase):
    def test_verify_and_catalog(self):
        result = bp.verify_assets()
        self.assertEqual(result["components"], 7)
        self.assertGreaterEqual(result["files"], 47)
        ids = [c.id for c in bp.list_components()]
        self.assertEqual(ids, bp.release_info()["components"])
        capabilities = bp.capabilities()
        self.assertEqual(set(capabilities["components"]), set(ids))
        self.assertEqual(set(capabilities["datasets"]), {"rulearena-tax", "rulearena-airline"})
        self.assertEqual(capabilities["datasets"]["rulearena-airline"]["default_variant"], "revised")

    def test_references_bundled(self):
        tax = bp.load_references("rulearena-tax")
        self.assertEqual(len(tax), 300)
        self.assertEqual(sum(r["changed"] for r in tax), 43)
        airline = bp.load_references("rulearena-airline-objective")
        self.assertEqual(len(airline), 300)
        self.assertEqual(sum(r["allocation_sensitive"] for r in airline), 94)
        self.assertEqual(sum(r["pe_dash_case"] for r in airline), 4)
        self.assertFalse(any(r["allocation_sensitive"] and r["pe_dash_case"] for r in airline))
        self.assertTrue(all(r["original_reference"] == r["revised_reference"] for r in airline))
        nba = bp.load_references("rulearena-nba-location-errata")
        self.assertEqual([c["case_id"] for c in nba], ["nba/comp_1/62", "nba/comp_2/4"])

    def test_component_file_access_is_restricted(self):
        component = bp.get_component("rulearena-airline-objective")
        text = component.read_bytes("components/rulearena-airline-objective/objective.txt")
        self.assertTrue(text.startswith(b"For the described journey"))
        with self.assertRaises(bp.ConfigurationError):
            component.read_bytes("components/rulearena-tax/labels.json")
        with self.assertRaises(bp.ConfigurationError):
            component.read_bytes("../../etc/passwd")

    def test_tampered_assets_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            installed = package_dir() / "_assets"
            if installed.is_dir():
                shutil.copytree(package_dir(), Path(tmp) / "bar_policy",
                                ignore=shutil.ignore_patterns("__pycache__"))
                path, assets = Path(tmp), Path(tmp) / "bar_policy" / "_assets"
            else:
                root = checkout()
                if root is None:
                    self.skipTest("needs the source checkout or an installed package")
                assets = Path(tmp) / "bar"
                inventory = json.loads((root / "inventory.json").read_text())["files"]
                for name in list(inventory) + ["inventory.json"]:
                    (assets / name).parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(root / name, assets / name)
                path = assets / "src"
            labels = assets / "components/rulearena-tax/labels.json"
            labels.write_bytes(labels.read_bytes().replace(b"-16734.0", b"-16735.0", 1))
            code = ("import bar_policy as bp\n"
                    "assert bp.__file__.startswith(%r)\n"
                    "try:\n bp.verify_assets()\nexcept bp.AssetIntegrityError as e: print('REJECTED', e)\n"
                    "try:\n bp.load_references('rulearena-tax')\n"
                    "except bp.AssetIntegrityError as e: print('REJECTED', e)\n") % str(path)
            result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                                    env={**os.environ, "PYTHONPATH": str(path)}, cwd=tmp)
            self.assertEqual(result.stdout.count("REJECTED"), 2, result.stdout + result.stderr)
            self.assertIn("components/rulearena-tax/labels.json", result.stdout)


class Configuration(unittest.TestCase):
    def test_dataset_selection_errors_precede_source_access(self):
        missing = "/nonexistent/bar-source"
        cases = [
            (dict(name="rulearena-nba"), bp.UnsupportedError),
            (dict(name="rulearena-nba-location-errata"), bp.UnsupportedError),
            (dict(name="conditionalqa"), bp.UnsupportedError),
            (dict(name="legalbench-sara-numeric"), bp.UnsupportedError),
            (dict(name="rulearena-airline-objective"), bp.UnsupportedError),
            (dict(name="rulearena-ailine"), bp.ConfigurationError),
            (dict(name="rulearena-tax", variant="latest"), bp.ConfigurationError),
            (dict(name="rulearena-airline", variant="original"), bp.ConfigurationError),
            (dict(name="rulearena-airline", mode="textual-zero-shot"), bp.UnsupportedError),
            (dict(name="rulearena-airline", mode="markdown-one-shot"), bp.UnsupportedError),
            (dict(name="rulearena-airline", mode="textual-one-shot"), bp.UnsupportedError),
            (dict(name="rulearena-tax", mode="textual"), bp.UnsupportedError),
            (dict(name="rulearena-tax", mode="markdown-zero-shot"), bp.ConfigurationError),
            (dict(name="rulearena-tax", mode="few-shot"), bp.ConfigurationError),
            (dict(name="rulearena-tax", variant=["revised"]), bp.ConfigurationError),
            (dict(name="rulearena-airline", mode=0), bp.ConfigurationError),
        ]
        for kwargs, error in cases:
            with self.subTest(**kwargs):
                name = kwargs.pop("name")
                with self.assertRaises(error) as caught:
                    bp.load_dataset(name, missing, **kwargs)
                self.assertNotIsInstance(caught.exception, bp.SourceNotFoundError)

    def test_unsupported_mode_message_makes_no_correction_claim(self):
        with self.assertRaises(bp.UnsupportedError) as caught:
            bp.load_dataset("rulearena-airline", "/x", mode="textual-zero-shot")
        self.assertIn("no correction claim", str(caught.exception))

    def test_source_arguments(self):
        with self.assertRaises(bp.ConfigurationError):
            bp.load_dataset("rulearena-tax", None)
        with self.assertRaises(bp.ConfigurationError):
            bp.load_dataset("rulearena-tax", 42)
        with self.assertRaises(bp.SourceNotFoundError) as caught:
            bp.load_dataset("rulearena-tax", "/nonexistent/bar-source")
        self.assertIsInstance(caught.exception, FileNotFoundError)
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(bp.SourceNotFoundError) as caught:
                bp.load_dataset("rulearena-airline", tmp)
            self.assertIn("Missing pinned source file", str(caught.exception))
            with self.assertRaises(bp.SourceNotFoundError):
                bp.score_conditionalqa([], source=tmp)

    def test_unsupported_component_operations(self):
        with self.assertRaises(bp.UnsupportedError):
            bp.component_rows("legalbench-sara-numeric", "/x")
        with self.assertRaises(bp.UnsupportedError):
            bp.component_rows("rulearena-airline-scoring", "/x")
        with self.assertRaises(bp.UnsupportedError):
            bp.prepare_component("rulearena-airline-objective", "/x", "/y")
        with self.assertRaises(bp.UnsupportedError):
            bp.load_references("conditionalqa-scoring")
        with self.assertRaises(bp.ConfigurationError):
            bp.get_component("rulearena-unknown")

    def test_error_hierarchy(self):
        for cls in (bp.ConfigurationError, bp.UnsupportedError, bp.SourceMismatchError,
                    bp.AssetIntegrityError, bp.PatchError, bp.ResponseError,
                    bp.MissingResponsesError):
            self.assertTrue(issubclass(cls, bp.BARError) and issubclass(cls, ValueError))
        self.assertTrue(issubclass(bp.SourceNotFoundError, FileNotFoundError))
        self.assertTrue(issubclass(bp.DependencyError, ImportError))


class TaxScorer(unittest.TestCase):
    def test_native_parse_and_sign(self):
        # Expected values follow the exact upstream regex in tax/auto_test.py,
        # including its unescaped final "." and alternation order.
        cases = [
            ("The total tax owed is $1,234.50.", 1234.5, True),
            ("The total tax overpaid is $1,234.50.", -1234.5, False),
            ("**The total tax owed is $1,234.50.**", 1234.5, True),
            ("The total tax owed is $1,234.50", 1234.5, True),
            ("The total tax owed is $1234.50.", 123.0, False),
            ("The total tax owed is $123.", 123.0, False),
            ("the total tax owed is $1,234.50.", None, False),
            ("", None, False),
            ("First: The total tax owed is $5. Then The total tax owed is $1,234.50.", 5.0, False),
        ]
        for text, parsed, accepted in cases:
            with self.subTest(text=text):
                score = bp.score_tax_response(text, 1234.5, scorer="rulearena-tax-native")
                self.assertEqual(score.parsed, parsed)
                self.assertIs(score.accepted, accepted)
                self.assertEqual(score.scorer, "rulearena-tax-native")

    def test_isclose_boundaries_against_numpy(self):
        try:
            import numpy as np
        except ImportError:
            self.skipTest("numpy not installed")
        for reference in (0.0, 1.0, -16734.0, 3241.6800000000003, 1e7, -0.004):
            tolerance = 1e-8 + 1e-5 * abs(reference)
            for delta in (0, 0.5, 0.999, 1.0, 1.001, 2):
                for sign in (1, -1):
                    prediction = round(reference + sign * delta * tolerance, 2)
                    text = (f"The total tax {'owed' if prediction >= 0 else 'overpaid'} is "
                            f"${abs(prediction):,.2f}.")
                    score = bp.score_tax_response(text, reference)
                    expected = bool(np.isclose(score.parsed, reference, rtol=1e-5, atol=1e-8))
                    self.assertIs(score.accepted, expected, (text, reference))

    def test_invalid_inputs_raise(self):
        for reference in (math.nan, math.inf, -math.inf):
            with self.assertRaises(bp.ConfigurationError):
                bp.score_tax_response("The total tax owed is $1.", reference)
        for reference in (True, "1", None, Decimal("1")):
            with self.assertRaises(TypeError):
                bp.score_tax_response("The total tax owed is $1.", reference)
        for response in (None, 1, b"The total tax owed is $1."):
            with self.assertRaises(TypeError):
                bp.score_tax_response(response, 1.0)


class AirlineScorer(unittest.TestCase):
    def test_documented_probes(self):
        cases = [
            ("The total cost is $1,198.00", True), ("The total cost is $1198.", True),
            ("**The total cost is $1,198.00**", True), ("The total cost is $1,198 USD.", True),
            ("The total cost is $11,980 USD", False), ("The total cost is $1,19.8", False),
            ("The total cost is: $1,198.", False), ("The total cost is $ 1,198.", False),
            ("The total cost is $1,198. Thanks.", False), ("", False),
            ("The total cost is calculated below. The total cost is $1,198.", False),
        ]
        for text, accepted in cases:
            with self.subTest(text=text):
                self.assertIs(bp.score_airline_response(text, 1198).accepted, accepted)
        self.assertEqual(bp.score_airline_response("The total cost is $1,198.00", 1198).parsed,
                         Decimal("1198.00"))

    def test_invalid_inputs_raise(self):
        for reference in ("NaN", "Infinity", float("nan"), "abc", None):
            with self.assertRaises(bp.ConfigurationError):
                bp.score_airline_response("The total cost is $1.", reference)
        with self.assertRaises(TypeError):
            bp.score_airline_response("The total cost is $1.", True)
        with self.assertRaises(TypeError):
            bp.score_airline_response(None, 1198)


class SaraScorer(unittest.TestCase):
    def setUp(self):
        try:
            import numpy  # noqa: F401
        except ImportError:
            self.skipTest("numpy not installed")

    def test_conformance_vectors(self):
        component = bp.get_component("legalbench-sara-numeric")
        data = component.read_bytes("components/legalbench-sara-numeric/conformance.json")
        vectors = json.loads(data)["vectors"]
        self.assertGreater(len(vectors), 50)
        for vector in vectors:
            score = bp.score_sara_numeric(vector["predictions"], vector["references"])
            self.assertEqual(type(score).__name__, "float64")
            self.assertEqual(float(score), vector["score"], vector)

    def test_batch_population_and_errors(self):
        self.assertEqual(bp.score_sara_numeric(["$1", "no answer"], ["$1", "$2"]), 0.5)
        self.assertEqual(bp.score_sara_numeric([""], ["0"]), 0.0)
        with self.assertRaises(bp.ConfigurationError):
            bp.score_sara_numeric([], [])
        with self.assertRaises(bp.ConfigurationError):
            bp.score_sara_numeric(["1"], ["1", "2"])
        for reference in ("NaN", "Infinity", "abc", ""):
            with self.assertRaises(bp.ConfigurationError):
                bp.score_sara_numeric(["1"], [reference])
        with self.assertRaises(TypeError):
            bp.score_sara_numeric([None], ["1"])
        with self.assertRaises(TypeError):
            bp.score_sara_numeric("1", "1")


class ConsoleCommand(unittest.TestCase):
    def test_list_and_verify(self):
        run = lambda *args: subprocess.run([sys.executable, "-m", "bar_policy.cli", *args],
                                           capture_output=True, text=True)
        listed = run("list")
        self.assertEqual(listed.returncode, 0, listed.stderr)
        self.assertEqual(len(listed.stdout.splitlines()), 7)
        verified = run("verify")
        self.assertEqual(verified.returncode, 0, verified.stderr)
        self.assertRegex(verified.stdout, r"^Verified \d+ packaged files and 7 components\.\n$")
        failed = run("dataset", "conditionalqa-scoring", "--source", "/x", "--output", "/y")
        self.assertEqual(failed.returncode, 1)
        self.assertIn("This component has no dataset builder", failed.stderr)


class Installed(unittest.TestCase):
    def test_expected_installation(self):
        if os.environ.get("BAR_EXPECT_INSTALLED") != "1":
            self.skipTest("BAR_EXPECT_INSTALLED not set")
        self.assertTrue((package_dir() / "_assets" / "inventory.json").is_file())
        self.assertIn("site-packages", str(package_dir()))
        forbidden = os.environ.get("BAR_FORBIDDEN_ROOT")
        if forbidden:
            self.assertFalse(package_dir().is_relative_to(Path(forbidden).resolve()))
        for name in ("LICENSE", "THIRD_PARTY.md", "components/rulearena-tax/UPSTREAM-LICENSE",
                     "components/conditionalqa-scoring/UPSTREAM-LICENSE"):
            self.assertTrue((package_dir() / "_assets" / name).is_file(), name)


if __name__ == "__main__":
    unittest.main()
