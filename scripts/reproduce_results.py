#!/usr/bin/env python3
"""Offline replay of the four BAR paper studies. No network or model clients.

BAR-original implementation, MIT. Small mathematical implementations below are
independent equivalents of the pinned evaluators, not vendored upstream code.
The shared JSON extraction interface preserves the frozen BAR implementation.
"""
from __future__ import annotations

import argparse
import ast
from collections import Counter
import copy
import csv
from decimal import Decimal
import hashlib
import io
import itertools
import json
import math
from pathlib import Path, PurePosixPath
import re
import string
import sys
import tarfile
from types import SimpleNamespace

METRICS = ("EM", "EM_with_conditions", "F1", "F1_with_conditions")
MODELS = ("H", "L", "G")
ARMS = ("released", "corrected", "omitted")
TAX_PATTERN = r"The total tax (owed|overpaid) is \$((?:\d{1,3}(?:,\d{3})*|\d+)(\.\d+)?)."


def sha(data):
    return hashlib.sha256(data).hexdigest()


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode()


def check(condition, message):
    if not condition:
        raise ValueError(message)


def equal(actual, expected, where):
    """Compare nested frozen ledgers without weakening membership/type checks."""
    if isinstance(expected, dict):
        check(isinstance(actual, dict) and actual.keys() == expected.keys(),
              f"{where}: mapping keys differ")
        for key in expected:
            equal(actual[key], expected[key], f"{where}/{key}")
    elif isinstance(expected, list):
        check(isinstance(actual, list) and len(actual) == len(expected),
              f"{where}: list length differs")
        for i, (a, b) in enumerate(zip(actual, expected)):
            equal(a, b, f"{where}/{i}")
    elif type(expected) is float:
        check(type(actual) in (int, float) and math.isfinite(actual)
              and abs(actual - expected) <= 1e-12,
              f"{where}: {actual!r} != {expected!r}")
    else:
        check(actual == expected, f"{where}: {actual!r} != {expected!r}")


def parse_object(text):
    """Frozen BAR final-object extraction; no repair of ambiguous submissions."""
    value = text.strip()
    try:
        obj = json.loads(value)
        if not isinstance(obj, dict):
            raise ValueError("Expected one JSON object.")
        return obj
    except json.JSONDecodeError:
        pass
    blocks = re.findall(r"<final_output>\s*(.*?)\s*</final_output>", value, re.S)
    if blocks:
        if len(blocks) != 1:
            raise ValueError("Multiple final-output envelopes.")
        return parse_object(blocks[0])
    blocks = re.findall(r"```(?:json)?\s*\n(.*?)```", value, re.S)
    if len(blocks) == 1:
        return parse_object(blocks[0])
    decoder = json.JSONDecoder()
    candidates, pos = [], 0
    while (pos := value.find("{", pos)) >= 0:
        try:
            obj, consumed = decoder.raw_decode(value[pos:])
            if isinstance(obj, dict):
                candidates.append(obj)
            pos += consumed
        except json.JSONDecodeError:
            pos += 1
    if len(candidates) != 1:
        raise ValueError("No unambiguous final JSON object.")
    return candidates[0]


def decode_cqa(text, ident):
    try:
        obj = parse_object(text)
    except (ValueError, TypeError, RecursionError):
        return None, "invalid_answer"
    item = obj.get("answer")
    if (not isinstance(item, dict) or set(item) != {"id", "answers"}
            or item["id"] != ident or not isinstance(item["answers"], list)):
        return None, "invalid_native_item"
    for pair in item["answers"]:
        if (not isinstance(pair, list) or len(pair) != 2
                or not isinstance(pair[0], str) or not isinstance(pair[1], list)
                or any(not isinstance(c, str) for c in pair[1])):
            return None, "invalid_native_item"
    return item, "valid"


def decode_oe(text):
    try:
        obj = parse_object(text)
    except (ValueError, TypeError, RecursionError):
        return None, "invalid_answer"
    if "answer" not in obj:
        return None, "invalid_envelope"
    if obj["answer"] is None:
        return None, "abstained"
    if (set(obj) != {"answer"} or type(obj["answer"]) not in (int, float)
            or not math.isfinite(obj["answer"])):
        return None, "invalid_numeric"
    return obj["answer"], "valid_answer"


