# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Yanru Xiao and Yifei Cai
"""Copy the inventoried BAR assets into the wheel at build time.

The repository files remain the only maintained copy. Every copied file is
checked against inventory.json, so a wheel cannot contain changed payloads.
"""
import hashlib
import json
from pathlib import Path
import shutil

from setuptools import setup
from setuptools.command.build_py import build_py

ROOT = Path(__file__).resolve().parent
PACKAGE_PREFIX = "src/bar_policy/"


def asset_files():
    inventory = json.loads((ROOT / "inventory.json").read_text(encoding="utf-8"))["files"]
    for name, expected in inventory.items():
        if name.startswith(PACKAGE_PREFIX):
            continue  # Package code is installed as the package itself.
        data = (ROOT / name).read_bytes()
        if hashlib.sha256(data).hexdigest() != expected["sha256"] or len(data) != expected["bytes"]:
            raise SystemExit(f"Refusing to build: {name} differs from inventory.json")
        yield name
    yield "inventory.json"
    yield "LICENSE"


class BuildWithAssets(build_py):
    def run(self):
        super().run()
        if getattr(self, "editable_mode", False):
            return  # Editable installs read the checkout directly.
        target = Path(self.build_lib) / "bar_policy" / "_assets"
        for name in asset_files():
            destination = target / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / name, destination)


setup(cmdclass={"build_py": BuildWithAssets})
