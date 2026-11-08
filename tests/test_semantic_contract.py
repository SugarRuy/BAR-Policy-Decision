# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Yanru Xiao and Yifei Cai
"""Task directives and version-bound references must survive the public views."""
from pathlib import Path
import tempfile
import unittest

import bar_policy as bp

from _support import require


class TaskViews(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source = require("BAR_TEST_RULEARENA")
        cls.tax = bp.load_dataset("rulearena-tax", source)
        cls.airline = bp.load_dataset("rulearena-airline", source)
        cls.airline_original = bp.load_dataset(
            "rulearena-airline", source, variant="original-input"
        )

    def test_native_task_directives_are_accessible_as_question(self):
        for dataset, marker in (
            (self.tax, "The total tax owed is"),
            (self.airline, "The total cost is"),
        ):
            for example in dataset:
                self.assertTrue(example.question, example.id)
                self.assertIn(marker, "".join(s.text for s in example.question))
                for segment in example.question:
                    self.assertIn(segment, example.segments)
                for index, message in enumerate(example.messages):
                    self.assertEqual(
                        "".join(s.text for s in example.segments
                                if s.message_index == index),
                        message["content"],
                    )

    def test_selected_objective_is_part_of_question(self):
        for revised, original in zip(self.airline, self.airline_original):
            self.assertEqual(len(revised.amendments), 1)
            amendment = revised.amendments[0]
            self.assertIn(amendment, revised.question)
            self.assertIn(amendment, revised.instructions)
            self.assertEqual(amendment.origin, "bar")
            self.assertFalse(original.amendments)
            self.assertTrue(all(s.origin == "upstream" for s in original.question))

    def test_tax_views_keep_the_native_overlap(self):
        for example in self.tax:
            self.assertEqual(example.policy, example.case)
            self.assertEqual(len(example.policy), 1)
            self.assertIs(example.policy[0], example.case[0])

    def test_reference_and_identity_are_read_only(self):
        for dataset in (self.tax, self.airline):
            example = dataset[0]
            reference = example.reference
            for name, value in (("reference", reference + 1),
                                ("id", "changed"), ("segments", ())):
                with self.assertRaises(AttributeError):
                    setattr(example, name, value)
            for name in ("name", "release", "variant", "mode", "scorer"):
                with self.assertRaises(AttributeError):
                    setattr(dataset, name, "changed")
            copy = example.references
            copy["revised"] = reference + 1
            self.assertEqual(example.reference, reference)

    def test_provenance_cannot_be_changed_through_another_example(self):
        first = self.airline[0].amendments[0]
        second = self.airline[1].amendments[0]
        original = second.provenance[0]["sha256"]
        with self.assertRaises(TypeError):
            first.provenance[0]["sha256"] = "changed"
        exported = first.to_dict()
        exported["provenance"][0]["sha256"] = "changed"
        self.assertEqual(first.provenance[0]["sha256"], original)
        self.assertEqual(second.provenance[0]["sha256"], original)

    def test_export_returns_the_created_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "exported"
            result = bp.write_component_dataset(
                "rulearena-tax", require("BAR_TEST_RULEARENA"), target
            )
            self.assertEqual(result, target)
            self.assertTrue((result / "data.jsonl").is_file())

    def test_batch_score_records_release_and_mode(self):
        for dataset in (self.tax, self.airline):
            result = dataset.score({}, allow_missing=True)
            self.assertEqual(result.release, dataset.release)
            self.assertEqual(result.mode, dataset.mode)
            self.assertEqual(result.denominator, 300)
            self.assertEqual(result.accepted, 0)


class VersionAndSourceErrors(unittest.TestCase):
    def test_direct_component_constructor_rejects_unknown_release(self):
        with self.assertRaises(bp.UnsupportedError):
            bp.Component("rulearena-tax", "0.1.0")

    def test_prepare_and_export_report_missing_pinned_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "source"
            source.mkdir()
            for operation, name in (
                (bp.prepare_component, "prepared"),
                (bp.write_component_dataset, "dataset"),
            ):
                with self.assertRaises(bp.SourceNotFoundError):
                    operation("rulearena-tax", source, Path(tmp) / name)


if __name__ == "__main__":
    unittest.main()
