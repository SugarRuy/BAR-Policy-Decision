# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Yanru Xiao and Yifei Cai
"""Scoring entry points with explicit scorer identities and input validation.

Invalid references, wrong argument types and source problems raise errors;
they are never converted into a rejected (zero-credit) response.
"""
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from functools import partial
import json
import math
import os
from pathlib import Path
import re
import tempfile
import types
import warnings
from typing import Any, Mapping, Optional, Tuple

from . import _assets, _core, _sources

TAX_SCORER = "rulearena-tax-numeric-v1"
TAX_NATIVE_SCORER = "rulearena-tax-native"
AIRLINE_SCORER = "rulearena-airline-scoring"

# Require a complete amount: the upstream alternation can read $1234 as $123.
# Validate at the first phrase; do not skip a malformed amount for a later one.
_TAX_PHRASE = re.compile(r"The total tax (owed|overpaid) is \$")
_TAX_AMOUNT = re.compile(
    r"((?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?)"
    # Reject adjacent letters/digits and incomplete decimal/thousands groups.
    # Underscores can close Markdown emphasis and are allowed like punctuation.
    r"(?![^\W_]|[.,_]+\d)"
)


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
    """Patched native metrics, input provenance and submission coverage."""
    metrics: Mapping[str, Mapping[str, Optional[float]]]
    reference_file: str
    reference_sha256: str
    reference_pinned: bool
    evaluator_sha256: str
    denominator: int
    submitted: int
    missing: Tuple[str, ...]
    empty_answers: Tuple[str, ...]
    prediction_sha256: str
    scorer: str = "conditionalqa-scoring"
    input_validation: str = "conditionalqa-input-v1"


def _check_response(response):
    if not isinstance(response, str):
        raise TypeError(f"response must be a str, not {type(response).__name__}; "
                        "leave absent records out of a batch instead of passing placeholders")


def score_tax_response(response, reference, *, scorer=TAX_SCORER):
    """Score one Tax response with complete numeric parsing by default.

    ``rulearena-tax-numeric-v1`` fixes truncated amounts and malformed grouping.
    It retains the native phrase, sign and tolerance. The amount after the
    first such phrase must be valid; a malformed amount is not skipped.
    Pass ``scorer="rulearena-tax-native"`` to reproduce the published studies
    with the unchanged ``decode_tax``/``tax_accept`` implementation.
    Both scorers use rtol=1e-5, atol=1e-8 and need no NumPy.
    """
    if not isinstance(scorer, str):
        raise _core.ConfigurationError(f"scorer must be a string, not {type(scorer).__name__}")
    if scorer not in (TAX_SCORER, TAX_NATIVE_SCORER):
        raise _core.UnsupportedError(f"Unsupported Tax scorer: {scorer!r}")
    _check_response(response)
    if isinstance(reference, bool) or not isinstance(reference, (int, float)):
        raise TypeError(f"Tax reference must be an int or float, not {type(reference).__name__}")
    if not math.isfinite(reference):
        raise _core.ConfigurationError("Tax reference must be finite")
    native = _assets.tax_native_scorer()
    if scorer == TAX_NATIVE_SCORER:
        parsed = native.decode_tax(response)
    else:
        text = response.replace("**", "")
        phrase = _TAX_PHRASE.search(text)
        amount = _TAX_AMOUNT.match(text, phrase.end()) if phrase else None
        parsed = float(amount[1].replace(",", "")) if amount else None
        if parsed is not None:
            parsed = (-parsed if phrase[1] == "overpaid" else parsed)
            if not math.isfinite(parsed):
                parsed = None
    return ItemScore(bool(native.tax_accept(parsed, reference)), parsed, reference, scorer)


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
    # Match validation's decoding on every locale, using real file I/O.
    module.__dict__["open"] = partial(open, encoding="utf-8")
    exec(compile(revised, f"{path} + {patch['patch']}", "exec"), module.__dict__)
    references = next(p for p in manifest["source_files"] if p["path"] == "v1_0/dev.json")
    return module.evaluate, root, references, patch["after_sha256"]


