# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Yanru Xiao and Yifei Cai
"""Build sdist and wheel, install the wheel and use it outside the source tree.

Enabled with BAR_TEST_PACKAGING=1. Needs setuptools>=77 and venv; no network.
"""
import email
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile
import textwrap
import unittest
import zipfile

from _support import checkout, env_path

FORBIDDEN = ("evidence/", "studies/", "releases/", "docs/assets/", ".png", ".tar.gz",
             "AGENTS.md", "__pycache__", ".pyc", "release-inventory.json", ".egg-info/")

PROBE = textwrap.dedent('''
    import os, sys
    from pathlib import Path
    forbidden = Path(os.environ["BAR_FORBIDDEN_ROOT"]).resolve()
    def hook(event, args):
        if event == "open" and isinstance(args[0], (str, bytes, os.PathLike)):
            path = Path(os.fsdecode(args[0])).resolve()
            if path.is_relative_to(forbidden):
                raise RuntimeError(f"source checkout accessed: {path}")
        if event.startswith("socket."):
            raise RuntimeError("network access attempted")
    sys.addaudithook(hook)
    import bar_policy as bp
    assert not Path(bp.__file__).resolve().is_relative_to(forbidden)
    print(bp.verify_assets())
    rulearena = os.environ.get("BAR_TEST_RULEARENA")
    if rulearena:
        tax = bp.load_dataset("rulearena-tax", rulearena)
        air = bp.load_dataset("rulearena-airline", rulearena)
        print(len(tax), len(air), tax[0].score("The total tax owed is $1.").accepted)
    print(bp.score_airline_response("The total cost is $1,198.", 1198).accepted)
''')


