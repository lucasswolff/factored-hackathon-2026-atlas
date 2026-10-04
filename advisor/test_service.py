import unittest
from unittest.mock import patch
import io
import json
import os

from advisor.service import Conversation, _classify_intent, _generate, respond
from advisor.synthetic_data import SyntheticDirectory
from advisor.session import grant_profile_permission, select_demo_persona
from advisor.product_routing import classify_product_intent


class ConversationTests(unittest.TestCase):
    def test_model_first_intent_overrides_brittle_application_words(self):
        directory = SyntheticDirectory()
        for intent, message, expected_route in (
                ("PUBLIC_FACT", "No quiero solicitar esta tarjeta", "ANSWER_FACT"),
                ("PUBLIC_FACT", "¿Cómo solicito esta tarjeta?", "ANSWER_FACT"),
                ("APPLY", "queiro esta", "ASK_PRECHECK_CONSENT"),
                ("APPLY", "Me gustaría quedarme con esta", "ASK_PRECHECK_CONSENT")):
            with self.subTest(message=message):
                chat = Conversation.start("es", "México", selected_card="Horizon")
                select_demo_persona(chat, directory, "P05")
                grant_profile_permission(chat)
                classified = {"intent": intent, "card": "CURRENT", "lower_annual_fee": False,
                              "no_annual_fee": False, "travel_required": False,
                              "skip_precheck": False}
                with patch("advisor.service._classify_intent", return_value=classified), patch(
                        "advisor.service._generate", return_value={
                            "answer": "Puedo explicar las condiciones de Horizon.",
                            "citations": ["BENEFIT.HORIZON"], "unresolved": False,
                            "application_request": "NONE",
                            "comparison": {"kind": "NONE", "reference_card": "",
                                           "requires_travel_benefits": False}}) as answer_model:
                    result = respond(chat, message, directory=directory)
                self.assertEqual(result["route"], expected_route)
                if intent == "APPLY":
                    self.assertEqual(result["card"], "Horizon")
                    answer_model.assert_not_called()

    def test_model_first_profile_and_comparison_stay_service_owned(self):
        directory = SyntheticDirectory()
        chat = Conversation.start("pt", "México", selected_card="Horizon")
        select_demo_persona(chat, directory, "P05")
        grant_profile_permission(chat)
        base = {"card": "CURRENT", "lower_annual_fee": False,
                "no_annual_fee": False, "travel_required": False, "skip_precheck": False}
        with patch("advisor.service._classify_intent", return_value={**base, "intent": "RECOMMEND"}), patch(
                "advisor.service._generate") as answer_model:
            result = respond(chat, "Qual cartão combina com meu perfil?", directory=directory)
        self.assertEqual(result["route"], "POLICY_SUGGESTION")
        self.assertEqual(result["policy"].card, "Horizon")
        answer_model.assert_not_called()
        chat.selected_card = "Summit"
        with patch("advisor.service._classify_intent", return_value={
                **base, "intent": "COMPARE", "card": "Summit", "lower_annual_fee": True}), patch(
                "advisor.service._generate") as answer_model:
            result = respond(chat, "um mais barato que o Summit", directory=directory)
        self.assertEqual(result["route"], "ANSWER_FACT")
        self.assertIn("Rewards", result["answer"])
        self.assertEqual(chat.selected_card, "Summit")
        answer_model.assert_not_called()

    def test_intent_request_excludes_profile_values_and_uses_typed_choices(self):
        directory = SyntheticDirectory()
        chat = Conversation.start("es", "México", selected_card="Horizon")
        select_demo_persona(chat, directory, "P08")
        grant_profile_permission(chat)
        profile = directory.read_profile(chat.demo_token, True)
        decision = {"intent": "APPLY", "card": "CURRENT", "lower_annual_fee": False,
                    "no_annual_fee": False, "travel_required": False, "skip_precheck": False}
        wire = {"content": [{"type": "text", "text": json.dumps(decision)}]}
        class Response(io.BytesIO):
            def __enter__(self):
                return self
            def __exit__(self, *_args):
                self.close()
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-only"}), patch(
                "advisor.service.urlopen", side_effect=lambda *_a, **_kw: Response(json.dumps(wire).encode())) as opened:
            result = _classify_intent(chat, "queiro esta")
        self.assertEqual(result["intent"], "APPLY")
        payload = json.loads(opened.call_args.args[0].data)
        self.assertEqual(payload["model"], "claude-haiku-4-5-20251001")
        self.assertIn("APPLY", payload["output_config"]["format"]["schema"]["properties"]["intent"]["enum"])
        context = payload["messages"][0]["content"]
        self.assertNotIn("P08", context)
        self.assertNotIn(str(profile.score), context)
        self.assertNotIn(str(profile.monthly_income), context)

    def test_product_intent_routes_preferences_without_starting_actions(self):
        examples = (
            ("Qual cartão você me recomenda?", "PROFILE_RECOMMENDATION", False),
            ("¿Qué tarjeta me recomiendas?", "PROFILE_RECOMMENDATION", False),
            ("Sou estudante; qual o melhor cartão para mim?", "PROFILE_RECOMMENDATION", False),
            ("¿Cuál es la mejor tarjeta para mí?", "PROFILE_RECOMMENDATION", False),
            ("Me recomende outra opção com anuidade menor", "CATALOG_COMPARISON", True),
            ("Tem uma opção mais em conta?", "CATALOG_COMPARISON", True),
            ("¿Hay otra tarjeta sin cuota anual?", "CATALOG_COMPARISON", True),
            ("Qual cartão você me recomenda para viagem?", "CATALOG_COMPARISON", False),
            ("Qual outro cartão posso solicitar que atenda meus critérios?", "CATALOG_COMPARISON", False),
            ("Quero solicitar outro cartão", "CHOOSE_OTHER_CARD", False),
            ("Quiero solicitar otra tarjeta", "CHOOSE_OTHER_CARD", False),
            ("Quero solicitar Rewards", "PUBLIC_QUESTION", False),
            ("O cartão tem limite de crédito menor?", "PUBLIC_QUESTION", False),
            ("Quero acesso a salas VIP e seguro viagem", "PUBLIC_QUESTION", False),
            ("Ok, gostei do Rewards", "PUBLIC_QUESTION", False),
            ("Quero solicitar este cartão", "PUBLIC_QUESTION", False),
        )
        for message, route, lower_cost in examples:
            with self.subTest(message=message):
                named = ("Rewards",) if "Rewards" in message else ()
                intent = classify_product_intent(message, "Summit", named)
                self.assertEqual((intent.kind, intent.lower_cost), (route, lower_cost))

    def test_sonnet_uses_low_effort_and_haiku_omits_it(self):
        wire = {"content": [{"type": "text", "text": json.dumps(
            {"answer": "OK", "citations": [], "unresolved": False,
             "application_request": "NONE",
             "comparison": {"kind": "NONE", "reference_card": "", "requires_travel_benefits": False}})}]}
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

    def test_model_cannot_invent_application_confirmation(self):
        chat = Conversation.start("es", "Colombia", selected_card="Horizon")
        invented = {"answer": "Confírmame y quedará registrada tu solicitud.",
                    "citations": ["CATALOG.IDENTITY"], "unresolved": False,
                    "application_request": "NONE",
                    "comparison": {"kind": "NONE", "reference_card": "",
                                   "requires_travel_benefits": False}}
        with patch("advisor.service._generate", return_value=invented) as model:
            result = respond(chat, "Cuéntame sobre Horizon")
        self.assertEqual(result["route"], "SERVICE_BOUNDARY")
        self.assertNotIn("Confírmame", result["answer"])
        self.assertEqual(model.call_count, 2)

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

    def test_existing_card_cancellation_request_stays_out_of_acquisition(self):
        for language, message in (("pt", "quero cancelar meu cartao"),
                                  ("es", "Quiero dar de baja mi tarjeta")):
            with self.subTest(message=message), patch("advisor.service._generate") as model:
                result = respond(Conversation.start(language, "México"), message)
                self.assertEqual(result["route"], "SERVICE_BOUNDARY")
                self.assertIn("TERM.CANCELLATION", result["citations"])
                self.assertIn("nenhum cancelamento" if language == "pt" else
                              "ninguna cancelación", result["answer"].casefold())
                model.assert_not_called()

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

    def test_no_commitment_term_reaches_focused_card_questions(self):
        cases = (
            ("pt", "México", "Rewards", "Gostei do Rewards: tem fidelidade ou posso cancelar quando quiser?"),
            ("pt", "Colombia", "Campus", "Preciso manter o Campus por um período mínimo?"),
            ("es", "Argentina", "Summit", "¿Puedo dar de baja Summit antes de doce meses?"),
            ("es", "México", "Horizon", "¿Hay permanencia obligatoria para Horizon?"),
        )
        for language, country, card, question in cases:
            with self.subTest(question=question):
                chat = Conversation.start(language, country, selected_card=card)
                answer = ("Pode solicitar o cancelamento a qualquer momento, sem fidelidade nem multa."
                          if language == "pt" else
                          "Puedes solicitar la cancelación en cualquier momento, sin permanencia ni penalización.")
                with patch("advisor.service._generate", return_value={
                    "answer": answer, "citations": ["TERM.CANCELLATION"], "unresolved": False,
                }) as generate:
                    result = respond(chat, question)
                self.assertEqual(result["route"], "ANSWER_FACT")
                self.assertEqual(result["citations"], ["TERM.CANCELLATION"])
                self.assertIn("[TERM.CANCELLATION]", generate.call_args.args[0])
                self.assertEqual(chat.selected_card, card)

    def test_cancellation_questions_do_not_start_application(self):
        cases = (
            ("es", "Si contrato Horizon, ¿puedo cancelar sin multa cuando quiera?"),
            ("es", "¿Puedo solicitar la cancelación de Rewards antes del año?"),
            ("pt", "Se eu contratar Summit, posso cancelar logo depois?"),
            ("pt", "Posso pedir o cancelamento do Rewards a qualquer momento?"),
        )
        for language, question in cases:
            with self.subTest(question=question):
                chat = Conversation.start(language, "México", selected_card="Rewards")
                chat.demo_alias = "P08"
                with patch("advisor.service._generate", return_value={
                    "answer": "Sem prazo mínimo de permanência." if language == "pt" else
                              "Sin permanencia mínima.",
                    "citations": ["TERM.CANCELLATION"], "unresolved": False,
                }) as model:
                    result = respond(chat, question, directory=object())
                self.assertEqual(result["route"], "ANSWER_FACT")
                self.assertEqual(result["citations"], ["TERM.CANCELLATION"])
                model.assert_called_once()

    def test_model_cannot_claim_card_was_cancelled(self):
        chat = Conversation.start("pt", "México", selected_card="Rewards")
        with patch("advisor.service._generate", side_effect=[
            {"answer": "Cancelei seu cartão Rewards.", "citations": ["TERM.CANCELLATION"],
             "unresolved": False},
            {"answer": "O Rewards não tem fidelidade; você pode solicitar o cancelamento a qualquer momento.",
             "citations": ["TERM.CANCELLATION"], "unresolved": False},
        ]) as model:
            result = respond(chat, "Posso cancelar o Rewards quando quiser?")
        self.assertEqual(model.call_count, 2)
        self.assertEqual(result["route"], "ANSWER_FACT")
        self.assertIn("pode solicitar", result["answer"])

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

    def test_want_a_named_or_referenced_card_routes_locally_in_both_languages(self):
        for language, message, card in (
            ("pt", "quero o cartao summit", "Summit"),
            ("pt", "quero este cartão", "Horizon"),
            ("es", "quiero la tarjeta Summit", "Summit"),
            ("es", "quiero esta tarjeta", "Horizon"),
        ):
            with self.subTest(message=message):
                chat = Conversation.start(language, "México", selected_card="Horizon")
                chat.demo_alias = "P05"
                with patch("advisor.service._generate", side_effect=AssertionError("application intent must stay local")):
                    result = respond(chat, message)
                self.assertEqual(result["route"], "ASK_PRECHECK_CONSENT")
                self.assertEqual(result["card"], card)
                self.assertTrue(result["wants_application"])

    def test_model_cannot_claim_confirmation_was_recorded(self):
        chat = Conversation.start("pt", "México", selected_card="Summit")
        false_receipt = {"answer": "Essa confirmação já foi registrada; agora é só aguardar o encaminhamento.",
                         "citations": ["CATALOG.IDENTITY"], "unresolved": False}
        with patch("advisor.service._generate", return_value=false_receipt) as model:
            result = respond(chat, "Gostei da explicação")
        self.assertEqual(model.call_count, 2)
        self.assertEqual(result["route"], "SERVICE_BOUNDARY")
        self.assertIn("Nenhuma nova solicitação foi registrada", result["answer"])

    def test_want_more_information_is_not_application_intent(self):
        chat = Conversation.start("pt", "Colombia", "CMP-NM2UHJMKPA0C")
        chat.demo_alias = "P04"
        with patch("advisor.service._generate", return_value={"answer": "Detalhes dos benefícios.",
                                                              "citations": ["BENEFIT.REWARDS"]}):
            result = respond(chat, "Eu quero saber mais sobre os benefícios do Rewards")
        self.assertEqual(result["route"], "ANSWER_FACT")

    def test_cheaper_card_followup_uses_offer_fees_not_profile_suggestion(self):
        cases = (
            ("Colombia", "COP 3.000.000", "FEE.CO"),
            ("México", "MXN 15.000", "FEE.MX"),
            ("Argentina", "ARS 400.000", "FEE.AR"),
        )
        for country, threshold, fee_id in cases:
            with self.subTest(country=country):
                chat = Conversation.start("pt", country, selected_card="Summit")
                with patch("advisor.service._generate", side_effect=AssertionError("comparison must use facts")):
                    result = respond(chat, "Esse valor é alto. Existe algum cartão com valor menor e bons benefícios?",
                                     directory=object())
                self.assertEqual(result["route"], "ANSWER_FACT")
                self.assertIn(threshold, result["answer"])
                self.assertIn("Rewards", result["answer"])
                self.assertIn("Horizon", result["answer"])
                self.assertIn("não um pagamento obrigatório", result["answer"])
                self.assertIn(fee_id, result["citations"])
                self.assertEqual(chat.selected_card, "Summit")
        chat = Conversation.start("es", "México", selected_card="Summit")
        with patch("advisor.service._generate", side_effect=AssertionError("comparison must use facts")):
            result = respond(chat, "Háblame de otra tarjeta más barata que Summit", directory=object())
        self.assertEqual(result["route"], "ANSWER_FACT")
        self.assertIn("MXN 15.000", result["answer"])
        self.assertIn("no un pago obligatorio", result["answer"])

    def test_alternatives_filter_by_selected_card_fee_and_requested_benefit(self):
        with patch("advisor.service._generate", side_effect=AssertionError("comparison must use facts")):
            summit = Conversation.start("pt", "México", selected_card="Summit")
            vip = respond(summit, "Há outro cartão mais barato com sala VIP?", directory=object())
            self.assertEqual(vip["route"], "ANSWER_FACT")
            self.assertIn("Rewards:", vip["answer"])
            self.assertNotIn("Horizon:", vip["answer"])
            self.assertEqual(summit.selected_card, "Summit")

            horizon = Conversation.start("es", "México", selected_card="Horizon")
            no_fee = respond(horizon, "¿Hay otra tarjeta sin cuota anual?", directory=object())
            self.assertIn("Campus:", no_fee["answer"])
            self.assertNotIn("Rewards:", no_fee["answer"])

            rewards = Conversation.start("pt", "México", selected_card="Rewards")
            choice = respond(rewards, "Quero solicitar outro cartão", directory=object())
            self.assertEqual(choice["route"], "ASK_CARD")
            self.assertTrue(choice["wants_application"])
            no_check = respond(rewards, "Quero solicitar outro cartão sem avaliação", directory=object())
            self.assertEqual(no_check["route"], "ASK_CARD")
            self.assertTrue(no_check["skip_precheck"])

            direct = Conversation.start("pt", "México")
            travel = respond(direct, "Qual cartão você me recomenda para viagem?", directory=object())
            self.assertEqual(travel["route"], "ANSWER_FACT")
            self.assertIn("Summit:", travel["answer"])
            self.assertIn("Rewards:", travel["answer"])

    def test_named_card_in_price_comparison_does_not_switch_selected_card(self):
        chat = Conversation.start("pt", "México", selected_card="Horizon")
        with patch("advisor.service._generate", side_effect=AssertionError("comparison must use facts")):
            result = respond(chat, "quero um cartão mais barato que o Summit")
        self.assertIn("Rewards:", result["answer"])
        self.assertIn("Horizon:", result["answer"])
        self.assertEqual(chat.selected_card, "Horizon")

    def test_semantic_comparison_handles_unlisted_cheaper_paraphrase(self):
        chat = Conversation.start("pt", "México", selected_card="Horizon")
        with patch("advisor.service._generate", return_value={
            "answer": "Resposta provisória do modelo.", "citations": [], "unresolved": False,
            "comparison": {"kind": "LOWER_ANNUAL_FEE", "reference_card": "Summit",
                           "requires_travel_benefits": True},
        }) as model:
            result = respond(chat, "Existe um cartão que pese menos no bolso do que o Summit e ainda dê sala VIP?")
        self.assertEqual(model.call_count, 1)
        self.assertEqual(result["route"], "ANSWER_FACT")
        self.assertIn("Rewards:", result["answer"])
        self.assertNotIn("Horizon:", result["answer"])
        self.assertEqual(chat.selected_card, "Horizon")

    def test_semantic_comparison_does_not_own_application_or_interest_questions(self):
        chat = Conversation.start("pt", "México", selected_card="Summit")
        with patch("advisor.service._generate", return_value={
            "answer": "A taxa de compras é 36% ao ano.", "citations": ["RATE.MX"],
            "unresolved": False,
            "comparison": {"kind": "NONE", "reference_card": "Summit",
                           "requires_travel_benefits": False},
        }):
            result = respond(chat, "A taxa de juros do Summit é menor?")
        self.assertEqual(result["route"], "ANSWER_FACT")
        self.assertEqual(result["citations"], ["RATE.MX"])

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

    def test_benefits_and_annual_fee_keep_both_topics_in_context(self):
        examples = (
            ("pt", "México", "quais os beneficios deste cartão e qual a anualidade?", "FEE.MX"),
            ("pt", "México", "quais os beneficios e qual a mensalidade?", "FEE.MX"),
            ("pt", "México", "quais os beneficios e quanto pago todo mês?", "FEE.MX"),
            ("es", "México", "¿Qué beneficios tiene esta tarjeta y qual la anualidad?", "FEE.MX"),
            ("es", "México", "¿Cuáles son los beneficios y cuánto es la anualidad?", "FEE.MX"),
            ("es", "Colombia", "¿Qué beneficios tiene y cuál es la cuota anual?", "FEE.CO"),
            ("es", "Argentina", "¿Qué beneficios ofrece Summit y cuál es su tarifa anual?", "FEE.AR"),
            ("pt", "Argentina", "Quais os benefícios e a anuidade?", "FEE.AR"),
        )
        for language, country, question, fee_id in examples:
            with self.subTest(language=language, country=country):
                chat = Conversation.start(language, country, selected_card="Summit")
                with patch("advisor.service._generate", return_value={
                    "answer": "Summit oferece benefícios e tem uma anuidade informada nos termos.",
                    "citations": ["BENEFIT.SUMMIT", fee_id, "FEE.WAIVER"],
                }) as model:
                    result = respond(chat, question)
                self.assertEqual(result["route"], "ANSWER_FACT")
                system = model.call_args.args[0]
                for fact in ("BENEFIT.SUMMIT", fee_id, "FEE.WAIVER"):
                    self.assertIn(f"[{fact}]", system)
                self.assertNotIn("[BENEFIT.REWARDS]", system)
                for other_fee in {"FEE.CO", "FEE.MX", "FEE.AR"} - {fee_id}:
                    self.assertNotIn(f"[{other_fee}]", system)

    def test_combined_question_retries_answer_that_omits_annual_fee(self):
        chat = Conversation.start("pt", "México", selected_card="Summit")
        with patch("advisor.service._generate", side_effect=[
            {"answer": "Summit oferece milhas e acesso a salas VIP; não tenho a anuidade.",
             "citations": ["BENEFIT.SUMMIT"]},
            {"answer": "Summit oferece milhas e acesso a salas VIP. A anuidade máxima é MXN 6.000, "
                       "em parcelas de MXN 500, com dispensa condicional.",
             "citations": ["BENEFIT.SUMMIT", "FEE.MX", "FEE.WAIVER"]},
        ]) as model:
            result = respond(chat, "quais os beneficios deste cartão e qual a anualidade?")
        self.assertEqual(model.call_count, 2)
        self.assertIn("omitted a requested topic", model.call_args.args[0])
        self.assertIn("MXN 6.000", result["answer"])
        self.assertEqual(result["citations"], ["BENEFIT.SUMMIT", "FEE.MX", "FEE.WAIVER"])

    def test_monthly_fee_question_retries_benefit_only_answer(self):
        chat = Conversation.start("pt", "México", selected_card="Summit")
        with patch("advisor.service._generate", side_effect=[
            {"answer": "O Summit oferece milhas; não tenho a mensalidade.",
             "citations": ["BENEFIT.SUMMIT"]},
            {"answer": "O Summit oferece milhas e a parcela mensal máxima é MXN 500, com isenção por gastos elegíveis.",
             "citations": ["BENEFIT.SUMMIT", "FEE.MX", "FEE.WAIVER"]},
        ]) as model:
            result = respond(chat, "quais os beneficios e qual a mensalidade?")
        self.assertEqual(model.call_count, 2)
        self.assertIn("MXN 500", result["answer"])

    def test_selected_card_fee_fact_excludes_other_card_amounts(self):
        chat = Conversation.start("es", "México", selected_card="Summit")
        with patch("advisor.service._generate", return_value={
            "answer": "Summit ofrece millas y una cuota mensual máxima de MXN 500.",
            "citations": ["BENEFIT.SUMMIT", "FEE.MX"],
        }) as model:
            respond(chat, "¿Qué ventajas tiene Summit y cuánto se paga cada mes?")
        system = model.call_args.args[0]
        self.assertIn("[FEE.MX] México: Summit maximum MXN 6,000/year in monthly MXN 500", system)
        self.assertNotIn("MXN 150", system)
        self.assertNotIn("[BENEFIT.REWARDS]", system)

    def test_wrong_monthly_fee_amount_is_retried(self):
        chat = Conversation.start("es", "México", selected_card="Summit")
        with patch("advisor.service._generate", side_effect=[
            {"answer": "Summit ofrece millas y cuesta MXN 150 por mes.",
             "citations": ["BENEFIT.SUMMIT", "FEE.MX"]},
            {"answer": "Summit ofrece millas y su cuota mensual máxima es MXN 500.",
             "citations": ["BENEFIT.SUMMIT", "FEE.MX"]},
        ]) as model:
            result = respond(chat, "¿Qué ventajas tiene Summit y cuánto se paga cada mes?")
        self.assertEqual(model.call_count, 2)
        self.assertIn("amount that does not belong", model.call_args.args[0])
        self.assertIn("MXN 500", result["answer"])

    def test_customer_spend_amount_does_not_fail_fee_validation(self):
        chat = Conversation.start("pt", "México", selected_card="Summit")
        with patch("advisor.service._generate", return_value={
            "answer": "Com MXN 30.000 em compras elegíveis, a parcela de MXN 500 não seria isenta "
                      "se esse for o gasto líquido final do ciclo completo; a meta é MXN 50.000.",
            "citations": ["FEE.MX", "FEE.WAIVER"],
        }) as model:
            result = respond(chat, "Com MXN 30.000 em compras, qual a mensalidade do Summit?")
        self.assertEqual(model.call_count, 1)
        self.assertEqual(result["route"], "ANSWER_FACT")

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
        self.assertIn("[FEE.CO]", system)
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
