# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Yanru Xiao and Yifei Cai
"""``bar-policy`` console command: the scripts/bar.py CLI on the installed assets."""
import sys

from . import _assets, _core


def main(argv=None):
    try:
        root, locate = _assets.root(), _assets.locate()
    except _core.BARError as error:
        raise SystemExit(str(error))
    _core.cli_main(root, locate, argv, prog="bar-policy")


if __name__ == "__main__":
    sys.exit(main())
