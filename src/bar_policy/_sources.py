# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Yanru Xiao and Yifei Cai
"""Validate user-supplied upstream source roots. BAR never downloads them."""
import os
from pathlib import Path

from . import _core


def repository(manifest):
    """Split ``owner/name@commit`` into its two parts."""
    name, _, revision = manifest["source_repository"].partition("@")
    return name, revision


def source_root(source, expected):
    if source is None:
        raise _core.ConfigurationError(
            f"source is required: a local checkout of {expected}. BAR never downloads sources.")
    try:
        path = Path(os.fspath(source)).expanduser()
    except TypeError:
        raise _core.ConfigurationError(
            f"source must be a path, not {type(source).__name__}") from None
    if not path.is_dir():
        raise _core.SourceNotFoundError(
            f"Source directory not found: {path} (expected a local checkout of {expected})")
    return path.resolve()


def read_pins(source, pins, expected):
    """Read pinned files; missing files and hash mismatches raise before any execution."""
    for pin in pins:
        if not _core.child(source, pin["path"]).is_file():
            raise _core.SourceNotFoundError(
                f"Missing pinned source file {pin['path']} under {source}; expected {expected} "
                f"(SHA-256 {pin['sha256']})")
    try:
        return _core.pinned_sources(source, pins)
    except _core.SourceMismatchError as error:
        raise _core.SourceMismatchError(
            f"{error} under {source}; expected {expected}") from error


def unchanged(source, sources):
    _core.unchanged_sources(source, sources, "Source changed while BAR was reading it: {name}")
