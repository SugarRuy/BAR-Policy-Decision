# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Yanru Xiao and Yifei Cai
"""Scoring entry points that reuse existing native or BAR evaluators unchanged.

Invalid references, wrong argument types and source problems raise errors;
they are never converted into a rejected (zero-credit) response.
"""
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import json
import math
import os
from pathlib import Path
import tempfile
import types
import warnings
from typing import Any, Mapping, Optional, Tuple

from . import _assets, _core, _sources

TAX_SCORER = "rulearena-tax-native"
AIRLINE_SCORER = "rulearena-airline-scoring"


@dataclass(frozen=True)
class ItemScore:
    """Result for one response; ``parsed`` is ``None`` when no answer was found."""
    accepted: bool
    parsed: Any
    reference: Any
    scorer: str


@dataclass(frozen=True)
class BatchScore:
    """Full-denominator result for a dataset.

    ``missing`` lists absent records (counted as not accepted only when the
    caller allowed it). An empty string is a response, not a missing record.
    """
    dataset: str
    variant: str
    scorer: str
    denominator: int
    accepted: int
    missing: Tuple[str, ...]
    items: Mapping[str, Optional[ItemScore]]
    release: str
    mode: str

    @property
    def accuracy(self):
        return self.accepted / self.denominator


@dataclass(frozen=True)
class ConditionalQAResult:
    """Output of the patched native ``evaluate`` plus input provenance."""
    metrics: Mapping[str, Mapping[str, Optional[float]]]
    reference_file: str
    reference_sha256: str
    reference_pinned: bool
    evaluator_sha256: str
    scorer: str = "conditionalqa-scoring"


def _check_response(response):
    if not isinstance(response, str):
        raise TypeError(f"response must be a str, not {type(response).__name__}; "
                        "leave absent records out of a batch instead of passing placeholders")


def score_tax_response(response, reference):
    """Original/native RuleArena Tax scoring of one response (not a scorer repair).

    Reuses ``decode_tax``/``tax_accept`` from ``scripts/reproduce_results.py``:
    the native case-sensitive final-answer pattern after removing ``**``
    (overpaid amounts are negative) and the standard-library scalar equivalent
    of native ``numpy.isclose`` with ``rtol=1e-5``, ``atol=1e-8`` and the reference
    as second argument. Tax scoring does not require NumPy.
    """
    _check_response(response)
    if isinstance(reference, bool) or not isinstance(reference, (int, float)):
        raise TypeError(f"Tax reference must be an int or float, not {type(reference).__name__}")
    if not math.isfinite(reference):
        raise _core.ConfigurationError("Tax reference must be finite")
    native = _assets.tax_native_scorer()
    parsed = native.decode_tax(response)
    return ItemScore(bool(native.tax_accept(parsed, reference)), parsed, reference, TAX_SCORER)


def score_airline_response(response, reference):
    """BAR exact terminal-amount Airline scoring (``rulearena-airline-scoring``)."""
    _check_response(response)
    if isinstance(reference, bool):
        raise TypeError("Airline reference must be a numeric amount, not bool")
    evaluator = _assets.airline_evaluator()
    try:
        accepted = evaluator.score_total(response, reference)
    except ValueError as error:
        raise _core.ConfigurationError(str(error)) from error
    return ItemScore(bool(accepted), evaluator.parse_total(response), reference, AIRLINE_SCORER)


def score_sara_numeric(generations, answers):
    """BAR LegalBench SARA numeric batch score (mean over the whole population).

    Returns ``numpy.float64`` exactly as the bundled evaluator does. There is
    no per-item variant; pass the complete population.
    """
    for name, values in (("generations", generations), ("answers", answers)):
        if isinstance(values, (str, bytes)) or not isinstance(values, (list, tuple)):
            raise TypeError(f"{name} must be a list or tuple")
    evaluator = _assets.sara_evaluator()
    for value in generations:
        if not isinstance(value, str):
            raise TypeError(f"SARA generations must be str, not {type(value).__name__}; "
                            "an unanswered row is an empty string")
    for value in answers:
        if isinstance(value, bool) or not isinstance(value, (str, int, float)):
            raise TypeError(f"SARA reference must be str, int or float, not {type(value).__name__}")
        try:
            amount = Decimal(str(value).translate(evaluator._CURRENCY_MARKS))
        except InvalidOperation:
            raise _core.ConfigurationError(f"Invalid SARA reference: {value!r}") from None
        if not amount.is_finite():
            raise _core.ConfigurationError(f"SARA reference must be finite: {value!r}")
    try:
        return evaluator.evaluate_sara_numeric_acc(list(generations), list(answers))
    except ValueError as error:
        raise _core.ConfigurationError(str(error)) from error