def decode_tax(text):
    match = re.search(TAX_PATTERN, text.replace("**", ""))
    if match is None:
        return None
    value = float(match[2].replace(",", ""))
    value = -value if match[1] == "overpaid" else value
    return value if math.isfinite(value) else None


def tax_accept(prediction, reference):
    # numpy.isclose(a,b,rtol=1e-5,atol=1e-8), finite scalars only; b is reference.
    return (prediction is not None and math.isfinite(prediction)
            and abs(prediction-reference) <= 1e-8 + 1e-5 * abs(reference))


def sara_score(text, reference):
    old = re.search(r"\d+", text.replace(",", "").replace(".", ""))
    new = re.search(r"[-+]?\s*\d+(?:\.\d+)?", text.replace(",", "").replace("$", ""))
    old_value = int(old[0]) if old else None
    decimal_value = str(Decimal(re.sub(r"\s+", "", new[0]))) if new else None
    value = float(decimal_value) if decimal_value is not None else None
    legacy = lambda p: p is not None and abs(p / (reference + 0.1) - 1) < 0.1
    return {"parsed": [old_value, decimal_value, decimal_value],
            "accepted": [legacy(old_value), legacy(value),
                         (value == 0 if reference == 0 and value is not None else legacy(value))]}


def normalize(text):
    text = "".join(c for c in text.lower() if c not in string.punctuation)
    return " ".join(re.sub(r"\b(a|an|the)\b", " ", text).split())


def cqa_pair(prediction, reference):
    p, r = normalize(prediction[0]), normalize(reference[0])
    pt, rt = normalize(p).split(), normalize(r).split()
    common = sum((Counter(pt) & Counter(rt)).values())
    if not pt or not rt:
        f1 = float(pt == rt)
    elif not common:
        f1 = 0.0
    else:
        precision, recall = common / len(pt), common / len(rt)
        f1 = 2 * precision * recall / (precision + recall)
    pc, rc = set(prediction[1]), set(reference[1])
    if not rc:
        cond = float(not pc)
    elif not pc or not (pc & rc):
        cond = 0.0
    else:
        precision, recall = len(pc & rc) / len(pc), len(pc & rc) / len(rc)
        cond = 2 / (1 / precision + 1 / recall)
    em = float(p == r)
    return [em, em * cond, f1, f1 * cond]


def cqa_metrics(prediction, reference):
    """Maximum injective alignment using subset DP, independently for 4 metrics.

    An unused permutation suffix cannot affect the native zip. DP enumerates all
    injective assignments, including padding, without factorial duplication.
    The full padded prediction count still determines the native gamma penalty.
    """
    if not reference:
        return [float(not prediction)] * 4
    n = len(reference)
    pred = list(prediction) + [["", []]] * max(0, n-len(prediction))
    dp = [[-math.inf] * (1 << n) for _ in METRICS]
    for row in dp:
        row[0] = 0.0
    for p in pred:
        weights = [cqa_pair(p, r) for r in reference]
        new = [row[:] for row in dp]
        for mask in range(1 << n):
            for j in range(n):
                if mask & (1 << j):
                    continue
                target = mask | (1 << j)
                for k in range(4):
                    new[k][target] = max(new[k][target], dp[k][mask] + weights[j][k])
        dp = new
    gamma = math.exp(1 - len(pred)/n)
    return [row[-1] / n * gamma for row in dp]


def cqa_groups(reference):
    groups = ["total"]
    if reference:
        groups.append("yesno" if any(a[0] in ("yes", "no") for a in reference) else "extractive")
    if any(a[1] for a in reference):
        groups.append("conditional")
    return groups


def cqa_aggregate(rows):
    output = {}
    for version in ("original", "revised"):
        metrics, denominators = {}, {}
        for group in ("total", "yesno", "extractive", "conditional"):
            chosen = [r for r in rows if group in r["groups"]
                      and (version == "revised" or r["prediction_present"])]
            denominators[group] = len(chosen)
            metrics[group] = {m: sum(r["metrics"][i] for r in chosen)/len(chosen)
                              if chosen else None for i, m in enumerate(METRICS)}
        output[version] = {"metrics": metrics, "denominators": denominators}
    return output


