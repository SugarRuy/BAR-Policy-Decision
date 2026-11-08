# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Yanru Xiao and Yifei Cai
"""Integrated RuleArena Tax and Airline policy-decision datasets.

Model-visible inputs are the canonical native messages built by the shared
CLI implementation. Each message is also decomposed into verbatim segments
whose concatenation is the message content; BAR does not rewrite or split
native text beyond the native template boundaries. References, flags and the
raw native record are kept outside the model-visible input.
"""
import copy
from dataclasses import dataclass
from functools import partial
from types import MappingProxyType
from typing import Mapping, Optional, Tuple

from . import _assets, _core, _sources, scoring

INSTRUCTION, POLICY, CASE, QUESTION, AMENDMENT = (
    "instruction", "policy", "case", "question", "amendment"
)

_DATASETS = {
    "rulearena-tax": {
        "description": "RuleArena Tax, 300 native cases with the scoped line-22 reference revision.",
        "default_variant": "revised",
        "variants": {
            "revised": "Native inputs; line-22 floor-revised references.",
            "original": "Native inputs; original RuleArena references.",
        },
        "modes": ("zero-shot",),
        "default_mode": "zero-shot",
        "default_scorer": scoring.TAX_SCORER,
        "scorers": (scoring.TAX_SCORER, scoring.TAX_NATIVE_SCORER),
        "unsupported_modes": {
            "one-shot": "the native one-shot example is not built by BAR",
            "textual": "the native textual forms are not built by BAR",
            "distractor": "the native distractor forms are not built by BAR",
        },
        "components": ("rulearena-tax",),
    },
    "rulearena-airline": {
        "description": "RuleArena Airline, 300 native cases.",
        "default_variant": "revised",
        "variants": {
            "revised": "Integrated: minimum-cost objective amendment, prompt errata (no effect "
                       "in Markdown zero-shot; verified) and exact amount scorer.",
            "original-input": "Native Markdown zero-shot inputs without the objective amendment; "
                              "unchanged references; exact amount scorer. The native substring "
                              "scorer is not exposed.",
        },
        "modes": ("markdown-zero-shot",),
        "default_mode": "markdown-zero-shot",
        "default_scorer": scoring.AIRLINE_SCORER,
        "scorers": (scoring.AIRLINE_SCORER,),
        "unsupported_modes": {
            "markdown-one-shot": "the objective builder implements Markdown zero-shot only",
            "textual-zero-shot": "the objective builder implements Markdown zero-shot only",
            "textual-one-shot": "the objective builder implements Markdown zero-shot only",
        },
        "components": ("rulearena-airline-objective", "rulearena-airline-prompt-errata",
                       "rulearena-airline-scoring"),
    },
}

_NOT_DATASETS = {
    "rulearena-nba": "No RuleArena NBA policy-decision dataset with model-visible messages is "
                     "implemented. Use component_rows('rulearena-nba-location-errata', source) "
                     "for the 216 original/revised raw records, or prepare_component(...) for the "
                     "two JSON patches.",
    "rulearena-nba-location-errata": "This component has no policy-decision dataset; use "
                                     "component_rows(...) for its raw records.",
    "legalbench-sara-numeric": "BAR distributes no SARA inputs or labels; use score_sara_numeric "
                               "with your own pinned LegalBench data.",
    "conditionalqa": "BAR distributes no ConditionalQA inputs or labels; use score_conditionalqa "
                     "or score_conditionalqa_file with your pinned checkout.",
    "conditionalqa-scoring": "This scorer component has no dataset; use score_conditionalqa.",
    "rulearena-airline-objective": "Load the integrated dataset 'rulearena-airline', or use "
                                   "component_rows('rulearena-airline-objective', source) for the "
                                   "component's own rows.",
    "rulearena-airline-prompt-errata": "Load the integrated dataset 'rulearena-airline'.",
    "rulearena-airline-scoring": "Load the integrated dataset 'rulearena-airline'.",
}


def dataset_capabilities():
    result = {}
    for name, spec in _DATASETS.items():
        result[name] = {
            "description": spec["description"], "default_variant": spec["default_variant"],
            "variants": dict(spec["variants"]), "modes": list(spec["modes"]),
            "default_mode": spec["default_mode"],
            "default_scorer": spec["default_scorer"],
            "scorers": list(spec["scorers"]),
            "unsupported_modes": dict(spec["unsupported_modes"]),
            "components": list(spec["components"]),
        }
    return result


