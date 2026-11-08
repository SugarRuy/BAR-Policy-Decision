# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Yanru Xiao and Yifei Cai
"""Shared lower-level implementation of the BAR CLI and Python API.

The functions below were moved from ``scripts/bar.py`` and
``scripts/rulearena.py`` without changing their checks, outputs or messages.
The artifact root is now an explicit argument. This module uses only the
standard library and has no package-relative imports, so the checkout CLI can
load it by file path without changing ``sys.path`` or ``sys.modules``.
"""
import argparse
import ast
import copy
import functools
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
import tempfile
from types import SimpleNamespace


class BARError(Exception):
    """Base class of every error raised deliberately by BAR."""


class ConfigurationError(BARError, ValueError):
    """Invalid argument, unknown name or unusable output location."""


class UnsupportedError(ConfigurationError):
    """A release, variant, mode or operation that BAR does not implement."""


class AssetIntegrityError(BARError, ValueError):
    """A packaged BAR file is missing, changed or inconsistent."""


class SourceMismatchError(BARError, ValueError):
    """A user-supplied upstream source differs from its pinned identity."""


class PatchError(BARError, ValueError):
    """A distributed patch did not produce its pinned result."""


class SourceNotFoundError(BARError, FileNotFoundError):
    """A required user-supplied source directory or file is absent."""


class ResponseError(BARError, ValueError):
    """Responses passed for scoring do not match the dataset."""


class MissingResponsesError(ResponseError):
    """Batch scoring found absent records and missing ones were not allowed."""


class DependencyError(BARError, ImportError):
    """An optional dependency needed by one scorer is not installed."""


def digest(data):
    return hashlib.sha256(data).hexdigest()


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def child(root, name):
    relative = PurePosixPath(name)
    if relative.is_absolute() or ".." in relative.parts or "\\" in name:
        raise ConfigurationError(f"Unsafe relative path: {name}")
    path = root.joinpath(*relative.parts)
    if not path.resolve().is_relative_to(root.resolve()):
        raise ConfigurationError(f"Path escapes its root: {name}")
    return path


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":")).encode("utf-8")


def catalog(root):
    return read_json(root / "components.json")["components"]


def component_manifest(root, identifier):
    matches = [c for c in catalog(root) if c["id"] == identifier]
    if len(matches) != 1:
        raise ConfigurationError(f"Unknown component: {identifier}")
    return read_json(child(root, matches[0]["manifest"]))


def verify(root, locate=None, echo=None):
    """Check every inventoried file; return (file count, component count).

    ``locate`` maps an inventory name to a path. It lets an installed package
    verify its own code, which is not stored below the asset root. ``echo``
    receives the CLI's progress lines; the Python API passes none.
    """
    locate = locate or (lambda name: child(root, name))
    inventory = read_json(root / "inventory.json")["files"]
    for name, expected in inventory.items():
        path = locate(name)
        if (not path.is_file() or digest(path.read_bytes()) != expected["sha256"]
                or path.stat().st_size != expected["bytes"]):
            raise AssetIntegrityError(f"Missing or changed packaged file: {name}")
    ids = [c["id"] for c in catalog(root)]
    if len(ids) != len(set(ids)) or set(ids) != set(read_json(root / "release.json")["components"]):
        raise AssetIntegrityError("The component catalog differs from release metadata")
    actual = {str(p.relative_to(root)) for p in (root / "components").rglob("*")
              if p.is_file() and "__pycache__" not in p.parts}
    if actual != {name for name in inventory if name.startswith("components/")}:
        raise AssetIntegrityError("Component file inventory differs from the release")
    declared = set()
    for component in catalog(root):
        manifest = read_json(child(root, component["manifest"]))
        declared.update({component["manifest"], f"components/{component['id']}/README.md"})
        declared.update(manifest["payload_files"])
        for patch in manifest["patches"]:
            declared.add(patch["patch"])
            data = child(root, patch["patch"]).read_bytes()
            if digest(data) != patch["patch_sha256"]:
                raise AssetIntegrityError(f"Patch hash mismatch: {patch['patch']}")
    if actual != declared:
        raise AssetIntegrityError("Unexpected or undeclared component payload")
    if echo:
        echo(f"Verified {len(inventory)} packaged files and {len(catalog(root))} components.")
    return len(inventory), len(catalog(root))


