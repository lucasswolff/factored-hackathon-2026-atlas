"""Tests for dataset parsing and retrieval measurement, without model downloads."""

import unittest

from evaluate_conversation_retrieval import (
    is_retrievable,
    keyword_rank,
    load_cases,
    load_facts,
    metrics,
    query,
)
from evaluate_conversation_retrieval import CASES


class ConversationRetrievalTests(unittest.TestCase):
    def test_source_ids_and_case_labels_are_valid(self):
        facts = load_facts()
        cases = load_cases(CASES, {fact_id for fact_id, _ in facts})
        self.assertEqual(len(facts), 22)
        self.assertEqual(len(cases), 24)
        self.assertEqual({case["language"] for case in cases}, {"es", "pt"})
        self.assertEqual(len(keyword_rank(facts, cases)), len(cases))

    def test_query_uses_context_not_gold_or_workflow_state(self):
        case = load_cases(CASES, {fact_id for fact_id, _ in load_facts()})[0].copy()
        case["required_points"] = ["SECRET_EXPECTED_ANSWER"]
        case["session"] = "SECRET_SESSION_MARKER"
        case["profile_permission"] = True
        text = query(case)
        self.assertNotIn("SECRET_EXPECTED_ANSWER", text)
        self.assertNotIn("SECRET_SESSION_MARKER", text)
        self.assertIn(case["user_utterance"], text)

    def test_workflow_facts_are_not_scored_as_retrieval(self):
        self.assertFalse(is_retrievable("ACCESS.PERSONAL"))
        self.assertFalse(is_retrievable("CATALOG.STATUS"))
        self.assertTrue(is_retrievable("FEE.MX"))
        case = {"case_id": "toy", "language": "es", "route": "ANSWER_FACT",
                "relevant_fact_ids": ["ACCESS.ENTRY", "FEE.MX"]}
        result = metrics([case], {"toy": ["FEE.MX"]}, 1)["all"]
        self.assertEqual(result["hit_at_1"], 1.0)
        self.assertEqual(result["recall_at_k"], 1.0)


if __name__ == "__main__":
    unittest.main()