@dataclass(frozen=True)
class Segment:
    """A verbatim slice of one model-visible message.

    ``roles`` is a subset of ``instruction``, ``policy``, ``case``,
    ``question`` and ``amendment``. A segment with several roles is native text that mixes
    them; BAR keeps it whole rather than splitting or paraphrasing it.
    """
    message_index: int
    roles: Tuple[str, ...]
    text: str
    origin: str
    provenance: Tuple[Mapping, ...]
    note: Optional[str] = None

    def __post_init__(self):
        object.__setattr__(self, "provenance", tuple(
            MappingProxyType(copy.deepcopy(dict(p))) for p in self.provenance
        ))

    def to_dict(self):
        return {"message_index": self.message_index, "roles": list(self.roles),
                "text": self.text, "origin": self.origin,
                "provenance": [copy.deepcopy(dict(p)) for p in self.provenance], "note": self.note}


class Example:
    """One case: model-visible input, separate references and provenance."""

    def __init__(self, identifier, messages, segments, reference, references, metadata,
                 source, source_record, scorer):
        self._id = identifier
        self._messages = messages
        self._segments = tuple(segments)
        self._reference = reference
        self._references = references
        self._metadata = metadata
        self._source = source
        self._source_record = source_record
        self._scorer = scorer

    @property
    def id(self):
        return self._id

    @property
    def reference(self):
        """The selected version's reference, read-only."""
        return self._reference

    @property
    def segments(self):
        return self._segments

    def __repr__(self):
        return f"Example({self.id!r})"

    @property
    def messages(self):
        """Canonical model-visible chat messages (a fresh copy)."""
        return copy.deepcopy(self._messages)

    def model_input(self):
        """Everything a model may see, and nothing else."""
        return {"messages": self.messages}

    def _with(self, role):
        return tuple(s for s in self.segments if role in s.roles)

    @property
    def policy(self):
        return self._with(POLICY)

    @property
    def case(self):
        return self._with(CASE)

    @property
    def question(self):
        """Verbatim task directives, including any selected BAR objective amendment.

        May be empty when policy/case already state the task without a separate
        directive. Role views may overlap; use messages for canonical input.
        """
        return self._with(QUESTION)

    @property
    def instructions(self):
        return self._with(INSTRUCTION)

    @property
    def amendments(self):
        return self._with(AMENDMENT)

    @property
    def references(self):
        """Original and revised references and whether they differ (not model-visible)."""
        return copy.deepcopy(self._references)

    @property
    def metadata(self):
        """Per-case flags and remaining dependencies (not model-visible)."""
        return copy.deepcopy(self._metadata)

    @property
    def source(self):
        """Source location and hashes of the native case."""
        return copy.deepcopy(self._source)

    @property
    def source_record(self):
        """The complete raw native record. Not model-visible; may contain annotations."""
        return copy.deepcopy(self._source_record)

    def score(self, response):
        """Score one response against this example's reference."""
        return self._scorer(response, self.reference)

    def to_dict(self, include_source_record=False):
        record = {"id": self.id, "input": {"messages": self.messages,
                                           "segments": [s.to_dict() for s in self.segments]},
                  "reference": self.reference, "references": self.references,
                  "metadata": self.metadata, "source": self.source}
        if include_source_record:
            record["source_record"] = self.source_record
        return record


