#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Yanru Xiao and Yifei Cai
"""Inspect BAR artifacts, prepare revised data, and apply pinned code patches."""
import argparse
import ast
import copy
import hashlib
import json
from pathlib import Path, PurePosixPath
import subprocess
import tempfile
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]


def digest(data):
    return hashlib.sha256(data).hexdigest()


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def child(root, name):
    relative = PurePosixPath(name)
    if relative.is_absolute() or ".." in relative.parts or "\\" in name:
        raise ValueError(f"Unsafe relative path: {name}")
    path = root.joinpath(*relative.parts)
    if not path.resolve().is_relative_to(root.resolve()):
        raise ValueError(f"Path escapes its root: {name}")
    return path


def catalog():
    return read_json(ROOT / "components.json")["components"]


def verify():
    inventory = read_json(ROOT / "inventory.json")["files"]
    for name, expected in inventory.items():
        path = child(ROOT, name)
        if (not path.is_file() or digest(path.read_bytes()) != expected["sha256"]
                or path.stat().st_size != expected["bytes"]):
            raise ValueError(f"Missing or changed packaged file: {name}")
    ids = [c["id"] for c in catalog()]
    if len(ids) != len(set(ids)) or set(ids) != set(read_json(ROOT / "release.json")["components"]):
        raise ValueError("The component catalog differs from release metadata")
    actual = {str(p.relative_to(ROOT)) for p in (ROOT / "components").rglob("*")
              if p.is_file() and "__pycache__" not in p.parts}
    if actual != {name for name in inventory if name.startswith("components/")}:
        raise ValueError("Component file inventory differs from the release")
    declared = set()
    for component in catalog():
        manifest = read_json(child(ROOT, component["manifest"]))
        declared.update({component["manifest"], f"components/{component['id']}/README.md"})
        declared.update(manifest["payload_files"])
        for patch in manifest["patches"]:
            declared.add(patch["patch"])
            data = child(ROOT, patch["patch"]).read_bytes()
            if digest(data) != patch["patch_sha256"]:
                raise ValueError(f"Patch hash mismatch: {patch['patch']}")
    if actual != declared:
        raise ValueError("Unexpected or undeclared component payload")
    print(f"Verified {len(inventory)} packaged files and {len(catalog())} components.")


def prepare(identifier, source, output):
    verify()
    matches = [c for c in catalog() if c["id"] == identifier]
    if len(matches) != 1:
        raise ValueError(f"Unknown component: {identifier}")
    manifest = read_json(child(ROOT, matches[0]["manifest"]))
    replacement = manifest.get("replacement")
    if not manifest["patches"] and not replacement:
        raise ValueError("This component has no portable code patch; read its status.")
    source = source.resolve(strict=True)
    output = output.absolute()
    if output.exists() or output.is_symlink():
        raise ValueError("Output must be a new directory.")
    if not output.parent.is_dir():
        raise ValueError("Create the output's parent directory first.")
    if output.resolve().is_relative_to(source):
        raise ValueError("Output must be outside the upstream source tree.")
    if output.resolve().is_relative_to(ROOT):
        raise ValueError("Output must be outside this artifact tree.")

    staged = {}
    patches = []
    if replacement:
        name = replacement["upstream_path"]
        data = child(source, name).read_bytes()
        if digest(data) != replacement["before_sha256"]:
            raise ValueError(f"Original source mismatch: {name}")
        staged[name] = data
        payload = child(ROOT, replacement["implementation"]).read_bytes()
        if digest(payload) != replacement["after_sha256"]:
            raise ValueError("BAR replacement hash mismatch")
    for patch in manifest["patches"]:
        name = patch["upstream_path"]
        data = child(source, name).read_bytes()
        if digest(data) != patch["before_sha256"]:
            raise ValueError(f"Original source mismatch: {name}")
        patch_path = child(ROOT, patch["patch"])
        if digest(patch_path.read_bytes()) != patch["patch_sha256"]:
            raise ValueError(f"Distributed patch mismatch: {patch['patch']}")
        # The selected patches each address one existing file. Check headers
        # before invoking patch, so no extra target can be written.
        headers = [line for line in patch_path.read_text().splitlines()
                   if line.startswith(("--- ", "+++ "))]
        if headers != [f"--- a/{name}", f"+++ b/{name}"]:
            raise ValueError(f"Unexpected patch targets: {patch['patch']}")
        if name in staged:
            raise ValueError("Multiple patches for one file require a composed manifest.")
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
                raise ValueError(result.stdout + result.stderr)
            target = child(tree, patch["upstream_path"])
            if digest(target.read_bytes()) != patch["after_sha256"]:
                raise ValueError(f"Revised source mismatch: {patch['upstream_path']}")
        for addition in manifest.get("additional_files", []):
            data = child(ROOT, addition["payload"]).read_bytes()
            if digest(data) != addition["sha256"]:
                raise ValueError("Additional implementation hash mismatch")
            destination = child(tree, addition["output_path"])
            if destination.exists():
                raise ValueError("Additional implementation would replace a patched file")
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(data)
        for name, original in staged.items():
            if child(source, name).read_bytes() != original:
                raise ValueError(f"Source changed during preparation: {name}")
        for notice in manifest.get("notices", []):
            child(tree, Path(notice).name).write_bytes(child(ROOT, notice).read_bytes())
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
    print(f"Prepared {identifier}: {output}")


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
        raise ValueError("Expected one pinned native Tax prompt renderer.")
    namespace["args"] = SimpleNamespace(distractor=False, textual=False)
    # No upstream imports, experiment entrypoints, model clients or graders run.
    exec(compile(ast.Module(body=nodes, type_ignores=[]),
                 "<pinned-native-tax-renderer>", "exec"), namespace)
    return namespace["system_prompt"], namespace["build_prompt"]


