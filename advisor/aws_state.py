"""DynamoDB-backed state for the public, synthetic-fixture judge deployment.

The table uses string ``pk`` and ``sk`` keys. Session records expire via TTL;
mock actions are retained for the reviewer queue until the stack is removed.
"""

from __future__ import annotations

import json
import secrets
import time
from dataclasses import asdict
from typing import Any

from .applications import ApplicationStorageError
from .policy import CARDS, OFFER_VERSION
from .service import Conversation
from .web import BrowserSession, SESSION_SECONDS


def encode_session(state: BrowserSession) -> str:
    fields = {key: value for key, value in vars(state).items() if key != "lock"}
    if state.chat is not None:
        fields["chat"] = asdict(state.chat)
        fields["chat"]["turns"] = fields["chat"]["turns"][-12:]
    return json.dumps(fields, ensure_ascii=False, separators=(",", ":"))


def decode_session(value: str) -> BrowserSession:
    data = json.loads(value)
    if not isinstance(data, dict):
        raise ValueError("Invalid stored session")
    chat = data.pop("chat", None)
    allowed = set(BrowserSession.__dataclass_fields__) - {"lock"}
    if set(data) - allowed:
        raise ValueError("Unknown stored session fields")
    state = BrowserSession(**data)
    if chat is not None:
        state.chat = Conversation(**chat)
    return state


class DynamoSessionStore:
    def __init__(self, table: Any):
        self.table = table

    def read(self, sid: str) -> tuple[BrowserSession, int] | None:
        response = self.table.get_item(Key={"pk": f"SESSION#{sid}", "sk": "STATE"},
                                       ConsistentRead=True)
        item = response.get("Item")
        if not item or int(item["expires_at"]) <= int(time.time()):
            return None
        return decode_session(item["state"]), int(item["version"])

    def write(self, sid: str, state: BrowserSession, version: int | None) -> None:
        # The serialized conversation has a tight bound, well below DynamoDB's
        # 400-KB item limit even when the visitor sends maximum-length messages.
        data = encode_session(state)
        if len(data.encode("utf-8")) > 350_000:
            raise ValueError("Conversation is too long to save")
        item = {"pk": f"SESSION#{sid}", "sk": "STATE", "state": data,
                "version": 1 if version is None else version + 1,
                "expires_at": int(state.last_active_at) + SESSION_SECONDS}
        if version is None:
            self.table.put_item(Item=item, ConditionExpression="attribute_not_exists(pk)")
        else:
            self.table.put_item(Item=item, ConditionExpression="#v = :prior",
                                ExpressionAttributeNames={"#v": "version"},
                                ExpressionAttributeValues={":prior": version})


