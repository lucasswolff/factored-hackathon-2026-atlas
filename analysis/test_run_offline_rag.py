"""Local checks for the synthetic answer-generation adapter."""

import io
import json
import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(__file__))
from evaluate_conversation_retrieval import CASES, load_cases, load_facts
from run_offline_rag import generate_anthropic, historical_fx_fact, selected_facts, validate_response


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.close()


class AnthropicAdapterTests(unittest.TestCase):
    def test_missing_key_is_clear_without_making_a_request(self):
        with patch.dict(os.environ, {}, clear=True), patch("run_offline_rag.urlopen") as urlopen:
            with self.assertRaisesRegex(RuntimeError, "ANTHROPIC_API_KEY is not set"):
                generate_anthropic([], "claude-sonnet-5", 1)
            urlopen.assert_not_called()

    def test_request_uses_schema_and_returns_usage(self):
        reply = {"route": "ANSWER_FACT", "answer": "Draft offer.", "citations": ["CATALOG.STATUS"]}
        wire = {"content": [{"type": "text", "text": json.dumps(reply)}],
                "usage": {"input_tokens": 12, "output_tokens": 8}, "stop_reason": "end_turn"}
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-secret", "ANTHROPIC_WORKSPACE_ID": "test-workspace"}), \
             patch("run_offline_rag.urlopen", return_value=FakeResponse(json.dumps(wire).encode())) as urlopen:
            result, stats = generate_anthropic(
                [{"role": "system", "content": "Use facts"},
                 {"role": "user", "content": "What is the fee?"}],
                "claude-sonnet-5", 1,
            )
        request = urlopen.call_args.args[0]
        payload = json.loads(request.data)
        self.assertEqual(request.full_url, "https://api.anthropic.com/v1/messages")
        self.assertEqual(payload["system"], "Use facts")
        self.assertEqual(payload["messages"], [{"role": "user", "content": "What is the fee?"}])
        self.assertEqual(payload["output_config"]["format"]["type"], "json_schema")
        self.assertEqual(request.get_header("Authorization"), "Bearer test-secret")
        self.assertEqual(request.get_header("Anthropic-workspace-id"), "test-workspace")
        self.assertEqual(result, reply)
        self.assertEqual(stats["prompt_tokens"], 12)

    def test_invalid_route_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "route/answer invalid"):
            validate_response({"route": "APPROVE", "answer": "Yes", "citations": []})

    def test_historical_fx_evidence_comes_from_csv_not_gold_label(self):
        cases = load_cases(CASES, {fact_id for fact_id, _ in load_facts()})
        case = next(case for case in cases if case["case_id"] == "ES-007")
        fact_id, body = historical_fx_fact(case)
        self.assertEqual(fact_id, "FX.HISTORICAL")
        self.assertIn("2025-08-31", body)
        self.assertIn("0.057989", body)
        self.assertNotIn("57.99 miles", body)

    def test_historical_fx_missing_row_fails_closed(self):
        case = {"case_id": "toy", "fx_lookup": {"date": "2024-02-30",
                "source_currency": "MXN", "target_currency": "USD"}}
        with self.assertRaisesRegex(ValueError, "Invalid FX date"):
            historical_fx_fact(case)

    def test_full_context_contains_each_fact_once(self):
        fact_map = dict(load_facts())
        selected = selected_facts({"country": "México"}, [], fact_map, 5, "full")
        self.assertEqual(len(selected), len(fact_map))
        self.assertEqual({fid for fid, _ in selected}, set(fact_map))


if __name__ == "__main__":
    unittest.main()
