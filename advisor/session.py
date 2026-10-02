"""Server-owned demo session, permission, and precheck transitions."""

from __future__ import annotations

from .data_access import DemoDirectory
from .policy import CARDS, PolicyResult, precheck, suggest
from .service import Conversation, FACT_VERSION

REASONS = {
    "current_credit_card_requires_review": ("Ya consta una tarjeta de crédito actual; se necesita revisión humana.", "Já consta um cartão de crédito atual; é necessária revisão humana."),
    "missing_profile_data": ("Faltan datos del perfil para esta simulación.", "Faltam dados do perfil para esta simulação."),
    "score_below_demo_threshold": ("El puntaje está por debajo del umbral de esta evaluación inicial.", "A pontuação está abaixo do limite desta avaliação inicial."),
    "score_near_demo_threshold": ("El puntaje está cerca del umbral de esta evaluación inicial y requiere revisión humana.", "A pontuação está próxima do limite desta avaliação inicial e exige análise humana."),
    "income_below_demo_threshold": ("El ingreso estimado está por debajo del umbral local de esta evaluación inicial.", "A renda estimada está abaixo do limite local desta avaliação inicial."),
    "student_enrollment_unverified": ("La inscripción estudiantil no está verificada; requiere revisión humana.", "A matrícula estudantil não foi verificada; exige revisão humana."),
    "student_segment_unverified_enrollment": ("El segmento Student solo sirve para conversar sobre Campus; no prueba inscripción.", "O segmento Student serve apenas para conversar sobre o Campus; não comprova matrícula."),
    "student_status_unverified": ("Campus es solo para estudiantes; este perfil no registra el segmento Student y necesita verificación humana.", "O Campus é apenas para estudantes; este perfil não registra o segmento Student e precisa de verificação humana."),
    "customer_not_active": ("El cliente no figura como activo en la instantánea.", "O cliente não consta como ativo na captura."),
    "profile_needs_human_review": ("Los datos disponibles no respaldan una sugerencia automática; se necesita revisión humana.", "Os dados disponíveis não sustentam uma sugestão automática; é necessária revisão humana."),
    "country_income_and_score_band": ("El puntaje y el ingreso estimado entran en la banda local de conversación.", "A pontuação e a renda estimada entram na faixa local de conversa."),
    "entry_income_and_score_band": ("El puntaje y el ingreso estimado entran en la banda inicial local.", "A pontuação e a renda estimada entram na faixa inicial local."),
    "synthetic_thresholds_met": ("Se cumplen los umbrales de la evaluación inicial.", "Os limites da avaliação inicial foram atendidos."),
}


def select_demo_persona(chat: Conversation, directory: DemoDirectory, alias: str) -> None:
    """Only a known fixture alias may establish this trusted test session."""
    if chat.stopped:
        raise PermissionError("Conversation has ended")
    public = directory.public_persona(alias)
    if chat.country is not None and chat.country != public["country"]:
        raise PermissionError("Persona country conflicts with conversation country")
    if chat.campaign_id == "CMP-YYT37NY1CZS7" and public["country"] != "Colombia":
        raise PermissionError("Persona country conflicts with historical campaign target")
    directory.close_session(chat.demo_token)
    chat.demo_token = directory.issue_test_session(alias)
    chat.demo_alias = alias
    chat.country = public["country"]
    chat.profile_permission = False
    chat.precheck_consent_card = None
    chat.turns.clear()


def sign_out(chat: Conversation, directory: DemoDirectory) -> None:
    directory.close_session(chat.demo_token)
    chat.demo_alias = None
    chat.demo_token = None
    chat.profile_permission = False
    chat.precheck_consent_card = None
    chat.turns.clear()


def grant_profile_permission(chat: Conversation) -> None:
    if chat.demo_token is None or chat.stopped:
        raise PermissionError("Trusted demo session required")
    chat.profile_permission = True


def _authorized_profile(chat: Conversation, directory: DemoDirectory):
    if chat.demo_token is None or chat.stopped:
        raise PermissionError("Trusted demo session required")
    return directory.read_profile(chat.demo_token, chat.profile_permission)