class Dataset:
    """An integrated, versioned dataset configuration (read-only)."""

    def __init__(self, name, release, variant, mode, examples, info, scorer_id):
        self._name = name
        self._release = release
        self._variant = variant
        self._mode = mode
        self._examples = tuple(examples)
        self._index = {e.id: e for e in self._examples}
        if len(self._index) != len(self._examples):
            raise _core.AssetIntegrityError("Duplicate example IDs")
        self._info = info
        self._scorer_id = scorer_id

    @property
    def name(self):
        return self._name

    @property
    def release(self):
        return self._release

    @property
    def variant(self):
        return self._variant

    @property
    def mode(self):
        return self._mode

    @property
    def scorer(self):
        return self._scorer_id

    def __repr__(self):
        return (f"Dataset({self.name!r}, release={self.release!r}, variant={self.variant!r}, "
                f"mode={self.mode!r}, examples={len(self)})")

    def __len__(self):
        return len(self._examples)

    def __iter__(self):
        return iter(self._examples)

    def __getitem__(self, key):
        if isinstance(key, str):
            if key not in self._index:
                raise KeyError(key)
            return self._index[key]
        return self._examples[key]

    @property
    def ids(self):
        return tuple(self._index)

    @property
    def info(self):
        """Configuration, applied components, amendments, provenance and limits."""
        return copy.deepcopy(self._info)

    def score(self, responses, *, allow_missing=False):
        """Score ``{id: response}`` with the full dataset as denominator.

        Unknown IDs and non-string responses raise. Absent IDs raise
        :class:`MissingResponsesError` unless ``allow_missing=True``, in which
        case they count as not accepted and are listed in ``missing``.
        """
        if not isinstance(responses, Mapping):
            raise TypeError("responses must be a mapping from example ID to response text")
        unknown = [key for key in responses if key not in self._index]
        if unknown:
            raise _core.ResponseError(f"{len(unknown)} response IDs are not in {self.name}: "
                                      f"{sorted(map(str, unknown))[:5]}")
        for value in responses.values():
            scoring._check_response(value)
        missing = tuple(i for i in self._index if i not in responses)
        if missing and not allow_missing:
            raise _core.MissingResponsesError(
                f"{len(missing)} of {len(self)} examples have no response (first: "
                f"{list(missing[:5])}); pass allow_missing=True to count them as not accepted")
        items = {i: (self._index[i].score(responses[i]) if i in responses else None)
                 for i in self._index}
        accepted = sum(1 for item in items.values() if item is not None and item.accepted)
        return scoring.BatchScore(self.name, self.variant, self.scorer, len(self), accepted,
                                  missing, items, release=self.release, mode=self.mode)


def _upstream(manifest, path, sources, **extra):
    repository, revision = _sources.repository(manifest)
    return MappingProxyType({"repository": repository, "revision": revision, "path": path,
                             "sha256": _core.digest(sources[path]), **extra})


def _split_once(text, marker):
    if text.count(marker) != 1:
        raise _core.SourceMismatchError(f"Native template must contain {marker} exactly once")
    return text.split(marker)


def _checked(messages, segments, identifier):
    for index, message in enumerate(messages):
        joined = "".join(s.text for s in segments if s.message_index == index)
        if joined != message["content"]:
            raise _core.AssetIntegrityError(
                f"Segments do not reproduce message {index} of {identifier}")
    return [s for s in segments if s.text]


def _component_info(identifier, role, applied, effect=None):
    info = _assets_component(identifier)
    info.update({"role": role, "applied": applied})
    if effect:
        info["model_visible_effect"] = effect
    return info


def _assets_component(identifier):
    from .components import get_component
    return get_component(identifier).provenance()


