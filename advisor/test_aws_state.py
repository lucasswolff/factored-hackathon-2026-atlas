"""Local contract tests for the DynamoDB deployment path."""

from __future__ import annotations

import json
import unittest

from advisor.applications import ApplicationStorageError
from advisor.aws_state import (DynamoAnswerCounter, DynamoApplicationStore,
                               DynamoSessionStore, decode_session, encode_session)
from advisor.policy import OFFER_VERSION
from advisor.service import Conversation
from advisor.web import BrowserSession, DemoLimitError


class ConditionalFailure(Exception):
    response = {"Error": {"Code": "ConditionalCheckFailedException"}}


class FakeTable:
    def __init__(self):
        self.items = {}

    def get_item(self, *, Key, ConsistentRead):
        item = self.items.get((Key["pk"], Key["sk"]))
        return {"Item": item.copy()} if item else {}

    def put_item(self, *, Item, ConditionExpression, ExpressionAttributeValues=None, **_kwargs):
        key = (Item["pk"], Item["sk"])
        old = self.items.get(key)
        if ConditionExpression == "attribute_not_exists(pk)" and old:
            raise ConditionalFailure()
        if ConditionExpression == "#v = :prior" and (not old or old["version"] != ExpressionAttributeValues[":prior"]):
            raise ConditionalFailure()
        self.items[key] = Item.copy()

    def scan(self, **_kwargs):
        return {"Items": [item.copy() for item in self.items.values()
                          if item["pk"].startswith("ACTION#")]}

    def update_item(self, *, Key, ConditionExpression, ExpressionAttributeValues, **_kwargs):
        key = (Key["pk"], Key["sk"])
        item = self.items.get(key, {**Key, "used": 0})
        if item["used"] >= ExpressionAttributeValues[":limit"]:
            raise ConditionalFailure()
        item["used"] += 1
        self.items[key] = item


class AwsStateTest(unittest.TestCase):
    def test_session_round_trip_and_conditional_create(self):
        table = FakeTable()
        store = DynamoSessionStore(table)
        state = BrowserSession()
        state.chat = Conversation.start("es", "México", selected_card="Horizon")
        state.chat.demo_alias = "P05"
        state.chat.demo_token = "server-issued-token"
        state.chat.profile_permission = True
        state.events = [{"role": "assistant", "text": "Hola"}]
        store.write("sid", state, None)
        restored, version = store.read("sid")
        self.assertEqual(version, 1)
        self.assertEqual(restored.chat.demo_alias, "P05")
        self.assertEqual(restored.events, state.events)
        self.assertEqual(json.loads(encode_session(restored))["chat"]["selected_card"], "Horizon")
        self.assertEqual(decode_session(encode_session(restored)).chat.country, "México")
        with self.assertRaises(ConditionalFailure):
            store.write("sid", state, None)

    def test_mock_actions_read_back_and_review_queue(self):
        store = DynamoApplicationStore(FakeTable())
        draft = {"conversation_id": "conversation", "confirmation_token": "explicit-token",
                 "customer_alias": "P05", "country": "México", "card": "Horizon",
                 "offer_version": OFFER_VERSION, "campaign_id": None,
                 "precheck_status": "REVIEW_REQUIRED", "precheck_reasons": ["reason"],
                 "precheck_policy_version": "POLICY-1", "precheck_consent_at": "timestamp"}
        first = store.create_and_verify(draft, "time")
        self.assertEqual(store.create_and_verify(draft, "later")["application_id"], first["application_id"])
        self.assertEqual(store.read("conversation", "Horizon")["status"], "PENDING_REVIEW")
        changed = {**draft, "confirmation_token": "different-token"}
        with self.assertRaises(ApplicationStorageError):
            store.create_and_verify(changed, "later")
        handoff = store.create_handoff_and_verify(
            {"conversation_id": "conversation", "customer_alias": "P05", "country": "México",
             "language": "es", "card": "Horizon", "reason": "CUSTOMER_REQUEST",
             "offer_version": OFFER_VERSION}, "time")
        self.assertEqual(store.read_handoff("conversation", "CUSTOMER_REQUEST")["handoff_id"], handoff["handoff_id"])
        queue = store.review_queue()
        self.assertEqual(queue["applications"][0]["precheck_reasons"], ["reason"])
        self.assertEqual(len(queue["handoffs"]), 1)

    def test_global_answer_cap(self):
        counter = DynamoAnswerCounter(FakeTable())
        counter.consume("2026-10-01", 2)
        counter.consume("2026-10-01", 2)
        with self.assertRaises(DemoLimitError):
            counter.consume("2026-10-01", 2)


if __name__ == "__main__":
    unittest.main()
