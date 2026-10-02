"""The AI challenge remains reproducible after the fact sheet advances."""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))
from evaluate_conversation_retrieval import load_facts
from freeze_ai_challenge import freeze


class ChallengeFreezeTests(unittest.TestCase):
    def test_v3_archive_preserves_frozen_case_version(self):
        archived = Path(__file__).resolve().parents[1] / "plan/conversation_data/snapshots/source_pack_v3.md"
        self.assertEqual(len(load_facts(archived, "CONV-FACTS-2026-09-29-v3")), 22)
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "cases.jsonl"
            self.assertEqual(freeze(output=output), 24)
            manifest = json.loads(output.with_suffix(".manifest.json").read_text())
            self.assertEqual(manifest["fact_version"], "CONV-FACTS-2026-09-29-v3")


if __name__ == "__main__":
    unittest.main()