def oe_target(assets):
    # Independent category bound for two equal, separately exempting spouses.
    grouped = {k: [] for k in (1, 2, 3, 4, 5, 6, 9)}
    for a in assets:
        grouped[a["category"]].append(Decimal(str(a["value"])) / 2)
    totals = {k: sum(v, Decimal(0)) for k, v in grouped.items()}
    home = min(totals[1], Decimal(27900))
    specific = (home + max([Decimal(0)] + [min(v, Decimal(4450)) for v in grouped[2]])
                + min(sum((min(v, Decimal(700)) for v in grouped[3]), Decimal(0)), Decimal(14875))
                + min(totals[4], Decimal(1875)) + min(totals[6], Decimal(2800)) + totals[9])
    wildcard = Decimal(1475) + min(Decimal(13950), Decimal(27900)-home)
    return float(2 * max(Decimal(0), sum(totals.values()) - specific - wildcard))


def transitions(old, new):
    return {"gains": sum(not a and b for a, b in zip(old, new)),
            "losses": sum(a and not b for a, b in zip(old, new))}


def source_bytes(manifest, sources, key):
    item = manifest["upstream"][key]
    check(item["root"] in sources, f"Supply source root {item['root']!r} in --sources")
    root = Path(sources[item["root"]]).expanduser()
    candidates = item.get("alternatives", [item["path"]])
    for relative in candidates:
        path = root / relative if relative else root
        if path.is_file() and sha(path.read_bytes()) == item["sha256"]:
            return path.read_bytes()
    raise ValueError(f"Missing or hash-mismatched {key}: root={root}, paths={candidates}, "
                     f"required SHA-256={item['sha256']}")


def source_json(manifest, sources, key):
    return json.loads(source_bytes(manifest, sources, key))


def load_archive(path, expected_sha):
    data = path.read_bytes()
    check(sha(data) == expected_sha, f"Archive hash mismatch: {path}")
    # Never extract archive members into the filesystem.
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as archive:
        files = {}
        for member in archive.getmembers():
            p = PurePosixPath(member.name)
            check(member.isfile() and not p.is_absolute() and ".." not in p.parts,
                  f"Unsafe archive member: {member.name}")
            check(member.name not in files, "Duplicate archive member")
            check(member.size < 100_000_000, "Unexpectedly large member")
            files[member.name] = archive.extractfile(member).read()
    manifest = json.loads(files["manifest.json"])
    check(set(files) == {"manifest.json", *manifest["files"]}, "Unexpected archive contents")
    for name, pin in manifest["files"].items():
        check(sha(files[name]) == pin, f"Member hash mismatch: {name}")
    return manifest, {name: json.loads(data) for name, data in files.items() if name != "manifest.json"}


def native_cqa(manifest, sources):
    """Load only the allowlisted pure functions from hash-pinned user code."""
    text = source_bytes(manifest, sources, "evaluator").decode()
    names = {"compute_metrics", "compute_em_f1", "compute_conditions_f1",
             "compute_answer_f1", "get_tokens", "normalize_answer"}
    nodes = [n for n in ast.parse(text).body if isinstance(n, ast.FunctionDef) and n.name in names]
    check({n.name for n in nodes} == names, "Native CQA function set differs")
    namespace = {"json": json, "math": math, "re": re, "string": string,
                 "collections": __import__("collections"), "itertools": itertools}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), "<pinned-cqa-functions>", "exec"), namespace)
    return namespace


def validate_cqa_native(prediction, reference, values, native):
    for p in prediction + [["", []]]:
        for r in reference:
            equal(cqa_pair(p, r), list(native["compute_em_f1"](p, r)), "native pair")
    # Bound literal execution, while every row is also checked against frozen
    # per-case scores and every pair above uses actual upstream function code.
    n = max(len(prediction), len(reference))
    if n <= 7:
        equal(values, list(native["compute_metrics"](copy.deepcopy(prediction),
                                                    copy.deepcopy(reference))), "native literal")
        return 1
    return 0