def check_new_output(root, source, output):
    """Output checks shared by every command that writes a directory."""
    if output.exists() or output.is_symlink():
        raise ConfigurationError("Output must be a new directory.")
    if not output.parent.is_dir():
        raise ConfigurationError("Create the output's parent directory first.")
    if output.resolve().is_relative_to(source):
        raise ConfigurationError("Output must be outside the upstream source tree.")
    if output.resolve().is_relative_to(root):
        raise ConfigurationError("Output must be outside this artifact tree.")


def prepare(root, identifier, source, output, locate=None, echo=None):
    """Apply one component's existing patches/replacement to a new directory."""
    verify(root, locate, echo)
    manifest = component_manifest(root, identifier)
    replacement = manifest.get("replacement")
    if not manifest["patches"] and not replacement:
        raise UnsupportedError("This component has no portable code patch; read its status.")
    source = source.resolve(strict=True)
    output = output.absolute()
    check_new_output(root, source, output)

    staged = {}
    patches = []
    if replacement:
        name = replacement["upstream_path"]
        data = _read_source(child(source, name))
        if digest(data) != replacement["before_sha256"]:
            raise SourceMismatchError(f"Original source mismatch: {name}")
        staged[name] = data
        payload = child(root, replacement["implementation"]).read_bytes()
        if digest(payload) != replacement["after_sha256"]:
            raise AssetIntegrityError("BAR replacement hash mismatch")
    for patch in manifest["patches"]:
        name = patch["upstream_path"]
        data = _read_source(child(source, name))
        if digest(data) != patch["before_sha256"]:
            raise SourceMismatchError(f"Original source mismatch: {name}")
        patch_path = child(root, patch["patch"])
        if digest(patch_path.read_bytes()) != patch["patch_sha256"]:
            raise AssetIntegrityError(f"Distributed patch mismatch: {patch['patch']}")
        # The selected patches each address one existing file. Check headers
        # before invoking patch, so no extra target can be written.
        headers = [line for line in patch_path.read_text().splitlines()
                   if line.startswith(("--- ", "+++ "))]
        if headers != [f"--- a/{name}", f"+++ b/{name}"]:
            raise AssetIntegrityError(f"Unexpected patch targets: {patch['patch']}")
        if name in staged:
            raise UnsupportedError("Multiple patches for one file require a composed manifest.")
        staged[name] = data
        patches.append((patch, patch_path))

    with tempfile.TemporaryDirectory(prefix=".bar-prepare-", dir=output.parent) as tmp:
        tree = Path(tmp) / "revised"
        tree.mkdir()
        for name, data in staged.items():
            destination = child(tree, name)
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(payload if replacement else data)
        for patch, patch_path in patches:
            result = subprocess.run(
                ["patch", "--batch", "--fuzz=0", "-p1", "-i", str(patch_path)],
                cwd=tree, capture_output=True, text=True,
            )
            if result.returncode:
                raise PatchError(result.stdout + result.stderr)
            target = child(tree, patch["upstream_path"])
            if digest(target.read_bytes()) != patch["after_sha256"]:
                raise PatchError(f"Revised source mismatch: {patch['upstream_path']}")
        for addition in manifest.get("additional_files", []):
            data = child(root, addition["payload"]).read_bytes()
            if digest(data) != addition["sha256"]:
                raise AssetIntegrityError("Additional implementation hash mismatch")
            destination = child(tree, addition["output_path"])
            if destination.exists():
                raise AssetIntegrityError("Additional implementation would replace a patched file")
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(data)
        for name, original in staged.items():
            if child(source, name).read_bytes() != original:
                raise SourceMismatchError(f"Source changed during preparation: {name}")
        for notice in manifest.get("notices", []):
            child(tree, Path(notice).name).write_bytes(child(root, notice).read_bytes())
        receipt = {
            "component": identifier,
            "operation": ("install_bar_original_numeric_evaluator" if replacement else
                          "apply_existing_patches_to_new_copies"),
            "scientific_scope": manifest["accepted_scope"],
            "files": {name: digest(child(tree, name).read_bytes()) for name in staged},
            "original_files": {name: digest(data) for name, data in staged.items()},
            "source_repository": manifest["source_repository"],
            "additional_files": {item["output_path"]: item["sha256"]
                                 for item in manifest.get("additional_files", [])},
            "model_calls": 0,
        }
        (tree / "bar-preparation.json").write_text(json.dumps(receipt, indent=2) + "\n")
        # Reserve the output atomically; an existing file/directory is never
        # removed or overwritten, even if it appeared while checks ran.
        output.mkdir()
        try:
            for item in tree.iterdir():
                item.rename(output / item.name)
        except Exception:
            raise RuntimeError(f"Move failed; preserve and inspect partial output: {output}")
    if echo:
        echo(f"Prepared {identifier}: {output}")
    return receipt


