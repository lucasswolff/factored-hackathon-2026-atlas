"""Function URL adapter smoke test without AWS credentials or network calls."""

from __future__ import annotations

import base64
import json
import os
import threading
import time
import unittest
from unittest.mock import patch

from advisor import lambda_app
from advisor.aws_state import DynamoAnswerCounter, DynamoApplicationStore, DynamoSessionStore
from advisor.synthetic_data import SyntheticDirectory
from advisor.test_aws_state import FakeTable
from advisor.web import AdvisorServer, WebApp


class LambdaAdapterTest(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {"ADVISOR_REVIEW_CODE": "review-test-code-9876543210",
                                        "ANTHROPIC_API_KEY": "fake-test-key"})
        self.env.start()
        self.table = FakeTable()
        self.sessions = DynamoSessionStore(self.table)
        self.app = WebApp(directory=SyntheticDirectory(), applications=DynamoApplicationStore(self.table),
                          hosted=True, answer_counter=DynamoAnswerCounter(self.table))
        self.server = AdvisorServer(("127.0.0.1", 0), self.app)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.original = (lambda_app._server, lambda_app._app, lambda_app._sessions)
        lambda_app._server, lambda_app._app, lambda_app._sessions = self.server, self.app, self.sessions
        self.cookies = []

    def tearDown(self):
        lambda_app._server, lambda_app._app, lambda_app._sessions = self.original
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)
        self.env.stop()

    def call(self, method, path, body=None, headers=None):
        event = {"version": "2.0", "rawPath": path, "cookies": self.cookies,
                 "headers": {"host": "example.lambda-url.us-east-2.on.aws",
                             "content-type": "application/json"},
                 "requestContext": {"http": {"method": method}}}
        if headers:
            event["headers"].update(headers)
        if body is not None:
            event["body"] = json.dumps(body)
        result = lambda_app.lambda_handler(event, None)
        if result.get("cookies"):
            self.cookies = [cookie.split(";", 1)[0] for cookie in result["cookies"]]
        return result

    def test_session_survives_cold_start_like_memory_clear(self):
        self.assertEqual(self.call("GET", "/")["statusCode"], 200)
        result = self.call("POST", "/api/start", {"entry": "direct", "country": "México",
                                                    "language": "es", "alias": "P05"})
        self.assertEqual(result["statusCode"], 200)
        self.assertEqual(json.loads(result["body"])["profile"]["country"], "México")
        # The adapter clears process memory on each invocation and restores the
        # trusted fixture binding from DynamoDB before executing the request.
        result = self.call("GET", "/api/state")
        self.assertEqual(result["statusCode"], 200)
        self.assertEqual(json.loads(result["body"])["conversation"]["demo_alias"], "P05")
        self.assertEqual(json.loads(result["body"])["profile"]["country"], "México")
        self.assertEqual(self.call("GET", "/assets/app.css")["statusCode"], 200)
        self.assertEqual(self.table.items[("SESSION#" + self.cookies[0].split("=", 1)[1], "STATE")]["version"], 2)

    def test_review_shell_opens_and_api_requires_explicit_code(self):
        shell = self.call("GET", "/review")
        self.assertEqual(shell["statusCode"], 200)
        self.assertIn("Reviewer code", shell["body"])
        self.assertEqual(self.call("GET", "/api/review")["statusCode"], 401)
        wrong = base64.b64encode(b"reviewer:wrong-code").decode()
        self.assertEqual(self.call("GET", "/api/review", headers={"authorization": f"Basic {wrong}"})["statusCode"], 401)
        valid = base64.b64encode(b"reviewer:review-test-code-9876543210").decode()
        self.assertEqual(self.call("GET", "/api/review", headers={"authorization": f"Basic {valid}"})["statusCode"], 200)

    def test_chat_application_and_read_back_survive_invocations(self):
        self.call("GET", "/")
        self.assertEqual(self.call("POST", "/api/start", {
            "entry": "direct", "country": "Argentina", "language": "es", "alias": "P06"})["statusCode"], 200)
        first = json.loads(self.call("POST", "/api/chat", {"message": "Quiero solicitar Horizon"})["body"])
        self.assertEqual(first["events"][-1]["route"], "ASK_PRECHECK_CONSENT")
        self.call("POST", "/api/chat", {"message": "no"})
        final = json.loads(self.call("POST", "/api/chat", {"message": "sí"})["body"])
        reference = final["application"]["application_id"]
        self.assertEqual(final["application"]["status"], "PENDING_REVIEW")
        self.assertEqual(json.loads(self.call("GET", "/api/state")["body"])["application"]["application_id"], reference)
        self.assertEqual(self.app.applications.review_queue()["applications"][0]["application_id"], reference)

    def test_request_log_omits_chat_content_and_profile(self):
        self.call("GET", "/")
        self.call("POST", "/api/start", {
            "entry": "direct", "country": "Argentina", "language": "es", "alias": "P06"})
        with patch("advisor.lambda_app._emit") as emit:
            response = self.call("POST", "/api/chat", {"message": "Quiero solicitar Horizon"})
        self.assertEqual(response["statusCode"], 200)
        report = emit.call_args.args[0]
        self.assertEqual(report["event"], "advisor_request")
        self.assertEqual(report["endpoint"], "/api/chat")
        self.assertEqual(report["route"], "ASK_PRECHECK_CONSENT")
        self.assertNotIn("Quiero", json.dumps(report))
        self.assertNotIn("P06", json.dumps(report))

    def _start_application(self):
        self.assertEqual(self.call("GET", "/")["statusCode"], 200)
        self.assertEqual(self.call("POST", "/api/start", {
            "entry": "direct", "country": "México", "language": "es", "alias": "P05"})["statusCode"], 200)
        prepared = self.call("POST", "/api/application-prepare", {"card": "Horizon"})
        self.assertEqual(prepared["statusCode"], 200)
        return json.loads(prepared["body"])["application_draft"]["confirmation_token"]

    def _action_rows(self):
        return [item for (pk, sk), item in self.table.items.items()
                if pk.startswith("ACTION#") and sk.startswith("APPLICATION#")]

    def test_model_outage_returns_fallback_without_mock_action(self):
        self.call("GET", "/")
        self.call("POST", "/api/start", {
            "entry": "offer", "selected_card": "Rewards", "country": "México",
            "language": "es", "alias": "P05"})
        with patch("advisor.service._generate", side_effect=RuntimeError("provider offline")) as model:
            response = self.call("POST", "/api/chat", {"message": "¿Qué beneficios tiene Rewards?"})
        self.assertEqual(response["statusCode"], 200)
        state = json.loads(response["body"])
        self.assertEqual(state["last_result"]["route"], "FALLBACK")
        self.assertIsNone(state["application"])
        self.assertEqual(len(self._action_rows()), 0)
        self.assertEqual(model.call_count, 1)
        self.assertEqual(sum(item.get("used", 0) for (pk, _), item in self.table.items.items()
                             if pk.startswith("QUOTA#")), 1)

    def test_failed_application_write_can_retry_same_confirmation(self):
        token = self._start_application()
        original_put = self.table.put_item
        def fail_action_write(**kwargs):
            if kwargs["Item"]["pk"].startswith("ACTION#"):
                raise OSError("simulated write failure")
            return original_put(**kwargs)
        with patch.object(self.table, "put_item", side_effect=fail_action_write):
            response = self.call("POST", "/api/application-submit", {
                "confirm": True, "confirmation_token": token})
        self.assertEqual(response["statusCode"], 503)
        self.assertEqual(len(self._action_rows()), 0)
        state = json.loads(self.call("GET", "/api/state")["body"])
        self.assertIsNone(state["application"])
        self.assertTrue(state["application_draft"]["verification_pending"])
        retried = self.call("POST", "/api/application-submit", {
            "confirm": True, "confirmation_token": token})
        self.assertEqual(retried["statusCode"], 200)
        self.assertEqual(len(self._action_rows()), 1)
        self.assertEqual(json.loads(retried["body"])["application"]["status"], "PENDING_REVIEW")

    def test_expired_session_cannot_confirm_application(self):
        token = self._start_application()
        sid = self.cookies[0].split("=", 1)[1]
        self.table.items[("SESSION#" + sid, "STATE")]["expires_at"] = int(time.time()) - 1
        stale = self.call("POST", "/api/application-submit", {
            "confirm": True, "confirmation_token": token})
        self.assertEqual(stale["statusCode"], 400)
        self.assertEqual(len(self._action_rows()), 0)
        state = json.loads(self.call("GET", "/api/state")["body"])
        self.assertIsNone(state["conversation"])
        self.assertIsNone(state["application"])

    def test_double_submit_uses_one_stored_application(self):
        token = self._start_application()
        payload = {"confirm": True, "confirmation_token": token}
        first = self.call("POST", "/api/application-submit", payload)
        second = self.call("POST", "/api/application-submit", payload)
        self.assertEqual(first["statusCode"], 200)
        self.assertEqual(second["statusCode"], 200)
        first_id = json.loads(first["body"])["application"]["application_id"]
        self.assertEqual(json.loads(second["body"])["application"]["application_id"], first_id)
        self.assertEqual(len(self._action_rows()), 1)
        self.assertEqual(self.app.applications.review_queue()["applications"][0]["application_id"], first_id)
        repeated_chat = self.call("POST", "/api/chat", {"message": "sí"})
        self.assertEqual(repeated_chat["statusCode"], 200)
        self.assertEqual(json.loads(repeated_chat["body"])["application"]["application_id"], first_id)
        self.assertEqual(len(self._action_rows()), 1)

    def test_session_save_failure_after_action_recovers_by_readback(self):
        token = self._start_application()
        original_put = self.table.put_item
        def fail_session_write(**kwargs):
            if kwargs["Item"]["pk"].startswith("SESSION#"):
                raise OSError("simulated session write failure")
            return original_put(**kwargs)
        with patch.object(self.table, "put_item", side_effect=fail_session_write):
            response = self.call("POST", "/api/application-submit", {
                "confirm": True, "confirmation_token": token})
        self.assertEqual(response["statusCode"], 503)
        self.assertEqual(len(self._action_rows()), 1)
        retried = self.call("POST", "/api/application-submit", {
            "confirm": True, "confirmation_token": token})
        self.assertEqual(retried["statusCode"], 200)
        self.assertEqual(len(self._action_rows()), 1)
        self.assertEqual(json.loads(retried["body"])["application"]["application_id"],
                         self._action_rows()[0]["record"]["application_id"])

    def test_action_readback_failure_retries_existing_record(self):
        token = self._start_application()
        original_get = self.table.get_item
        def fail_action_read(**kwargs):
            if kwargs["Key"]["pk"].startswith("ACTION#"):
                raise OSError("simulated readback failure")
            return original_get(**kwargs)
        with patch.object(self.table, "get_item", side_effect=fail_action_read):
            response = self.call("POST", "/api/application-submit", {
                "confirm": True, "confirmation_token": token})
        self.assertEqual(response["statusCode"], 503)
        self.assertEqual(len(self._action_rows()), 1)
        state = json.loads(self.call("GET", "/api/state")["body"])
        self.assertIsNone(state["application"])
        self.assertTrue(state["application_draft"]["verification_pending"])
        retried = self.call("POST", "/api/application-submit", {
            "confirm": True, "confirmation_token": token})
        self.assertEqual(retried["statusCode"], 200)
        self.assertEqual(len(self._action_rows()), 1)
        self.assertEqual(json.loads(retried["body"])["application"]["application_id"],
                         self._action_rows()[0]["record"]["application_id"])


if __name__ == "__main__":
    unittest.main()
