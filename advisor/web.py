"""Local, dependency-free browser shell for the demo advisor.

Only public conversation text is sent to Claude. Demo profiles and policy
decisions stay in the server process and are never included in model prompts.
"""

from __future__ import annotations

import argparse
import base64
import binascii
import hmac
import json
import os
import re
import secrets
import threading
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from http import HTTPStatus
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from .applications import ApplicationStorageError, ApplicationStore, utc_now
from .agents import EmptyAgentDirectory, LocalAgentDirectory, choose_agent
from .chat_flow import (application_choice, application_question, choice, expired,
                        named_card, pending, plain_text, precheck_question,
                        wants_information)
from .data_access import DemoDirectory
from .policy import CARDS, OFFER_VERSION
from .service import CAMPAIGNS, FACT_VERSION, PRIVATE_INPUT, Conversation, respond, wants_human
from .session import (grant_precheck_consent, grant_profile_permission,
                      profile_summary, recommendation_for_session, run_precheck,
                      select_demo_persona, sign_out)
from .synthetic_data import SyntheticDirectory

UI_DIR = Path(__file__).with_name("ui")
CAMPAIGN_CARDS = [
    {"id": cid, "card": card, "country_restriction": restriction}
    for cid, (card, restriction) in CAMPAIGNS.items()
]
STATIC = {"/": ("index.html", "text/html; charset=utf-8"),
          "/review": ("review.html", "text/html; charset=utf-8"),
          "/assets/app.css": ("app.css", "text/css; charset=utf-8"),
          "/assets/app.js": ("app.js", "text/javascript; charset=utf-8"),
          "/assets/review.js": ("review.js", "text/javascript; charset=utf-8")}
SESSION_SECONDS = 2 * 60 * 60
RATE_WINDOW_SECONDS = 10 * 60
MAX_REQUESTS_PER_WINDOW = 60
MAX_ANSWER_CALLS_PER_DAY = 200


class DemoLimitError(Exception):
    """A hosted-demo traffic or model-usage limit was reached."""


def load_local_key() -> None:
    """Read only the two supported Anthropic settings from an ignored .env."""
    path = Path(__file__).resolve().parents[1] / ".env"
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        key, sep, value = line.partition("=")
        key = key.strip()
        if sep and key in {"ANTHROPIC_API_KEY", "ANTHROPIC_WORKSPACE_ID"} and key not in os.environ:
            value = value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                value = value[1:-1]
            os.environ[key] = value


@dataclass
class BrowserSession:
    created_at: float = field(default_factory=time.time)
    last_active_at: float = field(default_factory=time.time)
    request_times: list[float] = field(default_factory=list)
    chat: Conversation | None = None
    events: list[dict[str, Any]] = field(default_factory=list)
    last_result: dict[str, Any] | None = None
    conversation_id: str | None = None
    prechecks: dict[str, dict[str, Any]] = field(default_factory=dict)
    precheck_consent_at: dict[str, str] = field(default_factory=dict)
    application_draft: dict[str, Any] | None = None
    application_record: dict[str, Any] | None = None
    handoff_record: dict[str, Any] | None = None
    topic_cards: list[str] = field(default_factory=list)
    application_submission_uncertain: bool = False
    pending_action: dict[str, Any] | None = None
    lock: Any = field(default_factory=threading.RLock)


