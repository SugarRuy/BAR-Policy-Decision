# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Yanru Xiao and Yifei Cai
"""Exact amounts in the native Airline final-answer phrase.

Retains the first case-sensitive ``The total cost is`` marker and removal of
Markdown bold markers. Supports US comma grouping, optional sign, cents,
an optional USD suffix, terminal period, and surrounding whitespace.
Malformed or multiple final answers are rejected rather than searched for
a substring matching the reference.
"""
from decimal import Decimal, InvalidOperation
import re

MARKER = "The total cost is"
AMOUNT = re.compile(
    r"\s*\$(?P<amount>[+-]?(?:[0-9]{1,3}(?:,[0-9]{3})+|[0-9]+)"
    r"(?:\.[0-9]{1,2})?)(?:\s+USD)?\.?\s*\Z"
)


def parse_total(response):
    """Return a Decimal, or None for an invalid/missing terminal amount."""
    if not isinstance(response, str):
        return None
    response = response.replace("**", "")
    start = response.find(MARKER)
    if start == -1:
        return None
    match = AMOUNT.fullmatch(response[start + len(MARKER):])
    if match is None:
        return None
    return Decimal(match.group("amount").replace(",", ""))


def score_total(response, reference):
    """Compare exact numeric values; no tolerance or substring acceptance."""
    try:
        expected = Decimal(str(reference))
    except (InvalidOperation, ValueError) as error:
        raise ValueError("Reference must be a finite numeric amount") from error
    if not expected.is_finite():
        raise ValueError("Reference must be a finite numeric amount")
    predicted = parse_total(response)
    return predicted is not None and predicted == expected


def score_saved_log(text):
    """Rescore the original response in a native log, ignoring stored parsing.

    Both old and revised logs contain the response followed by these two
    metadata lines. Reusing ``GPT Predicted`` would preserve old parser errors.
    The final matching pair is the writer's metadata, after the response.
    """
    prefix, reference_marker, tail = text.rpartition("\nRule Calculated: ")
    response, prediction_marker, _ = prefix.rpartition("\n\nGPT Predicted: ")
    reference, line_end, _ = tail.partition("\n")
    if not reference_marker or not prediction_marker or not line_end:
        raise ValueError("Missing native response/reference log boundary")
    # Legacy predictions may themselves contain line breaks and trailing prose.
    return score_total(response, reference.strip())
