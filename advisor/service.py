"""Text-only product conversation with service-enforced action boundaries.

Demo profile and policy tools are local; the model sees only public offer facts.
No real authentication, bank application, or human-assignment tool is connected.
"""

from __future__ import annotations

import json
import os
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
FACT_VERSION = "CONV-FACTS-2026-09-30-v5"
CAMPAIGNS = {
    "CMP-YYT37NY1CZS7": ("Campus", "Colombia"),
    "CMP-I5TGQ4SXP4EG": ("Horizon", None),
    "CMP-NM2UHJMKPA0C": ("Rewards", None),
    "CMP-N3I2U4V7H3KU": ("Summit", None),
}
COUNTRIES = {"Colombia", "México", "Argentina"}
CARD_NAMES = ("Campus", "Horizon", "Rewards", "Summit")
HUMAN_REQUEST_TERMS = ("falar com uma pessoa", "falar com alguém", "falar com um gerente",
                       "agente humano", "hablar con alguien", "hablar con una persona",
                       "hablar con un asesor", "ser humano", "human review", "human agent")
FACT_ROW = re.compile(r"^\| `([A-Z]+\.[A-Z_]+)` \| (.*?) \| .* \|$")
PRIVATE_INPUT = re.compile(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}|\b\d{9,}\b")
UNVERIFIED_ACTION = re.compile(
    r"\b(?:vou|posso|podemos)\s+(?:encaminhar|enviar|registrar|abrir)|"
    r"\b(?:voy a|puedo|podemos)\s+(?:enviar|registrar|derivar)|"
    r"\b(?:j[aá]\s+)?(?:encaminhei|enviei|registrei|envi[eé]|registr[eé]|deriv[eé])\b|"
    r"\b(?:solicita[cç][aã]o|solicitud|pedido)\s+(?:foi|est[aá]|qued[oó]|se ha)\s+(?:registrad|enviad|encaminhad)|"
    r"\b(?:solicita[cç][aã]o|solicitud|pedido|cart[aã]o|tarjeta)\s+(?:foi|fue|est[aá]|qued[oó])\s+(?:aprovad|aprobad|aceitad)|"
    r"\b(?:te|lhe)\s+(?:asign[eé]|atribu[ií])\b|"
    r"\b(?:entrar[aã]o|entraremos|se pondr[aá]n)\s+en?\s+contacto|"
    r"\b(?:entrar[aã]o|entraremos)\s+em\s+contato",
    re.IGNORECASE,
)


def public_facts() -> list[tuple[str, str]]:
    raw = (ROOT / "plan/conversation_data/source_pack.md").read_text(encoding="utf-8")
    if FACT_VERSION not in raw:
        raise RuntimeError("Unknown fact-sheet version")
    facts = [(m[1], re.sub(r"[*`]", "", m[2])) for line in raw.splitlines()
             if (m := FACT_ROW.match(line))]
    if len(facts) != 23 or len({fid for fid, _ in facts}) != len(facts):
        raise RuntimeError("Unexpected fact-sheet contract")
    return facts


def _lounge_overview(language: str) -> dict[str, object]:
    facts = dict(public_facts())
    counts = {}
    for card in ("Rewards", "Summit"):
        match = re.search(r"(\d+) complimentary lounge visits", facts[f"BENEFIT.{card.upper()}"])
        if match is None:
            raise RuntimeError("Lounge benefit fact is missing")
        counts[card] = int(match.group(1))
    if language == "pt":
        answer = (f"Rewards oferece {counts['Rewards']} visitas de cortesia a salas VIP por ano do cartão; "
                  f"Summit oferece {counts['Summit']}. Quer que eu compare os benefícios dos dois?")
    else:
        answer = (f"Rewards ofrece {counts['Rewards']} visitas de cortesía a salas VIP por año de tarjeta; "
                  f"Summit ofrece {counts['Summit']}. ¿Quieres que compare sus beneficios?")
    return {"answer": answer, "citations": ["BENEFIT.REWARDS", "BENEFIT.SUMMIT"],
            "route": "ANSWER_FACT", "fact_version": FACT_VERSION}