def apply_patch_bytes(data, patch, name):
    """Apply a single-file unified diff in memory, exactly (no offset or fuzz).

    Used only where BAR also checks the result against the manifest's
    ``after_sha256``; the CLI ``prepare`` command still uses ``patch``.
    """
    lines = patch.splitlines(keepends=True)
    if [line.rstrip(b"\n") for line in lines[:2]] != [f"--- a/{name}".encode(),
                                                      f"+++ b/{name}".encode()]:
        raise PatchError(f"Unexpected patch targets for {name}")
    original = data.splitlines(keepends=True)
    result, position, index = [], 0, 2
    header = re.compile(rb"@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")
    while index < len(lines):
        match = header.match(lines[index])
        if match is None:
            raise PatchError(f"Malformed patch hunk for {name}")
        start = int(match[1])
        old_count = int(match[2]) if match[2] is not None else 1
        new_count = int(match[4]) if match[4] is not None else 1
        index += 1
        old, new = [], []
        while len(old) < old_count or len(new) < new_count:
            if index >= len(lines):
                raise PatchError(f"Truncated patch hunk for {name}")
            line = lines[index]
            index += 1
            tag, text = line[:1], line[1:]
            if tag == b" ":
                old.append(text)
                new.append(text)
            elif tag == b"-":
                old.append(text)
            elif tag == b"+":
                new.append(text)
            else:
                raise PatchError(f"Unsupported patch line for {name}")
        begin = start - 1 if old_count else start
        if begin < position or original[begin:begin + old_count] != old:
            raise PatchError(f"Patch context does not match {name}")
        result.extend(original[position:begin])
        result.extend(new)
        position = begin + old_count
    result.extend(original[position:])
    return b"".join(result)


def _read_source(path):
    try:
        return path.read_bytes()
    except FileNotFoundError as error:
        # Keep the legacy CLI diagnostic while exposing a specific API type.
        raise SourceNotFoundError(str(error)) from error


def pinned_sources(source, pins):
    """Read every pinned upstream file, rejecting the first hash mismatch."""
    sources = {}
    for pin in pins:
        data = _read_source(child(source, pin["path"]))
        if digest(data) != pin["sha256"]:
            raise SourceMismatchError(f"Original source mismatch: {pin['path']}")
        sources[pin["path"]] = data
    return sources


def unchanged_sources(source, sources, message):
    for name, data in sources.items():
        if child(source, name).read_bytes() != data:
            raise SourceMismatchError(message.format(name=name))


