"""Classify public product requests before profile or action services run.

This is a conservative local router. Unrecognized wording remains a public
question; it never grants consent or creates an application.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass


@dataclass(frozen=True)
class ProductIntent:
    kind: str = "PUBLIC_QUESTION"
    lower_cost: bool = False
    require_travel_benefits: bool = False
    asks_eligibility: bool = False
    no_annual_fee: bool = False
    exclude_current: bool = False


def normalize(message: str) -> str:
    plain = unicodedata.normalize("NFKD", message.casefold())
    plain = "".join(char for char in plain if not unicodedata.combining(char))
    return " ".join(re.findall(r"[a-z]+", plain))


def classify_product_intent(message: str, selected_card: str | None,
                            named_cards: tuple[str, ...] = ()) -> ProductIntent:
    plain = normalize(message)
    words = set(plain.split())
    asks_recommendation = any(word.startswith(("recomend", "recomiend", "suger", "sugest", "indic"))
                              for word in words)
    asks_recommendation = asks_recommendation or (
        any(word in words for word in ("melhor", "mejor", "best"))
        and any(word in words for word in ("cartao", "tarjeta", "card"))
        and any(phrase in plain for phrase in ("para mim", "para mi", "for me")))
    product_words = any(word.startswith(("carta", "tarjeta", "card", "opca", "opci", "alternativ"))
                        for word in words)
    asks_alternative = (any(word.startswith(("outr", "otr", "other", "alternativ", "diferent"))
                            for word in words) and (product_words or len(words) <= 2))
    asks_affordable = any(word.startswith(("barat", "economic", "accesib", "asequib", "afford", "cheap"))
                          for word in words) or any(phrase in plain for phrase in (
                              "mais em conta", "menos caro", "menos cara", "lower fee"))
    lower_amount = any(word.startswith(("menor", "baix", "baj")) for word in words) and any(
        word.startswith(("valor", "prec", "cust", "cost", "anuid", "anualid", "tarif", "cuot", "gasto", "isen", "exen"))
        for word in words)
    lower_amount = lower_amount or ("menos" in words and any(
        word.startswith(("anuid", "anualid", "tarif", "cuot", "cost", "cust")) for word in words))
    no_annual_fee = any(phrase in plain for phrase in (
        "sem anuidade", "sin cuota anual", "sin anualidad", "no annual fee", "anuidade zero"))
    lower_cost = asks_affordable or lower_amount or no_annual_fee
    require_travel_benefits = ("vip" in words or any(
        word.startswith(("lounge", "viagem", "viaje", "travel")) for word in words))
    asks_eligibility = any(word.startswith(("criter", "elegib", "calific", "qualif", "aprov"))
                           for word in words)
    explicit_apply = any(word in words for word in ("quero", "quiero", "desejo", "deseo", "want")) and any(
        word.startswith(("solicit", "apply", "aplic", "pedir")) for word in words)
    question = "?" in message or any(word in words for word in (
        "qual", "quais", "que", "cual", "cuales", "which", "whether"))

    if explicit_apply and len(named_cards) == 1:
        return ProductIntent()
    if asks_alternative and explicit_apply and not question and len(named_cards) == 0:
        return ProductIntent("CHOOSE_OTHER_CARD")
    if len(named_cards) >= 2:
        return ProductIntent()
    if asks_alternative or (lower_cost and (selected_card is not None or product_words)):
        return ProductIntent("CATALOG_COMPARISON", lower_cost, require_travel_benefits,
                             asks_eligibility, no_annual_fee,
                             asks_alternative or (lower_cost and selected_card is not None and not no_annual_fee))
    if asks_recommendation and require_travel_benefits:
        return ProductIntent("CATALOG_COMPARISON", require_travel_benefits=True)
    if asks_recommendation and not lower_cost:
        return ProductIntent("PROFILE_RECOMMENDATION")
    return ProductIntent()