def load_legalbench_evaluator(path):
    """Bind a user-supplied pinned LegalBench ``evaluation.py`` in memory.

    The file hash is checked before any upstream code runs. Only
    ``evaluate_sara_numeric_acc`` is replaced; the upstream module's own
    dependencies (scikit-learn, NLTK) must be installed by the user.
    """
    if path is None or not Path(os.fspath(path)).is_file():
        raise _core.SourceNotFoundError(f"LegalBench evaluation.py not found: {path}")
    evaluator = _assets.sara_evaluator()
    data = Path(os.fspath(path)).read_bytes()
    if _core.digest(data) != evaluator.UPSTREAM_SHA256:
        raise _core.SourceMismatchError(
            f"LegalBench evaluation.py source hash mismatch: {path}; expected "
            f"{_assets.manifest('legalbench-sara-numeric')['source_repository']}")
    return evaluator.load_upstream_evaluator(path)


def _silent(*args, **kwargs):
    """Replaces only the native evaluator's progress print."""


def _conditionalqa_evaluator(source):
    manifest = _assets.manifest("conditionalqa-scoring")
    expected = manifest["source_repository"]
    root = _sources.source_root(source, expected)
    patch = manifest["patches"][0]
    name = patch["upstream_path"]
    path = _core.child(root, name)
    if not path.is_file():
        raise _core.SourceNotFoundError(f"Missing {name} under {root}; expected {expected}")
    data = path.read_bytes()
    # Version check before any upstream code is executed.
    if _core.digest(data) != patch["before_sha256"]:
        raise _core.SourceMismatchError(f"Original source mismatch: {name} under {root}; "
                                        f"expected {expected}")
    patch_bytes = _assets.read_verified(patch["patch"])
    if _core.digest(patch_bytes) != patch["patch_sha256"]:
        raise _core.AssetIntegrityError(f"Distributed patch mismatch: {patch['patch']}")
    revised = _core.apply_patch_bytes(data, patch_bytes, name)
    if _core.digest(revised) != patch["after_sha256"]:
        raise _core.PatchError(f"Revised source mismatch: {name}")
    module = types.ModuleType("_bar_policy_conditionalqa_evaluate")
    module.__dict__["print"] = _silent
    exec(compile(revised, f"{path} + {patch['patch']}", "exec"), module.__dict__)
    references = next(p for p in manifest["source_files"] if p["path"] == "v1_0/dev.json")
    return module.evaluate, root, references, patch["after_sha256"]


def score_conditionalqa_file(prediction_file, *, source, reference_file=None,
                             allow_unpinned_reference=False):
    """Score a native ConditionalQA prediction file with the full-denominator patch.

    ``source`` is a local ``haitian-sun/ConditionalQA`` checkout at the pinned
    commit. The evaluator is hash-checked, patched in memory, checked against
    the patched hash and then run unchanged. Absent IDs score zero and stay in
    every denominator; ``answers: []`` is a valid submission. Categories with
    no references return ``None``.
    """
    evaluate, root, pin, evaluator_sha256 = _conditionalqa_evaluator(source)
    if reference_file is None:
        reference_path = _core.child(root, pin["path"])
    else:
        reference_path = Path(os.fspath(reference_file)).expanduser()
    if not reference_path.is_file():
        raise _core.SourceNotFoundError(f"ConditionalQA reference file not found: {reference_path}")
    reference_sha256 = _core.digest(reference_path.read_bytes())
    pinned = reference_sha256 == pin["sha256"]
    if not pinned and not allow_unpinned_reference:
        raise _core.SourceMismatchError(
            f"Reference file {reference_path} is not the pinned {pin['path']} "
            f"(SHA-256 {pin['sha256']}); pass allow_unpinned_reference=True to score "
            "against another reference file")
    prediction_path = Path(os.fspath(prediction_file))
    if not prediction_path.is_file():
        raise FileNotFoundError(f"Prediction file not found: {prediction_path}")
    with warnings.catch_warnings():
        # The native loader leaves its files to the garbage collector.
        warnings.simplefilter("ignore", ResourceWarning)
        metrics = evaluate(str(prediction_path), str(reference_path))
    return ConditionalQAResult(metrics, str(reference_path), reference_sha256, pinned,
                               evaluator_sha256)


def score_conditionalqa(predictions, *, source, reference_file=None,
                        allow_unpinned_reference=False):
    """Score in-memory native predictions (a list of ``{"id", "answers"}``).

    The list is written unchanged to a temporary JSON file and scored by
    :func:`score_conditionalqa_file`, so aggregation is the native one.
    """
    if not isinstance(predictions, (list, tuple)):
        raise TypeError("predictions must be a list of {'id': ..., 'answers': [...]} records")
    _conditionalqa_evaluator(source)  # Fail on source problems before writing anything.
    with tempfile.TemporaryDirectory(prefix="bar-policy-cqa-") as tmp:
        path = Path(tmp) / "predictions.json"
        path.write_text(json.dumps(list(predictions), ensure_ascii=False), encoding="utf-8")
        return score_conditionalqa_file(path, source=source, reference_file=reference_file,
                                        allow_unpinned_reference=allow_unpinned_reference)