def _tax(source, variant, scorer):
    root = _assets.root()
    manifest = _assets.manifest("rulearena-tax")
    spec = manifest["dataset"]
    expected = manifest["source_repository"]
    source = _sources.source_root(source, expected)
    sources = _sources.read_pins(source, spec["source_files"], expected)
    rows, sign_convention = _core.tax_rows(root, spec, sources)
    _sources.unchanged(source, sources)
    template = _core.literals(sources["tax/auto_test.py"].decode("utf-8"),
                              {"system_prompt", "prompt_template"})
    before, rest = _split_once(template["prompt_template"], "$example")
    between, after = _split_once(rest, "$forms")
    examples = []
    for row in rows:
        messages = row["messages"]
        user = messages[1]["content"]
        head = before + between
        if not (user.startswith(head) and user.endswith(after)
                and len(user) >= len(head) + len(after)):
            raise _core.AssetIntegrityError(f"Unexpected native Tax prompt layout: {row['id']}")
        forms = user[len(head):len(user) - len(after)]
        auto_test = "tax/auto_test.py"
        segments = _checked(messages, [
            Segment(0, (INSTRUCTION,), messages[0]["content"], "upstream",
                    (_upstream(manifest, auto_test, sources, symbol="system_prompt"),)),
            Segment(1, (INSTRUCTION, QUESTION), before, "upstream",
                    (_upstream(manifest, auto_test, sources, symbol="prompt_template",
                               part="text before $example"),)),
            Segment(1, (INSTRUCTION,), between, "upstream",
                    (_upstream(manifest, auto_test, sources, symbol="prompt_template",
                               part="text between $example and $forms"),),
                    "Zero-shot: the native $example placeholder is empty."),
            Segment(1, (POLICY, CASE), forms, "upstream",
                    (_upstream(manifest, "tax/prompt.py", sources,
                               symbol="form templates selected by build_prompt"),
                     _upstream(manifest, row["source_file"], sources,
                               record=row["source_index"], field="dict",
                               record_sha256=row["case_sha256"])),
                    "Rendered by the pinned native build_prompt: the case values are "
                    "substituted into the policy forms, so policy and case are one native "
                    "text. BAR does not split it."),
            Segment(1, (INSTRUCTION, QUESTION), after, "upstream",
                    (_upstream(manifest, auto_test, sources, symbol="prompt_template",
                               part="text after $forms"),)),
        ], row["id"])
        references = {"original": row["original_reference"], "revised": row["revised_reference"],
                      "changed": row["reference_changed"]}
        reference = references["revised" if variant == "revised" else "original"]
        examples.append(Example(
            row["id"], messages, segments, reference, references,
            {"remaining_dependencies": row["remaining_dependencies"]},
            {**_upstream(manifest, row["source_file"], sources, record=row["source_index"]),
             "case_sha256": row["case_sha256"]},
            row["native_case"], partial(scoring.score_tax_response, scorer=scorer)))
    is_native = scorer == scoring.TAX_NATIVE_SCORER
    info = {
        "components": [_component_info("rulearena-tax", "reference revision",
                                       variant == "revised")],
        "amendments": [],
        "scorer": {
            "id": scorer,
            "kind": ("original/native RuleArena Tax scoring" if is_native
                     else "BAR complete numeric parsing with native sign and tolerance"),
            "implementation": ("decode_tax and tax_accept in scripts/reproduce_results.py"
                               if is_native else "src/bar_policy/scoring.py"),
            "is_repair": not is_native,
            "answer_selection": ("first matching native final-answer pattern" if is_native
                                 else "first native answer phrase; reject an invalid amount"),
        },
        "reference_kind": ("line22_repaired_signed_answer" if variant == "revised"
                           else "original_signed_answer"),
        "record_count": len(examples),
        "changed_references": sum(e._references["changed"] for e in examples),
        "sign_convention": sign_convention,
        "dependency_definitions": copy.deepcopy(spec["dependency_definitions"]),
        "input_contract": spec["input_contract"],
        "question_segments": "Native task directives before and after the rendered forms.",
        "accepted_scope": manifest["accepted_scope"],
        "remaining_limits": manifest["remaining_limits"],
        "source": {"repository": expected, "files": copy.deepcopy(spec["source_files"])},
        "not_complete_ground_truth_certification": True,
        "model_calls": 0,
    }
    return examples, info, scorer


def _verify_errata_no_effect(sources, rows, objective):
    """Apply the prompt errata in memory and prove Markdown zero-shot is unchanged."""
    manifest = _assets.manifest("rulearena-airline-prompt-errata")
    patched = dict(sources)
    applied = []
    for patch in manifest["patches"]:
        name = patch["upstream_path"]
        if _core.digest(sources[name]) != patch["before_sha256"]:
            raise _core.SourceMismatchError(f"Original source mismatch: {name}")
        data = _assets.read_verified(patch["patch"])
        if _core.digest(data) != patch["patch_sha256"]:
            raise _core.AssetIntegrityError(f"Distributed patch mismatch: {patch['patch']}")
        revised = _core.apply_patch_bytes(patched[name], data, name)
        if _core.digest(revised) != patch["after_sha256"]:
            raise _core.PatchError(f"Revised source mismatch: {name}")
        patched[name] = revised
        applied.append({"patch": patch["patch"], "upstream_path": name,
                        "after_sha256": patch["after_sha256"]})
    for row in rows:
        if _core.airline_messages(patched, row["native_case"], objective) != row["messages"]:
            raise _core.PatchError(
                f"Prompt errata would change Markdown zero-shot input {row['id']}; "
                "refusing to describe them as having no effect")
    return applied


