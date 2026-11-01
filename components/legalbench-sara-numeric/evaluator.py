# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Yanru Xiao and Yifei Cai
"""BAR implementation of the accepted SARA numeric parsing/scoring contract.

This file contains no LegalBench source. ``load_upstream_evaluator`` optionally
binds a user-provided pinned LegalBench module in memory, leaving its other
evaluators intact. The standalone numeric API needs only NumPy.
"""
from decimal import Decimal
import hashlib
import importlib.util
from pathlib import Path
import re

import numpy as np

UPSTREAM_SHA256 = "7bbae257d64ea9f29d97a25d92bbfca4343f3d2d495fd5c724f75b3ab0671e1a"
_AMOUNT = re.compile(r"[+-]?\s*\d+(?:\.\d+)?")
_CURRENCY_MARKS = str.maketrans("", "", "$,")


def parse_amount(value):
    """Read the first signed decimal after removing US currency separators."""
    token = _AMOUNT.search(str(value).translate(_CURRENCY_MARKS))
    if token is None:
        return None
    return Decimal("".join(token.group().split()))


def evaluate_sara_numeric_acc(generations, answers):
    """Return the mean acceptance rate; preserve the native nonzero tolerance."""
    count = len(answers)
    if len(generations) != count or count == 0:
        raise ValueError("Expected one generation for each nonempty reference row")
    accepted = 0
    for index in range(count):
        prediction = parse_amount(generations[index])
        reference = Decimal(str(answers[index]).translate(_CURRENCY_MARKS))
        if prediction is None:
            continue
        if reference.is_zero():
            accepted += int(prediction.is_zero())
        else:
            # Deliberately retain binary float, strict <, and the native +0.1.
            relative_error = abs(float(prediction) / (float(reference) + 0.1) - 1)
            accepted += int(relative_error < 0.1)
    return np.float64(accepted / count)


def load_upstream_evaluator(path):
    """Load a pinned local evaluator, then replace only its numeric function.

    The user's local module supplies all other public APIs and its dependencies
    (including scikit-learn and NLTK). No upstream bytes are written or bundled.
    """
    source = Path(path).resolve(strict=True)
    data = source.read_bytes()
    if hashlib.sha256(data).hexdigest() != UPSTREAM_SHA256:
        raise ValueError("LegalBench evaluation.py source hash mismatch")
    spec = importlib.util.spec_from_file_location("_bar_user_legalbench", source)
    module = importlib.util.module_from_spec(spec)
    # Compile the already verified bytes; do not create a cache in user sources.
    exec(compile(data, str(source), "exec"), module.__dict__)
    module.evaluate_sara_numeric_acc = evaluate_sara_numeric_acc
    return module
