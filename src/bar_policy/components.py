# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Yanru Xiao and Yifei Cai
"""Low-level access to the seven versioned BAR components."""
import copy
import json
from pathlib import Path

from . import _assets, _core, _sources

# Operations implemented for each component. Anything absent raises
# UnsupportedError instead of being approximated.
_CAPABILITIES = {
    "rulearena-tax": {
        "operations": ("load_references", "component_rows", "write_component_dataset",
                       "prepare_component"),
        "datasets": ("rulearena-tax",),
        "notes": "Reference revision; Tax datasets use the original/native RuleArena scorer.",
    },
    "legalbench-sara-numeric": {
        "operations": ("score_sara_numeric", "load_legalbench_evaluator", "prepare_component"),
        "datasets": (),
        "notes": "Batch scorer only; LegalBench labels and inputs are not distributed or revised.",
    },
    "conditionalqa-scoring": {
        "operations": ("score_conditionalqa", "score_conditionalqa_file", "prepare_component"),
        "datasets": (),
        "notes": "Full-denominator file/batch scoring with a user-supplied pinned evaluator.",
    },
    "rulearena-airline-prompt-errata": {
        "operations": ("prepare_component",),
        "datasets": ("rulearena-airline",),
        "notes": "Affects one-shot and textual prompts only; no effect in Markdown zero-shot.",
    },
    "rulearena-airline-objective": {
        "operations": ("load_references", "component_rows", "write_component_dataset"),
        "datasets": ("rulearena-airline",),
        "notes": "Markdown zero-shot objective amendment; reference amounts unchanged.",
    },
    "rulearena-airline-scoring": {
        "operations": ("score_airline_response", "prepare_component"),
        "datasets": ("rulearena-airline",),
        "notes": "Exact terminal-amount scorer.",
    },
    "rulearena-nba-location-errata": {
        "operations": ("load_references", "component_rows", "write_component_dataset",
                       "prepare_component"),
        "datasets": (),
        "notes": "Original/revised raw records and JSON patches only; no policy-decision "
                 "dataset with model-visible messages is implemented.",
    },
}


class Component:
    """One BAR component of a pinned asset release (read-only view)."""

    def __init__(self, identifier, release):
        _assets.check_release(release)
        entry = next((c for c in _core.catalog(_assets.root()) if c["id"] == identifier), None)
        if entry is None:
            known = ", ".join(c["id"] for c in _core.catalog(_assets.root()))
            raise _core.ConfigurationError(f"Unknown component {identifier!r}; known: {known}")
        data = _assets.read_verified(entry["manifest"])
        self._manifest = json.loads(data)
        self._entry = entry
        self.id = identifier
        self.release = release
        self.kind = entry["kind"]
        self.payload_status = entry["payload_status"]
        self.manifest_path = entry["manifest"]
        self.manifest_sha256 = _core.digest(data)
        dataset = self._manifest.get("dataset", {})
        self.revision = dataset.get("revision") or dataset.get("asset_name")
        self.source_repository = self._manifest["source_repository"]
        self.accepted_scope = self._manifest["accepted_scope"]
        self.remaining_limits = tuple(self._manifest["remaining_limits"])
        self.payload_files = tuple(self._manifest["payload_files"])
        capability = _CAPABILITIES[identifier]
        self.operations = capability["operations"]
        self.datasets = capability["datasets"]
        self.notes = capability["notes"]

    def __repr__(self):
        return f"Component({self.id!r}, release={self.release!r}, kind={self.kind!r})"

    def manifest(self):
        """A copy of the exact ``component.json``."""
        return copy.deepcopy(self._manifest)

    def source_pins(self):
        """Pinned upstream files (path, URL, SHA-256) that users must supply."""
        pins = list(self._manifest["source_files"])
        pins += self._manifest.get("dataset", {}).get("source_files", [])
        unique = {pin["path"]: pin for pin in pins}
        return [copy.deepcopy(unique[name]) for name in sorted(unique)]

    def patches(self):
        return copy.deepcopy(self._manifest["patches"])

    def read_bytes(self, name):
        """Read one of this component's packaged files after hash verification."""
        allowed = {self.manifest_path, f"components/{self.id}/README.md", *self.payload_files,
                   *(p["patch"] for p in self._manifest["patches"])}
        if name not in allowed:
            raise _core.ConfigurationError(f"{name!r} is not a file of component {self.id}")
        return _assets.read_verified(name)

    def provenance(self):
        return {"component": self.id, "release": self.release, "kind": self.kind,
                "revision": self.revision, "manifest": self.manifest_path,
                "manifest_sha256": self.manifest_sha256,
                "source_repository": self.source_repository}

    def capabilities(self):
        return {"operations": list(self.operations), "datasets": list(self.datasets),
                "notes": self.notes}


