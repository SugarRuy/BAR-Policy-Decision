# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Yanru Xiao and Yifei Cai
"""Build scoped RuleArena input and localization revisions from pinned sources.

Compatibility interface for the offline checkers; the implementation is shared
with the Python API in ``src/bar_policy/_core.py``.
"""
import importlib.util
from pathlib import Path

_path = Path(__file__).resolve().parents[1] / "src" / "bar_policy" / "_core.py"
_spec = importlib.util.spec_from_file_location("_bar_checkout_core", _path)
_core = importlib.util.module_from_spec(_spec)
exec(compile(_path.read_bytes(), str(_path), "exec"), _core.__dict__)

canonical = _core.canonical
literals = _core.literals
airline_messages = _core.airline_messages


def source_bytes(bar, manifest, source):
    return _core.pinned_sources(source, manifest["source_files"])


def objective_rows(bar, manifest, sources):
    return _core.objective_rows(bar.ROOT, manifest, sources)


def nba_rows(bar, manifest, sources):
    return _core.nba_rows(bar.ROOT, manifest, sources)


def dataset(bar, identifier, source, output):
    _core.rulearena_dataset(bar.ROOT, identifier, source, output, echo=print)