def _cqa_records(data, *, reference):
    """Validate native record shapes before upstream dict construction."""
    error = _core.ConfigurationError if reference else _core.ResponseError
    label = "reference" if reference else "prediction"

    def unique_object(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise error(f"ConditionalQA {label}: duplicate JSON key {key!r}")
            result[key] = value
        return result

    try:
        records = json.loads(data.decode("utf-8"), object_pairs_hook=unique_object)
    except (ValueError, UnicodeError) as exc:
        raise error(f"Invalid ConditionalQA {label} JSON: {exc}") from exc
    if not isinstance(records, list):
        raise error(f"ConditionalQA {label} must be a JSON list of records")
    if reference and not records:
        raise error("ConditionalQA references must contain at least one record")
    by_id = {}
    for index, record in enumerate(records):
        where = f"ConditionalQA {label} record {index}"
        if not isinstance(record, dict):
            raise error(f"{where}: expected an object with 'id' and 'answers'")
        identifier = record.get("id")
        if not isinstance(identifier, str) or not identifier:
            raise error(f"{where}: 'id' must be a nonempty string")
        if identifier in by_id:
            raise error(f"{where}: duplicate ID {identifier!r}")
        answers = record.get("answers")
        if not isinstance(answers, list):
            raise error(f"{where} ({identifier}): 'answers' must be a list; [] is valid")
        for answer in answers:
            if (not isinstance(answer, list) or len(answer) != 2
                    or not isinstance(answer[0], str)
                    or not isinstance(answer[1], list)
                    or not all(isinstance(c, str) for c in answer[1])):
                raise error(
                    f"{where} ({identifier}): each answer must be "
                    "[answer_text, [condition_text, ...]]")
        by_id[identifier] = answers
    return by_id


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
    reference_data = reference_path.read_bytes()
    reference_sha256 = _core.digest(reference_data)
    pinned = reference_sha256 == pin["sha256"]
    if not pinned and not allow_unpinned_reference:
        raise _core.SourceMismatchError(
            f"Reference file {reference_path} is not the pinned {pin['path']} "
            f"(SHA-256 {pin['sha256']}); pass allow_unpinned_reference=True to score "
            "against another reference file")
    prediction_path = Path(os.fspath(prediction_file))
    if not prediction_path.is_file():
        raise FileNotFoundError(f"Prediction file not found: {prediction_path}")
    prediction_data = prediction_path.read_bytes()
    references = _cqa_records(reference_data, reference=True)
    predictions = _cqa_records(prediction_data, reference=False)
    unknown = [i for i in predictions if i not in references]
    if unknown:
        raise _core.ResponseError(
            f"{len(unknown)} ConditionalQA prediction IDs are absent from the references: "
            f"{unknown[:5]}")
    missing = tuple(i for i in references if i not in predictions)
    empty = tuple(i for i in references if i in predictions and not predictions[i])
    # Evaluate the exact bytes that passed validation and provenance checks.
    with tempfile.TemporaryDirectory(prefix="bar-policy-cqa-validated-") as tmp, \
            warnings.catch_warnings():
        frozen_prediction = Path(tmp) / "predictions.json"
        frozen_reference = Path(tmp) / "references.json"
        frozen_prediction.write_bytes(prediction_data)
        frozen_reference.write_bytes(reference_data)
        # The native loader leaves its files to the garbage collector.
        warnings.simplefilter("ignore", ResourceWarning)
        metrics = evaluate(str(frozen_prediction), str(frozen_reference))
    return ConditionalQAResult(metrics, str(reference_path), reference_sha256, pinned,
                               evaluator_sha256, len(references), len(predictions),
                               missing, empty, _core.digest(prediction_data))


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
