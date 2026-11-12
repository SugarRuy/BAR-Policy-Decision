#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Yanru Xiao and Yifei Cai
"""Inspect BAR artifacts, prepare revised data, and apply pinned code patches."""
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load_core(root):
    # Load the shared implementation by path. Neither sys.path nor sys.modules
    # is changed, and no bytecode is written into the artifact tree.
    path = root / "src" / "bar_policy" / "_core.py"
    spec = importlib.util.spec_from_file_location("_bar_checkout_core", path)
    module = importlib.util.module_from_spec(spec)
    exec(compile(path.read_bytes(), str(path), "exec"), module.__dict__)
    return module


_core = _load_core(ROOT)
digest = _core.digest
read_json = _core.read_json
child = _core.child
tax_prompt_renderer = _core.tax_prompt_renderer


def catalog():
    return _core.catalog(ROOT)


def verify():
    _core.verify(ROOT, echo=print)


def prepare(identifier, source, output, *, release=None):
    _core.prepare(ROOT, identifier, source, output, echo=print, release=release)


def dataset(identifier, source, output, *, release=None):
    _core.dataset(ROOT, identifier, source, output, echo=print, release=release)


def main():
    _core.cli_main(ROOT)


if __name__ == "__main__":
    main()
