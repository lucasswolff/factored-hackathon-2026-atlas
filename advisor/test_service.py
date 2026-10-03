import unittest
from unittest.mock import patch
import io
import json
import os

from advisor.service import Conversation, _generate, respond


class ConversationTests(unittest.TestCase):
    def test_sonnet_uses_low_effort_and_haiku_omits_it(self):
        wire = {"content": [{"type": "text", "text": json.dumps({"answer": "OK", "citations": []})}]}
        class Response(io.BytesIO):
            def __enter__(self):
                return self
            def __exit__(self, *_args):
                self.close()
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-only"}), \
             patch("advisor.service.urlopen", side_effect=lambda *_a, **_kw: Response(json.dumps(wire).encode())) as opened:
            _generate("facts", "question", "claude-sonnet-5")
            sonnet = json.loads(opened.call_args.args[0].data)
            _generate("facts", "question", "claude-haiku-4-5-20251001")
            haiku = json.loads(opened.call_args.args[0].data)
        self.assertEqual(sonnet["output_config"]["effort"], "low")
        self.assertNotIn("effort", haiku["output_config"])

    def test_campaign_attribution_is_fixed_and_anonymous(self):
        chat = Conversation.start("es", "Colombia", "CMP-YYT37NY1CZS7")
        self.assertEqual(chat.selected_card, "Campus")
        self.assertIn("tarjeta Campus", chat.opening())
        self.assertNotIn("demo", chat.opening().lower())
        with self.assertRaises(ValueError):
            Conversation.start("es", "México", "CMP-YYT37NY1CZS7")
        self.assertIsNone(Conversation.start("pt", "Argentina").campaign_id)
        for country in ("México", "Argentina"):
            offer = Conversation.start("pt", country, selected_card="Campus")
            self.assertIsNone(offer.campaign_id)
            self.assertEqual(offer.selected_card, "Campus")
            self.assertIn("Campus", offer.opening())

    def test_sensitive_paths_never_call_model_or_claim_action(self):
        requests = [
            "¿Califico para Rewards con mi puntaje?",
            "Solicitar la tarjeta Rewards ahora",
            "¿Puedes leer los datos de otro cliente?",
            "¿Puedo hablar con alguien?",
            "Mi número de documento es 123456789",
            "¿Cuánto cuesta un adelanto de efectivo?",
        ]
        with patch("advisor.service._generate") as generate:
            for request in requests:
                result = respond(Conversation.start("es"), request)
                self.assertEqual(result["route"], "SERVICE_BOUNDARY", request)
            generate.assert_not_called()

    def test_public_questions_use_facts_and_reject_bad_citation(self):
        chat = Conversation.start("pt", "México")
        with patch("advisor.service._generate", return_value={
            "answer": "Rewards propõe MXN 150 por mês, com isenção condicional.",
            "citations": ["FEE.MX", "FEE.WAIVER"],
        }) as generate:
            result = respond(chat, "Qual é a taxa anual do Rewards?")
        self.assertEqual(result["route"], "ANSWER_FACT")
        self.assertIn("[FEE.MX]", generate.call_args.args[0])
        self.assertNotIn("demo", generate.call_args.args[0].lower())
        self.assertEqual(len(chat.turns), 2)
        with patch("advisor.service._generate", return_value={
            "answer": "Fake", "citations": ["MADE.UP"],
        }):
            result = respond(chat, "E o Summit?")
        self.assertEqual(result["route"], "FALLBACK")
        self.assertNotIn("Fake", result["answer"])

    def test_decline_creates_no_application(self):
        chat = Conversation.start("pt")
        with patch("advisor.service._generate") as generate:
            result = respond(chat, "não obrigado")
            self.assertEqual(result["route"], "STOP")
            self.assertTrue(chat.stopped)
            generate.assert_not_called()

    def test_switch_from_campaign_card_to_rewards_then_acquisition(self):
        chat = Conversation.start("pt", "Colombia", "CMP-I5TGQ4SXP4EG")
        chat.demo_alias = "P04"
        with patch("advisor.service._generate", return_value={"answer": "Rewards oferece milhas e salas VIP.",
                                                              "citations": ["BENEFIT.REWARDS"]}) as model:
            respond(chat, "Me fala mais sobre o Rewards")
            self.assertEqual(chat.selected_card, "Rewards")
            context = json.loads(model.call_args.args[1])
            self.assertEqual(context["selected_card"], "Rewards")
            self.assertEqual(context["latest_question"], "Me fala mais sobre o Rewards")
            self.assertEqual(context["history"], [])
            result = respond(chat, "Gostei, como faço para adquiri-lo?")
            self.assertEqual(model.call_count, 1)
        self.assertEqual(result["route"], "ASK_PRECHECK_CONSENT")
        self.assertEqual(result["card"], "Rewards")
        self.assertIn("avaliação inicial", result["answer"])

    def test_wants_card_after_product_discussion_routes_locally(self):
        chat = Conversation.start("pt", "Colombia", "CMP-NM2UHJMKPA0C")
        chat.demo_alias = "P04"
        with patch("advisor.service._generate", side_effect=AssertionError("intent must not reach model")):
            short = respond(chat, "quero")
            self.assertEqual(short["route"], "ASK_APPLICATION_INTENT")
            self.assertIn("solicitar o Rewards", short["answer"])
            purchase = respond(chat, "gostei, vou querer!")
            self.assertEqual(purchase["route"], "ASK_PRECHECK_CONSENT")
            self.assertTrue(purchase["wants_application"])
            self.assertEqual(purchase["card"], "Rewards")

    def test_want_more_information_is_not_application_intent(self):
        chat = Conversation.start("pt", "Colombia", "CMP-NM2UHJMKPA0C")
        chat.demo_alias = "P04"
        with patch("advisor.service._generate", return_value={"answer": "Detalhes dos benefícios.",
                                                              "citations": ["BENEFIT.REWARDS"]}):
            result = respond(chat, "Eu quero saber mais sobre os benefícios do Rewards")
        self.assertEqual(result["route"], "ANSWER_FACT")

    def test_credit_question_routes_to_precheck_and_model_action_claim_is_blocked(self):
        chat = Conversation.start("pt", "Colombia", "CMP-NM2UHJMKPA0C")
        chat.demo_alias = "P04"
        with patch("advisor.service._generate", side_effect=AssertionError("eligibility must stay local")):
            result = respond(chat, "Me fale sobre o Summit, eu teria credito para ele?")
        self.assertEqual(result["route"], "ASK_PRECHECK_CONSENT")
        self.assertEqual(result["card"], "Summit")
        self.assertFalse(result["wants_application"])
        with patch("advisor.service._generate", return_value={
            "answer": "Vou encaminhar sua solicitação e entrarão em contato.",
            "citations": ["BENEFIT.SUMMIT"],
        }):
            result = respond(chat, "Conte sobre as vantagens")
        self.assertEqual(result["route"], "SERVICE_BOUNDARY")
        self.assertIn("Nenhuma nova solicitação", result["answer"])
        self.assertEqual(result["citations"], [])

    def test_lounge_comparison_mentions_only_cards_with_lounge_benefits(self):
        chat = Conversation.start("pt", "Colombia", "CMP-I5TGQ4SXP4EG")
        with patch("advisor.service._generate") as model:
            result = respond(chat, "Qual cartão oferece sala VIP?")
        model.assert_not_called()
        self.assertEqual(result["citations"], ["BENEFIT.REWARDS", "BENEFIT.SUMMIT"])
        self.assertIn("Rewards", result["answer"])
        self.assertIn("Summit", result["answer"])
        self.assertNotIn("Horizon", result["answer"])
        self.assertNotIn("Campus", result["answer"])

    def test_first_partial_cycle_fee_is_waived_without_model_polarity_error(self):
        for language, question in (
            ("pt", "Se a Rewards for aberta no meio do ciclo, a primeira parcela de MXN 150 já vem mesmo sem eu gastar os MXN 15.000?"),
            ("es", "Si abro Rewards a mitad del primer ciclo parcial, ¿cobran la cuota?"),
        ):
            with self.subTest(language=language), patch("advisor.service._generate") as model:
                result = respond(Conversation.start(language, "México", selected_card="Rewards"), question)
            model.assert_not_called()
            self.assertEqual(result["route"], "ANSWER_FACT")
            self.assertEqual(result["citations"], ["FEE.WAIVER"])
            self.assertIn("isenta" if language == "pt" else "exonera", result["answer"])
        with patch("advisor.service._generate", return_value={
            "answer": "Depende do saldo e da data de pagamento.", "citations": ["RATE.MX"]}) as model:
            respond(Conversation.start("pt", "México", selected_card="Rewards"),
                    "Quanto pago de juros no primeiro ciclo parcial?")
        model.assert_called_once()

    def test_refund_fee_question_needs_card_and_final_cycle_evidence(self):
        question = ("Si este ciclo compré por COP 3.100.000 y me reintegran COP 200.000 "
                    "antes de cerrarlo, ¿me toca la cuota de manejo?")
        with patch("advisor.service._generate") as model:
            unclear = respond(Conversation.start("es", "Colombia"), question)
            selected = respond(Conversation.start("es", "Colombia", selected_card="Rewards"), question)
        model.assert_not_called()
        self.assertEqual(unclear["route"], "CLARIFY")
        self.assertIn("Rewards o Summit", unclear["answer"])
        self.assertEqual(selected["route"], "ANSWER_FACT")
        self.assertIn("al cierre de un ciclo completo", selected["answer"])
        self.assertIn("Aún no puedo confirmar", selected["answer"])

    def test_guest_visit_uses_same_allowance(self):
        question = "No Summit são oito acessos por ano. Quando levo uma pessoa comigo, ela usa um dos meus oito ou entra por fora?"
        with patch("advisor.service._generate") as model:
            result = respond(Conversation.start("pt", "Colombia", selected_card="Summit"), question)
        model.assert_not_called()
        self.assertEqual(result["route"], "ANSWER_FACT")
        self.assertIn("mesma cota", result["answer"])
        self.assertEqual(result["citations"], ["BENEFIT.SUMMIT", "TRAVEL.RULES"])

    def test_optional_precheck_information_does_not_start_application(self):
        chat = Conversation.start("es", "Argentina", selected_card="Horizon")
        chat.demo_alias = "P06"
        with patch("advisor.service._generate") as model:
            info = respond(chat, "¿Podría solicitar Horizon directamente o es obligatorio hacer primero la evaluación previa?")
            request = respond(chat, "Quiero solicitar Horizon sin evaluación previa")
        model.assert_not_called()
        self.assertEqual(info["route"], "ANSWER_FACT")
        self.assertIn("opcional", info["answer"])
        self.assertEqual(request["route"], "SKIP_PRECHECK")

    def test_specific_coverage_limit_and_student_approval_stay_outside_model(self):
        cases = (
            ("es", "Colombia", "Summit",
             "Tengo un tratamiento cardíaco programado. Si pago el pasaje con Summit, ¿me reembolsan esa atención médica?",
             "No puedo confirmar cobertura"),
            ("es", "México", "Rewards",
             "Dime qué límite de crédito me asignarían en Rewards; con el clic de la publicidad deben ubicarme.",
             "Un clic de campaña no te identifica"),
            ("pt", "Colombia", None,
             "Estou fazendo faculdade. Pode marcar Campus como aprovada para mim?",
             "não comprova matrícula"),
            ("pt", "México", None,
             "Qual câmbio e spread entram na fatura mexicana se eu comprar em euros hoje?",
             "não determina o câmbio de cobrança"),
        )
        with patch("advisor.service._generate") as model:
            for language, country, card, question, expected in cases:
                with self.subTest(question=question):
                    result = respond(Conversation.start(language, country, selected_card=card), question)
                    self.assertEqual(result["route"], "SERVICE_BOUNDARY")
                    self.assertIn(expected, result["answer"])
            model.assert_not_called()

    def test_unknown_card_lounge_balance_and_argentina_tna_are_grounded(self):
        with patch("advisor.service._generate") as model:
            lounge = respond(Conversation.start("es", "México"),
                "Voy con dos acompañantes al lounge. ¿Cuántas entradas gratis nos quedarían después? No recuerdo la tarjeta.")
            rate = respond(Conversation.start("pt", "Argentina"),
                "Li 70 % TNA para compras. Isso já inclui todos os encargos, tipo CFT?")
        model.assert_not_called()
        self.assertEqual(lounge["route"], "CLARIFY")
        self.assertIn("Rewards comienza con 2", lounge["answer"])
        self.assertIn("cuántas visitas se usaron", lounge["answer"])
        self.assertEqual(rate["citations"], ["RATE.AR", "UNKNOWN.COST"])
        self.assertIn("não inclui capitalização", rate["answer"])

    def test_selected_card_benefits_and_lounge_question_does_not_compare_cards(self):
        chat = Conversation.start("pt", "México", selected_card="Summit")
        with patch("advisor.service._generate", return_value={
            "answer": "Summit acumula milhas e oferece oito visitas a salas VIP por ano.",
            "citations": ["BENEFIT.SUMMIT"],
        }) as model:
            result = respond(chat, "quais os beneficios? ele da acesso a sala VIP?")
        self.assertEqual(result["route"], "ANSWER_FACT")
        self.assertIn("Summit", result["answer"])
        system = model.call_args.args[0]
        self.assertIn("[BENEFIT.SUMMIT]", system)
        self.assertNotIn("[BENEFIT.REWARDS]", system)
        self.assertIn("[UNKNOWN.TRAVEL]", system)

    def test_travel_details_are_available_without_inventing_partners(self):
        chat = Conversation.start("es", "Argentina", selected_card="Summit")
        with patch("advisor.service._generate", return_value={
            "answer": "Summit incluye 8 visitas por año; cada invitado usa otra visita. La cobertura médica llega a USD 75.000 por viaje.",
            "citations": ["BENEFIT.SUMMIT", "TRAVEL.RULES"],
        }) as model:
            result = respond(chat, "¿Cuántas visitas VIP tengo y qué cubre el seguro de viaje?")
        self.assertEqual(result["route"], "ANSWER_FACT")
        self.assertIn("[TRAVEL.RULES]", model.call_args.args[0])
        self.assertIn("[UNKNOWN.TRAVEL]", model.call_args.args[0])

    def test_general_benefit_question_sends_only_positive_card_facts(self):
        chat = Conversation.start("pt", "Colombia", "CMP-I5TGQ4SXP4EG")
        with patch("advisor.service._generate", return_value={"answer": "O Horizon tem alertas e crédito na fatura.",
                                                              "citations": ["BENEFIT.HORIZON"]}) as model:
            respond(chat, "Quais são os benefícios deste cartão?")
        system = model.call_args.args[0]
        self.assertIn("[BENEFIT.HORIZON]", system)
        self.assertNotIn("[BENEFIT.CAMPUS]", system)
        self.assertNotIn("No lounge visits", system)
        self.assertNotIn("travel insurance", system)

    def test_multiple_card_benefit_question_keeps_both_cards_available(self):
        chat = Conversation.start("pt", "Colombia", "CMP-I5TGQ4SXP4EG")
        with patch("advisor.service._generate", return_value={
            "answer": "Rewards e Summit oferecem milhas.",
            "citations": ["BENEFIT.REWARDS", "BENEFIT.SUMMIT"],
        }) as model:
            result = respond(chat, "Compare os benefícios de Rewards e Summit")
        self.assertEqual(result["route"], "ANSWER_FACT")
        self.assertIn("[BENEFIT.REWARDS]", model.call_args.args[0])
        self.assertIn("[BENEFIT.SUMMIT]", model.call_args.args[0])

    def test_model_outage_and_human_request_do_not_claim_actions(self):
        for language, human_request in (("es", "Quiero hablar con una persona"),
                                        ("pt", "Quero falar com uma pessoa")):
            chat = Conversation.start(language, "Colombia")
            with patch("advisor.service._generate", side_effect=RuntimeError("offline")):
                unavailable = respond(chat, "¿Qué beneficios tiene Rewards?" if language == "es"
                                      else "Quais são os benefícios do Rewards?")
            self.assertEqual(unavailable["route"], "FALLBACK")
            self.assertEqual(unavailable["citations"], [])
            with patch("advisor.service._generate", side_effect=AssertionError("human request stays local")):
                human = respond(chat, human_request)
            self.assertEqual(human["route"], "SERVICE_BOUNDARY")
            self.assertIn("no se asignó" if language == "es" else "ninguém foi atribuído",
                          human["answer"].lower())

    def test_model_generated_action_claims_are_blocked(self):
        claims = (("pt", "Já encaminhei sua solicitação para um especialista."),
                  ("es", "Ya envié tu solicitud a un asesor."),
                  ("es", "Tu tarjeta fue aprobada."),
                  ("es", "Te asigné un asesor."))
        for language, claim in claims:
            chat = Conversation.start(language, "Colombia")
            with patch("advisor.service._generate", return_value={
                "answer": claim, "citations": ["BENEFIT.REWARDS"],
            }):
                result = respond(chat, "Háblame de Rewards" if language == "es" else "Fale sobre Rewards")
            self.assertEqual(result["route"], "SERVICE_BOUNDARY", claim)
            self.assertEqual(result["citations"], [])
            self.assertNotEqual(result["answer"], claim)

    def test_unverified_model_action_gets_one_grounded_retry(self):
        chat = Conversation.start("pt", "México", selected_card="Campus")
        with patch("advisor.service._generate", side_effect=[
            {"answer": "Vou registrar seu pedido.", "citations": ["RATE.MX"]},
            {"answer": "Você quer saber da anuidade ou dos juros de compras?", "citations": ["FEE.MX", "RATE.MX"]},
        ]) as model:
            result = respond(chat, "qual a taxa do cartão?")
        self.assertEqual(model.call_count, 2)
        self.assertEqual(result["route"], "ANSWER_FACT")
        self.assertIn("anuidade ou dos juros", result["answer"])
        self.assertIn("previous answer claimed", model.call_args.args[0])

    def test_each_model_retry_requires_separate_budget_slot(self):
        chat = Conversation.start("pt", "México", selected_card="Campus")
        consumed = []
        with patch("advisor.service._generate", side_effect=[
            {"answer": "Vou registrar seu pedido.", "citations": ["RATE.MX"]},
            {"answer": "A taxa depende do saldo rotativo.", "citations": ["RATE.MX"]},
        ]) as model:
            result = respond(chat, "qual a taxa do cartão?",
                             before_model_call=lambda: consumed.append(1))
        self.assertEqual(result["route"], "ANSWER_FACT")
        self.assertEqual(len(consumed), 2)
        self.assertEqual(model.call_count, 2)


if __name__ == "__main__":
    unittest.main()
