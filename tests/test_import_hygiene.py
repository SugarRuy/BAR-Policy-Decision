# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Yanru Xiao and Yifei Cai
"""Importing and using bar_policy must not pollute the interpreter or the network."""
import json
import os
import subprocess
import sys
import textwrap
import unittest

from _support import env_path

PROBE = textwrap.dedent('''
    import json, os, sys
    events = {"network": [], "opened": []}
    def hook(event, args):
        if event.startswith("socket.") or event.startswith("urllib."):
            events["network"].append(event)
            raise RuntimeError("network access attempted: " + event)
        if event == "open" and isinstance(args[0], str):
            events["opened"].append(args[0])
    sys.addaudithook(hook)
    path, modules = list(sys.path), set(sys.modules)
    import bar_policy
    report = {"path_unchanged": sys.path == path,
              "imported": sorted(set(sys.modules) - modules),
              "opened_on_import": [p for p in events["opened"] if "/_assets/" in p
                                   or p.endswith((".json", ".jsonl", ".patch", ".txt"))]}
    sources = json.loads(os.environ["PROBE_SOURCES"])
    if sources.get("rulearena"):
        tax = bar_policy.load_dataset("rulearena-tax", sources["rulearena"])
        tax[0].score("The total tax owed is $1.")
        air = bar_policy.load_dataset("rulearena-airline", sources["rulearena"])
        air[0].score("The total cost is $1.")
        bar_policy.component_rows("rulearena-nba-location-errata", sources["rulearena"])
    bar_policy.score_tax_response("The total tax owed is $1.", 1.0)
    bar_policy.score_airline_response("The total cost is $1.", 1)
    report["numpy_before_sara"] = "numpy" in sys.modules
    if sources.get("conditionalqa"):
        bar_policy.score_conditionalqa([], source=sources["conditionalqa"])
    try:
        import numpy
        bar_policy.score_sara_numeric(["1"], ["1"])
    except ImportError:
        pass
    report["path_unchanged_after_use"] = sys.path == path
    report["used"] = sorted(set(sys.modules) - modules)
    report["network"] = events["network"]
    print(json.dumps(report))
''')


class ImportHygiene(unittest.TestCase):
    def run_probe(self):
        sources = {"rulearena": str(env_path("BAR_TEST_RULEARENA") or ""),
                   "conditionalqa": str(env_path("BAR_TEST_CONDITIONALQA") or "")}
        result = subprocess.run([sys.executable, "-c", PROBE], capture_output=True, text=True,
                                env={**os.environ, "PROBE_SOURCES": json.dumps(sources)})
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout.splitlines()[-1])

    def test_import_and_use(self):
        report = self.run_probe()
        self.assertTrue(report["path_unchanged"])
        self.assertTrue(report["path_unchanged_after_use"])
        self.assertEqual(report["opened_on_import"], [])
        self.assertEqual(report["network"], [])
        stdlib = set(sys.stdlib_module_names)
        top = lambda names: {name.split(".")[0] for name in names}
        self.assertEqual(top(report["imported"]) - stdlib, {"bar_policy"})
        self.assertFalse(report["numpy_before_sara"])
        foreign = top(report["used"]) - stdlib - {"bar_policy", "numpy"}
        self.assertEqual(foreign, set(), "unexpected modules after use")
        for name in report["used"]:
            self.assertFalse(name.startswith("_bar"), name)
            self.assertNotIn(name, {"bar", "rulearena", "evaluate", "evaluation",
                                    "reproduce_results", "auto_test", "evaluator"})


if __name__ == "__main__":
    unittest.main()
