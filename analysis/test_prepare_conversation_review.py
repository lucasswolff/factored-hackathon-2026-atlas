"""Ensure independent review packets contain no draft answers or labels."""

import csv
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))
from prepare_conversation_review import prepare


class ReviewPacketTests(unittest.TestCase):
    def test_phase_one_is_blind_and_heldout_template_is_empty(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.assertEqual(prepare(root), 24)
            with (root / "phase1_blind_labels/cases.csv").open(encoding="utf-8", newline="") as file:
                rows = list(csv.DictReader(file))
            self.assertEqual(len(rows), 24)
            self.assertTrue(all(not row["review_route"] for row in rows))
            self.assertTrue(all(not row["review_required_points"] for row in rows))
            self.assertNotIn("route", rows[0])
            self.assertNotIn("required_points", rows[0])
            self.assertIn("0.057989", next(row for row in rows if row["case_id"] == "ES-007")["verified_fx_evidence"])
            with (root / "heldout_writer/case_template.csv").open(encoding="utf-8", newline="") as file:
                self.assertEqual(len(list(csv.DictReader(file))), 0)
            self.assertFalse((root / "phase2_answer_review").exists())


if __name__ == "__main__":
    unittest.main()