class WebApp:
    def __init__(self, directory: DemoDirectory | None = None,
                 applications: ApplicationStore | None = None, *, hosted: bool = False,
                 answer_limit: int = MAX_ANSWER_CALLS_PER_DAY,
                 local_http_preview: bool = False, answer_counter: Any = None,
                 on_model_attempt: Any = None, agent_directory: Any = None):
        self.hosted = hosted
        self.local_http_preview = local_http_preview
        self.directory = directory if directory is not None else (SyntheticDirectory() if hosted else DemoDirectory())
        self.applications = applications or ApplicationStore()
        self.agent_directory = agent_directory if agent_directory is not None else (
            EmptyAgentDirectory() if hosted else LocalAgentDirectory())
        self.sessions: dict[str, BrowserSession] = {}
        self.lock = threading.Lock()
        self.answer_lock = threading.Lock()
        self.answer_slots = threading.BoundedSemaphore(3)
        self.answer_day = datetime.now(timezone.utc).date()
        self.answer_count = 0
        self.answer_limit = answer_limit
        self.answer_counter = answer_counter
        self.on_model_attempt = on_model_attempt

    def limited_respond(self, chat: Conversation, message: str) -> dict[str, Any]:
        if not self.hosted:
            return respond(chat, message, directory=self.directory)
        if not self.answer_slots.acquire(blocking=False):
            raise DemoLimitError("Advisor is busy; try again shortly")
        try:
            return respond(chat, message, directory=self.directory,
                           before_model_call=self._consume_model_attempt)
        finally:
            self.answer_slots.release()

    def _consume_model_attempt(self) -> None:
        day = datetime.now(timezone.utc).date()
        if self.answer_counter is not None:
            self.answer_counter.consume(day.isoformat(), self.answer_limit)
        else:
            with self.answer_lock:
                if day != self.answer_day:
                    self.answer_day, self.answer_count = day, 0
                if self.answer_count >= self.answer_limit:
                    raise DemoLimitError("Today's advisor answer limit has been reached")
                self.answer_count += 1
        if self.on_model_attempt is not None:
            self.on_model_attempt()

    def check_request_rate(self, state: BrowserSession) -> None:
        if not self.hosted:
            return
        now = time.time()
        state.request_times = [t for t in state.request_times if now - t < RATE_WINDOW_SECONDS]
        if len(state.request_times) >= MAX_REQUESTS_PER_WINDOW:
            raise DemoLimitError("Too many requests; try again later")
        state.request_times.append(now)

    def session(self, cookie_header: str | None, *, touch: bool = False) -> tuple[str, BrowserSession, bool]:
        cookie = SimpleCookie()
        try:
            cookie.load(cookie_header or "")
            sid = cookie["advisor_session"].value if "advisor_session" in cookie else None
        except Exception:
            sid = None
        with self.lock:
            if self.hosted:
                now = time.time()
                expired_ids = [key for key, state in self.sessions.items()
                               if now - state.last_active_at >= SESSION_SECONDS]
                for key in expired_ids:
                    old = self.sessions.pop(key)
                    if old.chat:
                        sign_out(old.chat, self.directory)
            if sid in self.sessions:
                state = self.sessions[sid]
                if touch:
                    state.last_active_at = time.time()
                return sid, state, False
            if self.hosted and len(self.sessions) >= 500:
                raise DemoLimitError("Demo is at capacity; try again shortly")
            sid = secrets.token_urlsafe(32)
            state = BrowserSession()
            self.sessions[sid] = state
            return sid, state, True

    def snapshot(self, state: BrowserSession) -> dict[str, Any]:
        chat = state.chat
        info: dict[str, Any] = {
            "chat_available": bool(os.environ.get("ANTHROPIC_API_KEY")),
            "review_available": not self.hosted,
            "campaigns": CAMPAIGN_CARDS,
            "personas": self.directory.public_list(),
            "cards": sorted(CARDS),
            "events": state.events[-50:],
            "last_result": state.last_result,
            "conversation": None,
            "profile": None,
            "application_draft": None,
            "application": None,
            "handoff": None,
            "pending_action": None,
            "prechecks": {card: check["status"] for card, check in state.prechecks.items()},
        }
        if chat:
            info["conversation"] = {
                "language": chat.language, "country": chat.country,
                "campaign_id": chat.campaign_id, "selected_card": chat.selected_card,
                "entry_kind": chat.entry_kind,
                "demo_alias": chat.demo_alias,
                "profile_permission": chat.profile_permission,
                "precheck_consent_card": chat.precheck_consent_card,
                "stopped": chat.stopped,
            }
            if chat.profile_permission and chat.demo_token and not chat.stopped:
                info["profile"] = profile_summary(chat, self.directory)
            if state.application_draft and not state.application_record:
                draft = state.application_draft
                info["application_draft"] = {k: draft[k] for k in (
                    "card", "country", "offer_version", "campaign_id", "precheck_status",
                    "confirmation_token")}
                info["application_draft"]["verification_pending"] = state.application_submission_uncertain
            if state.application_record:
                info["application"] = self._public_application(state.application_record)
            if state.handoff_record:
                info["handoff"] = self._public_handoff(state.handoff_record)
            if state.pending_action:
                info["pending_action"] = {k: state.pending_action[k] for k in ("kind", "card")}
        return info

    @staticmethod
    def _public_application(record: dict[str, Any]) -> dict[str, Any]:
        return {k: record[k] for k in ("application_id", "card", "country", "status",
                                      "offer_version", "campaign_id", "precheck_status", "confirmed_at")}

    @staticmethod
    def _public_handoff(record: dict[str, Any]) -> dict[str, Any]:
        result = {k: record[k] for k in ("handoff_id", "card", "country", "language",
                                         "reason", "status", "created_at")}
        packet = record.get("packet")
        if isinstance(packet, str):
            packet = json.loads(packet)
        result["assignment"] = packet.get("assignment") if packet else None
        return result

    def review_queue(self) -> dict[str, Any]:
        return self.applications.review_queue()

    def _prepare_application(self, state: BrowserSession, chat: Conversation,
                             card: str) -> dict[str, Any] | None:
        if card not in CARDS:
            raise ValueError("Choose a card before starting an application")
        if state.application_submission_uncertain and state.application_draft and state.application_draft["card"] != card:
            raise PermissionError("Verify the previous application before choosing another card")
        if state.application_record and state.application_record["card"] != card:
            raise ValueError("Finish this customer journey before choosing another application")
        profile = profile_summary(chat, self.directory)
        if state.conversation_id is None:
            raise PermissionError("Active customer session required")
        existing = self.applications.read(state.conversation_id, card)
        if existing:
            state.application_record = existing
            state.application_draft = None
            state.application_submission_uncertain = False
            return existing
        check = state.prechecks.get(card)
        if not state.application_draft or state.application_draft["card"] != card:
            state.application_draft = {
                "conversation_id": state.conversation_id,
                "confirmation_token": secrets.token_urlsafe(24),
                "customer_alias": chat.demo_alias,
                "country": profile["country"], "card": card,
                "offer_version": OFFER_VERSION, "campaign_id": chat.campaign_id,
                "precheck_status": check["status"] if check else None,
                "precheck_reasons": check["reasons"] if check else None,
                "precheck_policy_version": check["policy_version"] if check else None,
                "precheck_consent_at": check["consent_at"] if check else None,
            }
        chat.selected_card = card
        return None

    def _submit_application(self, state: BrowserSession, chat: Conversation,
                            token: str) -> dict[str, Any]:
        draft = state.application_draft
        if (draft is None or token != draft["confirmation_token"] or
            chat.demo_alias != draft["customer_alias"] or
            state.conversation_id != draft["conversation_id"]):
            raise PermissionError("Explicit confirmation for the active application required")
        try:
            record = self.applications.create_and_verify(draft, utc_now())
        except ApplicationStorageError:
            state.application_submission_uncertain = True
            raise
        state.application_record = record
        state.application_submission_uncertain = False
        state.pending_action = pending("post_application_followup", record["card"])
        return record

    def _ask_application(self, state: BrowserSession, chat: Conversation, card: str) -> dict[str, Any]:
        if state.application_record and state.application_record["card"] != card:
            recorded = state.application_record["card"]
            answer = (f"Você já tem uma solicitação de {recorded} registrada nesta conversa. "
                      f"Posso explicar ou avaliar o {card}, mas para solicitar outro cartão, inicie uma nova conversa."
                      if chat.language == "pt" else
                      f"Ya tienes una solicitud de {recorded} registrada en esta conversación. "
                      f"Puedo explicar o evaluar {card}, pero para solicitar otra tarjeta, inicia una conversación nueva.")
            return {"answer": answer, "citations": [], "route": "APPLICATION_EXISTS", "card": card}
        existing = self._prepare_application(state, chat, card)
        if existing:
            state.pending_action = pending("post_application_followup", card)
            return {"answer": self._application_message(existing, chat.language),
                    "citations": [], "route": "APPLICATION_RECORDED", "card": card}
        state.pending_action = pending("application_confirm", card)
        check = state.prechecks.get(card)
        return {"answer": application_question(card, chat.language, check["status"] if check else None),
                "citations": [], "route": "APPLICATION_CONFIRM", "card": card}

    def _ask_precheck(self, state: BrowserSession, chat: Conversation,
                      card: str, *, apply_after: bool) -> dict[str, Any]:
        state.pending_action = pending("precheck_choice", card, apply_after=apply_after)
        return {"answer": precheck_question(card, chat.language, apply_after=apply_after),
                "citations": [], "route": "ASK_PRECHECK_CONSENT", "card": card}

    def _record_handoff(self, state: BrowserSession, chat: Conversation,
                        question: str | None = None, customer_message: str | None = None) -> dict[str, Any]:
        if state.conversation_id is None or chat.demo_alias is None or chat.country is None:
            raise PermissionError("Active customer session required")
        if state.handoff_record:
            record = state.handoff_record
            return {"answer": (f"Seu pedido anterior de atendimento humano já está registrado. "
                               f"Protocolo {record['handoff_id']}; aguardando revisão."
                               if chat.language == "pt" else
                               f"Tu solicitud anterior de atención humana ya está registrada. "
                               f"Referencia {record['handoff_id']}; pendiente de revisión."),
                    "citations": [], "route": "HANDOFF_RECORDED", "card": record["card"]}
        try:
            existing = self.applications.read_handoff(state.conversation_id, "CUSTOMER_REQUEST")
        except ApplicationStorageError:
            existing = None
        if existing:
            if (existing.get("customer_alias") != chat.demo_alias or
                    existing.get("country") != chat.country or
                    existing.get("language") != chat.language or
                    existing.get("status") != "PENDING_REVIEW" or
                    existing.get("offer_version") != OFFER_VERSION):
                raise ApplicationStorageError("Existing handoff did not pass verification")
            state.handoff_record = existing
            return {"answer": (f"Sua conversa foi encaminhada para atendimento humano. "
                               f"Protocolo {existing['handoff_id']}; aguardando revisão."
                               if chat.language == "pt" else
                               f"Tu conversación quedó derivada a atención humana. "
                               f"Referencia {existing['handoff_id']}; pendiente de revisión."),
                    "citations": [], "route": "HANDOFF_RECORDED", "card": existing["card"]}
        profile = profile_summary(chat, self.directory)
        checks = [{"card": card, "status": check["status"],
                   "reasons": check["reasons"], "missing_data": check.get("missing_data", []),
                   "policy_version": check["policy_version"], "consent_at": check["consent_at"]}
                  for card, check in state.prechecks.items()]
        application = state.application_record
        try:
            assignment = choose_agent(self.agent_directory.candidates(), chat.language,
                                      chat.country, state.conversation_id)
        except Exception:
            assignment = None
        request = (f"Customer requested review of an unanswered question about {chat.selected_card}"
                   if question and chat.selected_card else
                   "Customer requested review of an unanswered card question" if question else
                   f"Customer requested a person to review {chat.selected_card}"
                   if chat.selected_card else "Customer requested a person to review card options")
        transcript = [{"role": event["role"],
                       "text": PRIVATE_INPUT.sub("[redacted]", event["text"]),
                       **({"route": event["route"]} if event.get("route") else {})}
                      for event in state.events if event.get("role") in {"user", "assistant"}
                      and isinstance(event.get("text"), str)]
        if customer_message:
            transcript.append({"role": "user", "text": PRIVATE_INPUT.sub("[redacted]", customer_message[:2000])})
        packet = {
            "request": request,
            "conversation_id": state.conversation_id,
            "transcript": transcript,
            "unresolved_question": PRIVATE_INPUT.sub("[redacted]", question[:500]) if question else None,
            "assignment": assignment,
            "verified_facts": {"fixture": chat.demo_alias, "source": profile["source"],
                               "country": profile["country"], "segment": profile["segment"],
                               "has_current_credit_card": profile["has_current_credit_card"]},
            "actions_taken": {"prechecks": checks,
                              "application": ({"reference": application["application_id"],
                                               "status": application["status"]} if application else None)},
            "evidence": {"offer_version": OFFER_VERSION, "fact_version": FACT_VERSION,
                         "campaign_id": chat.campaign_id, "entry_kind": chat.entry_kind},
            "open_questions": (["Verify missing profile fields before eligibility review"]
                               if any(check["missing_data"] for check in checks) else []) +
                              (["Verify current student enrollment"] if chat.selected_card == "Campus" else []) +
                              ["Answer the unresolved customer question" if question else
                               "Review the customer's request and decide the next step"],
        }
        draft = {"conversation_id": state.conversation_id, "customer_alias": chat.demo_alias,
                 "country": chat.country, "language": chat.language, "card": chat.selected_card,
                 "reason": "CUSTOMER_REQUEST", "offer_version": OFFER_VERSION,
                 "packet": packet}
        try:
            record = self.applications.create_handoff_and_verify(draft, utc_now())
        except ApplicationStorageError:
            return {"answer": ("Não consegui verificar o encaminhamento da conversa. Tente novamente."
                               if chat.language == "pt" else
                               "No pude verificar la derivación de la conversación. Inténtalo de nuevo."),
                    "citations": [], "route": "HANDOFF_UNVERIFIED", "card": chat.selected_card}
        state.handoff_record = record
        return {"answer": (f"Sua conversa foi encaminhada para atendimento humano. "
                           f"Protocolo {record['handoff_id']}; aguardando revisão."
                           if chat.language == "pt" else
                           f"Tu conversación quedó derivada a atención humana. "
                           f"Referencia {record['handoff_id']}; pendiente de revisión."),
                "citations": [], "route": "HANDOFF_RECORDED", "card": chat.selected_card}

    @staticmethod
    def _options_overview(language: str) -> dict[str, Any]:
        answer = ("Claro. Campus é voltado a estudantes; Horizon é uma opção para o dia a dia sem anuidade; "
                  "Rewards oferece milhas e benefícios de viagem; Summit reúne os benefícios premium. "
                  "Sobre qual cartão você quer saber mais?"
                  if language == "pt" else
                  "Claro. Campus está dirigido a estudiantes; Horizon es una opción para el día a día sin cuota anual; "
                  "Rewards ofrece millas y beneficios de viaje; Summit reúne los beneficios premium. "
                  "¿Sobre cuál tarjeta quieres saber más?")
        return {"answer": answer, "citations": ["CATALOG.IDENTITY"], "route": "ANSWER_FACT"}

    @staticmethod
    def _expanded_product_followup(state: BrowserSession, chat: Conversation,
                                   message: str) -> str | None:
        plain = plain_text(message)
        if plain not in {"quero", "quiero", "sim", "si", "ambas", "ambos",
                         "cuentame mas", "hablame mas", "me fale mais", "me fala mais"}:
            return None
        last = next((event for event in reversed(state.events) if event["role"] == "assistant"), None)
        if not last or last.get("route") != "ANSWER_FACT":
            return None
        if len(state.topic_cards) > 1:
            cards = " e ".join(state.topic_cards) if chat.language == "pt" else " y ".join(state.topic_cards)
            if plain in {"cuentame mas", "hablame mas", "me fale mais", "me fala mais"}:
                return (f"Compare os principais benefícios de {cards}." if chat.language == "pt" else
                        f"Compara los principales beneficios de {cards}.")
            if (last["text"].rstrip().endswith("?") and
                re.search(r"taxa|tarifa|anuidade|juros|condi[cç][aã]|cuota|inter[eé]s|costo|tasa|monto|umbral", last["text"].casefold())):
                return (f"Explique os valores exatos de anuidade, limites de isenção e juros de compras de {cards} no país atual."
                        if chat.language == "pt" else
                        f"Explica los importes exactos de cuota anual, umbrales de bonificación y tasa de compras de {cards} en el país actual.")
            return None
        if (plain not in {"quero", "quiero", "sim", "si"} or
            not last["text"].rstrip().endswith("?") or
            not re.search(r"taxa|tarifa|anuidade|juros|condi[cç][aã]|cuota|inter[eé]s", last["text"].casefold())):
            return None
        benefit_cards = {fid.split(".", 1)[1].title() for fid in last.get("citations", [])
                         if fid.startswith("BENEFIT.")}
        card = next(iter(benefit_cards)) if len(benefit_cards) == 1 else chat.selected_card
        if card is None:
            return None
        return (f"Explique a anuidade, os juros de compras e as condições do {card}, em resposta ao meu 'quero'."
                if chat.language == "pt" else
                f"Explica la cuota anual, los intereses de compras y las condiciones de {card}, en respuesta a mi 'quiero'.")

    def _handle_pending_chat(self, state: BrowserSession, chat: Conversation,
                             message: str) -> dict[str, Any] | None:
        action = state.pending_action
        if not action:
            return None
        if action["kind"] == "post_application_followup":
            decision = choice(message)
            if decision is False:
                state.pending_action = None
                return respond(chat, "encerrar" if chat.language == "pt" else "terminar",
                               directory=self.directory)
            if decision is True:
                return {"answer": ("Claro. Qual é a sua pergunta?" if chat.language == "pt" else
                                   "Claro. ¿Cuál es tu pregunta?"),
                        "citations": [], "route": "ASK_FOLLOWUP_QUESTION"}
            state.pending_action = None
            return None
        if expired(action) and not state.application_submission_uncertain:
            state.pending_action = None
            state.application_draft = None
            if choice(message) is not None:
                return {"answer": ("Essa confirmação expirou. Diga qual cartão deseja avaliar para começarmos de novo."
                                   if chat.language == "pt" else
                                   "Esa confirmación venció. Dime qué tarjeta deseas evaluar para empezar de nuevo."),
                        "citations": [], "route": "ACTION_EXPIRED"}
            return None
        if wants_information(message) and not state.application_submission_uncertain:
            state.pending_action = None
            state.application_draft = None
            return self._options_overview(chat.language)
        if action["kind"] == "choose_card":
            card = named_card(message)
            if card:
                chat.selected_card = card
                state.pending_action = None
                if action.get("skip_precheck") and action["apply_after"]:
                    return self._ask_application(state, chat, card)
                if action["apply_after"] and card in state.prechecks:
                    return self._ask_application(state, chat, card)
                return self._ask_precheck(state, chat, card, apply_after=action["apply_after"])
            if len(message.split()) <= 5:
                return {"answer": ("Qual cartão você quer solicitar: Campus, Horizon, Rewards ou Summit?"
                                   if chat.language == "pt" else
                                   "¿Qué tarjeta quieres solicitar: Campus, Horizon, Rewards o Summit?"),
                        "citations": [], "route": "ASK_CARD"}
            state.pending_action = None
            return None
        decision = application_choice(message) if action["kind"] == "application_confirm" else choice(message)
        if decision is None:
            if state.application_submission_uncertain:
                return {"answer": ("Responda sim ou não à pergunta anterior, por favor."
                                   if chat.language == "pt" else
                                   "Responde sí o no a la pregunta anterior, por favor."),
                        "citations": [], "route": "CLARIFY_CONFIRMATION", "card": action["card"]}
            # A fresh question or card choice withdraws the outstanding confirmation.
            # Keep ambiguous short replies pending, but never trap an explicit topic switch.
            topic_switch = ("?" in message or named_card(message) is not None or
                            any(term in plain_text(message) for term in (
                                "outro cartao", "outros cartoes", "outra tarjeta",
                                "otras tarjetas", "opcoes", "opciones", "beneficios",
                                "benefits", "recomenda", "recomiend", "solicitar")))
            if not topic_switch and len(message.split()) <= 5:
                return {"answer": ("Responda sim ou não à pergunta anterior, por favor."
                                   if chat.language == "pt" else
                                   "Responde sí o no a la pregunta anterior, por favor."),
                        "citations": [], "route": "CLARIFY_CONFIRMATION", "card": action["card"]}
            state.pending_action = None
            if action["kind"] == "application_confirm":
                state.application_draft = None
            return None
        card = action["card"]
        if action["kind"] == "handoff_offer":
            state.pending_action = None
            if decision:
                return self._record_handoff(state, chat, action.get("question"), message)
            return {"answer": ("Tudo bem. Não registrei pedido de atendimento humano."
                               if chat.language == "pt" else
                               "De acuerdo. No registré una solicitud de atención humana."),
                    "citations": [], "route": "HANDOFF_DECLINED", "card": card}
        if action["kind"] == "application_intent_clarify":
            state.pending_action = None
            if decision:
                if card is None:
                    state.pending_action = pending("choose_card", None, apply_after=True)
                    return {"answer": ("Qual cartão você quer solicitar: Campus, Horizon, Rewards ou Summit?"
                                       if chat.language == "pt" else
                                       "¿Qué tarjeta quieres solicitar: Campus, Horizon, Rewards o Summit?"),
                            "citations": [], "route": "ASK_CARD"}
                if card in state.prechecks:
                    return self._ask_application(state, chat, card)
                return self._ask_precheck(state, chat, card, apply_after=True)
            subject = f"o {card}" if card else "os cartões"
            subject_es = card or "las tarjetas"
            return {"answer": (f"Claro. O que você gostaria de saber sobre {subject}?"
                               if chat.language == "pt" else
                               f"Claro. ¿Qué te gustaría saber sobre {subject_es}?"),
                    "citations": [], "route": "APPLICATION_INTENT_DECLINED", "card": card}
        if action["kind"] == "precheck_choice":
            state.pending_action = None
            if not decision:
                if action["apply_after"]:
                    return self._ask_application(state, chat, card)
                return {"answer": ("Tudo bem. Não fiz nenhuma avaliação inicial."
                                   if chat.language == "pt" else
                                   "De acuerdo. No hice ninguna evaluación inicial."),
                        "citations": [], "route": "PRECHECK_DECLINED", "card": card}
            grant_precheck_consent(chat, self.directory, card)
            state.precheck_consent_at[card] = utc_now()
            result = run_precheck(chat, self.directory, card)
            policy = result["policy"]
            state.prechecks[card] = {"status": policy.status, "reasons": list(policy.reasons),
                                     "missing_data": list(policy.missing_data),
                                     "policy_version": policy.policy_version,
                                     "consent_at": state.precheck_consent_at[card]}
            state.application_draft = None
            if action["apply_after"]:
                followup = self._ask_application(state, chat, card)
                followup["answer"] = result["answer"] + " " + followup["answer"]
                return followup
            return result
        if action["kind"] == "application_confirm":
            if not decision:
                if state.application_submission_uncertain:
                    return {"answer": ("Ainda não consegui verificar se a solicitação foi registrada. Responda sim para tentar confirmar o mesmo pedido; não criarei outro."
                                       if chat.language == "pt" else
                                       "Aún no pude verificar si se registró la solicitud. Responde sí para comprobar el mismo pedido; no crearé otro."),
                            "citations": [], "route": "APPLICATION_UNVERIFIED", "card": card}
                state.pending_action = None
                state.application_draft = None
                return {"answer": ("Entendido. Nenhuma solicitação foi enviada."
                                   if chat.language == "pt" else
                                   "Entendido. No se envió ninguna solicitud."),
                        "citations": [], "route": "APPLICATION_CANCELLED", "card": card}
            try:
                record = self._submit_application(state, chat, state.application_draft["confirmation_token"])
            except ApplicationStorageError:
                return {"answer": ("Não consegui verificar o registro da solicitação. Responda sim novamente para conferir o mesmo pedido; não criarei outro."
                                   if chat.language == "pt" else
                                   "No pude verificar el registro de la solicitud. Responde sí de nuevo para comprobar el mismo pedido; no crearé otro."),
                        "citations": [], "route": "APPLICATION_UNVERIFIED", "card": card}
            return {"answer": self._application_message(record, chat.language),
                    "citations": [], "route": "APPLICATION_RECORDED", "card": card}
        state.pending_action = None
        return None

    def action(self, state: BrowserSession, path: str, body: dict[str, Any]) -> dict[str, Any]:
        chat = state.chat
        if path in {"/api/home", "/api/signout"}:
            if chat:
                sign_out(chat, self.directory)
            state.chat = None
            state.events = []
            state.last_result = None
            state.conversation_id = None
            state.prechecks = {}
            state.precheck_consent_at = {}
            state.application_draft = None
            state.application_record = None
            state.handoff_record = None
            state.topic_cards = []
            state.application_submission_uncertain = False
            state.pending_action = None
            return self.snapshot(state)
        if path == "/api/start":
            if self.hosted and chat is not None:
                raise PermissionError("End the current test session before choosing another fixture")
            entry = body.get("entry")
            if entry not in {"direct", "campaign", "offer"}:
                raise ValueError("Choose direct, offer, or campaign entry")
            cid = body.get("campaign_id") if entry == "campaign" else None
            if entry == "campaign" and cid is None:
                raise ValueError("Choose a campaign")
            card = body.get("selected_card") if entry == "offer" else None
            if entry == "offer" and card is None:
                raise ValueError("Choose an offer")
            if entry != "campaign" and body.get("campaign_id") is not None:
                raise ValueError("Campaign ID requires campaign entry")
            if entry != "offer" and body.get("selected_card") is not None:
                raise ValueError("Selected card requires offer entry")
            new_chat = Conversation.start(body.get("language"), body.get("country"), cid, card)
            alias = body.get("alias")
            if not isinstance(alias, str):
                raise ValueError("Choose a demo customer")
            select_demo_persona(new_chat, self.directory, alias)
            grant_profile_permission(new_chat)
            if chat:
                sign_out(chat, self.directory)
            state.chat = new_chat
            state.conversation_id = secrets.token_urlsafe(24)
            state.events = [{"role": "assistant", "text": new_chat.opening(), "route": "OPENING"}]
            state.last_result = None
            state.prechecks = {}
            state.precheck_consent_at = {}
            state.application_draft = None
            state.application_record = None
            state.handoff_record = None
            state.topic_cards = []
            state.application_submission_uncertain = False
            state.pending_action = None
            return self.snapshot(state)
        if state.handoff_record:
            raise PermissionError("This conversation is waiting for human review")
        if path == "/api/persona-preview":
            return {"persona": self.directory.persona_preview(body.get("alias"))}
        if chat is None:
            raise ValueError("Start a conversation first")
        if chat.stopped:
            raise ValueError("Conversation ended; start a new one")
        if state.application_submission_uncertain and path not in {"/api/application-submit", "/api/application-prepare", "/api/chat"}:
            raise PermissionError("Application outcome is unverified; retry or check the same application first")
        if path == "/api/recommend":
            result = recommendation_for_session(chat, self.directory)
            self._record_result(state, result)
        elif path == "/api/precheck-consent":
            if body.get("agree") is not True:
                raise ValueError("Explicit card-specific consent required")
            card = body.get("card")
            grant_precheck_consent(chat, self.directory, card)
            state.precheck_consent_at[card] = utc_now()
            state.events.append({"role": "assistant", "text":
                                 (f"Autorização registrada para avaliar {card}. Posso fazer a verificação inicial agora."
                                  if chat.language == "pt" else
                                  f"Autorización registrada para evaluar {card}. Puedo hacer la verificación inicial ahora."),
                                 "route": "PRECHECK_CONSENT", "card": card})
        elif path == "/api/precheck":
            result = run_precheck(chat, self.directory, body.get("card"))
            policy = result["policy"]
            state.prechecks[policy.card] = {"status": policy.status,
                                            "reasons": list(policy.reasons),
                                            "missing_data": list(policy.missing_data),
                                            "policy_version": policy.policy_version,
                                            "consent_at": state.precheck_consent_at.get(policy.card)}
            state.application_draft = None
            state.application_submission_uncertain = False
            state.pending_action = None
            self._record_result(state, result)
        elif path == "/api/application-prepare":
            card = body.get("card") or chat.selected_card
            existing = self._prepare_application(state, chat, card)
            if existing:
                state.events.append({"role": "assistant", "text": self._application_message(existing, chat.language),
                                     "route": "APPLICATION_RECORDED", "card": card})
            else:
                state.pending_action = pending("application_confirm", card)
                answer = (f"Posso registrar sua solicitação do {card} para análise humana. "
                          "Confirme se deseja enviá-la; isso não é uma aprovação de crédito."
                          if chat.language == "pt" else
                          f"Puedo registrar tu solicitud de {card} para revisión humana. "
                          "Confirma si deseas enviarla; esto no es una aprobación de crédito.")
                state.events.append({"role": "assistant", "text": answer,
                                     "route": "APPLICATION_CONFIRM", "card": card})
        elif path == "/api/application-cancel":
            if not state.application_draft or state.application_record:
                raise ValueError("No pending application confirmation")
            if state.application_submission_uncertain:
                raise PermissionError("Submission outcome is unverified; retry the same confirmation before cancelling")
            state.application_draft = None
            state.pending_action = None
            state.events.append({"role": "assistant", "text":
                                 ("Entendido. Nenhuma solicitação foi enviada." if chat.language == "pt" else
                                  "Entendido. No se envió ninguna solicitud."),
                                 "route": "APPLICATION_CANCELLED"})
        elif path == "/api/application-submit":
            if body.get("confirm") is not True:
                raise PermissionError("Explicit confirmation for the active application required")
            record = self._submit_application(state, chat, body.get("confirmation_token"))
            state.last_result = {"route": "APPLICATION_RECORDED", "application": self._public_application(record)}
            if not state.events or state.events[-1].get("route") != "APPLICATION_RECORDED":
                state.events.append({"role": "assistant", "text": self._application_message(record, chat.language),
                                     "route": "APPLICATION_RECORDED", "card": record["card"]})
        elif path == "/api/chat":
            message = body.get("message")
            if not isinstance(message, str):
                raise ValueError("Message must be text")
            if not 1 <= len(message.strip()) <= 2000:
                raise ValueError("message must contain 1-2000 characters")
            mentioned = [card for card in CARDS if re.search(rf"\b{card.casefold()}\b", message.casefold())]
            if mentioned:
                state.topic_cards = mentioned
            closing = message.strip().casefold() in {"salir", "terminar", "sair", "encerrar"}
            if wants_human(message) and not state.application_submission_uncertain:
                state.pending_action = None
                state.application_draft = None
                result = self._record_handoff(state, chat, customer_message=message.strip())
            else:
                result = self.limited_respond(chat, message) if closing else self._handle_pending_chat(state, chat, message.strip())
            if result is None:
                if state.application_submission_uncertain:
                    raise PermissionError("Application outcome is unverified; confirm the same request first")
                expanded = self._expanded_product_followup(state, chat, message)
                last_assistant = next((event for event in reversed(state.events)
                                       if event["role"] == "assistant"), None)
                if expanded:
                    result = self.limited_respond(chat, expanded)
                elif (plain_text(message) in {"quero", "quiero", "sim", "si"} and
                      last_assistant and last_assistant.get("route") == "ANSWER_FACT"):
                    result = {"answer": ("Claro. Sobre qual cartão ou condição você gostaria de saber mais?"
                                         if chat.language == "pt" else
                                         "Claro. ¿Sobre qué tarjeta o condición quieres saber más?"),
                              "citations": [], "route": "CLARIFY_PRODUCT_INTENT"}
                elif choice(message) is True or message.strip().casefold() in {
                        "pode prosseguir", "pode seguir", "vamos em frente", "puede continuar",
                        "adelante", "go ahead"}:
                    card = chat.selected_card
                    result = {"answer": ((f"Você quer solicitar o {card} ou prefere saber mais sobre ele?"
                                          if card else "Você quer solicitar um cartão ou prefere conhecer as opções?")
                                         if chat.language == "pt" else
                                         (f"¿Quieres solicitar {card} o prefieres saber más sobre la tarjeta?"
                                          if card else "¿Quieres solicitar una tarjeta o prefieres conocer las opciones?")),
                              "citations": [], "route": "ASK_APPLICATION_INTENT", "card": card}
                else:
                    result = self.limited_respond(chat, message)
                if self._needs_handoff_offer(result):
                    state.pending_action = pending("handoff_offer", result.get("card") or chat.selected_card)
                    state.pending_action["question"] = message.strip()[:500]
                    result = {**result, "answer": result["answer"] + (
                        " Quer que eu registre um pedido para um especialista em crédito revisar sua pergunta? Responda sim ou não."
                        if chat.language == "pt" else
                        " ¿Quieres que registre una solicitud para que un especialista en crédito revise tu pregunta? Responde sí o no."),
                        "route": "OFFER_HANDOFF"}
                if result["route"] == "ASK_CARD":
                    state.pending_action = pending("choose_card", None,
                                                   apply_after=result.get("wants_application", False))
                    state.pending_action["skip_precheck"] = result.get("skip_precheck", False)
                elif result["route"] == "ASK_APPLICATION_INTENT":
                    state.pending_action = pending("application_intent_clarify", result["card"])
                elif result["route"] == "ASK_PRECHECK_CONSENT":
                    card = result.get("card")
                    if result.get("wants_application") and card in state.prechecks:
                        result = self._ask_application(state, chat, card)
                    else:
                        result = self._ask_precheck(state, chat, card,
                                                    apply_after=result.get("wants_application", False))
                elif result["route"] == "SKIP_PRECHECK":
                    result = self._ask_application(state, chat, result["card"])
            if state.application_draft and chat.selected_card != state.application_draft["card"]:
                state.application_draft = None
            if result["route"] == "ANSWER_FACT":
                benefit_cards = [fid.split(".", 1)[1].title() for fid in result.get("citations", [])
                                 if fid.startswith("BENEFIT.")]
                if len(benefit_cards) > 1:
                    state.topic_cards = [card for card in CARDS if card in benefit_cards]
            state.events.extend([{"role": "user", "text": message.strip()},
                                 {"role": "assistant", "text": result["answer"],
                                  "route": result["route"], "citations": result["citations"],
                                  "card": result.get("card") or (result["policy"].card if "policy" in result else None),
                                  "wants_application": result.get("wants_application", False)}])
            self._set_last_result(state, result)
            if result["route"] == "STOP":
                state.application_draft = None
                state.pending_action = None
        else:
            raise ValueError("Unknown action")
        state.events = state.events[-50:]
        return self.snapshot(state)

    @staticmethod
    def _needs_handoff_offer(result: dict[str, Any]) -> bool:
        if result.get("route") not in {"ANSWER_FACT", "SERVICE_BOUNDARY"}:
            return False
        citations = result.get("citations") or []
        return bool(result.get("unresolved")) or any(fid.startswith("UNKNOWN.") for fid in citations) or (
            result.get("route") == "ANSWER_FACT" and not citations)

    @staticmethod
    def _application_message(record: dict[str, Any], language: str) -> str:
        if language == "pt":
            return (f"Sua solicitação do {record['card']} foi registrada para análise humana. "
                    f"Protocolo {record['application_id']}; status PENDING_REVIEW. Ainda não há decisão de crédito. "
                    "Você tem outra pergunta? Escreva sua pergunta ou responda não para encerrar a conversa.")
        return (f"Tu solicitud de {record['card']} quedó registrada para revisión humana. "
                f"Referencia {record['application_id']}; estado PENDING_REVIEW. Aún no hay decisión de crédito. "
                "¿Tienes otra pregunta? Escríbela o responde no para terminar la conversación.")

    @staticmethod
    def _set_last_result(state: BrowserSession, result: dict[str, Any]) -> None:
        state.last_result = {k: asdict(v) if k == "policy" else v
                             for k, v in result.items() if k != "error"}

    def _record_result(self, state: BrowserSession, result: dict[str, Any]) -> None:
        self._set_last_result(state, result)
        state.events.append({"role": "assistant", "text": result["answer"],
                             "route": result["route"], "citations": result["citations"],
                             "card": result["policy"].card if "policy" in result else result.get("card")})