def _airline(source, variant, scorer):
    root = _assets.root()
    manifest = _assets.manifest("rulearena-airline-objective")
    expected = manifest["source_repository"]
    source = _sources.source_root(source, expected)
    sources = _sources.read_pins(source, manifest["source_files"], expected)
    rows = _core.objective_rows(root, manifest, sources)
    _sources.unchanged(source, sources)
    objective = _core.airline_objective(root)
    revised = variant == "revised"
    errata = _verify_errata_no_effect(sources, rows, objective) if revised else None
    template = _core.literals(sources["airline/auto_test.py"].decode(),
                              {"system_prompt", "prompt_template"})
    head, rest = _split_once(template["prompt_template"], "$reference_rules")
    middle, rest = _split_once(rest, "$example_prompt")
    lead, tail = _split_once(rest, "$question_prompt")
    policy = sources["airline/reference_rules.txt"].decode()
    objective_path = "components/rulearena-airline-objective/objective.txt"
    amendment = MappingProxyType({"origin": "bar", "component": "rulearena-airline-objective",
                                  "path": objective_path,
                                  "sha256": _assets.inventory_entry(objective_path)["sha256"],
                                  "kind": "objective amendment"})
    expected_counts = manifest["dataset"]
    examples = []
    for row in rows:
        messages = row["messages"] if revised else row["original_messages"]
        auto_test = "airline/auto_test.py"
        parts = [
            Segment(0, (INSTRUCTION, QUESTION), messages[0]["content"], "upstream",
                    (_upstream(manifest, auto_test, sources, symbol="system_prompt"),)),
            Segment(1, (INSTRUCTION,), head, "upstream",
                    (_upstream(manifest, auto_test, sources, symbol="prompt_template",
                               part="text before $reference_rules"),)),
            Segment(1, (POLICY,), policy, "upstream",
                    (_upstream(manifest, "airline/reference_rules.txt", sources),),
                    "Markdown policy."),
            Segment(1, (INSTRUCTION,), middle, "upstream",
                    (_upstream(manifest, auto_test, sources, symbol="prompt_template",
                               part="text between $reference_rules and $example_prompt"),)),
            Segment(1, (INSTRUCTION,), lead, "upstream",
                    (_upstream(manifest, auto_test, sources, symbol="prompt_template",
                               part="text between $example_prompt and $question_prompt"),),
                    "Zero-shot: the native $example_prompt placeholder is empty."),
            Segment(1, (CASE,), row["native_case"]["prompt"], "upstream",
                    (_upstream(manifest, row["source_file"], sources, record=row["source_index"],
                               field="prompt", record_sha256=row["case_sha256"]),),
                    "Native field 'prompt' (named question_prompt in airline/auto_test.py); "
                    "the task itself is stated by the native instructions."),
        ]
        if revised:
            parts.append(Segment(1, (AMENDMENT, INSTRUCTION, QUESTION), "\n\n" + objective, "bar", (amendment,),
                                 "BAR minimum-cost objective, appended after the native case "
                                 "text with a blank line by the objective component."))
        parts.append(Segment(1, (INSTRUCTION, QUESTION), tail, "upstream",
                             (_upstream(manifest, auto_test, sources, symbol="prompt_template",
                                        part="text after $question_prompt"),)))
        segments = _checked(messages, parts, row["id"])
        references = {"original": row["original_reference"], "revised": row["revised_reference"],
                      "changed": row["reference_changed"]}
        metadata = {key: row[key] for key in (
            "allocation_sensitive", "allocation_minimum", "allocation_maximum",
            "listed_order_reference", "pe_dash_case", "original_messages_sha256",
            "revised_messages_sha256")}
        metadata["objective_amended"] = revised
        examples.append(Example(
            row["id"], messages, segments, row["revised_reference"], references, metadata,
            {**_upstream(manifest, row["source_file"], sources, record=row["source_index"]),
             "source_id": row["source_id"], "case_sha256": row["case_sha256"]},
            row["native_case"], scoring.score_airline_response))
    counts = {
        "allocation_sensitive": sum(e._metadata["allocation_sensitive"] for e in examples),
        "listed_order_above_minimum": sum(
            e._metadata["listed_order_reference"] > e._metadata["allocation_minimum"]
            for e in examples),
        "pe_dash_cases": sum(e._metadata["pe_dash_case"] for e in examples),
        "changed_references": sum(e._references["changed"] for e in examples),
    }
    if any(counts[key] != expected_counts[key] for key in counts):
        raise _core.AssetIntegrityError(f"Airline flag counts differ from the manifest: {counts}")
    errata_effect = ("none in markdown-zero-shot (verified for all 300 inputs); the errata "
                     "change only the one-shot example and the textual policy")
    info = {
        "components": [
            _component_info("rulearena-airline-objective",
                            "input amendment and source-bound reference records", revised,
                            "adds the minimum-cost objective" if revised else None),
            _component_info("rulearena-airline-prompt-errata", "prompt errata", revised,
                            errata_effect if revised else None),
            _component_info("rulearena-airline-scoring", "amount scorer", True),
        ],
        "amendments": ([{"component": "rulearena-airline-objective", "kind": "objective amendment",
                         "text": objective, "changes_model_visible_input": True,
                         "placement": "after the native case text, before the native "
                                      "instruction, separated by a blank line"}]
                       if revised else []),
        "prompt_errata": ({"applied_in_memory": errata, "model_visible_effect": errata_effect}
                          if revised else None),
        "scorer": {"id": scoring.AIRLINE_SCORER, "kind": "BAR exact terminal-amount scorer",
                   "implementation": "components/rulearena-airline-scoring/evaluator.py",
                   "is_repair": True},
        "reference_kind": "native calculator amount (unchanged by BAR)",
        "record_count": len(examples),
        "flag_counts": counts,
        "question_segments": "Native system and template task directives, plus the BAR "
                             "minimum-cost objective when the revised variant is selected.",
        "accepted_scope": {c: _assets.manifest(c)["accepted_scope"]
                           for c in _DATASETS["rulearena-airline"]["components"]},
        "remaining_limits": {c: _assets.manifest(c)["remaining_limits"]
                             for c in _DATASETS["rulearena-airline"]["components"]},
        "source": {"repository": expected, "files": copy.deepcopy(manifest["source_files"])},
        "not_complete_ground_truth_certification": True,
        "model_calls": 0,
    }
    return examples, info, scoring.AIRLINE_SCORER