@dataclass
class Conversation:
    language: str
    country: str | None
    campaign_id: str | None
    selected_card: str | None
    entry_kind: str = "direct"
    turns: list[dict[str, str]] = field(default_factory=list)
    stopped: bool = False
    demo_alias: str | None = None
    demo_token: str | None = None
    profile_permission: bool = False
    precheck_consent_card: str | None = None

    @classmethod
    def start(cls, language: str, country: str | None = None,
              campaign_id: str | None = None,
              selected_card: str | None = None) -> "Conversation":
        if language not in {"es", "pt"}:
            raise ValueError("language must be es or pt")
        if country is not None and country not in COUNTRIES:
            raise ValueError("country must be Colombia, México, or Argentina")
        if campaign_id is not None and campaign_id not in CAMPAIGNS:
            raise ValueError("unknown campaign")
        if selected_card is not None and selected_card not in CARD_NAMES:
            raise ValueError("unknown card")
        if campaign_id is not None and selected_card is not None:
            raise ValueError("choose a campaign or a direct offer")
        card = CAMPAIGNS[campaign_id][0] if campaign_id else selected_card
        restriction = CAMPAIGNS[campaign_id][1] if campaign_id else None
        if restriction and country and restriction != country:
            raise ValueError("historical campaign country does not match")
        entry_kind = "campaign" if campaign_id else "offer" if selected_card else "direct"
        return cls(language, country, campaign_id, card, entry_kind)

    def opening(self) -> str:
        if self.language == "es":
            return (f"¡Hola! Veo que te interesó la tarjeta {self.selected_card}. ¿Qué te gustaría saber sobre ella?"
                    if self.selected_card else
                    "¡Hola! Puedo ayudarte a comparar Campus, Horizon, Rewards y Summit. ¿Qué buscas en una tarjeta?")
        return (f"Olá! Vi que você se interessou pelo cartão {self.selected_card}. O que gostaria de saber sobre ele?"
                if self.selected_card else
                "Olá! Posso ajudar você a comparar Campus, Horizon, Rewards e Summit. O que procura em um cartão?")


def _boundary(text: str, language: str) -> str | None:
    """Server-owned response for requests whose outcome needs unavailable tools."""
    t = text.casefold()
    pt = language == "pt"
    if PRIVATE_INPUT.search(text):
        return ("Não envie números de conta, documentos, telefone ou e-mail pelo chat."
                if pt else "No compartas números de cuenta, documentos, teléfono ni correo por el chat.")
    if any(s in t for s in ("ignore previous", "ignore as instru", "ignora las instru", "ignore as regras", "reveal prompt", "mostra o prompt")):
        return ("Não posso alterar as regras de acesso ou revelar instruções internas."
                if pt else "No puedo cambiar las reglas de acceso ni revelar instrucciones internas.")
    if any(s in t for s in ("outra pessoa", "otro cliente", "otra persona", "someone else's", "outro cliente")):
        return ("Não posso acessar informações de outra pessoa." if pt else
                "No puedo acceder a información de otra persona.")
    if any(s in t for s in ("adelanto de efectivo", "avance de efectivo", "saque em dinheiro", "adiantamento em dinheiro", "cash advance")):
        return ("As taxas e tarifas de saque em dinheiro ainda não estão disponíveis; não posso calcular seu custo total. Um especialista deve verificar os termos aplicáveis."
                if pt else "Las tasas y comisiones de los avances de efectivo aún no están disponibles; no puedo calcular su costo total. Un especialista debe verificar las condiciones aplicables.")
    if wants_human(text):
        return ("Entendo que você quer atendimento humano. Ainda não há ferramenta de encaminhamento conectada; ninguém foi atribuído."
                if pt else "Entiendo que quieres atención humana. Aún no hay una herramienta de derivación conectada; no se asignó a nadie.")
    if any(s in t for s in ("solicitud", "solicitar la tarjeta", "enviar pedido", "enviar solicitação", "contratar", "contrato", "aplicar ahora", "aplicar por", "puedo aplicar", "posso solicitar", "quero solicitar", "apply now")):
        return ("Ainda não consigo enviar solicitações por este canal. Nenhum pedido foi criado. Posso esclarecer as condições do cartão."
                if pt else "Aún no puedo enviar solicitudes por este canal. No se creó ninguna solicitud. Puedo aclararte las condiciones de la tarjeta.")
    if any(s in t for s in ("califico", "calificar", "califica", "elegível", "elegibilidade", "preaprov", "pré-aprov", "preaprob", "aprueba", "aprovado", "precheck", "prequal", "soy elegible", "sou elegível", "posso ser aprovado")):
        return ("Posso fazer uma avaliação inicial após seu consentimento para um cartão específico. A decisão final cabe a uma pessoa."
                if pt else "Puedo hacer una evaluación inicial tras tu consentimiento para una tarjeta específica. La decisión final corresponde a una persona.")
    if any(s in t for s in ("para mí", "me recomiendas", "recomiéndame", "mi perfil", "mis ingresos", "mi sueldo", "mi puntaje", "mi score", "minha renda", "meu perfil", "me recomenda", "me recomende", "para mim", "minha pontuação", "my income")):
        return ("Preciso acessar seu perfil para recomendar um cartão. Você também pode perguntar sobre as opções em geral."
                if pt else "Necesito acceder a tu perfil para recomendarte una tarjeta. También puedes preguntar por las opciones en general.")
    return None