def replay(study, manifest, payload, sources, native_checks=False):
    rows = payload["responses.json"]
    expected = payload["expected.json"]
    check(len({(r["model"], r["id"]) for r in rows}) == len(rows), "Duplicate retained response")
    for r in rows:
        check(sha(r["raw_text"].encode()) == r["raw_text_sha256"], "Visible response hash mismatch")
        config = manifest["configs"][r["config_id"]]
        check(config["modelId"] == manifest["models"][r["model"]], "Response/config model mismatch")
        if "saved_envelope" in r:
            try:
                envelope = parse_object(r["raw_text"])
            except (ValueError, TypeError, RecursionError):
                envelope = None
            equal(envelope, r["saved_envelope"], f"{r['model']}/{r['id']}/saved envelope")
    result, details = {}, []
    if study == "rulearena-tax":
        refs = {r["id"]: r for r in payload["references.json"]}
        for model in MODELS:
            chosen = [r for r in rows if r["model"] == model]
            old, new = [], []
            for r in chosen:
                ref = refs[r["id"]]
                value = decode_tax(r["raw_text"])
                scores = [tax_accept(value, ref[k]) for k in ("original", "revised")]
                equal(value, r["parsed"], f"{model}/{r['id']}/parsed")
                equal(scores, r["scores"], f"{model}/{r['id']}/scores")
                old.append(scores[0]); new.append(scores[1])
                details.append({"model": model, "id": r["id"], "parsed": value, "scores": scores})
            result[model] = {"n": len(chosen), "original": sum(old), "revised": sum(new),
                             **transitions(old, new)}
        lookup = {(r["model"], r["id"]): r for r in rows}
        attribution = Counter()
        for a in payload["attributions.json"]["records"]:
            r = lookup[a["model"], a["id"]]
            check(a["raw_text_sha256"] == r["raw_text_sha256"], "Trace/response binding mismatch")
            for excerpt in a["excerpts"]:
                check(excerpt["quote"] in r["raw_text"], f"Trace excerpt mismatch: {a['id']}")
            scores = r["scores"]
            if scores[0] != scores[1]:
                attribution[("gain" if scores[1] else "loss") + ":" + a["floor_evidence"]] += 1
        result["attribution"] = dict(attribution)
        result["changed_references"] = sum(r["original"] != r["revised"] for r in refs.values())
    elif study == "legalbench-sara-numeric":
        data = list(csv.DictReader(io.StringIO(source_bytes(manifest, sources, "test").decode()), delimiter="\t"))
        refs = {r["case id"]: float(r["answer"].replace("$", "").replace(",", "")) for r in data}
        for model in MODELS:
            chosen = [r for r in rows if r["model"] == model]
            scored = []
            for r in chosen:
                reference = refs[r["id"]]
                check(sha(canonical(reference)) == r["reference_sha256"], "SARA reference binding differs")
                s = sara_score(r["raw_text"], reference)
                equal(s["parsed"], r["parsed"], f"{model}/{r['id']}/parse")
                equal(s["accepted"], r["scores"], f"{model}/{r['id']}/score")
                scored.append(s["accepted"])
                details.append({"model": model, "id": r["id"], **s})
            result[model] = {"n": len(chosen), "accepted": [sum(r[i] for r in scored) for i in range(3)],
                             **transitions([r[0] for r in scored], [r[2] for r in scored])}
    elif study == "conditionalqa":
        refs = source_json(manifest, sources, "dev")
        refmap = {r["id"]: r["answers"] for r in refs}
        native = native_cqa(manifest, sources) if native_checks else None
        native_literals = 0
        for model in MODELS:
            calculated = []
            for r in [r for r in rows if r["model"] == model]:
                item, status = decode_cqa(r["raw_text"], r["id"])
                equal(item, r["parsed"], f"{model}/{r['id']}/submission")
                equal(status, r["submission_status"], f"{model}/{r['id']}/status")
                reference = refmap[r["id"]]
                values = cqa_metrics(item["answers"], reference) if item is not None else [0.0]*4
                equal(values, r["scores"], f"{model}/{r['id']}/four metrics")
                if native and item is not None:
                    native_literals += validate_cqa_native(item["answers"], reference, values, native)
                calculated.append({"model": model, "id": r["id"], "prediction_present": item is not None,
                                   "groups": cqa_groups(reference), "metrics": values})
            result[model] = cqa_aggregate(calculated)
            result[model]["attempts"] = len(calculated)
            result[model]["empty_submissions"] = sum(r["parsed"] is not None and r["parsed"]["answers"] == []
                                                     for r in rows if r["model"] == model)
            details.extend(calculated)
        controls = {}
        for control in payload["controls.json"]:
            data = source_json(manifest, sources, control["source_key"])
            check(len(data) == len({r["id"] for r in data}) == 285, "Incomplete published control")
            check({r["id"] for r in data} == set(refmap), "Published ID population differs")
            calculated = []
            for r in data:
                values = cqa_metrics(r["answers"], refmap[r["id"]])
                equal(values, control["per_case"][r["id"]], "published per-case metrics")
                if native:
                    native_literals += validate_cqa_native(r["answers"], refmap[r["id"]], values, native)
                calculated.append({"id": r["id"], "prediction_present": True,
                                   "groups": cqa_groups(refmap[r["id"]]), "metrics": values})
            controls[control["name"]] = cqa_aggregate(calculated)
            equal(controls[control["name"]]["original"], controls[control["name"]]["revised"],
                  "complete-file zero effect")
        result["controls"] = controls
    elif study == "openexempt":
        targets = {r["id"]: r for r in payload["targets.json"]}
        for t in targets.values():
            equal(oe_target(t["assets"]), t["target"], f"{t['id']}/independent target")
        for model in MODELS:
            calculated = {}
            for r in [r for r in rows if r["model"] == model]:
                answer, status = decode_oe(r["raw_text"])
                target = targets[r["case_id"]]
                accepted = answer is not None and answer >= 0 and abs(answer-target["target"]) <= .005
                equal(answer, r["parsed"], f"{model}/{r['id']}/parsed")
                equal(status, r["submission_status"], f"{model}/{r['id']}/status")
                equal(accepted, r["scores"], f"{model}/{r['id']}/score")
                calculated[r["id"]] = accepted
                details.append({"model": model, "id": r["id"], "parsed": answer, "accepted": accepted})
            grouped = {}
            for group, selected in [
                ("all", list(targets.values())),
                ("positive", [r for r in targets.values() if r["target"] > 0]),
                ("zero", [r for r in targets.values() if r["target"] == 0]),
                ("unchanged_tables", [r for r in targets.values() if not r["affected"]]),
                ("sensitive", [r for r in targets.values() if r["sensitive"]]),
            ]:
                grouped[group] = {"n": len(selected), "accepted": [
                    sum(calculated[t["id"]+":"+arm] for t in selected) for arm in ARMS]}
            old = [calculated[t+":"+ARMS[0]] for t in targets]
            new = [calculated[t+":"+ARMS[1]] for t in targets]
            grouped.update(transitions(old, new))
            grouped["released_ceiling_matches_sensitive"] = sum(
                r["parsed"] is not None and abs(r["parsed"]-targets[r["case_id"]]["released_ceiling"]) <= .005
                for r in rows if r["model"] == model and r["arm"] == "released"
                and targets[r["case_id"]]["sensitive"])
            result[model] = grouped
        overlaps = payload["overlap.json"]["per_case"]
        check({r["id"] for r in overlaps} == set(targets), "Overlap population mismatch")
        for row in overlaps:
            equal(row["changed_steps"], targets[row["id"]]["affected"], "Overlap affected flag")
            equal(row["sensitive"], targets[row["id"]]["sensitive"], "Overlap sensitive flag")
        result["overlap"] = {
            "cases": len(overlaps),
            "changed_tables": sum(t["affected"] for t in targets.values()),
            "sensitive": sum(t["sensitive"] for t in targets.values()),
            "native_second_claim": sum(r["native_second_federal_claim"] for r in overlaps),
            "native_second_claim_sensitive": sum(r["native_second_federal_claim"] and r["sensitive"] for r in overlaps),
            "native_terminal_conflict": sum(r["native_terminal_conflict"] for r in overlaps),
            "native_terminal_conflict_sensitive": sum(r["native_terminal_conflict"] and r["sensitive"] for r in overlaps)}
    else:
        raise ValueError(f"Unknown study: {study}")
    equal(result, expected, study)
    report = {"status": "passed", "retained_responses": len(rows), "results": result,
              "per_case": details}
    if study == "conditionalqa" and native_checks:
        report["native_checks"] = {"all_submitted_answer_pairs_checked": True,
                                   "literal_permutation_cases": native_literals}
    return report


