# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Yanru Xiao and Yifei Cai
"""Test configuration. Optional inputs are given by environment variables.

BAR_TEST_RULEARENA, BAR_TEST_LEGALBENCH, BAR_TEST_CONDITIONALQA
    Local roots of the pinned upstream sources (never downloaded by tests).
BAR_TEST_BASELINE
    A checkout of the pre-API revision, for CLI parity tests.
BAR_TEST_BASELINE_RESULTS
    Golden outputs written by that pre-API CLI (data.jsonl, prepared trees,
    score-golden.json and ConditionalQA prediction files).
BAR_TEST_TAX_STUDY
    BAR-study-rulearena-tax-v1.tar.gz (v0.2.0 Release asset) with frozen
    model-visible input hashes. Defaults to studies/ in the checkout.
BAR_EXPECT_INSTALLED=1
    Require that bar_policy is an installed wheel, not the checkout.
BAR_TEST_PACKAGING=1
    Build sdist and wheel, install the wheel in a fresh venv and rerun the
    suite from outside the source tree.
"""
import hashlib
import json
import os
from pathlib import Path
import unittest

import bar_policy

HERE = Path(__file__).resolve().parent


def env_path(name):
    value = os.environ.get(name)
    return Path(value) if value else None


def checkout():
    """The source checkout containing these tests, if any."""
    root = HERE.parent
    if (root / "scripts" / "bar.py").is_file() and (root / "src" / "bar_policy").is_dir():
        return root
    return None


def require(name):
    path = env_path(name)
    if path is None or not path.exists():
        raise unittest.SkipTest(f"{name} not provided")
    return path


def tax_study():
    path = env_path("BAR_TEST_TAX_STUDY")
    if path is None and checkout():
        path = checkout() / "studies" / "BAR-study-rulearena-tax-v1.tar.gz"
    if path is None or not path.is_file():
        raise unittest.SkipTest("Tax study archive not available")
    return path


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":")).encode("utf-8")


def jsonl(path):
    return [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines()]


def package_dir():
    return Path(bar_policy.__file__).resolve().parent
