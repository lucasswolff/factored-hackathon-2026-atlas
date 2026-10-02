"""Small, explicit chat decisions for consent and application confirmation."""

from __future__ import annotations

import re
import time
import unicodedata

from .policy import CARDS

PENDING_SECONDS = 600
YES = {"sim", "sim por favor", "sim pode", "sim quero continuar", "si",
       "si por favor", "si quiero continuar", "yes", "yes please",
       "yes go ahead", "confirmo", "confirmar", "claro", "pode", "puede",
       "quero", "quiero"}
NO = {"nao", "nao obrigado", "nao obrigada", "agora nao", "no", "no gracias",
      "not now", "no thanks", "prefiro nao", "prefiero no"}
APPLICATION_YES = {"desejo", "desejo sim", "si deseo", "quiero hacerlo"}
INFORMATION_CHOICE = {"conhecer as opcoes", "prefiro conhecer as opcoes",
                      "quero conhecer as opcoes", "ver as opcoes",
                      "conocer las opciones", "prefiero conocer las opciones",
                      "quiero conocer las opciones", "ver las opciones"}


def plain_text(message: str) -> str:
    plain = unicodedata.normalize("NFKD", message.casefold())
    plain = "".join(c for c in plain if not unicodedata.combining(c))
    plain = re.sub(r"[^a-z ]", " ", plain)
    return " ".join(plain.split())


def choice(message: str) -> bool | None:
    plain = plain_text(message)
    if plain in YES:
        return True
    if plain in NO:
        return False
    return None


def application_choice(message: str) -> bool | None:
    plain = plain_text(message)
    return True if plain in APPLICATION_YES else choice(message)


def wants_information(message: str) -> bool:
    return plain_text(message) in INFORMATION_CHOICE


def named_card(message: str) -> str | None:
    found = [card for card in CARDS if re.search(rf"\b{card.casefold()}\b", message.casefold())]
    return found[0] if len(found) == 1 else None


def pending(kind: str, card: str | None, *, apply_after: bool = False) -> dict:
    return {"kind": kind, "card": card, "apply_after": apply_after, "created_at": time.time()}


def expired(action: dict) -> bool:
    return time.time() - action["created_at"] > PENDING_SECONDS


def precheck_question(card: str, language: str, *, apply_after: bool) -> str:
    if language == "pt":
        lead = f"Para seguir com o {card}, " if apply_after else ""
        target = "" if apply_after else f" do {card}"
        return (lead + f"posso usar sua renda estimada e pontuação para fazer uma avaliação inicial{target}? "
                "Responda sim ou não. Isso não aprova crédito.")
    lead = f"Para seguir con {card}, " if apply_after else ""
    target = "" if apply_after else f" de {card}"
    return (lead + f"¿puedo usar tus ingresos estimados y puntuación para hacer una evaluación inicial{target}? "
            "Responde sí o no. Esto no aprueba crédito.")


def application_question(card: str, language: str, precheck_status: str | None) -> str:
    if language == "pt":
        context = ("A avaliação inicial não atendeu aos critérios; uma pessoa ainda pode revisar o pedido. "
                   if precheck_status == "DOES_NOT_MEET_DEMO_RULES" else
                   "A avaliação inicial exige revisão humana. " if precheck_status == "REVIEW_REQUIRED" else
                   "A avaliação inicial já foi feita. " if precheck_status else
                   "Você optou por não fazer a avaliação inicial. ")
        return (context + f"Deseja que eu registre uma solicitação do {card} para análise humana? "
                "Responda sim ou não. Isso não é aprovação de crédito.")
    context = ("La evaluación inicial no cumplió los criterios; una persona aún puede revisar la solicitud. "
               if precheck_status == "DOES_NOT_MEET_DEMO_RULES" else
               "La evaluación inicial requiere revisión humana. " if precheck_status == "REVIEW_REQUIRED" else
               "La evaluación inicial ya se realizó. " if precheck_status else
               "Elegiste no hacer la evaluación inicial. ")
    return (context + f"¿Quieres que registre una solicitud de {card} para revisión humana? "
            "Responde sí o no. Esto no es una aprobación de crédito.")