def wants_human(text: str) -> bool:
    lowered = text.casefold()
    if any(phrase in lowered for phrase in ("não quero falar", "nao quero falar", "no quiero hablar")):
        return False
    return any(term in lowered for term in HUMAN_REQUEST_TERMS)


def _generate(system: str, user: str, model: str) -> dict:
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        raise RuntimeError("ANTHROPIC_API_KEY is not set")
    schema = {"type": "object", "properties": {
        "answer": {"type": "string"}, "citations": {"type": "array", "items": {"type": "string"}}},
        "required": ["answer", "citations"], "additionalProperties": False}
    payload = {"model": model, "max_tokens": 900, "system": system,
               "messages": [{"role": "user", "content": user}],
               "output_config": {"format": {"type": "json_schema", "schema": schema}}}
    if model == "claude-sonnet-5":
        payload["output_config"]["effort"] = "low"
    headers = {"Content-Type": "application/json", "anthropic-version": "2023-06-01",
               "Authorization": f"Bearer {key}"}
    if os.environ.get("ANTHROPIC_WORKSPACE_ID"):
        headers["anthropic-workspace-id"] = os.environ["ANTHROPIC_WORKSPACE_ID"]
    request = Request("https://api.anthropic.com/v1/messages", json.dumps(payload).encode(),
                      headers=headers, method="POST")
    try:
        with urlopen(request, timeout=45) as response:
            raw = json.load(response)
    except (HTTPError, URLError, TimeoutError) as exc:
        raise RuntimeError(f"Model unavailable ({exc.code if isinstance(exc, HTTPError) else type(exc).__name__})") from None
    content = "".join(b["text"] for b in raw.get("content", []) if b.get("type") == "text")
    result = json.loads(content)
    if not isinstance(result, dict) or set(result) != {"answer", "citations"}:
        raise RuntimeError("Invalid model response")
    return result