class DynamoApplicationStore:
    """Idempotent application and handoff writes with committed read-back."""

    def __init__(self, table: Any):
        self.table = table

    @staticmethod
    def _key(conversation_id: str, suffix: str) -> dict[str, str]:
        return {"pk": f"ACTION#{conversation_id}", "sk": suffix}

    def _read(self, key: dict[str, str]) -> dict | None:
        try:
            response = self.table.get_item(Key=key, ConsistentRead=True)
            return response.get("Item", {}).get("record")
        except Exception as exc:
            raise ApplicationStorageError("Mock action could not be read") from exc

    def _create(self, key: dict[str, str], record: dict, expected: dict) -> dict:
        try:
            self.table.put_item(Item={**key, "record": record},
                                ConditionExpression="attribute_not_exists(pk)")
        except Exception as exc:
            # An already committed record is safe to return only after its
            # identity and confirmation fields pass verification below.
            if getattr(exc, "response", {}).get("Error", {}).get("Code") != "ConditionalCheckFailedException":
                raise ApplicationStorageError("Mock action could not be written") from exc
        saved = self._read(key)
        if saved is None or any(saved.get(k) != v for k, v in expected.items()) or saved.get("status") != "PENDING_REVIEW":
            raise ApplicationStorageError("Mock action did not pass read-back verification")
        return saved

    def read(self, conversation_id: str, card: str) -> dict | None:
        return self._read(self._key(conversation_id, f"APPLICATION#{card}"))

    def create_and_verify(self, draft: dict, confirmed_at: str) -> dict:
        if draft.get("card") not in CARDS or draft.get("offer_version") != OFFER_VERSION:
            raise ValueError("Unknown card or offer version")
        expected = {key: draft[key] for key in (
            "conversation_id", "confirmation_token", "customer_alias", "country", "card",
            "offer_version", "campaign_id", "precheck_status", "precheck_policy_version",
            "precheck_consent_at")}
        expected["precheck_reasons"] = (json.dumps(draft["precheck_reasons"])
                                        if draft["precheck_reasons"] is not None else None)
        record = {**expected, "application_id": "APP-" + secrets.token_hex(6).upper(),
                  "confirmed_at": confirmed_at, "status": "PENDING_REVIEW"}
        return self._create(self._key(draft["conversation_id"], f"APPLICATION#{draft['card']}"), record, expected)

    def read_handoff(self, conversation_id: str, reason: str) -> dict | None:
        return self._read(self._key(conversation_id, f"HANDOFF#{reason}"))

    def create_handoff_and_verify(self, draft: dict, created_at: str) -> dict:
        if (draft.get("reason") != "CUSTOMER_REQUEST" or draft.get("offer_version") != OFFER_VERSION or
            draft.get("card") not in (*CARDS, None) or draft.get("language") not in {"es", "pt"}):
            raise ValueError("Invalid mock handoff request")
        expected = {key: draft[key] for key in (
            "conversation_id", "customer_alias", "country", "language", "card", "reason", "offer_version")}
        record = {**expected, "handoff_id": "HND-" + secrets.token_hex(6).upper(),
                  "created_at": created_at, "status": "PENDING_REVIEW"}
        return self._create(self._key(draft["conversation_id"], "HANDOFF#CUSTOMER_REQUEST"), record, expected)

    def review_queue(self) -> dict[str, list[dict]]:
        applications, handoffs = [], []
        cursor = None
        try:
            while True:
                args = {"FilterExpression": "begins_with(pk, :prefix)",
                        "ExpressionAttributeValues": {":prefix": "ACTION#"}}
                if cursor:
                    args["ExclusiveStartKey"] = cursor
                result = self.table.scan(**args)
                for item in result.get("Items", []):
                    record = item["record"].copy()
                    if item["sk"].startswith("APPLICATION#"):
                        record["precheck_reasons"] = json.loads(record["precheck_reasons"]) if record["precheck_reasons"] else []
                        applications.append({key: record[key] for key in (
                            "application_id", "customer_alias", "country", "card", "campaign_id",
                            "precheck_status", "precheck_reasons", "precheck_policy_version",
                            "confirmed_at", "status")})
                    elif item["sk"].startswith("HANDOFF#"):
                        handoffs.append({key: record[key] for key in (
                            "handoff_id", "customer_alias", "country", "language", "card",
                            "reason", "created_at", "status")})
                cursor = result.get("LastEvaluatedKey")
                if not cursor:
                    break
        except Exception as exc:
            raise ApplicationStorageError("Review queue could not be read") from exc
        applications.sort(key=lambda item: item["confirmed_at"], reverse=True)
        handoffs.sort(key=lambda item: item["created_at"], reverse=True)
        return {"applications": applications, "handoffs": handoffs}


class DynamoAnswerCounter:
    def __init__(self, table: Any):
        self.table = table

    def consume(self, day: str, limit: int) -> None:
        from .web import DemoLimitError
        try:
            self.table.update_item(
                Key={"pk": f"QUOTA#{day}", "sk": "ANSWERS"},
                UpdateExpression="SET #n = if_not_exists(#n, :zero) + :one, expires_at = :expiry",
                ConditionExpression="attribute_not_exists(#n) OR #n < :limit",
                ExpressionAttributeNames={"#n": "used"},
                ExpressionAttributeValues={":zero": 0, ":one": 1, ":limit": limit,
                                           ":expiry": int(time.time()) + 3 * 86400})
        except Exception as exc:
            if getattr(exc, "response", {}).get("Error", {}).get("Code") == "ConditionalCheckFailedException":
                raise DemoLimitError("Today's advisor answer limit has been reached") from exc
            raise DemoLimitError("Advisor usage limit is temporarily unavailable") from exc