def grant_precheck_consent(chat: Conversation, directory: DemoDirectory, card: str) -> None:
    if card not in CARDS:
        raise ValueError("Unknown card")
    _authorized_profile(chat, directory)
    chat.precheck_consent_card = card


def profile_summary(chat: Conversation, directory: DemoDirectory) -> dict[str, object]:
    profile = _authorized_profile(chat, directory)
    return {"country": profile.country, "segment": profile.segment,
            "credit_score": profile.score,
            "estimated_monthly_income": str(profile.monthly_income) if profile.monthly_income is not None else None,
            "income_currency": profile.currency,
            "has_current_credit_card": profile.has_current_credit_card,
            "source": getattr(directory, "source_label", "ORGANIZER_SYNTHETIC_CURRENT_SNAPSHOT")}


def _format_result(result: PolicyResult, language: str) -> str:
    pt = language == "pt"
    detail = " ".join(REASONS[r][1 if pt else 0] for r in result.reasons)
    if result.status == "SUGGESTED_FOR_DISCUSSION":
        lead = (f"Sugestão para conversar: {result.card}. Não é avaliação nem aprovação de crédito. "
                if pt else f"Sugerencia para conversar: {result.card}. No es evaluación ni aprobación de crédito. ")
    elif result.status == "NO_SUGGESTION":
        lead = ("Não há sugestão automática para este perfil. " if pt else
                "No hay sugerencia automática para este perfil. ")
    else:
        status = {
            "MEETS_DEMO_THRESHOLDS_PENDING_REVIEW": ("passou pela triagem inicial e aguarda análise humana", "superó la evaluación inicial y espera revisión humana"),
            "DOES_NOT_MEET_DEMO_RULES": ("não atende aos critérios iniciais", "no cumple los criterios iniciales"),
            "REVIEW_REQUIRED": ("precisa de análise humana", "requiere revisión humana"),
        }.get(result.status, ("precisa de análise humana", "requiere revisión humana"))
        lead = (f"Resultado para {result.card}: {status[0]}. " if pt else
                f"Resultado para {result.card}: {status[1]}. ")
        if "missing_profile_data" in result.reasons:
            lead += ("Não foi possível determinar se atende aos limites desta simulação; não há pré-aprovação. "
                     if pt else
                     "No se pudo determinar si cumple los umbrales de esta simulación; no hay preaprobación. ")
    tail = (" Os dados do perfil são estimativas." if pt else
            " Los datos del perfil son estimaciones.")
    return lead + detail + tail


def recommendation_for_session(chat: Conversation, directory: DemoDirectory) -> dict[str, object]:
    try:
        profile = _authorized_profile(chat, directory)
    except PermissionError as exc:
        pt = chat.language == "pt"
        message = ("Selecione uma persona de teste permitida e conceda permissão separada para usar pontuação e renda armazenadas."
                   if pt else "Selecciona una persona de prueba permitida y concede permiso separado para usar puntaje e ingresos almacenados.")
        return {"answer": message, "citations": [], "route": "ASK_PERMISSION" if chat.demo_alias else "ASK_SIGN_IN",
                "fact_version": FACT_VERSION, "error": str(exc)}
    result = suggest(profile)
    return {"answer": _format_result(result, chat.language), "citations": [],
            "route": "POLICY_SUGGESTION", "policy": result, "fact_version": FACT_VERSION}


def run_precheck(chat: Conversation, directory: DemoDirectory, card: str) -> dict[str, object]:
    if card not in CARDS:
        raise ValueError("Unknown card")
    profile = _authorized_profile(chat, directory)
    if chat.precheck_consent_card != card:
        raise PermissionError("Separate card-specific precheck consent required")
    chat.precheck_consent_card = None  # One use; switching cards requires new consent.
    result = precheck(profile, card)
    return {"answer": _format_result(result, chat.language), "citations": [],
            "route": "SIMULATED_PRECHECK", "policy": result, "fact_version": FACT_VERSION}