class Handler(BaseHTTPRequestHandler):
    server: "AdvisorServer"

    def log_message(self, format: str, *args: Any) -> None:
        # Avoid writing customer questions or tokens to process logs.
        pass

    def _review_authorized(self) -> bool:
        if not self.server.app.hosted:
            return True
        raw = self.headers.get("Authorization", "")
        try:
            kind, encoded = raw.split(" ", 1)
            user, password = base64.b64decode(encoded, validate=True).decode().split(":", 1)
        except (ValueError, UnicodeError, binascii.Error):
            user, password, kind = "", "", ""
        expected_code = os.environ["ADVISOR_REVIEW_CODE"]
        if kind.casefold() == "basic" and user == "reviewer" and hmac.compare_digest(password, expected_code):
            return True
        self.send_response(HTTPStatus.UNAUTHORIZED)
        # The static review page handles sign-in; do not trigger a browser
        # Basic-auth modal, which Lambda Function URLs also remap away.
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", "0")
        self.end_headers()
        return False

    def _headers(self, content_type: str, length: int, sid: str, fresh: bool, status: int = 200) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(length))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", "default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self' data:; base-uri 'none'; form-action 'none'")
        if fresh or (self.server.app.hosted and self.command == "POST"):
            flags = f"; Max-Age={SESSION_SECONDS}" if self.server.app.hosted else ""
            if self.server.app.hosted and not self.server.app.local_http_preview:
                flags += "; Secure"
            self.send_header("Set-Cookie", f"advisor_session={sid}; HttpOnly; SameSite=Strict; Path=/{flags}")
        self.end_headers()

    def _json(self, payload: dict[str, Any], sid: str, fresh: bool, status: int = 200) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self._headers("application/json; charset=utf-8", len(data), sid, fresh, status)
        self.wfile.write(data)

    def do_GET(self) -> None:
        path = urlsplit(self.path).path
        if path == "/healthz":
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", "2")
            self.end_headers()
            self.wfile.write(b"ok")
            return
        # Lambda Function URLs remap WWW-Authenticate, so browsers do not show
        # the Basic-auth prompt. Serve only the static sign-in shell publicly;
        # the queue data still requires the reviewer credential.
        if path == "/api/review" and not self._review_authorized():
            return
        try:
            sid, state, fresh = self.server.app.session(self.headers.get("Cookie"))
        except DemoLimitError:
            self.send_error(HTTPStatus.SERVICE_UNAVAILABLE)
            return
        if path == "/api/state":
            with state.lock:
                self._json(self.server.app.snapshot(state), sid, fresh)
            return
        if path == "/api/review":
            try:
                self._json(self.server.app.review_queue(), sid, fresh)
            except ApplicationStorageError:
                self._json({"error": "Local review queue unavailable"}, sid, fresh,
                           HTTPStatus.SERVICE_UNAVAILABLE)
            return
        if path not in STATIC:
            self._json({"error": "Not found"}, sid, fresh, HTTPStatus.NOT_FOUND)
            return
        filename, content_type = STATIC[path]
        data = (UI_DIR / filename).read_bytes()
        self._headers(content_type, len(data), sid, fresh)
        self.wfile.write(data)

    def do_POST(self) -> None:
        path = urlsplit(self.path).path
        try:
            sid, state, fresh = self.server.app.session(self.headers.get("Cookie"), touch=True)
        except DemoLimitError:
            self.send_error(HTTPStatus.SERVICE_UNAVAILABLE)
            return
        if not path.startswith("/api/"):
            self._json({"error": "Not found"}, sid, fresh, HTTPStatus.NOT_FOUND)
            return
        origin = self.headers.get("Origin")
        if self.server.app.hosted and origin and urlsplit(origin).netloc != self.headers.get("Host"):
            self._json({"error": "Origin not allowed"}, sid, fresh, HTTPStatus.FORBIDDEN)
            return
        if self.headers.get("Content-Type", "").split(";", 1)[0].strip() != "application/json":
            self._json({"error": "JSON required"}, sid, fresh, HTTPStatus.UNSUPPORTED_MEDIA_TYPE)
            return
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if not 0 < size <= 8192:
                raise ValueError("Request size must be 1-8192 bytes")
            body = json.loads(self.rfile.read(size))
            if not isinstance(body, dict):
                raise ValueError("JSON object required")
            with state.lock:
                self.server.app.check_request_rate(state)
                payload = self.server.app.action(state, path, body)
        except (ValueError, PermissionError, TypeError) as exc:
            self._json({"error": str(exc)}, sid, fresh, HTTPStatus.BAD_REQUEST)
            return
        except ApplicationStorageError:
            self._json({"error": "Application storage unavailable; submission was not verified. Retry with the same confirmation."},
                       sid, fresh, HTTPStatus.SERVICE_UNAVAILABLE)
            return
        except DemoLimitError as exc:
            self._json({"error": str(exc)}, sid, fresh, HTTPStatus.TOO_MANY_REQUESTS)
            return
        self._json(payload, sid, fresh)


class AdvisorServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address: tuple[str, int], app: WebApp):
        super().__init__(address, Handler)
        self.app = app


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the local credit advisor UI")
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8765")))
    parser.add_argument("--host", help="Bind address; hosted default is 0.0.0.0, local default is 127.0.0.1")
    parser.add_argument("--local-http-preview", action="store_true",
                        help="Allow non-Secure cookies only for a hosted preview bound to 127.0.0.1")
    args = parser.parse_args()
    mode = os.environ.get("ADVISOR_HOSTED", "0")
    if mode not in {"0", "1"}:
        parser.error("ADVISOR_HOSTED must be 0 or 1")
    hosted = mode == "1"
    host = args.host or ("0.0.0.0" if hosted else "127.0.0.1")
    if args.local_http_preview and (not hosted or host != "127.0.0.1"):
        parser.error("--local-http-preview requires hosted mode bound to 127.0.0.1")
    if hosted:
        review = os.environ.get("ADVISOR_REVIEW_CODE", "")
        db_path = os.environ.get("ADVISOR_DB_PATH", "")
        if len(review) < 20:
            parser.error("hosted mode requires a reviewer code of at least 20 characters")
        if not os.environ.get("ANTHROPIC_API_KEY"):
            parser.error("hosted mode requires ANTHROPIC_API_KEY in the process environment")
        if not db_path or not Path(db_path).is_absolute():
            parser.error("hosted mode requires an absolute ADVISOR_DB_PATH on persistent storage")
        try:
            answer_limit = int(os.environ.get("ADVISOR_MAX_ANSWERS_PER_DAY", str(MAX_ANSWER_CALLS_PER_DAY)))
        except ValueError:
            parser.error("ADVISOR_MAX_ANSWERS_PER_DAY must be an integer")
        if not 1 <= answer_limit <= 200:
            parser.error("ADVISOR_MAX_ANSWERS_PER_DAY must be between 1 and 200")
        store = ApplicationStore(Path(db_path))
        app = WebApp(applications=store, hosted=True, answer_limit=answer_limit,
                     local_http_preview=args.local_http_preview)
    else:
        load_local_key()
        app = WebApp()
    server = AdvisorServer((host, args.port), app)
    print(f"Advisor UI listening on {host}:{server.server_port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