def tax_prompt_renderer(sources):
    """Load literal templates and the hash-checked pure native renderer only."""
    namespace = {}
    for name in ["tax/prompt.py", "tax/auto_test.py"]:
        for node in ast.parse(sources[name].decode("utf-8")).body:
            if isinstance(node, ast.Assign) and len(node.targets) == 1:
                target = node.targets[0]
                if isinstance(target, ast.Name):
                    try:
                        namespace[target.id] = ast.literal_eval(node.value)
                    except (ValueError, TypeError):
                        pass
    nodes = [
        node for node in ast.parse(sources["tax/auto_test.py"].decode("utf-8")).body
        if isinstance(node, ast.FunctionDef) and node.name == "build_prompt"
    ]
    if len(nodes) != 1:
        raise SourceMismatchError("Expected one pinned native Tax prompt renderer.")
    namespace["args"] = SimpleNamespace(distractor=False, textual=False)
    # No upstream imports, experiment entrypoints, model clients or graders run.
    exec(compile(ast.Module(body=nodes, type_ignores=[]),
                 "<pinned-native-tax-renderer>", "exec"), namespace)
    return namespace["system_prompt"], namespace["build_prompt"]


def tax_rows(root, spec, sources):
    """Join the 300 scoped Tax references with unchanged native inputs."""
    reference_bytes = child(root, spec["reference_file"]).read_bytes()
    if digest(reference_bytes) != spec["reference_sha256"]:
        raise AssetIntegrityError("Reference payload mismatch.")
    references = json.loads(reference_bytes)
    native = {name: json.loads(data) for name, data in sources.items()
              if name.endswith(".json")}
    system, render = tax_prompt_renderer(sources)
    rows = []
    seen = set()
    seen_locations = set()
    for reference in references["records"]:
        identifier = reference["case_id"]
        if identifier in seen:
            raise AssetIntegrityError(f"Duplicate case ID: {identifier}")
        seen.add(identifier)
        name, index = reference["source_file"], reference["source_index"]
        if name not in native or not isinstance(index, int) or not 0 <= index < len(native[name]):
            raise SourceMismatchError(f"Invalid source location: {identifier}")
        level = Path(name).stem
        if identifier != f"tax/{level}/{index}":
            raise AssetIntegrityError(f"Case ID/source location mismatch: {identifier}")
        location = (name, index)
        if location in seen_locations:
            raise AssetIntegrityError(f"Duplicate source location: {identifier}")
        seen_locations.add(location)
        case = native[name][index]
        if digest(json.dumps(case, sort_keys=True).encode()) != reference["case_sha256"]:
            raise SourceMismatchError(f"Case/reference mismatch: {identifier}")
        changed = reference["original_signed_answer"] != reference["line22_repaired_signed_answer"]
        if changed != reference["changed"]:
            raise AssetIntegrityError(f"Changed-reference flag mismatch: {identifier}")
        rows.append({
            "id": identifier,
            "source_file": name,
            "source_index": index,
            "case_sha256": reference["case_sha256"],
            "native_case": case,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": render(copy.deepcopy(case["dict"])).replace("$example", "")},
            ],
            "original_reference": reference["original_signed_answer"],
            "revised_reference": reference["line22_repaired_signed_answer"],
            "reference_changed": changed,
            "remaining_dependencies": reference["other_unresolved_dependencies"],
        })
    all_locations = {(name, i) for name, cases in native.items() for i in range(len(cases))}
    if len(rows) != spec["record_count"] or seen_locations != all_locations:
        raise SourceMismatchError("Reference pairs do not cover the complete pinned dataset.")
    if sum(row["reference_changed"] for row in rows) != spec["changed_reference_count"]:
        raise AssetIntegrityError("Changed-reference count mismatch.")
    return rows, references["sign_convention"]


