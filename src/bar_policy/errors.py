# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Yanru Xiao and Yifei Cai
"""Exceptions raised by BAR.

Each class also derives from the matching built-in exception (``ValueError``,
``FileNotFoundError`` or ``ImportError``). Configuration, source and asset
problems are always raised; they are never converted into zero scores.
"""
from ._core import (
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

__all__ = [
    "AssetIntegrityError", "BARError", "ConfigurationError", "DependencyError",
    "MissingResponsesError", "PatchError", "ResponseError", "SourceMismatchError",
    "SourceNotFoundError", "UnsupportedError",
]
