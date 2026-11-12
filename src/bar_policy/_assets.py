# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Yanru Xiao and Yifei Cai
"""Locate bundled BAR assets, pin releases and load bundled BAR evaluators.

Nothing here downloads data, changes ``sys.path`` or registers modules in
``sys.modules``. Bundled evaluator files are hash-checked before execution.
"""
import functools
import json
from pathlib import Path
import types

from . import _core

PACKAGE_DIR = Path(__file__).resolve().parent
ASSET_RELEASE = "0.3.0"
SUPPORTED_RELEASES = ("0.2.0", "0.3.0")
_PACKAGE_PREFIX = "src/bar_policy/"


@functools.lru_cache(maxsize=None)
def _layout():
    bundled = PACKAGE_DIR / "_assets"
    if (bundled / "inventory.json").is_file():
        def locate(name):
            if name.startswith(_PACKAGE_PREFIX):
                return _core.child(PACKAGE_DIR, name[len(_PACKAGE_PREFIX):])
            return _core.child(bundled, name)
        return bundled, locate
    # Running from a source checkout (for example, the test suite with
    # PYTHONPATH=src). Installed wheels always use the bundled copy above.
    checkout = PACKAGE_DIR.parents[1]
    if ((checkout / "inventory.json").is_file()
            and (checkout / "src" / "bar_policy" / "_core.py").resolve()
            == (PACKAGE_DIR / "_core.py")):
        return checkout, None
    raise _core.AssetIntegrityError(
        "BAR assets were not found next to the bar_policy package; reinstall the package.")


def root():
    return _layout()[0]


def locate():
    return _layout()[1]


def path(name):
    """Return the location of one inventoried file."""
    finder = locate()
    return finder(name) if finder else _core.child(root(), name)


def verify():
    return _core.verify(root(), locate())


def check_release(release):
    if not isinstance(release, str):
        raise _core.ConfigurationError(
            f"release must be a version string such as {ASSET_RELEASE!r}, not {type(release).__name__}")
    if release not in SUPPORTED_RELEASES:
        raise _core.UnsupportedError(
            f"BAR asset release {release!r} is not available in this package. "
            f"Supported releases: {', '.join(SUPPORTED_RELEASES)}. "
            "Releases are never resolved remotely or by 'latest'.")
    bundled = release_metadata(release)["version"]
    if bundled != release:
        raise _core.AssetIntegrityError(
            f"Bundled release metadata is {bundled!r}, expected {release!r}")
    return release


def inventory_entry(name):
    files = _core.read_json(root() / "inventory.json")["files"]
    if name not in files:
        raise _core.AssetIntegrityError(f"Not an inventoried BAR file: {name}")
    return files[name]


def read_verified(name):
    """Read one inventoried file after checking its SHA-256 and size."""
    expected = inventory_entry(name)
    data = path(name).read_bytes()
    if _core.digest(data) != expected["sha256"] or len(data) != expected["bytes"]:
        raise _core.AssetIntegrityError(f"Missing or changed packaged file: {name}")
    return data


def manifest(identifier, release=ASSET_RELEASE):
    entry = next(c for c in _core.catalog(root(), release) if c["id"] == identifier)
    return json.loads(read_verified(entry["manifest"]))


@functools.lru_cache(maxsize=None)
def _module(name, expected_sha256, module_name):
    data = read_verified(name)
    if expected_sha256 is not None and _core.digest(data) != expected_sha256:
        raise _core.AssetIntegrityError(f"Bundled evaluator hash mismatch: {name}")
    module = types.ModuleType(module_name)
    module.__file__ = str(path(name))
    # Execute verified bytes in a private module; nothing is added to
    # sys.modules and no bytecode is written.
    exec(compile(data, str(path(name)), "exec"), module.__dict__)
    return module


def tax_native_scorer():
    """decode_tax/tax_accept from the inventoried scripts/reproduce_results.py."""
    return _module("scripts/reproduce_results.py", None, "_bar_policy_reproduce_results")


def airline_evaluator():
    spec = manifest("rulearena-airline-scoring")["additional_files"][0]
    return _module(spec["payload"], spec["sha256"], "_bar_policy_airline_scoring")


def sara_evaluator():
    spec = manifest("legalbench-sara-numeric")["replacement"]
    try:
        import numpy  # noqa: F401  (imported lazily, only for SARA scoring)
    except ImportError as error:
        raise _core.DependencyError(
            "SARA numeric scoring needs NumPy; install 'bar-policy-decision[sara]'.") from error
    return _module(spec["implementation"], spec["after_sha256"], "_bar_policy_sara_numeric")


def release_metadata(release=ASSET_RELEASE):
    # The catalog binds historical component manifests and release metadata.
    read_verified("components.json")
    spec = _core.release_spec(root(), release)
    return json.loads(read_verified(spec["metadata"]))