def _release(release):
    return _assets.check_release(release)


def list_components(*, release=_assets.ASSET_RELEASE):
    """All components of one pinned asset release."""
    _release(release)
    return [Component(c["id"], release) for c in _core.catalog(_assets.root())]


def get_component(component_id, *, release=_assets.ASSET_RELEASE):
    _release(release)
    return Component(component_id, release)


def _supporting(component_id, operation, release):
    component = get_component(component_id, release=release)
    if operation not in component.operations:
        hint = f" {component.notes}" if component.notes else ""
        raise _core.UnsupportedError(
            f"{component_id} does not support {operation}; supported: "
            f"{', '.join(component.operations)}.{hint}")
    return component


def verify_assets(*, release=_assets.ASSET_RELEASE):
    """Hash-check every inventoried file bundled with this package."""
    _release(release)
    files, components = _assets.verify()
    return {"release": release, "files": files, "components": components}


def load_references(component_id, *, release=_assets.ASSET_RELEASE):
    """Bundled source-bound reference or errata records; no upstream source needed."""
    component = _supporting(component_id, "load_references", release)
    _assets.verify()
    if component_id == "rulearena-tax":
        return json.loads(component.read_bytes("components/rulearena-tax/labels.json"))["records"]
    if component_id == "rulearena-airline-objective":
        data = component.read_bytes("components/rulearena-airline-objective/references.jsonl")
        return [json.loads(line) for line in data.decode("utf-8").splitlines()]
    data = component.read_bytes("components/rulearena-nba-location-errata/errata.json")
    return json.loads(data)["changes"]


def component_rows(component_id, source, *, release=_assets.ASSET_RELEASE):
    """The exact rows written by ``scripts/bar.py dataset <component>``, in memory."""
    component = _supporting(component_id, "component_rows", release)
    _assets.verify()
    root = _assets.root()
    manifest = component.manifest()
    expected = component.source_repository
    source = _sources.source_root(source, expected)
    if component_id == "rulearena-tax":
        spec = manifest["dataset"]
        sources = _sources.read_pins(source, spec["source_files"], expected)
        rows, _ = _core.tax_rows(root, spec, sources)
    else:
        sources = _sources.read_pins(source, manifest["source_files"], expected)
        rows = _core.RULEARENA_BUILDERS[component_id](root, manifest, sources)
    _sources.unchanged(source, sources)
    return rows


def write_component_dataset(component_id, source, output, *, release=_assets.ASSET_RELEASE):
    """Same as ``scripts/bar.py dataset``; returns the new output directory."""
    component = _supporting(component_id, "write_component_dataset", release)
    source = _sources.source_root(source, component.source_repository)
    destination = Path(output)
    _core.dataset(_assets.root(), component_id, source, destination, _assets.locate())
    return destination.absolute()


def prepare_component(component_id, source, output, *, release=_assets.ASSET_RELEASE):
    """Same as ``scripts/bar.py prepare``; returns the preparation receipt.

    Requires the ``patch`` command for patch-based components.
    """
    component = _supporting(component_id, "prepare_component", release)
    source = _sources.source_root(source, component.source_repository)
    return _core.prepare(_assets.root(), component_id, source, Path(output), _assets.locate())


def capabilities(*, release=_assets.ASSET_RELEASE):
    """Machine-readable summary of datasets, components and their operations."""
    from .datasets import dataset_capabilities
    _release(release)
    return {
        "release": release,
        "datasets": dataset_capabilities(),
        "components": {c.id: c.capabilities() for c in list_components(release=release)},
    }