def dataset(identifier, source, output):
    if identifier in ("rulearena-airline-objective", "rulearena-nba-location-errata"):
        import rulearena
        import sys
        return rulearena.dataset(sys.modules[__name__], identifier, source, output)
    if identifier != "rulearena-tax":
        raise ValueError("This component has no dataset builder. "
                         "Scorer corrections retain the upstream dataset labels.")
    verify()
    entry = next(c for c in catalog() if c["id"] == identifier)
    manifest = read_json(child(ROOT, entry["manifest"]))
    spec = manifest["dataset"]
    source = source.resolve(strict=True)
    output = output.absolute()
    if output.exists() or output.is_symlink():
        raise ValueError("Output must be a new directory.")
    if not output.parent.is_dir():
        raise ValueError("Create the output's parent directory first.")
    if output.resolve().is_relative_to(source):
        raise ValueError("Output must be outside the upstream source tree.")
    if output.resolve().is_relative_to(ROOT):
        raise ValueError("Output must be outside this artifact tree.")

    sources = {}
    for item in spec["source_files"]:
        data = child(source, item["path"]).read_bytes()
        if digest(data) != item["sha256"]:
            raise ValueError(f"Original source mismatch: {item['path']}")
        sources[item["path"]] = data
    reference_bytes = child(ROOT, spec["reference_file"]).read_bytes()
    if digest(reference_bytes) != spec["reference_sha256"]:
        raise ValueError("Reference payload mismatch.")
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
            raise ValueError(f"Duplicate case ID: {identifier}")
        seen.add(identifier)
        name, index = reference["source_file"], reference["source_index"]
        if name not in native or not isinstance(index, int) or not 0 <= index < len(native[name]):
            raise ValueError(f"Invalid source location: {identifier}")
        level = Path(name).stem
        if identifier != f"tax/{level}/{index}":
            raise ValueError(f"Case ID/source location mismatch: {identifier}")
        location = (name, index)
        if location in seen_locations:
            raise ValueError(f"Duplicate source location: {identifier}")
        seen_locations.add(location)
        case = native[name][index]
        if digest(json.dumps(case, sort_keys=True).encode()) != reference["case_sha256"]:
            raise ValueError(f"Case/reference mismatch: {identifier}")
        changed = reference["original_signed_answer"] != reference["line22_repaired_signed_answer"]
        if changed != reference["changed"]:
            raise ValueError(f"Changed-reference flag mismatch: {identifier}")
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
        raise ValueError("Reference pairs do not cover the complete pinned dataset.")
    if sum(row["reference_changed"] for row in rows) != spec["changed_reference_count"]:
        raise ValueError("Changed-reference count mismatch.")
    content = "".join(json.dumps(row, ensure_ascii=False, allow_nan=False) + "\n"
                      for row in rows).encode("utf-8")
    receipt = {
        **spec,
        "operation": "join_scoped_references_with_unchanged_native_inputs",
        "output_file": "data.jsonl",
        "output_sha256": digest(content),
        "sign_convention": references["sign_convention"],
        "not_a_complete_ground_truth_repair": True,
        "model_calls": 0,
    }
    for name, original in sources.items():
        if child(source, name).read_bytes() != original:
            raise ValueError(f"Source changed during preparation: {name}")
    # Reserve a fresh directory only after input and row checks succeed.
    output.mkdir()
    (output / "data.jsonl").write_bytes(content)
    (output / "dataset.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(f"Prepared {spec['asset_name']}: {len(rows)} cases, "
          f"{spec['changed_reference_count']} revised references in {output}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
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
    args = parser.parse_args()
    if args.command == "list":
        for entry in catalog():
            print(f"{entry['id']}\t{entry['kind']}\t{entry['payload_status']}")
    elif args.command == "verify":
        verify()
    elif args.command == "prepare":
        prepare(args.component, args.source, args.output)
    else:
        dataset(args.component, args.source, args.output)


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, RuntimeError) as error:
        raise SystemExit(str(error))
