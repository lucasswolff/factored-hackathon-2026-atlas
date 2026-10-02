"""Integration checks against ten selected organizer-synthetic source records."""

import unittest
from unittest.mock import patch
from decimal import Decimal
import json
import tempfile
from pathlib import Path

from advisor.data_access import DemoDirectory, Profile
from advisor.policy import POLICY_VERSION, precheck, suggest
from advisor.service import Conversation, respond
from advisor.session import (grant_precheck_consent, grant_profile_permission,
                             profile_summary, recommendation_for_session,
                             run_precheck, select_demo_persona, sign_out)


class CustomerPolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = DemoDirectory()

    def test_ten_source_personas_cover_expected_paths(self):
        expected = {
            "P01": ("Campus", "REVIEW_REQUIRED"),
            "P02": ("Campus", "REVIEW_REQUIRED"),
            "P03": ("Campus", "REVIEW_REQUIRED"),
            "P04": ("", "REVIEW_REQUIRED"),
            "P05": ("Horizon", "MEETS_DEMO_THRESHOLDS_PENDING_REVIEW"),
            "P06": ("", "REVIEW_REQUIRED"),
            "P07": ("Rewards", "MEETS_DEMO_THRESHOLDS_PENDING_REVIEW"),
            "P08": ("Summit", "MEETS_DEMO_THRESHOLDS_PENDING_REVIEW"),
            "P09": ("Summit", "MEETS_DEMO_THRESHOLDS_PENDING_REVIEW"),
            "P10": ("", "REVIEW_REQUIRED"),
        }
        self.assertEqual(set(self.directory.aliases()), set(expected))
        for alias, (suggested, status) in expected.items():
            with self.subTest(alias=alias):
                public = self.directory.public_persona(alias)
                chat = Conversation.start("es" if int(alias[-2:]) % 2 else "pt", public["country"])
                select_demo_persona(chat, self.directory, alias)
                grant_profile_permission(chat)
                proposal = recommendation_for_session(chat, self.directory)["policy"]
                self.assertEqual(proposal.card, suggested)
                card = suggested or ("Campus" if public["segment"] == "Student" else "Horizon")
                grant_precheck_consent(chat, self.directory, card)
                outcome = run_precheck(chat, self.directory, card)["policy"]
                self.assertEqual(outcome.status, status)
                self.assertEqual(outcome.policy_version, POLICY_VERSION)
                self.assertNotEqual(outcome.status, "APPROVED")
                sign_out(chat, self.directory)

    def test_unknown_alias_and_cross_country_selection_fail(self):
        with self.assertRaises(PermissionError):
            self.directory.issue_test_session("CUST-123")
        chat = Conversation.start("es", "México")
        with self.assertRaises(PermissionError):
            select_demo_persona(chat, self.directory, "P01")
        self.assertIsNone(chat.demo_alias)

    def test_directory_startup_does_not_read_score_or_income(self):
        with tempfile.TemporaryDirectory() as folder:
            cache_path = Path(folder) / "personas.json"
            with patch("advisor.data_access._score", side_effect=AssertionError("score read before permission")), \
                 patch("advisor.data_access._decimal", side_effect=AssertionError("income read before permission")):
                directory = DemoDirectory(cache_path=cache_path)
                self.assertEqual(len(directory.aliases()), 10)
            cache = json.loads(cache_path.read_text(encoding="utf-8"))
            self.assertEqual(set(cache["entries"]), set(directory.aliases()))
            self.assertNotIn("credit_score", cache_path.read_text(encoding="utf-8"))
            self.assertEqual(cache_path.stat().st_mode & 0o777, 0o600)
            with patch("advisor.data_access.csv.DictReader", side_effect=AssertionError("warm cache scanned CSV")):
                self.assertEqual(DemoDirectory(cache_path=cache_path).aliases(), directory.aliases())
        token = directory.issue_test_session("P05")
        with self.assertRaises(PermissionError):
            directory.read_profile(token, False)
        directory.close_session(token)
        with self.assertRaises(PermissionError):
            directory.read_profile(token, True)

    def test_permission_consent_and_one_use_precheck(self):
        chat = Conversation.start("es", "México")
        with self.assertRaises(PermissionError):
            grant_profile_permission(chat)
        select_demo_persona(chat, self.directory, "P05")
        with self.assertRaises(PermissionError):
            profile_summary(chat, self.directory)
        with self.assertRaises(PermissionError):
            grant_precheck_consent(chat, self.directory, "Horizon")
        self.assertEqual(recommendation_for_session(chat, self.directory)["route"], "ASK_PERMISSION")
        grant_profile_permission(chat)
        self.assertEqual(profile_summary(chat, self.directory)["income_currency"], "MXN")
        self.assertEqual(recommendation_for_session(chat, self.directory)["policy"].card, "Horizon")
        with self.assertRaises(PermissionError):
            run_precheck(chat, self.directory, "Horizon")
        grant_precheck_consent(chat, self.directory, "Horizon")
        with self.assertRaises(PermissionError):
            run_precheck(chat, self.directory, "Rewards")
        result = run_precheck(chat, self.directory, "Horizon")
        self.assertEqual(result["policy"].status, "MEETS_DEMO_THRESHOLDS_PENDING_REVIEW")
        with self.assertRaises(PermissionError):
            run_precheck(chat, self.directory, "Horizon")
        sign_out(chat, self.directory)
        with self.assertRaises(PermissionError):
            profile_summary(chat, self.directory)

    def test_public_model_request_has_no_persona_fields(self):
        chat = Conversation.start("pt", "México")
        select_demo_persona(chat, self.directory, "P08")
        grant_profile_permission(chat)
        profile = self.directory.read_profile(chat.demo_token, True)
        with patch("advisor.service._generate", return_value={"answer": "O Summit oferece benefícios de viagem.", "citations": ["BENEFIT.SUMMIT"]}) as model:
            result = respond(chat, "Qual é a anuidade do Summit?", directory=self.directory)
        self.assertEqual(result["route"], "ANSWER_FACT")
        system, context, _ = model.call_args.args
        self.assertNotIn("P08", system + context)
        self.assertNotIn(str(profile.monthly_income), system + context)
        self.assertNotIn(str(profile.score), context)
        with patch("advisor.service._generate") as model:
            result = respond(chat, "Qual cartão você me recomenda para mim?", directory=self.directory)
            self.assertEqual(result["route"], "POLICY_SUGGESTION")
            model.assert_not_called()

    def test_signed_in_questions_do_not_claim_session_is_missing_or_run_precheck(self):
        chat = Conversation.start("es", "México")
        select_demo_persona(chat, self.directory, "P05")
        with patch("advisor.service._generate") as model:
            result = respond(chat, "¿Califico para Horizon?", directory=self.directory)
            self.assertEqual(result["route"], "ASK_PRECHECK_CONSENT")
            self.assertEqual(result["card"], "Horizon")
            self.assertNotIn("falta una sesión", result["answer"])
            result = respond(chat, "Quiero solicitar la tarjeta", directory=self.directory)
            self.assertEqual(result["route"], "ASK_PRECHECK_CONSENT")
            model.assert_not_called()

    def test_switching_personas_revokes_previous_permissions(self):
        chat = Conversation.start("pt", "México")
        select_demo_persona(chat, self.directory, "P05")
        grant_profile_permission(chat)
        grant_precheck_consent(chat, self.directory, "Horizon")
        old_token = chat.demo_token
        select_demo_persona(chat, self.directory, "P08")
        with self.assertRaises(PermissionError):
            self.directory.read_profile(old_token, True)
        self.assertFalse(chat.profile_permission)
        self.assertIsNone(chat.precheck_consent_card)
        with self.assertRaises(PermissionError):
            profile_summary(chat, self.directory)
        grant_profile_permission(chat)
        outcome = recommendation_for_session(chat, self.directory)
        self.assertIn("Sugestão", outcome["answer"])
        self.assertEqual(outcome["policy"].card, "Summit")

    def test_country_threshold_boundaries_are_not_cross_currency(self):
        thresholds = {"Colombia": ("COP", "10000000"),
                      "México": ("MXN", "40000"),
                      "Argentina": ("ARS", "820000")}
        for country, (currency, minimum) in thresholds.items():
            with self.subTest(country=country):
                at = Profile("fixture", country, "Plus", 650, Decimal(minimum), currency, False, "Active")
                below = Profile("fixture", country, "Plus", 650, Decimal(minimum) - Decimal("0.01"), currency, False, "Active")
                self.assertEqual(precheck(at, "Rewards").status, "MEETS_DEMO_THRESHOLDS_PENDING_REVIEW")
                self.assertEqual(precheck(below, "Rewards").status, "DOES_NOT_MEET_DEMO_RULES")
                self.assertIn("income_below_demo_threshold", precheck(below, "Rewards").reasons)

    def test_student_segment_is_not_enrollment_proof_or_definitive_denial(self):
        student = Profile("fixture", "México", "Student", 700, Decimal("20000"), "MXN", False, "Active")
        other = Profile("fixture", "México", "Basic", 700, Decimal("20000"), "MXN", False, "Active")
        self.assertEqual(precheck(student, "Campus").status, "REVIEW_REQUIRED")
        self.assertEqual(precheck(other, "Campus").status, "REVIEW_REQUIRED")

    def test_student_low_score_and_horizon_review_band(self):
        student = Profile("student", "México", "Student", 539, Decimal("6594.74"), "MXN", False, "Active")
        self.assertEqual(suggest(student).card, "Campus")
        self.assertEqual(precheck(student, "Campus").status, "REVIEW_REQUIRED")
        for score, expected in ((539, "DOES_NOT_MEET_DEMO_RULES"),
                                (540, "REVIEW_REQUIRED"), (559, "REVIEW_REQUIRED"),
                                (560, "MEETS_DEMO_THRESHOLDS_PENDING_REVIEW")):
            profile = Profile("basic", "Colombia", "Basic", score, Decimal("4000000"), "COP", False, "Active")
            self.assertEqual(precheck(profile, "Horizon").status, expected)
        low_income = Profile("basic", "Colombia", "Basic", 550, Decimal("2999999"), "COP", False, "Active")
        self.assertEqual(precheck(low_income, "Horizon").status, "DOES_NOT_MEET_DEMO_RULES")


if __name__ == "__main__":
    unittest.main()
