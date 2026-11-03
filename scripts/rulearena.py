# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Yanru Xiao and Yifei Cai
"""Build scoped RuleArena input and localization revisions from pinned sources."""
import ast
import copy
import json


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":")).encode("utf-8")


def literals(text, names):
    values = {}
    for node in ast.parse(text).body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id in names:
                    values[target.id] = ast.literal_eval(node.value)
    if values.keys() != set(names):
        raise ValueError("Native prompt literals missing")
    return values


def airline_messages(sources, case, objective=None):
    template = literals(sources["airline/auto_test.py"].decode(),
                        {"system_prompt", "prompt_template"})
    question = case["prompt"]
    if objective:
        question += "\n\n" + objective
    prompt = template["prompt_template"].replace(
        "$reference_rules", sources["airline/reference_rules.txt"].decode())
    prompt = prompt.replace("$question_prompt", question).replace("$example_prompt", "")
    return [{"role": "system", "content": template["system_prompt"]},
            {"role": "user", "content": prompt}]


def source_bytes(bar, manifest, source):
    sources = {}
    for pin in manifest["source_files"]:
        data = bar.child(source, pin["path"]).read_bytes()
        if bar.digest(data) != pin["sha256"]:
            raise ValueError(f"Original source mismatch: {pin['path']}")
        sources[pin["path"]] = data
    return sources


def objective_rows(bar, manifest, sources):
    directory = bar.ROOT / "components/rulearena-airline-objective"
    objective = (directory / "objective.txt").read_text(encoding="utf-8").strip()
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
            raise ValueError("Invalid or duplicate Airline reference location")
        locations.add((name, index))
        case = native[name][index]
        if bar.digest(canonical(case)) != reference["case_sha256"]:
            raise ValueError("Airline case binding mismatch")
        if reference["id"] != f"airline/{name.split('/')[-1][:-6]}/{index}":
            raise ValueError("Airline ID/source mismatch")
        original = airline_messages(sources, case)
        amended = airline_messages(sources, case, objective)
        if (bar.digest(canonical(original)) != reference["original_messages_sha256"]
                or bar.digest(canonical(amended)) != reference["revised_messages_sha256"]):
            raise ValueError("Airline prompt binding mismatch")
        if reference["original_reference"] != reference["revised_reference"]:
            raise ValueError("The objective component must retain reference amounts")
        rows.append({**reference, "native_case": case,
                     "original_messages": original, "messages": amended})
    if locations != expected_locations or len(rows) != 300:
        raise ValueError("Airline references must cover all 300 source cases")
    return rows


def nba_rows(bar, manifest, sources):
    spec = bar.read_json(bar.ROOT / "components/rulearena-nba-location-errata/errata.json")
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
                if (bar.digest(canonical(original)) != edit["record_sha256"]
                        or original[edit["field"]] != edit["old"]):
                    raise ValueError("NBA record/old-value binding mismatch")
                revised[edit["field"]] = edit["new"]
                used.add((name, index))
            rows.append({
                "id": f"nba/{name.split('/')[-1][:-5]}/{index}",
                "source_file": name, "source_index": index,
                "case_sha256": bar.digest(canonical(original)),
                "original_record": original, "revised_record": revised,
                "changed": bool(edit), "changed_field": edit["field"] if edit else None,
            })
    if len(rows) != 216 or used != set(changes):
        raise ValueError("NBA errata must cover exactly two of 216 source records")
    return rows


def dataset(bar, identifier, source, output):
    bar.verify()
    manifest = bar.read_json(bar.ROOT / "components" / identifier / "component.json")
    source = source.resolve(strict=True)
    output = output.absolute()
    if output.exists() or output.is_symlink() or not output.parent.is_dir():
        raise ValueError("Output must be a new directory under an existing parent")
    if output.resolve().is_relative_to(source) or output.resolve().is_relative_to(bar.ROOT):
        raise ValueError("Output must be outside source and artifact trees")
    sources = source_bytes(bar, manifest, source)
    rows = (objective_rows(bar, manifest, sources)
            if identifier == "rulearena-airline-objective"
            else nba_rows(bar, manifest, sources))
    content = b"".join(canonical(row) + b"\n" for row in rows)
    for name, data in sources.items():
        if bar.child(source, name).read_bytes() != data:
            raise ValueError("Source changed during dataset construction")
    receipt = {
        "component": identifier, "source_repository": manifest["source_repository"],
        "scientific_scope": manifest["accepted_scope"],
        "remaining_limits": manifest["remaining_limits"],
        "record_count": len(rows), "data_sha256": bar.digest(content),
        "model_calls": 0,
    }
    output.mkdir()
    (output / "data.jsonl").write_bytes(content)
    (output / "dataset.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(f"Prepared {identifier}: {len(rows)} source-bound records in {output}")
