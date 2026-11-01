#!/usr/bin/env python3
"""Check selected saved audit observations. Does not run an agent or service."""
from pathlib import Path
import hashlib
import json

ROOT = Path(__file__).resolve().parents[1]


def load(path):
    return json.loads(path.read_text())


def main():
    evidence = ROOT / "evidence"
    tac = evidence / "tac-budget"
    index = load(evidence / "audit-index.json")
    assert len(index["entries"]) == index["reporting_units"] == 9
    assert len(load(evidence / "policyguardbench-consistency.json")["rows"]) == 6
    sharc = load(evidence / "sharc-exact-input-controls.json")
    assert next(s for s in sharc["splits"] if s["split"] == "test")["conflicts"] == []
    binding = load(tac / "export-binding.json")
    for name, expected_hash in binding["exported_records"].items():
        assert hashlib.sha256((tac / name).read_bytes()).hexdigest() == expected_hash, name
    assert len(binding["exported_records"]) >= 19
    assert load(tac / "runtime-binding.json")["all_equal"]
    assert all(r["matches_archive"] for r in load(tac / "source-binding.json")["files"])
    trajectory = load(tac / "trajectory.json")
    assert trajectory["model_generated"] is False
    assert trajectory["price_document_verified"] is False
    messages = {}
    pre = None
    trajectory_hashes = set()
    rows = []
    for condition in "ABCD":
        folder = tac / condition
        msgs = load(folder / "messages.json")
        native = load(folder / "native-readback.json")
        result = load(folder / "eval-result.json")
        converted = load(folder / "converted.json")
        assert msgs["baseline_equal"]
        assert msgs["only_one_final_message_added_per_manager"]
        assert msgs["pre_has_no_reference_totals"]
        if pre is None:
            pre = msgs["pre"]
        assert msgs["pre"] == pre
        trajectory_hashes.add(msgs["trajectory_sha256"])
        messages[condition] = {m: x["message"]["msg"] for m, x in msgs["sent"].items()}
        assert len(messages[condition]) == 3
        for manager, text in messages[condition].items():
            got = native["managers"][manager]
            assert got["official_content"]["ok"] and text in got["official_content"]["value"]
            sent_id = msgs["sent"][manager]["message"]["_id"]
            assert any(x["_id"] == sent_id and x["msg"] == text
                       for x in got["official_full"]["value"])
            assert any(x["_id"] == sent_id and x["msg"] == text for x in msgs["post"][manager])
        expected = [1, 1, 0] if condition == "D" else [1, 1, 2]
        assert [c["result"] for c in result["checkpoints"]] == expected
        assert result == converted["official_result"]
        points = result["final_score"]["result"]
        total = result["final_score"]["total"]
        # Independent arithmetic check of the frozen official conversion formula.
        score = points / total * 0.5 + (points // total) * 0.5
        assert score == converted["converted_score"] == (0.25 if condition == "D" else 1.0)
        rows.append({"condition": condition, "checkpoints": expected, "points": points,
                     "total": total, "converted_score": score})
    assert len(trajectory_hashes) == 1
    for manager, text in messages["A"].items():
        assert messages["D"][manager] == text.replace("11917", "11918")
        assert "sufficient" not in messages["B"][manager]
        judgment = text.split("The budget is ")[1]
        assert messages["C"][manager].endswith(
            "sufficient." if judgment == "insufficient." else "insufficient.")
    print(json.dumps({"status": "passed", "kind": "saved-record verification",
                      "runtime_rerun": False, "model_calls": 0, "results": rows}, indent=2))


if __name__ == "__main__":
    main()