@unittest.skipUnless(os.environ.get("BAR_TEST_PACKAGING") == "1", "BAR_TEST_PACKAGING not set")
class Packaging(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = checkout()
        if cls.root is None:
            raise unittest.SkipTest("needs the source checkout")
        cls.tmp = Path(tempfile.mkdtemp(prefix="bar-policy-packaging-"))
        listed = subprocess.run(["git", "ls-files", "--cached", "--others", "--exclude-standard"],
                                cwd=cls.root, capture_output=True, text=True, check=True)
        export = cls.tmp / "export"
        for name in listed.stdout.split():
            if (cls.root / name).is_file():
                (export / name).parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(cls.root / name, export / name)
        build = "import sys; from setuptools import build_meta as b; print(getattr(b, sys.argv[1])(sys.argv[2]))"
        cls.sdist = cls.tmp / "dist" / cls._build(build, "build_sdist", export, cls.tmp / "dist")
        with tarfile.open(cls.sdist) as archive:
            archive.extractall(cls.tmp / "unpacked", filter="data")
        unpacked = next((cls.tmp / "unpacked").iterdir())
        cls.wheel = cls.tmp / "wheel" / cls._build(build, "build_wheel", unpacked, cls.tmp / "wheel")
        cls.inventory = json.loads((cls.root / "inventory.json").read_text())["files"]

    @staticmethod
    def _build(code, hook, cwd, out):
        out.mkdir(parents=True, exist_ok=True)
        done = subprocess.run([sys.executable, "-c", code, hook, str(out)], cwd=cwd,
                              capture_output=True, text=True)
        if done.returncode:
            raise AssertionError(done.stdout + done.stderr)
        return done.stdout.strip().splitlines()[-1]

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def assertClean(self, names):
        for name in names:
            for pattern in FORBIDDEN:
                self.assertNotIn(pattern, name)

    def test_sdist_contents(self):
        with tarfile.open(self.sdist) as archive:
            names = {"/".join(n.split("/")[1:]) for n in archive.getnames()}
        required = set(self.inventory) | {"inventory.json", "LICENSE", "pyproject.toml", "setup.py",
                                          "MANIFEST.in", "README.md", "tests/_support.py"}
        self.assertEqual(required - names, set())
        self.assertClean(n for n in names if not n.startswith("src/bar_policy_decision.egg-info"))

    def test_wheel_contents(self):
        with zipfile.ZipFile(self.wheel) as archive:
            names = set(archive.namelist())
            prefix = "src/bar_policy/"
            expected = {("bar_policy/" + n[len(prefix):]) if n.startswith(prefix)
                        else "bar_policy/_assets/" + n for n in self.inventory}
            expected |= {"bar_policy/_assets/inventory.json", "bar_policy/_assets/LICENSE"}
            info = {n for n in names if ".dist-info/" in n}
            self.assertEqual(names - info, expected)
            for name in expected:
                original = name.replace("bar_policy/_assets/", "", 1) if "/_assets/" in name \
                    else "src/" + name
                self.assertEqual(archive.read(name), (self.root / original).read_bytes(), name)
            licenses = {n.split(".dist-info/licenses/")[1] for n in info if "/licenses/" in n}
            self.assertTrue({"LICENSE", "THIRD_PARTY.md",
                             "components/conditionalqa-scoring/UPSTREAM-LICENSE",
                             "components/rulearena-tax/UPSTREAM-LICENSE"} <= licenses)
            metadata = email.message_from_bytes(
                archive.read(next(n for n in info if n.endswith("METADATA"))))
        self.assertEqual(metadata["Name"], "bar-policy-decision")
        self.assertEqual(metadata["Version"], "1.0.0.dev1")
        self.assertEqual(metadata["License-Expression"], "MIT AND BSD-2-Clause")
        self.assertClean(names)

    def test_installed_wheel_outside_source_tree(self):
        venv = self.tmp / "venv"
        subprocess.run([sys.executable, "-m", "venv", "--system-site-packages", str(venv)], check=True)
        python = venv / "bin" / "python"
        subprocess.run([python, "-m", "pip", "install", "--no-index", "--no-deps", "--quiet",
                        str(self.wheel)], check=True)
        run = self.tmp / "run"
        shutil.copytree(self.root / "tests", run / "tests",
                        ignore=shutil.ignore_patterns("__pycache__", "test_packaging.py"))
        env = {k: v for k, v in os.environ.items() if k not in ("PYTHONPATH", "BAR_TEST_PACKAGING")}
        env.update({"BAR_EXPECT_INSTALLED": "1", "BAR_FORBIDDEN_ROOT": str(self.root),
                    "PYTHONDONTWRITEBYTECODE": "1"})
        study = self.root / "studies" / "BAR-study-rulearena-tax-v1.tar.gz"
        if "BAR_TEST_TAX_STUDY" not in env and study.is_file():
            shutil.copyfile(study, run / study.name)
            env["BAR_TEST_TAX_STUDY"] = str(run / study.name)
        probe = subprocess.run([python, "-c", PROBE], cwd=run, env=env, capture_output=True,
                               text=True)
        self.assertEqual(probe.returncode, 0, probe.stderr)
        command = subprocess.run([venv / "bin" / "bar-policy", "verify"], cwd=run, env=env,
                                 capture_output=True, text=True)
        self.assertEqual(command.returncode, 0, command.stderr)
        self.assertIn("and 7 components.", command.stdout)
        suite = subprocess.run([python, "-m", "unittest", "discover", "-s", "tests", "-v"],
                               cwd=run, env=env, capture_output=True, text=True)
        self.assertEqual(suite.returncode, 0, suite.stdout + suite.stderr)
        self.assertIn("test_expected_installation", suite.stderr)
        self.assertNotIn("test_expected_installation (test_api_offline.Installed."
                         "test_expected_installation) ... skipped", suite.stderr)
        report = env_path("BAR_TEST_PACKAGING_REPORT")
        if report:
            report.write_text(probe.stdout + command.stdout + suite.stderr)


if __name__ == "__main__":
    unittest.main()
