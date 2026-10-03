"""Exercise the browser API without spending model credits."""

from __future__ import annotations

import http.client
import json
import os
import sqlite3
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from advisor.applications import ApplicationStore
from advisor.policy import POLICY_VERSION
from advisor.web import AdvisorServer, WebApp


class BrowserJourneyTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tempdir = tempfile.TemporaryDirectory()
        cls.store_path = Path(cls.tempdir.name) / "mock_applications.sqlite"
        cls.server = AdvisorServer(("127.0.0.1", 0), WebApp(applications=ApplicationStore(cls.store_path)))
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=5)
        cls.tempdir.cleanup()

    def setUp(self):
        self.cookie = None

    def request(self, method, path, body=None):
        connection = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=10)
        headers = {}
        if self.cookie:
            headers["Cookie"] = self.cookie
        if body is not None:
            headers["Content-Type"] = "application/json"
            body = json.dumps(body)
        connection.request(method, path, body=body, headers=headers)
        response = connection.getresponse()
        raw = response.read()
        cookie = response.getheader("Set-Cookie")
        if cookie:
            self.cookie = cookie.split(";", 1)[0]
        status = response.status
        connection.close()
        return status, json.loads(raw) if response.getheader("Content-Type", "").startswith("application/json") else raw

    def test_static_and_campaign_entry(self):
        status, html = self.request("GET", "/")
        self.assertEqual(status, 200)
        self.assertIn(b"Explore a card offer", html)
        status, review_html = self.request("GET", "/review")
        self.assertEqual(status, 200)
        self.assertIn(b"Pending review queue", review_html)
        status, preview = self.request("POST", "/api/persona-preview", {"alias": "P01"})
        self.assertEqual(status, 200)
        self.assertEqual(preview["persona"]["country"], "Colombia")
        self.assertIn("city", preview["persona"])
        self.assertIn("estimated_monthly_income_usd", preview["persona"])
        self.assertIn("usd_rate_date", preview["persona"])
        self.assertNotIn("customer_id", json.dumps(preview))
        status, state = self.request("POST", "/api/start", {"entry": "campaign", "campaign_id": "CMP-YYT37NY1CZS7", "country": "Colombia", "language": "es", "alias": "P01"})
        self.assertEqual(status, 200)
        self.assertEqual(state["conversation"]["selected_card"], "Campus")
        self.assertEqual(state["conversation"]["entry_kind"], "campaign")
        self.assertEqual(state["conversation"]["demo_alias"], "P01")
        self.assertIsNotNone(state["profile"])
        self.assertEqual(state["events"][0]["route"], "OPENING")
        self.assertNotIn("demo_token", json.dumps(state))
        status, _ = self.request("POST", "/api/start", {"entry": "campaign", "campaign_id": "CMP-YYT37NY1CZS7", "country": "México", "language": "es", "alias": "P05"})
        self.assertEqual(status, 400)
        status, _ = self.request("POST", "/api/start", {"entry": "direct", "country": "México", "language": "es", "alias": "P01"})
        self.assertEqual(status, 400)

    def test_campus_offer_exploration_in_each_country_has_correct_attribution(self):
        for country, alias, language in (("México", "P05", "es"), ("Argentina", "P03", "pt")):
            status, state = self.request("POST", "/api/start", {
                "entry": "offer", "selected_card": "Campus", "country": country,
                "language": language, "alias": alias,
            })
            self.assertEqual(status, 200)
            self.assertEqual(state["conversation"]["selected_card"], "Campus")
            self.assertEqual(state["conversation"]["entry_kind"], "offer")
            self.assertIsNone(state["conversation"]["campaign_id"])
            self.assertIn("Campus", state["events"][0]["text"])
            self.assertEqual(state["conversation"]["country"], country)
        status, _ = self.request("POST", "/api/start", {
            "entry": "offer", "selected_card": "Unknown", "country": "México",
            "language": "es", "alias": "P05",
        })
        self.assertEqual(status, 400)
        status, _ = self.request("POST", "/api/start", {
            "entry": "offer", "selected_card": "Campus", "campaign_id": "CMP-YYT37NY1CZS7",
            "country": "México", "language": "es", "alias": "P05",
        })
        self.assertEqual(status, 400)

    def test_general_direct_visit_remains_direct_after_card_selection(self):
        status, state = self.request("POST", "/api/start", {
            "entry": "direct", "country": "México", "language": "es", "alias": "P05",
        })
        self.assertEqual(status, 200)
        self.assertEqual(state["conversation"]["entry_kind"], "direct")
        self.assertIsNone(state["conversation"]["selected_card"])
        with patch("advisor.service._generate", return_value={
            "answer": "Campus tiene beneficios para estudiantes.",
            "citations": ["BENEFIT.CAMPUS"],
        }):
            status, state = self.request("POST", "/api/chat", {"message": "Cuéntame de Campus"})
        self.assertEqual(status, 200)
        self.assertEqual(state["conversation"]["selected_card"], "Campus")
        self.assertEqual(state["conversation"]["entry_kind"], "direct")
        self.assertIsNone(state["conversation"]["campaign_id"])

    def test_demo_profile_and_precheck_gates(self):
        status, state = self.request("POST", "/api/start", {"entry": "direct", "country": "México", "language": "pt", "alias": "P05"})
        self.assertEqual(status, 200)
        self.assertIsInstance(state["profile"]["credit_score"], int)
        status, _ = self.request("POST", "/api/precheck", {"card": "Horizon"})
        self.assertEqual(status, 400)
        self.assertEqual(state["profile"]["income_currency"], "MXN")
        status, state = self.request("POST", "/api/recommend", {})
        self.assertEqual(status, 200)
        self.assertEqual(state["last_result"]["route"], "POLICY_SUGGESTION")
        status, state = self.request("POST", "/api/precheck-consent", {"card": "Horizon", "agree": True})
        self.assertEqual(status, 200)
        self.assertEqual(state["conversation"]["precheck_consent_card"], "Horizon")
        status, _ = self.request("POST", "/api/precheck", {"card": "Rewards"})
        self.assertEqual(status, 400)
        status, state = self.request("POST", "/api/precheck", {"card": "Horizon"})
        self.assertEqual(status, 200)
        self.assertEqual(state["last_result"]["route"], "SIMULATED_PRECHECK")
        self.assertIsNone(state["conversation"]["precheck_consent_card"])
        status, _ = self.request("POST", "/api/precheck", {"card": "Horizon"})
        self.assertEqual(status, 400)
        status, state = self.request("POST", "/api/signout", {})
        self.assertEqual(status, 200)
        self.assertIsNone(state["profile"])
        self.assertIsNone(state["conversation"])

    def test_model_only_for_chat_and_home_clears_session(self):
        with patch("advisor.web.respond", return_value={"answer": "Resposta de teste", "route": "ANSWER_FACT", "citations": ["OFFER.CAMPUS"], "fact_version": "test"}) as model:
            self.request("POST", "/api/start", {"entry": "direct", "country": "Argentina", "language": "pt", "alias": "P03"})
            self.request("POST", "/api/recommend", {})
            model.assert_not_called()
            status, state = self.request("POST", "/api/chat", {"message": "Quais são os benefícios?"})
            self.assertEqual(status, 200)
            self.assertEqual(state["events"][-1]["text"], "Resposta de teste")
            self.assertEqual(model.call_count, 1)
        status, state = self.request("POST", "/api/home", {})
        self.assertEqual(status, 200)
        self.assertIsNone(state["conversation"])
        self.assertEqual(state["events"], [])

    def test_local_application_flow_works_without_model_key(self):
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": ""}):
            _, state = self.request("POST", "/api/start", {"entry": "direct", "country": "México", "language": "es", "alias": "P05"})
            self.assertFalse(state["chat_available"])
            with patch("advisor.service._generate", side_effect=AssertionError("local actions must not call model")):
                _, state = self.request("POST", "/api/chat", {"message": "Quiero solicitar Horizon"})
                self.assertEqual(state["events"][-1]["route"], "ASK_PRECHECK_CONSENT")
                _, state = self.request("POST", "/api/chat", {"message": "no"})
                self.assertEqual(state["events"][-1]["route"], "APPLICATION_CONFIRM")
                _, state = self.request("POST", "/api/chat", {"message": "sí"})
                self.assertEqual(state["events"][-1]["route"], "APPLICATION_RECORDED")
                self.assertEqual(state["application"]["status"], "PENDING_REVIEW")

    def test_explicit_no_precheck_request_goes_to_application_confirmation(self):
        self.request("POST", "/api/start", {"entry": "direct", "country": "México",
                                              "language": "es", "alias": "P05"})
        with patch("advisor.service._generate", side_effect=AssertionError("workflow must stay local")):
            _, state = self.request("POST", "/api/chat", {"message":
                "¿Podría solicitar Horizon directamente o es obligatorio hacer primero la evaluación previa?"})
            self.assertEqual(state["events"][-1]["route"], "ANSWER_FACT")
            self.assertIsNone(state["pending_action"])
            _, state = self.request("POST", "/api/chat", {"message":
                "Quiero solicitar Horizon sin evaluación previa"})
        self.assertEqual(state["events"][-1]["route"], "APPLICATION_CONFIRM")
        self.assertEqual(state["prechecks"], {})
        self.assertIsNone(state["application"])
        _, state = self.request("POST", "/api/chat", {"message": "sí"})
        self.assertEqual(state["application"]["status"], "PENDING_REVIEW")

    def test_no_precheck_request_without_card_requires_card_choice_first(self):
        self.request("POST", "/api/start", {"entry": "direct", "country": "México",
                                              "language": "pt", "alias": "P05"})
        with patch("advisor.service._generate", side_effect=AssertionError("workflow must stay local")):
            _, state = self.request("POST", "/api/chat", {"message":
                "Quero solicitar sem avaliação prévia"})
            self.assertEqual(state["events"][-1]["route"], "ASK_CARD")
            self.assertIsNone(state["application"])
            _, state = self.request("POST", "/api/chat", {"message": "Horizon"})
        self.assertEqual(state["events"][-1]["route"], "APPLICATION_CONFIRM")
        self.assertEqual(state["prechecks"], {})
        self.assertIsNone(state["application"])

    def test_acquisition_has_card_specific_chat_precheck_path(self):
        self.request("POST", "/api/start", {"entry": "campaign", "campaign_id": "CMP-I5TGQ4SXP4EG", "country": "Colombia", "language": "pt", "alias": "P04"})
        with patch("advisor.service._generate", return_value={"answer": "Rewards oferece milhas.", "citations": ["BENEFIT.REWARDS"]}):
            self.request("POST", "/api/chat", {"message": "Me fala mais sobre Rewards"})
        status, state = self.request("POST", "/api/chat", {"message": "Gostei, como faço para adquiri-lo?"})
        self.assertEqual(status, 200)
        self.assertEqual(state["conversation"]["selected_card"], "Rewards")
        self.assertEqual(state["events"][-1]["route"], "ASK_PRECHECK_CONSENT")
        self.assertEqual(state["events"][-1]["card"], "Rewards")
        self.assertEqual(state["pending_action"], {"kind": "precheck_choice", "card": "Rewards"})
        self.assertIsNone(state["conversation"]["precheck_consent_card"])
        status, state = self.request("POST", "/api/chat", {"message": "sim"})
        self.assertEqual(status, 200)
        self.assertEqual(state["events"][-1]["route"], "APPLICATION_CONFIRM")
        self.assertEqual(state["pending_action"], {"kind": "application_confirm", "card": "Rewards"})
        precheck_status = state["application_draft"]["precheck_status"]
        self.assertIsNotNone(precheck_status)
        self.assertIsNone(state["application"])
        status, state = self.request("POST", "/api/chat", {"message": "sim"})
        self.assertEqual(status, 200)
        self.assertEqual(state["application"]["status"], "PENDING_REVIEW")
        self.assertEqual(state["events"][-1]["route"], "APPLICATION_RECORDED")
        with sqlite3.connect(self.store_path) as db:
            row = db.execute("SELECT customer_alias, campaign_id, precheck_status, precheck_policy_version, precheck_consent_at FROM mock_applications WHERE application_id = ?",
                             (state["application"]["application_id"],)).fetchone()
        self.assertEqual(row[:4], ("P04", "CMP-I5TGQ4SXP4EG", precheck_status, POLICY_VERSION))
        self.assertIsNotNone(row[4])

    def test_rewards_campaign_can_record_summit_application(self):
        campaign_id = "CMP-NM2UHJMKPA0C"
        self.request("POST", "/api/start", {"entry": "campaign", "campaign_id": campaign_id,
                                              "country": "Colombia", "language": "pt", "alias": "P04"})
        with patch("advisor.service._generate", side_effect=AssertionError("application flow must stay local")):
            _, state = self.request("POST", "/api/chat", {"message": "Quero solicitar Summit"})
            self.assertEqual(state["conversation"]["selected_card"], "Summit")
            self.assertEqual(state["pending_action"], {"kind": "precheck_choice", "card": "Summit"})
            _, state = self.request("POST", "/api/chat", {"message": "não"})
            self.assertEqual(state["pending_action"], {"kind": "application_confirm", "card": "Summit"})
            self.assertEqual(state["application_draft"]["card"], "Summit")
            self.assertIsNone(state["application"])
            _, state = self.request("POST", "/api/chat", {"message": "sim"})
        self.assertEqual(state["events"][-1]["route"], "APPLICATION_RECORDED")
        self.assertEqual(state["application"]["card"], "Summit")
        self.assertEqual(state["application"]["campaign_id"], campaign_id)
        self.assertEqual(state["application"]["status"], "PENDING_REVIEW")
        with sqlite3.connect(self.store_path) as db:
            card, source = db.execute(
                "SELECT card, campaign_id FROM mock_applications WHERE application_id = ?",
                (state["application"]["application_id"],)).fetchone()
        self.assertEqual((card, source), ("Summit", campaign_id))

    def test_chat_can_skip_precheck_and_confirm_application(self):
        self.request("POST", "/api/start", {"entry": "campaign", "campaign_id": "CMP-I5TGQ4SXP4EG", "country": "Colombia", "language": "es", "alias": "P04"})
        with patch("advisor.service._generate", side_effect=AssertionError("confirmation must remain local")):
            _, state = self.request("POST", "/api/chat", {"message": "Quiero solicitar Rewards"})
            self.assertEqual(state["pending_action"], {"kind": "precheck_choice", "card": "Rewards"})
            _, state = self.request("POST", "/api/chat", {"message": "No gracias"})
            self.assertEqual(state["events"][-1]["route"], "APPLICATION_CONFIRM")
            self.assertIsNone(state["application_draft"]["precheck_status"])
            _, state = self.request("POST", "/api/chat", {"message": "tal vez"})
            self.assertEqual(state["events"][-1]["route"], "CLARIFY_CONFIRMATION")
            self.assertIsNone(state["application"])
            _, state = self.request("POST", "/api/chat", {"message": "Sí, quiero continuar"})
            self.assertEqual(state["events"][-1]["route"], "APPLICATION_RECORDED")
            self.assertEqual(state["application"]["status"], "PENDING_REVIEW")
            self.assertIsNone(state["application"]["precheck_status"])

    def test_short_want_clarifies_then_enters_application_path(self):
        self.request("POST", "/api/start", {"entry": "campaign", "campaign_id": "CMP-NM2UHJMKPA0C", "country": "Colombia", "language": "pt", "alias": "P04"})
        with patch("advisor.service._generate", side_effect=AssertionError("intent must stay local")):
            _, state = self.request("POST", "/api/chat", {"message": "quero"})
            self.assertEqual(state["events"][-1]["route"], "ASK_APPLICATION_INTENT")
            self.assertEqual(state["pending_action"], {"kind": "application_intent_clarify", "card": "Rewards"})
            _, state = self.request("POST", "/api/chat", {"message": "sim"})
            self.assertEqual(state["events"][-1]["route"], "ASK_PRECHECK_CONSENT")
            _, state = self.request("POST", "/api/chat", {"message": "não"})
            self.assertEqual(state["events"][-1]["route"], "APPLICATION_CONFIRM")
            _, state = self.request("POST", "/api/chat", {"message": "sim"})
            self.assertEqual(state["events"][-1]["route"], "APPLICATION_RECORDED")
            self.assertEqual(state["application"]["status"], "PENDING_REVIEW")

    def test_colloquial_want_starts_precheck_without_model_confirmation_loop(self):
        self.request("POST", "/api/start", {"entry": "campaign", "campaign_id": "CMP-I5TGQ4SXP4EG",
                                              "country": "México", "language": "pt", "alias": "P05"})
        with patch("advisor.service._generate", side_effect=AssertionError("application intent must stay local")):
            _, state = self.request("POST", "/api/chat", {"message": "ok vou querer esse"})
        self.assertEqual(state["events"][-1]["route"], "ASK_PRECHECK_CONSENT")
        self.assertEqual(state["pending_action"], {"kind": "precheck_choice", "card": "Horizon"})

    def test_comparison_followups_do_not_fall_back_to_entry_card(self):
        self.request("POST", "/api/start", {"entry": "campaign", "campaign_id": "CMP-I5TGQ4SXP4EG",
                                              "country": "Argentina", "language": "es", "alias": "P03"})
        _, state = self.request("POST", "/api/chat", {"message": "¿Qué tarjetas ofrecen sala VIP?"})
        self.assertEqual(state["events"][-1]["route"], "ANSWER_FACT")
        with patch("advisor.service._generate", side_effect=[
            {"answer": "Rewards y Summit ofrecen millas y visitas VIP. ¿Quieres conocer costos y tasas?",
             "citations": ["BENEFIT.REWARDS", "BENEFIT.SUMMIT"]},
            {"answer": "Rewards y Summit tienen cuotas bonificables. ¿Quieres los montos exactos?",
             "citations": ["FEE.AR", "FEE.WAIVER"]},
            {"answer": "Rewards ARS 60.000; Summit ARS 120.000 por año.",
             "citations": ["FEE.AR"]},
        ]) as model:
            self.request("POST", "/api/chat", {"message": "Cuéntame más"})
            self.request("POST", "/api/chat", {"message": "sí"})
            _, state = self.request("POST", "/api/chat", {"message": "sí"})
        self.assertEqual(model.call_count, 3)
        for call in model.call_args_list:
            context = json.loads(call.args[1])
            self.assertIn("Rewards", context["latest_question"])
            self.assertIn("Summit", context["latest_question"])
            self.assertIsNone(context["selected_card"])
        self.assertEqual(state["conversation"]["selected_card"], "Horizon")
        self.assertIn("Summit", state["events"][-1]["text"])

    def test_short_want_after_product_question_continues_information(self):
        self.request("POST", "/api/start", {"entry": "direct", "country": "Colombia", "language": "pt", "alias": "P01"})
        with patch("advisor.service._generate", side_effect=[
            {"answer": "Campus é voltado a estudantes. Quer saber mais sobre taxas ou condições?",
             "citations": ["BENEFIT.CAMPUS"]},
            {"answer": "Campus não tem anuidade; os juros de compras dependem do saldo não pago.",
             "citations": ["FEE.CO", "RATE.CO"]},
        ]) as model:
            self.request("POST", "/api/chat", {"message": "sou estudante"})
            _, state = self.request("POST", "/api/chat", {"message": "quero"})
        self.assertEqual(model.call_count, 2)
        self.assertEqual(state["events"][-1]["route"], "ANSWER_FACT")
        self.assertIsNone(state["pending_action"])
        self.assertIsNone(state["application_draft"])
        self.assertEqual(state["conversation"]["selected_card"], "Campus")

    def test_information_choice_clears_application_intent(self):
        self.request("POST", "/api/start", {"entry": "direct", "country": "Colombia", "language": "pt", "alias": "P01"})
        _, state = self.request("POST", "/api/chat", {"message": "quero"})
        self.assertEqual(state["pending_action"], {"kind": "application_intent_clarify", "card": None})
        _, state = self.request("POST", "/api/chat", {"message": "conhecer as opções"})
        self.assertEqual(state["events"][-1]["route"], "ANSWER_FACT")
        self.assertIsNone(state["pending_action"])
        _, state = self.request("POST", "/api/chat", {"message": "sim"})
        self.assertEqual(state["events"][-1]["route"], "CLARIFY_PRODUCT_INTENT")
        self.assertIsNone(state["pending_action"])
        self.assertIsNone(state["application"])

    def test_desejo_confirms_only_pending_application(self):
        self.request("POST", "/api/start", {"entry": "offer", "selected_card": "Campus",
                                              "country": "México", "language": "pt", "alias": "P02"})
        self.request("POST", "/api/chat", {"message": "Quero solicitar Campus"})
        self.request("POST", "/api/chat", {"message": "sim"})
        _, state = self.request("POST", "/api/chat", {"message": "desejo"})
        self.assertEqual(state["events"][-1]["route"], "APPLICATION_RECORDED")
        self.assertEqual(state["prechecks"]["Campus"], "REVIEW_REQUIRED")
        self.assertEqual(state["application"]["precheck_status"], "REVIEW_REQUIRED")
        status, queue = self.request("GET", "/api/review")
        self.assertEqual(status, 200)
        item = next(r for r in queue["applications"]
                    if r["application_id"] == state["application"]["application_id"])
        self.assertEqual(item["customer_alias"], "P02")
        self.assertIn("score_below_demo_threshold", item["precheck_reasons"])
        self.assertEqual(item["precheck_policy_version"], POLICY_VERSION)
        self.assertNotIn("confirmation_token", json.dumps(queue))

    def test_human_request_is_stored_and_visible_without_assignment(self):
        self.request("POST", "/api/start", {"entry": "offer", "selected_card": "Campus",
                                              "country": "México", "language": "pt", "alias": "P02"})
        self.request("POST", "/api/chat", {"message": "Quero solicitar Campus"})
        _, state = self.request("POST", "/api/chat", {"message": "Prefiro falar com uma pessoa"})
        self.assertEqual(state["events"][-1]["route"], "HANDOFF_RECORDED")
        self.assertIsNone(state["pending_action"])
        self.assertIsNone(state["application_draft"])
        self.assertIsNone(state["application"])
        handoff_id = state["handoff"]["handoff_id"]
        self.assertIn(handoff_id, state["events"][-1]["text"])
        self.assertIn("não há pessoa atribuída", state["events"][-1]["text"])
        _, repeat = self.request("POST", "/api/chat", {"message": "Quero falar com uma pessoa"})
        self.assertEqual(repeat["handoff"]["handoff_id"], handoff_id)
        with patch("advisor.service._generate", return_value={
            "answer": "Rewards oferece milhas.", "citations": ["BENEFIT.REWARDS"]}):
            _, switched = self.request("POST", "/api/chat", {"message": "Fale sobre Rewards"})
        self.assertEqual(switched["conversation"]["selected_card"], "Rewards")
        _, repeat_after_switch = self.request("POST", "/api/chat", {"message": "Quero falar com uma pessoa"})
        self.assertEqual(repeat_after_switch["events"][-1]["route"], "HANDOFF_RECORDED")
        self.assertEqual(repeat_after_switch["handoff"]["handoff_id"], handoff_id)
        status, queue = self.request("GET", "/api/review")
        self.assertEqual(status, 200)
        item = next(r for r in queue["handoffs"] if r["handoff_id"] == handoff_id)
        self.assertEqual((item["customer_alias"], item["language"], item["card"]),
                         ("P02", "pt", "Campus"))
        self.assertEqual(item["status"], "PENDING_REVIEW")
        self.assertEqual(item["packet"]["verified_facts"]["fixture"], "P02")
        self.assertEqual(item["packet"]["evidence"]["offer_version"],
                         self.server.app.applications.read_handoff(
                             self.server.app.sessions[self.cookie.split("=", 1)[1]].conversation_id,
                             "CUSTOMER_REQUEST")["offer_version"])
        self.assertIn("Verify current student enrollment", item["packet"]["open_questions"])
        self.assertEqual(item["packet"]["actions_taken"]["prechecks"], [])
        self.assertNotIn("Prefiro falar", json.dumps(item))
        self.assertNotIn("agent_id", json.dumps(item))

    def test_handoff_packet_keeps_consented_policy_evidence_without_chat_dump(self):
        self.request("POST", "/api/start", {"entry": "direct", "country": "Argentina",
                                              "language": "es", "alias": "P06"})
        self.request("POST", "/api/chat", {"message": "Quiero solicitar Horizon"})
        self.request("POST", "/api/chat", {"message": "sí"})
        _, state = self.request("POST", "/api/chat", {"message": "Quiero hablar con una persona sobre esto"})
        handoff_id = state["handoff"]["handoff_id"]
        _, queue = self.request("GET", "/api/review")
        packet = next(r["packet"] for r in queue["handoffs"] if r["handoff_id"] == handoff_id)
        check = packet["actions_taken"]["prechecks"][0]
        self.assertEqual(check["card"], "Horizon")
        self.assertEqual(check["policy_version"], POLICY_VERSION)
        self.assertTrue(check["consent_at"])
        self.assertEqual(check["status"], "REVIEW_REQUIRED")
        self.assertIn("Verify missing profile fields before eligibility review", packet["open_questions"])
        self.assertIsNone(packet["actions_taken"]["application"])
        self.assertNotIn("Quiero hablar", json.dumps(packet))

    def test_handoff_readback_failure_never_claims_assignment(self):
        self.request("POST", "/api/start", {"entry": "direct", "country": "Argentina", "language": "es", "alias": "P03"})
        with patch.object(self.server.app.applications, "read_handoff", return_value=None):
            _, state = self.request("POST", "/api/chat", {"message": "Quiero hablar con una persona"})
        self.assertEqual(state["events"][-1]["route"], "HANDOFF_UNVERIFIED")
        self.assertIsNone(state["handoff"])
        _, state = self.request("POST", "/api/chat", {"message": "Quiero hablar con una persona"})
        self.assertEqual(state["events"][-1]["route"], "HANDOFF_RECORDED")
        self.assertEqual(state["handoff"]["status"], "PENDING_REVIEW")

    def test_second_card_credit_question_never_fakes_handoff(self):
        self.request("POST", "/api/start", {"entry": "campaign", "campaign_id": "CMP-NM2UHJMKPA0C", "country": "Colombia", "language": "pt", "alias": "P04"})
        self.request("POST", "/api/chat", {"message": "gostei, vou querer!"})
        self.request("POST", "/api/chat", {"message": "sim"})
        _, state = self.request("POST", "/api/chat", {"message": "sim"})
        rewards_id = state["application"]["application_id"]
        with patch("advisor.service._generate", side_effect=AssertionError("personal credit question must stay local")):
            _, state = self.request("POST", "/api/chat", {"message": "me fale sobre o Summit, eu teria credito para ele?"})
        self.assertEqual(state["events"][-1]["route"], "ASK_PRECHECK_CONSENT")
        self.assertEqual(state["pending_action"], {"kind": "precheck_choice", "card": "Summit"})
        _, state = self.request("POST", "/api/chat", {"message": "sim"})
        self.assertEqual(state["events"][-1]["route"], "SIMULATED_PRECHECK")
        self.assertIn("Summit", state["prechecks"])
        self.assertEqual(state["application"]["application_id"], rewards_id)
        _, state = self.request("POST", "/api/chat", {"message": "pode prosseguir"})
        self.assertEqual(state["events"][-1]["route"], "ASK_APPLICATION_INTENT")
        self.assertEqual(state["application"]["application_id"], rewards_id)
        _, state = self.request("POST", "/api/chat", {"message": "sim"})
        self.assertEqual(state["events"][-1]["route"], "APPLICATION_EXISTS")
        self.assertIn("solicitação de Rewards", state["events"][-1]["text"])
        self.assertEqual(state["application"]["application_id"], rewards_id)

    def test_affirmation_without_server_question_never_records_action(self):
        self.request("POST", "/api/start", {"entry": "direct", "country": "México", "language": "es", "alias": "P05"})
        with patch("advisor.service._generate", side_effect=AssertionError("bare confirmation must stay local")):
            _, state = self.request("POST", "/api/chat", {"message": "sí"})
            self.assertEqual(state["events"][-1]["route"], "ASK_APPLICATION_INTENT")
            self.assertIsNone(state["application"])
            _, state = self.request("POST", "/api/chat", {"message": "sí"})
            self.assertEqual(state["events"][-1]["route"], "ASK_CARD")
            self.assertIsNone(state["application"])

    def test_multiple_cards_require_choice_before_precheck(self):
        self.request("POST", "/api/start", {"entry": "campaign", "campaign_id": "CMP-NM2UHJMKPA0C", "country": "Colombia", "language": "pt", "alias": "P04"})
        with patch("advisor.service._generate", side_effect=AssertionError("precheck request must stay local")):
            _, state = self.request("POST", "/api/chat", {"message": "Quero solicitar Rewards ou Summit"})
        self.assertEqual(state["events"][-1]["route"], "ASK_CARD")
        self.assertEqual(state["pending_action"], {"kind": "choose_card", "card": None})
        self.assertEqual(state["conversation"]["selected_card"], "Rewards")
        self.assertIsNone(state["application_draft"])
        _, state = self.request("POST", "/api/chat", {"message": "Summit"})
        self.assertEqual(state["pending_action"], {"kind": "precheck_choice", "card": "Summit"})
        self.assertEqual(state["conversation"]["selected_card"], "Summit")

    def test_ending_after_application_does_not_deny_record(self):
        self.request("POST", "/api/start", {"entry": "direct", "country": "México", "language": "es", "alias": "P05"})
        self.request("POST", "/api/chat", {"message": "Quiero solicitar Horizon"})
        self.request("POST", "/api/chat", {"message": "no"})
        _, state = self.request("POST", "/api/chat", {"message": "sí"})
        application_id = state["application"]["application_id"]
        _, state = self.request("POST", "/api/chat", {"message": "salir"})
        self.assertEqual(state["events"][-1]["route"], "STOP")
        self.assertNotIn("no se creó", state["events"][-1]["text"])
        self.assertEqual(state["application"]["application_id"], application_id)
        self.assertTrue(state["conversation"]["stopped"])

    def test_ending_while_consent_pending_creates_no_action(self):
        self.request("POST", "/api/start", {"entry": "direct", "country": "Argentina", "language": "pt", "alias": "P03"})
        self.request("POST", "/api/chat", {"message": "Quero solicitar Campus"})
        _, state = self.request("POST", "/api/chat", {"message": "encerrar"})
        self.assertEqual(state["events"][-1]["route"], "STOP")
        self.assertIsNone(state["pending_action"])
        self.assertIsNone(state["application"])

    def test_chat_cancel_and_expired_confirmation_do_not_submit(self):
        self.request("POST", "/api/start", {"entry": "direct", "country": "México", "language": "es", "alias": "P05"})
        _, state = self.request("POST", "/api/chat", {"message": "Quiero solicitar una tarjeta"})
        self.assertEqual(state["events"][-1]["route"], "ASK_CARD")
        _, state = self.request("POST", "/api/chat", {"message": "Horizon"})
        self.assertEqual(state["pending_action"], {"kind": "precheck_choice", "card": "Horizon"})
        _, state = self.request("POST", "/api/chat", {"message": "no"})
        self.assertEqual(state["events"][-1]["route"], "APPLICATION_CONFIRM")
        _, state = self.request("POST", "/api/chat", {"message": "no"})
        self.assertEqual(state["events"][-1]["route"], "APPLICATION_CANCELLED")
        self.assertIsNone(state["application"])
        self.assertIsNone(state["application_draft"])
        self.assertIsNone(state["pending_action"])
        _, state = self.request("POST", "/api/chat", {"message": "Quiero solicitar Horizon"})
        self.assertEqual(state["events"][-1]["route"], "ASK_PRECHECK_CONSENT")
        self.server.app.sessions[self.cookie.split("=", 1)[1]].pending_action["created_at"] = 0
        _, state = self.request("POST", "/api/chat", {"message": "sí"})
        self.assertEqual(state["events"][-1]["route"], "ACTION_EXPIRED")
        self.assertIsNone(state["application"])
        self.assertIsNone(state["application_draft"])
        self.assertIsNone(state["pending_action"])

    def test_chat_readback_failure_is_not_reported_as_success(self):
        self.request("POST", "/api/start", {"entry": "direct", "country": "Argentina", "language": "pt", "alias": "P03"})
        self.request("POST", "/api/chat", {"message": "Quero solicitar Campus"})
        self.request("POST", "/api/chat", {"message": "não"})
        with patch.object(self.server.app.applications, "read", return_value=None):
            status, state = self.request("POST", "/api/chat", {"message": "sim"})
        self.assertEqual(status, 200)
        self.assertEqual(state["events"][-1]["route"], "APPLICATION_UNVERIFIED")
        self.assertIsNone(state["application"])
        self.assertTrue(state["application_draft"]["verification_pending"])
        status, state = self.request("POST", "/api/chat", {"message": "sim"})
        self.assertEqual(status, 200)
        self.assertEqual(state["events"][-1]["route"], "APPLICATION_RECORDED")
        self.assertEqual(state["application"]["status"], "PENDING_REVIEW")

    def test_application_requires_confirmation_and_is_idempotent(self):
        self.request("POST", "/api/start", {"entry": "direct", "country": "México", "language": "es", "alias": "P05"})
        status, _ = self.request("POST", "/api/application-submit", {"confirm": True, "confirmation_token": "guess"})
        self.assertEqual(status, 400)
        status, state = self.request("POST", "/api/chat", {"message": "Quiero solicitar la tarjeta Horizon"})
        self.assertEqual(status, 200)
        self.assertIsNone(state["application"])
        self.assertIsNone(state["application_draft"])
        status, state = self.request("POST", "/api/application-prepare", {"card": "Horizon"})
        self.assertEqual(status, 200)
        self.assertEqual(state["events"][-1]["route"], "APPLICATION_CONFIRM")
        token = state["application_draft"]["confirmation_token"]
        self.assertIsNone(state["application"])
        status, _ = self.request("POST", "/api/application-submit", {"confirm": False, "confirmation_token": token})
        self.assertEqual(status, 400)
        status, _ = self.request("POST", "/api/application-submit", {"confirm": True, "confirmation_token": "wrong"})
        self.assertEqual(status, 400)
        original_cookie = self.cookie
        self.cookie = None
        self.request("POST", "/api/start", {"entry": "direct", "country": "México", "language": "es", "alias": "P08"})
        status, _ = self.request("POST", "/api/application-submit", {"confirm": True, "confirmation_token": token})
        self.assertEqual(status, 400)
        self.cookie = original_cookie
        status, state = self.request("POST", "/api/chat", {"message": "tal vez"})
        self.assertEqual(status, 200)
        self.assertEqual(state["events"][-1]["route"], "CLARIFY_CONFIRMATION")
        self.assertIsNone(state["application"])
        status, state = self.request("POST", "/api/application-submit", {"confirm": True, "confirmation_token": token})
        self.assertEqual(status, 200)
        app = state["application"]
        self.assertEqual(app["status"], "PENDING_REVIEW")
        self.assertEqual(app["card"], "Horizon")
        self.assertIsNone(app["precheck_status"])
        self.assertEqual(state["events"][-1]["route"], "APPLICATION_RECORDED")
        self.assertIn(app["application_id"], state["events"][-1]["text"])
        status, retry = self.request("POST", "/api/application-submit", {"confirm": True, "confirmation_token": token})
        self.assertEqual(status, 200)
        self.assertEqual(retry["application"]["application_id"], app["application_id"])
        with sqlite3.connect(self.store_path) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM mock_applications WHERE application_id = ?", (app["application_id"],)).fetchone()[0], 1)
        self.assertEqual(self.store_path.stat().st_mode & 0o777, 0o600)
        status, _ = self.request("POST", "/api/application-prepare", {"card": "Rewards"})
        self.assertEqual(status, 400)

    def test_cancel_and_failed_readback_never_claim_success(self):
        self.request("POST", "/api/start", {"entry": "direct", "country": "Argentina", "language": "pt", "alias": "P03"})
        _, state = self.request("POST", "/api/application-prepare", {"card": "Campus"})
        old_token = state["application_draft"]["confirmation_token"]
        status, state = self.request("POST", "/api/application-cancel", {})
        self.assertEqual(status, 200)
        self.assertIsNone(state["application_draft"])
        self.assertIsNone(state["application"])
        status, _ = self.request("POST", "/api/application-submit", {"confirm": True, "confirmation_token": old_token})
        self.assertEqual(status, 400)
        _, state = self.request("POST", "/api/application-prepare", {"card": "Campus"})
        token = state["application_draft"]["confirmation_token"]
        with patch.object(self.server.app.applications, "read", return_value=None):
            status, error = self.request("POST", "/api/application-submit", {"confirm": True, "confirmation_token": token})
        self.assertEqual(status, 503)
        self.assertIn("not verified", error["error"])
        _, state = self.request("GET", "/api/state")
        self.assertIsNone(state["application"])
        self.assertTrue(state["application_draft"]["verification_pending"])
        self.assertNotIn("APPLICATION_RECORDED", [event["route"] for event in state["events"]])
        status, _ = self.request("POST", "/api/application-cancel", {})
        self.assertEqual(status, 400)
        status, state = self.request("POST", "/api/application-submit", {"confirm": True, "confirmation_token": token})
        self.assertEqual(status, 200)
        self.assertEqual(state["application"]["status"], "PENDING_REVIEW")


if __name__ == "__main__":
    unittest.main()