def literals(text):
    values = {}
    for node in ast.parse(text).body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            try:
                values[node.targets[0].id] = ast.literal_eval(node.value)
            except (ValueError, TypeError):
                pass
    return values


def verify_inputs(study, manifest, payload, sources):
    """Rebuild every model-visible user input from separately supplied upstream."""
    actual = {}
    inputs = payload["inputs.json"]
    if study == "rulearena-tax":
        auto = source_bytes(manifest, sources, "auto_test").decode()
        prompt = source_bytes(manifest, sources, "prompt").decode()
        ns = {**literals(auto), **literals(prompt),
              "args": SimpleNamespace(distractor=False, textual=False)}
        nodes = [n for n in ast.parse(auto).body if isinstance(n, ast.FunctionDef) and n.name == "build_prompt"]
        check(len(nodes) == 1, "Missing native Tax renderer")
        exec(compile(ast.Module(body=nodes, type_ignores=[]), "<pinned-tax-renderer>", "exec"), ns)
        for level in range(3):
            for i, row in enumerate(source_json(manifest, sources, f"comp_{level}")):
                ident = f"tax/comp_{level}/{i}"
                actual[ident] = ns["build_prompt"](copy.deepcopy(row["dict"])).replace("$example", "")
                check(sha(json.dumps(row, sort_keys=True).encode()) == inputs[ident]["source_record_sha256"],
                      "Tax source record mismatch")
    elif study == "legalbench-sara-numeric":
        rows = list(csv.DictReader(io.StringIO(source_bytes(manifest, sources, "test").decode()), delimiter="\t"))
        template = source_bytes(manifest, sources, "prompt").decode()
        for row in rows:
            text = template
            for key, value in row.items():
                text = text.replace("{{"+key+"}}", value)
            actual[row["case id"]] = text
    elif study == "conditionalqa":
        docs = {r["url"]: r for r in source_json(manifest, sources, "documents")}
        for r in source_json(manifest, sources, "dev"):
            task = {"policy": "\n".join(docs[r["url"]]["contents"]),
                    "question": r["question"] + manifest["question_suffix"].replace("__BAR_ID__", r["id"]),
                    "case": r["scenario"]}
            actual[r["id"]] = json.dumps(task, ensure_ascii=False)
    else:
        try:
            import pyarrow.parquet as pq
        except ImportError as exc:
            raise ValueError("--verify-inputs for OpenExempt needs pyarrow installed locally") from exc
        source = pq.read_table(io.BytesIO(source_bytes(manifest, sources, "parquet"))).to_pylist()
        targets = {r["id"]: r for r in payload["targets.json"]}
        templates = manifest["templates"]
        for row in source:
            if row["id"] not in targets:
                continue
            witness = targets[row["id"]]
            check(sha(json.dumps(row, sort_keys=True).encode()) == witness["source_row_sha256"],
                  "OE source row hash mismatch")
            case, prompt = json.loads(row["case"]), row["prompt"]
            steps = prompt.split("Solved Reasoning Steps:\n", 1)[1].split("\nStatutes:", 1)[0]
            original, corrected, eligibility = {}, {}, []
            for a in case["assets"]:
                desc, value = a["description"], a["dollar_value"]
                provisions = sorted(int(re.fullmatch(r"11 U.S.C. § 522\(d\)\((\d+)\)", s)[1])
                                    for s in a["applicable_exemptions"] if s.startswith("11 U.S.C."))
                category = next((k for k in provisions if k != 5), 5)
                segment = steps.split("The "+desc+" may be exempted under ", 1)[1].split("\n", 1)[0]
                parsed = {int(k): float(v.replace(",", "")) for k, v in
                          re.findall(r"11 U.S.C. § 522\(d\)\((\d+)\) \(\$([\d,.]+)\)", segment)}
                original[desc] = [{"citation": f"11 U.S.C. § 522(d)({k})", "maximum_amount": parsed[k]}
                                  for k in provisions]
                caps = {1: 27900, 2: 4450, 3: 700, 4: 1875, 5: 15425, 6: 2800}
                corrected[desc] = [{"citation": f"11 U.S.C. § 522(d)({k})",
                                    "maximum_amount": float(min(value, 2*caps[k]) if k != 9 else value)}
                                   for k in provisions]
                eligibility.append({"asset": desc, "equity": value,
                                    "category": templates["categories"][str(category)],
                                    "applicable_federal_provisions": [x["citation"] for x in original[desc]]})
            equal([{"value": a["equity"], "category": next(int(k) for k,v in templates["categories"].items()
                                                       if v == a["category"])} for a in eligibility],
                  witness["assets"], "OE asset/category target binding")
            for arm, table in zip(ARMS, (original, corrected, None)):
                case = {"source_facts": prompt.split("\nFacts:\n", 1)[1].split("\nSolved Reasoning Steps:", 1)[0],
                        "controlled_case_stipulations": templates["stipulations"],
                        "resolved_asset_eligibility": eligibility}
                if table is not None:
                    case["solved_reasoning_steps"] = {"instruction": templates["instruction"],
                                                     "independently_evaluated_asset_provision_maxima": table}
                task = {"policy": prompt.split("\nStatutes:\n", 1)[1].split("\nIllinois Compiled Statutes", 1)[0],
                        "question": templates["question"], "case": case}
                actual[row["id"]+":"+arm] = json.dumps(task, ensure_ascii=False)
    check(set(actual) == set(inputs), f"{study}: reconstructed input population differs")
    for r in payload["responses.json"]:
        text = actual[r["id"]]
        check(sha(text.encode()) == inputs[r["id"]]["user_text_sha256"], f"Input text mismatch: {r['id']}")
        request = {**manifest["configs"][r["config_id"]],
                   "messages": [{"role": "user", "content": [{"text": text}]}]}
        check(sha(canonical(request)) == r["request_sha256"], f"Request/config binding mismatch: {r['id']}")
        if "wire_config_id" in r:
            messages = []
            if request.get("system"):
                messages.append({"role": "system", "content": "\n".join(b["text"] for b in request["system"])})
            messages.append({"role": "user", "content": text})
            wire = {**manifest["wire_configs"][r["wire_config_id"]], "messages": messages}
            check(sha(canonical(wire)) == r["wire_request_sha256"],
                  f"Wire request/config binding mismatch: {r['id']}")
    return {"unique_inputs": len(actual), "requests": len(payload["responses.json"]),
            "wire_requests": sum("wire_config_id" in r for r in payload["responses.json"]), "status": "passed"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--studies-dir", type=Path, default=Path(__file__).resolve().parents[1] / "studies")
    parser.add_argument("--study", choices=("all", "rulearena-tax", "legalbench-sara-numeric", "conditionalqa", "openexempt"), default="all")
    parser.add_argument("--sources", type=Path, help="JSON mapping source root names to local paths")
    parser.add_argument("--list-inputs", action="store_true", help="Print hash-pinned source contracts; do not replay")
    parser.add_argument("--verify-inputs", action="store_true", help="Reconstruct model inputs from upstream (OE needs pyarrow)")
    parser.add_argument("--native-checks", action="store_true", help="Also check CQA pairs/literal small alignments against pinned native code")
    parser.add_argument("--output", type=Path, help="Write complete per-case verification JSON to a NEW file")
    args = parser.parse_args()
    sources = json.loads(args.sources.read_text()) if args.sources else {}
    index = json.loads((args.studies_dir / "index.json").read_text())
    selected = [s for s in index["studies"] if args.study in ("all", s["id"])]
    reports = {}
    for entry in selected:
        manifest, payload = load_archive(args.studies_dir / entry["archive"], entry["sha256"])
        if args.list_inputs:
            reports[entry["id"]] = manifest["upstream"]
            continue
        reports[entry["id"]] = replay(entry["id"], manifest, payload, sources, args.native_checks)
        if args.verify_inputs:
            reports[entry["id"]]["input_verification"] = verify_inputs(entry["id"], manifest, payload, sources)
    if args.output:
        with args.output.open("x", encoding="utf-8") as stream:
            json.dump(reports, stream, indent=2, ensure_ascii=False, allow_nan=False)
            stream.write("\n")
    concise = {key: {k:v for k,v in value.items() if k != "per_case"} for key,value in reports.items()}
    print(json.dumps(concise, indent=2, ensure_ascii=False, allow_nan=False))


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, KeyError) as exc:
        print(f"Replay failed: {exc}", file=sys.stderr)
        sys.exit(1)