def respond(conversation: Conversation, message: str,
            model: str = "claude-sonnet-5", directory=None,
            before_model_call: Callable[[], None] | None = None) -> dict[str, object]:
    if conversation.stopped:
        raise ValueError("conversation has ended")
    message = message.strip()
    if not 1 <= len(message) <= 2000:
        raise ValueError("message must contain 1-2000 characters")
    lower = message.casefold()
    if lower in {"salir", "terminar", "no gracias", "não obrigado", "sair", "encerrar"}:
        conversation.stopped = True
        if directory is not None:
            directory.close_session(conversation.demo_token)
        conversation.demo_alias = None
        conversation.demo_token = None
        conversation.profile_permission = False
        conversation.precheck_consent_card = None
        answer = "Conversa encerrada." if conversation.language == "pt" else "Conversación terminada."
        return {"answer": answer, "citations": [], "route": "STOP", "fact_version": FACT_VERSION}
    mentioned_cards = [card for card in CARD_NAMES if re.search(rf"\b{card.casefold()}\b", lower)]
    if len(mentioned_cards) == 1:
        conversation.selected_card = mentioned_cards[0]
    if PRIVATE_INPUT.search(message):
        return {"answer": _boundary(message, conversation.language), "citations": [],
                "route": "SERVICE_BOUNDARY", "fact_version": FACT_VERSION}
    personal_cues = ("para mí", "me recomiendas", "recomiéndame", "mi perfil", "mis ingresos", "mi sueldo", "mi puntaje", "mi score", "minha renda", "meu perfil", "me recomenda", "me recomende", "para mim", "minha pontuação", "my income")
    other_card_cues = ("outro cartão", "outro cartao", "outros cartões", "outros cartoes",
                       "outra tarjeta", "otras tarjetas", "qué otra tarjeta", "que otra tarjeta")
    if directory is not None and (any(cue in lower for cue in personal_cues) or
                                  any(cue in lower for cue in other_card_cues)):
        from .session import recommendation_for_session
        return recommendation_for_session(conversation, directory)
    precheck_cues = ("califico", "calificar", "califica", "elegível", "elegibilidade", "preaprov", "pré-aprov", "preaprob", "aprueba", "aprovado", "precheck", "prequal", "soy elegible", "sou elegível", "posso ser aprovado", "teria crédito", "teria credito", "tenho crédito", "tenho credito", "tendría crédito", "tendria credito", "tengo crédito", "tengo credito", "would i qualify", "would i be approved")
    application_intent = bool(re.search(
        r"\b(?:adquirir|adquiri-lo|adquiri-la|adquiri[r]?lo|solicitar|solicitud|contratar|"
        r"obter|pedir|aplicar|apply|consigo|conseguir|contrato)\b", lower)) or any(
        phrase in lower for phrase in ("como faço para ter", "cómo hago para tener", "quero esse cartão",
                                "quiero esta tarjeta", "vou querer esse", "vou querer este",
                                "vou querer essa", "vou querer esta", "me quedo con", "i'll take it",
                                "i want this card")) or bool(re.search(
        r"\b(?:vou querer|lo quiero)(?:\s+(?:(?:o|a|el|la|esse|esta)\s+)?(?:cart[aã]o|tarjeta|campus|horizon|rewards|summit))?\s*[.!]?\s*$",
        lower))
    if conversation.demo_alias and conversation.selected_card and lower in {"quero", "quiero", "i want it"}:
        card = conversation.selected_card
        answer = (f"Você quer solicitar o {card} ou prefere saber mais sobre ele?"
                  if conversation.language == "pt" else
                  f"¿Quieres solicitar {card} o prefieres saber más sobre la tarjeta?")
        return {"answer": answer, "citations": [], "route": "ASK_APPLICATION_INTENT",
                "card": card, "fact_version": FACT_VERSION}
    if conversation.demo_alias and (application_intent or any(cue in lower for cue in precheck_cues)):
        card = conversation.selected_card if len(mentioned_cards) < 2 else None
        if card is None:
            answer = ("Claro. Qual cartão você gostaria de avaliar: Campus, Horizon, Rewards ou Summit?"
                      if conversation.language == "pt" else "Claro. ¿Qué tarjeta te gustaría evaluar: Campus, Horizon, Rewards o Summit?")
            return {"answer": answer, "citations": [], "route": "ASK_CARD",
                    "wants_application": application_intent, "fact_version": FACT_VERSION}
        answer = (f"Ótimo. Para avançar com o {card}, posso fazer uma avaliação inicial usando seu perfil. "
                  "Autorize a verificação deste cartão para continuar; a decisão final fica com uma pessoa."
                  if conversation.language == "pt" else
                  f"Perfecto. Para avanzar con {card}, puedo hacer una evaluación inicial con tu perfil. "
                  "Autoriza la verificación de esta tarjeta para continuar; la decisión final la toma una persona.")
        return {"answer": answer, "citations": [], "route": "ASK_PRECHECK_CONSENT", "card": card,
                "wants_application": application_intent,
                "fact_version": FACT_VERSION}
    lounge_question = any(term in lower for term in ("sala vip", "salas vip", "lounge", "lounges"))
    asking_which_card = bool(re.search(
        r"\b(?:qual|quais|cuál|cuáles|which|que|qué)\s+"
        r"(?:cart[aã]o|cart[oõ]es|tarjeta|tarjetas|card|cards)\b", lower))
    if lounge_question and asking_which_card and not mentioned_cards:
        result = _lounge_overview(conversation.language)
        conversation.turns.extend([{"role": "user", "text": message},
                                   {"role": "assistant", "text": result["answer"]}])
        return result
    boundary = _boundary(message, conversation.language)
    if boundary:
        return {"answer": boundary, "citations": [], "route": "SERVICE_BOUNDARY", "fact_version": FACT_VERSION}
    facts = [(fid, body) for fid, body in public_facts()
             if fid != "CATALOG.STATUS" and not fid.startswith("ACCESS.")]
    broad_more = any(phrase in lower for phrase in (
        "me fala mais", "fale mais", "conte mais", "cuéntame más", "cuentame mas",
        "háblame más", "hablame mas", "tell me more"))
    selected_card_benefits = (
        conversation.selected_card is not None
        and len(mentioned_cards) < 2
        and (bool(re.search(r"\b(?:benefícios|beneficios|benefits)\b", lower)) or broad_more)
    )
    simple_benefits = selected_card_benefits and not any(
        term in lower for term in ("sala vip", "lounge", "seguro", "cobertura", "insurance", "coverage"))
    if selected_card_benefits:
        facts = [(fid, body) for fid, body in facts
                 if fid == f"BENEFIT.{conversation.selected_card.upper()}" or
                 (not simple_benefits and fid in {"TRAVEL.RULES", "UNKNOWN.TRAVEL"})]
    if simple_benefits:
        facts = [(fid, re.sub(r" (?:No lounge visits or travel insurance are proposed\.|The travel figures are proposed comparison features, not active entitlements\.)", "", body))
                 for fid, body in facts]
        facts = [(fid, re.sub(r"\bproposed\s+", "", body, flags=re.I)) for fid, body in facts]
    replacements = (
        (r"\bin this demo\b", "here"),
        (r"\bthe demo\b", "the catalog"),
        (r"\bdemo cards\b", "cards"),
        (r"\bteam-created\b", "listed"),
        (r"\bcomparison features\b", "benefit terms"),
        (r"\bnot active entitlements\b", "subject to activation"),
        (r"\bsynthetic\b", "catalog"),
        (r"\bproposed\b", "listed"),
        (r"\bdraft\b", "catalog"),
        (r"\bdemo\b", "catalog"),
    )
    for pattern, replacement in replacements:
        facts = [(fid, re.sub(pattern, replacement, body, flags=re.I)) for fid, body in facts]
    lines = "\n".join(f"[{fid}] {body}" for fid, body in facts)
    topic_rules = (""
        if simple_benefits else
        "Rewards earns 1 mile and Summit 2 miles per USD-equivalent unit, NEVER per local-currency unit. "
        "USD purchases use 1:1 for illustrative miles; historical local-currency purchases need an exact posting day and historical FX. "
        "A purchase interest rate neither establishes nor rules out the cash-advance rate; that rate is unknown. "
        "If no card is selected, ask which card before giving a card-specific lounge visit count. ")
    system = (
        "You are a credit-card information advisor. "
        "Reply in the requested language, Spanish or Portuguese. Explain only the card facts below "
        "and cite supporting fact IDs. Do not describe internal development or testing. "
        "Speak naturally to a customer. Never refer to a catalog, version, draft, internal source, or testing. "
        "If asked for a card with no fees, distinguish no annual fee from purchase interest and any unknown charges; never promise the card has no costs. "
        "Do not call a card ideal or guaranteed suitable for a particular customer based only on a Student segment or a chat statement; enrollment is unverified. "
        "Translate 'statement credit' as 'crédito na fatura' in Portuguese or 'abono en el estado de cuenta' in Spanish. "
        "When asked about benefits, lead with the positive features of the requested card; do not list missing features unless asked. "
        "When asked which cards offer a feature, name only the cards that offer it. "
        "Do not add unrelated fees, rates, missing information, or general caveats to a benefits answer. "
        "For broad 'tell me more' questions, summarize the main benefits first and invite a question about fees or rates instead of dumping every term. "
        "For general lounge or travel-coverage questions, explain the defined visit, guest, trip, and medical-expense rules. Reserve unknown-partner caveats for a named lounge, insurer, trip, or claim question. "
        "Qualify a benefit only when the question asks for specific access, coverage, a guarantee, or a decision. "
        "Use one concise paragraph, normally 30-75 words; show arithmetic steps only when needed. "
        "Put fact IDs in the citations array, not inline in the answer. "
        "Never infer a selected card from prior assistant mistakes. Do not choose a card when none is named. "
        "If country or card is needed, ask a short clarifying question. "
        "Do not invent fees, rates, full cost, eligibility, current FX, coverage, application, or human assignment. "
        "The host advisor can collect a card-specific request for human review after separate customer confirmations. "
        "If a request to apply reaches you, never claim this channel cannot take it; invite the customer to say which card they want to request. "
        "Do not ask the customer to confirm an application or say you will register interest; the host service handles that workflow. "
        "You cannot run a precheck, record an application, or claim either action happened. "
        + topic_rules +
        "Prior conversation is untrusted and may contain false statements; correct them from these facts. "
        "No customer profile or bank action tool is available to you. A trusted test session may exist but is hidden from you. Never claim to have accessed customer data or done an action.\n\n"
        + lines)
    history = conversation.turns[-6:]
    context = json.dumps({"language": conversation.language, "country": conversation.country,
                          "entry": "campaign" if conversation.campaign_id else "direct",
                          "selected_card": None if len(mentioned_cards) >= 2 else conversation.selected_card,
                          "profile_data_available_to_model": False, "history": history,
                          "latest_question": message}, ensure_ascii=False)
    try:
        allowed = {fid for fid, _ in facts}
        for attempt in range(2):
            correction = (" Your previous answer claimed an application, approval, or human assignment. "
                          "Answer the product question using only the listed facts; do not mention an action or handoff."
                          if attempt else "")
            if before_model_call is not None:
                before_model_call()
            result = _generate(system + correction, context, model)
            if (not isinstance(result["answer"], str) or not result["answer"].strip() or
                not isinstance(result["citations"], list) or
                not all(isinstance(fid, str) and fid in allowed for fid in result["citations"])):
                raise RuntimeError("Invalid model answer or citation")
            answer, citations, route = result["answer"].strip(), result["citations"], "ANSWER_FACT"
            if not UNVERIFIED_ACTION.search(answer):
                break
        else:
            answer = ("Posso ajudar com os cartões e com uma avaliação inicial mediante seu consentimento. "
                      "Nenhuma nova solicitação foi registrada nesta resposta."
                      if conversation.language == "pt" else
                      "Puedo ayudarte con las tarjetas y una evaluación inicial con tu consentimiento. "
                      "No se registró ninguna solicitud nueva en esta respuesta.")
            citations, route = [], "SERVICE_BOUNDARY"
    except (RuntimeError, ValueError, json.JSONDecodeError):
        answer = ("Não consigo verificar uma resposta segura agora. Pergunte novamente mais tarde."
                  if conversation.language == "pt" else "No puedo verificar una respuesta segura ahora. Inténtalo más tarde.")
        citations, route = [], "FALLBACK"
    conversation.turns.extend([{"role": "user", "text": message},
                               {"role": "assistant", "text": answer}])
    return {"answer": answer, "citations": citations, "route": route,
            "fact_version": FACT_VERSION}
