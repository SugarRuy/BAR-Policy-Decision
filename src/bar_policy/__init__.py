# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Yanru Xiao and Yifei Cai
"""BAR (Benchmark Audit and Revision): load revised policy-decision datasets and scorers.

Importing this package reads no files, downloads nothing and imports no
optional dependency. See docs/API.md for the complete interface contract.
"""
from ._assets import ASSET_RELEASE, SUPPORTED_RELEASES
from .components import (
    Component,
    capabilities,
    component_rows,
    get_component,
    list_components,
    load_references,
    prepare_component,
    verify_assets,
    write_component_dataset,
)
from .datasets import Dataset, Example, Segment, load_dataset
from .errors import (
    AssetIntegrityError,
    BARError,
    ConfigurationError,
    DependencyError,
    MissingResponsesError,
    PatchError,
    ResponseError,
    SourceMismatchError,
    SourceNotFoundError,
    UnsupportedError,
)
from .scoring import (
    BatchScore,
    ConditionalQAResult,
    ItemScore,
    load_legalbench_evaluator,
    score_airline_response,
    score_conditionalqa,
    score_conditionalqa_file,
    score_sara_numeric,
    score_tax_response,
)

__version__ = "1.0.0.dev1"  # Python package version; distinct from ASSET_RELEASE.


def release_info(*, release=ASSET_RELEASE):
    """The bundled ``release.json`` of one pinned asset release."""
    from . import _assets
    _assets.check_release(release)
    return _assets.release_metadata()


__all__ = [
    "ASSET_RELEASE", "SUPPORTED_RELEASES", "__version__", "release_info",
    "Component", "capabilities", "component_rows", "get_component", "list_components",
    "load_references", "prepare_component", "verify_assets", "write_component_dataset",
    "Dataset", "Example", "Segment", "load_dataset",
    "BatchScore", "ConditionalQAResult", "ItemScore", "load_legalbench_evaluator",
    "score_airline_response", "score_conditionalqa", "score_conditionalqa_file",
    "score_sara_numeric", "score_tax_response",
    "AssetIntegrityError", "BARError", "ConfigurationError", "DependencyError",
    "MissingResponsesError", "PatchError", "ResponseError", "SourceMismatchError",
    "SourceNotFoundError", "UnsupportedError",
]