def tax_dataset(root, source, output, locate=None, echo=None):
    verify(root, locate, echo)
    manifest = component_manifest(root, "rulearena-tax")
    spec = manifest["dataset"]
    source = source.resolve(strict=True)
    output = output.absolute()
    check_new_output(root, source, output)
    sources = pinned_sources(source, spec["source_files"])
    rows, sign_convention = tax_rows(root, spec, sources)
    content = "".join(json.dumps(row, ensure_ascii=False, allow_nan=False) + "\n"
                      for row in rows).encode("utf-8")
    receipt = {
        **spec,
        "operation": "join_scoped_references_with_unchanged_native_inputs",
        "output_file": "data.jsonl",
        "output_sha256": digest(content),
        "sign_convention": sign_convention,
        "not_a_complete_ground_truth_repair": True,
        "model_calls": 0,
    }
    unchanged_sources(source, sources, "Source changed during preparation: {name}")
    # Reserve a fresh directory only after input and row checks succeed.
    output.mkdir()
    (output / "data.jsonl").write_bytes(content)
    (output / "dataset.json").write_text(json.dumps(receipt, indent=2) + "\n")
    if echo:
        echo(f"Prepared {spec['asset_name']}: {len(rows)} cases, "
             f"{spec['changed_reference_count']} revised references in {output}")
    return output


def literals(text, names):
    values = {}
    for node in ast.parse(text).body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id in names:
                    values[target.id] = ast.literal_eval(node.value)
    if values.keys() != set(names):
        raise SourceMismatchError("Native prompt literals missing")
    return values


@functools.lru_cache(maxsize=8)
def _airline_template(auto_test):
    # Parsing is deterministic for the given bytes; cache it across cases.
    return literals(auto_test.decode(), {"system_prompt", "prompt_template"})


def airline_messages(sources, case, objective=None):
    template = _airline_template(sources["airline/auto_test.py"])
    question = case["prompt"]
    if objective:
        question += "\n\n" + objective
    prompt = template["prompt_template"].replace(
        "$reference_rules", sources["airline/reference_rules.txt"].decode())
    prompt = prompt.replace("$question_prompt", question).replace("$example_prompt", "")
    return [{"role": "system", "content": template["system_prompt"]},
            {"role": "user", "content": prompt}]


def airline_objective(root):
    path = root / "components/rulearena-airline-objective/objective.txt"
    return path.read_text(encoding="utf-8").strip()


def objective_rows(root, manifest, sources):
    directory = root / "components/rulearena-airline-objective"
    objective = airline_objective(root)
    references = [json.loads(line) for line in
                  (directory / "references.jsonl").read_text(encoding="utf-8").splitlines()]
    rows = []
    native = {name: [json.loads(line) for line in data.decode().splitlines()]
              for name, data in sources.items() if name.endswith(".jsonl")}
    expected_locations = {(name, i) for name, records in native.items()
                          for i in range(len(records))}
    locations = set()
    for reference in references:
        name, index = reference["source_file"], reference["source_index"]
        if (name, index) not in expected_locations or (name, index) in locations:
            raise AssetIntegrityError("Invalid or duplicate Airline reference location")
        locations.add((name, index))
        case = native[name][index]
        if digest(canonical(case)) != reference["case_sha256"]:
            raise SourceMismatchError("Airline case binding mismatch")
        if reference["id"] != f"airline/{name.split('/')[-1][:-6]}/{index}":
            raise AssetIntegrityError("Airline ID/source mismatch")
        original = airline_messages(sources, case)
        amended = airline_messages(sources, case, objective)
        if (digest(canonical(original)) != reference["original_messages_sha256"]
                or digest(canonical(amended)) != reference["revised_messages_sha256"]):
            raise SourceMismatchError("Airline prompt binding mismatch")
        if reference["original_reference"] != reference["revised_reference"]:
            raise AssetIntegrityError("The objective component must retain reference amounts")
        rows.append({**reference, "native_case": case,
                     "original_messages": original, "messages": amended})
    if locations != expected_locations or len(rows) != 300:
        raise SourceMismatchError("Airline references must cover all 300 source cases")
    return rows