_BUILDERS = {"rulearena-tax": _tax, "rulearena-airline": _airline}


def load_dataset(name, source, *, release=_assets.ASSET_RELEASE, variant=None, mode=None,
                 scorer=None):
    """Load an integrated, versioned policy-decision dataset.

    ``source`` is the local root of the pinned upstream checkout. The default
    ``variant`` is the final integrated revised configuration. Unsupported
    releases, variants, modes and scorers raise before any source is read.
    Tax defaults to ``rulearena-tax-numeric-v1``; select
    ``rulearena-tax-native`` to reproduce published scores.
    """
    if not isinstance(name, str):
        raise _core.ConfigurationError("dataset name must be a string")
    if name in _NOT_DATASETS:
        raise _core.UnsupportedError(_NOT_DATASETS[name])
    if name not in _DATASETS:
        raise _core.ConfigurationError(
            f"Unknown dataset {name!r}; available: {', '.join(_DATASETS)}")
    _assets.check_release(release)
    spec = _DATASETS[name]
    variant = spec["default_variant"] if variant is None else variant
    mode = spec["default_mode"] if mode is None else mode
    scorer = spec["default_scorer"] if scorer is None else scorer
    for label, value in (("variant", variant), ("mode", mode), ("scorer", scorer)):
        if not isinstance(value, str):
            raise _core.ConfigurationError(f"{label} must be a string, not {type(value).__name__}")
    if variant not in spec["variants"]:
        raise _core.ConfigurationError(
            f"Unknown variant {variant!r} for {name}; available: {', '.join(spec['variants'])}")
    if mode in spec["unsupported_modes"]:
        raise _core.UnsupportedError(
            f"Mode {mode!r} is not implemented for {name}: {spec['unsupported_modes'][mode]}. "
            f"BAR makes no correction claim for it. Supported: {', '.join(spec['modes'])}.")
    if mode not in spec["modes"]:
        raise _core.ConfigurationError(
            f"Unknown mode {mode!r} for {name}; supported: {', '.join(spec['modes'])}")
    if scorer not in spec["scorers"]:
        raise _core.UnsupportedError(
            f"Unsupported scorer {scorer!r} for {name}; supported: {', '.join(spec['scorers'])}")
    _assets.verify()
    examples, info, scorer = _BUILDERS[name](source, variant, scorer)
    info.update({"dataset": name, "release": release, "variant": variant, "mode": mode,
                 "variant_description": spec["variants"][variant]})
    return Dataset(name, release, variant, mode, examples, info, scorer)