def nba_rows(root, manifest, sources):
    spec = read_json(root / "components/rulearena-nba-location-errata/errata.json")
    changes = {(x["source_file"], x["source_index_zero_based"]): x for x in spec["changes"]}
    rows = []
    used = set()
    for name, data in sorted(sources.items()):
        if not name.startswith("nba/annotated_problems/"):
            continue
        for index, original in enumerate(json.loads(data)):
            revised = copy.deepcopy(original)
            edit = changes.get((name, index))
            if edit:
                if (digest(canonical(original)) != edit["record_sha256"]
                        or original[edit["field"]] != edit["old"]):
                    raise SourceMismatchError("NBA record/old-value binding mismatch")
                revised[edit["field"]] = edit["new"]
                used.add((name, index))
            rows.append({
                "id": f"nba/{name.split('/')[-1][:-5]}/{index}",
                "source_file": name, "source_index": index,
                "case_sha256": digest(canonical(original)),
                "original_record": original, "revised_record": revised,
                "changed": bool(edit), "changed_field": edit["field"] if edit else None,
            })
    if len(rows) != 216 or used != set(changes):
        raise SourceMismatchError("NBA errata must cover exactly two of 216 source records")
    return rows


RULEARENA_BUILDERS = {
    "rulearena-airline-objective": objective_rows,
    "rulearena-nba-location-errata": nba_rows,
}


def rulearena_dataset(root, identifier, source, output, locate=None, echo=None):
    verify(root, locate, echo)
    manifest = read_json(root / "components" / identifier / "component.json")
    source = source.resolve(strict=True)
    output = output.absolute()
    if output.exists() or output.is_symlink() or not output.parent.is_dir():
        raise ConfigurationError("Output must be a new directory under an existing parent")
    if output.resolve().is_relative_to(source) or output.resolve().is_relative_to(root):
        raise ConfigurationError("Output must be outside source and artifact trees")
    sources = pinned_sources(source, manifest["source_files"])
    rows = RULEARENA_BUILDERS[identifier](root, manifest, sources)
    content = b"".join(canonical(row) + b"\n" for row in rows)
    unchanged_sources(source, sources, "Source changed during dataset construction")
    receipt = {
        "component": identifier, "source_repository": manifest["source_repository"],
        "scientific_scope": manifest["accepted_scope"],
        "remaining_limits": manifest["remaining_limits"],
        "record_count": len(rows), "data_sha256": digest(content),
        "model_calls": 0,
    }
    output.mkdir()
    (output / "data.jsonl").write_bytes(content)
    (output / "dataset.json").write_text(json.dumps(receipt, indent=2) + "\n")
    if echo:
        echo(f"Prepared {identifier}: {len(rows)} source-bound records in {output}")
    return output


def dataset(root, identifier, source, output, locate=None, echo=None):
    """Write one component's dataset directory; return its absolute path."""
    if identifier in RULEARENA_BUILDERS:
        return rulearena_dataset(root, identifier, source, output, locate, echo)
    if identifier != "rulearena-tax":
        raise UnsupportedError("This component has no dataset builder. "
                               "Scorer corrections retain the upstream dataset labels.")
    return tax_dataset(root, source, output, locate, echo)


CLI_DESCRIPTION = "Inspect BAR artifacts, prepare revised data, and apply pinned code patches."


def cli_main(root, locate=None, argv=None, prog=None):
    """Command-line interface shared by scripts/bar.py and ``bar-policy``."""
    parser = argparse.ArgumentParser(prog=prog, description=CLI_DESCRIPTION)
    actions = parser.add_subparsers(dest="command", required=True)
    actions.add_parser("list")
    actions.add_parser("verify")
    patch = actions.add_parser("prepare")
    patch.add_argument("component")
    patch.add_argument("--source", type=Path, required=True)
    patch.add_argument("--output", type=Path, required=True)
    data = actions.add_parser("dataset")
    data.add_argument("component")
    data.add_argument("--source", type=Path, required=True)
    data.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "list":
            for entry in catalog(root):
                print(f"{entry['id']}\t{entry['kind']}\t{entry['payload_status']}")
        elif args.command == "verify":
            verify(root, locate, echo=print)
        elif args.command == "prepare":
            prepare(root, args.component, args.source, args.output, locate, echo=print)
        else:
            dataset(root, args.component, args.source, args.output, locate, echo=print)
    except (ValueError, OSError, RuntimeError) as error:
        raise SystemExit(str(error))
