"""Paired, local HTTP evaluation with fictional fixtures and frozen case labels.

Run after freezing the JSONL. The keyword FAQ baseline shares the advisor's
session, policy, consent, action, and handoff code. Only the public-answer
generator changes. Case text is never written to the result file.
"""

from __future__ import annotations

import argparse
import hashlib
import http.client
import json
import os
import re
import sys
import tempfile
import threading
import time
import unicodedata
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from advisor import service
from advisor.applications import ApplicationStorageError, ApplicationStore
from advisor.web import AdvisorServer, SESSION_SECONDS, WebApp, load_local_key

CASES = ROOT / "plan/conversation_data/automated_holdout_2026_10_04.jsonl"
FROZEN_SHA256 = "66b799fe9b39ce3adca1373c4a943f0c61198c6d83d20206fa907e413df12166"
ADJUDICATED_CASES = ROOT / "plan/conversation_data/automated_route_adjudication_2026_10_04.jsonl"
ADJUDICATED_SHA256 = "a1d39b7a1fa26b4acb4f7326a37fad01079e04edff632387f151ea4da9ef615f"


def normalize(value: str) -> str:
    value = unicodedata.normalize("NFKD", value.casefold())
    return "".join(char for char in value if not unicodedata.combining(char))


def baseline_answer(_system: str, user: str, _model: str) -> dict:
    """Small bilingual keyword FAQ drawn from the versioned public fact sheet."""
    context = json.loads(user)
    question = normalize(context["latest_question"])
    language = context["language"]
    card = context.get("selected_card")
    country = context.get("country")
    pt = language == "pt"
    facts = dict(service.public_facts())
    fee_id = {"Colombia": "FEE.CO", "México": "FEE.MX", "Argentina": "FEE.AR"}.get(country)
    def result(es: str, po: str, ids: list[str], unresolved: bool = False) -> dict:
        return {"answer": po if pt else es, "citations": ids, "unresolved": unresolved}
    if any(word in question for word in ("cat", "cft", "costo total", "custo total")):
        return result("No puedo verificar el costo total con estos datos.",
                      "Não consigo verificar o custo total com estes dados.",
                      ["UNKNOWN.COST"], True)
    if any(word in question for word in ("lounge", "sala vip")) and any(
            word in question for word in ("garant", "aeroporto", "aeropuerto", "amanha", "mañana")):
        return result("No puedo verificar el acceso a una sala concreta.",
                      "Não consigo verificar o acesso a uma sala específica.",
                      ["UNKNOWN.TRAVEL"], True)
    if any(word in question for word in ("millas", "milhas")) and any(
            word in question for word in ("hoy", "hoje", "exact", "exat")):
        return result("No tengo una tasa de cambio actual para calcular millas exactas.",
                      "Não tenho uma taxa de câmbio atual para calcular milhas exatas.",
                      ["MILES.HISTORY"], True)
    if any(word in question for word in ("acompanhante", "acompanante", "invitado", "convidado")):
        return result("El acompañante usa una visita adicional del mismo cupo.",
                      "O acompanhante usa outra visita da mesma cota.",
                      ["TRAVEL.RULES"])
    if any(word in question for word in ("anuidade", "anualidad", "cuota", "parcela", "isenc", "exoner")):
        if not fee_id or not card:
            return result("Indica la tarjeta y el país para consultar la cuota.",
                          "Informe o cartão e o país para consultar a anuidade.", [], False)
        if any(word in question for word in ("parcial", "primer", "primeir")):
            return result("La primera cuota del ciclo parcial se exonera.",
                          "A primeira parcela do ciclo parcial é isenta.", ["FEE.WAIVER"])
        if any(word in question for word in ("devolu", "reembols", "estorn")):
            return result("Solo cuentan compras contabilizadas, netas de devoluciones, al cierre.",
                          "Só contam compras lançadas, líquidas de estornos, no fechamento.", ["FEE.WAIVER"])
        match = re.search(rf"{card} (?:COP|MXN|ARS) ([\d,]+)", facts[fee_id].split("Waiver thresholds", 1)[-1])
        if match:
            amount = match.group(1).replace(",", ".")
            return result(f"El umbral de {card} es {amount} en compras elegibles por ciclo completo.",
                          f"O limite de {card} é {amount} em compras elegíveis por ciclo completo.",
                          [fee_id, "FEE.WAIVER"])
    if "tna" in question and country == "Argentina":
        return result("La TNA de compras es 70%; no es el costo financiero total.",
                      "A TNA de compras é 70%; não é o custo financeiro total.",
                      ["RATE.AR", "UNKNOWN.COST"])
    if any(word in question for word in ("beneficio", "beneficio", "vantagen", "supermercado", "mercado")) and card:
        fid = f"BENEFIT.{card.upper()}"
        if fid in facts:
            return result(f"{card} ofrece beneficios publicados; consulta las condiciones aplicables.",
                          f"{card} oferece benefícios publicados; consulte as condições aplicáveis.", [fid])
    return result("No encuentro una respuesta verificada. Puedo pedir revisión humana.",
                  "Não encontro uma resposta verificada. Posso pedir revisão humana.", [], True)


class Visitor:
    def __init__(self, port: int):
        self.port = port
        self.cookie = None

    def call(self, path: str, body: dict | None = None) -> tuple[int, dict, float]:
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=65)
        headers = {}
        if self.cookie:
            headers["Cookie"] = self.cookie
        raw = None
        if body is not None:
            headers["Content-Type"] = "application/json"
            raw = json.dumps(body, ensure_ascii=False).encode("utf-8")
        start = time.perf_counter()
        conn.request("POST" if body is not None else "GET", path, body=raw, headers=headers)
        response = conn.getresponse()
        data = response.read()
        elapsed = (time.perf_counter() - start) * 1000
        cookie = response.getheader("Set-Cookie")
        if cookie:
            self.cookie = cookie.split(";", 1)[0]
        status = response.status
        conn.close()
        return status, json.loads(data) if data else {}, elapsed


def percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return round(ordered[max(0, int(len(ordered) * fraction + 0.999999) - 1)], 1)


def evaluate_arm(cases: list[dict], arm: str, repeats: int) -> dict:
    observations = []
    original = service._generate
    with tempfile.TemporaryDirectory() as tmp:
        app = WebApp(applications=ApplicationStore(Path(tmp) / "actions.sqlite"), hosted=True,
                     answer_limit=200)
        server = AdvisorServer(("127.0.0.1", 0), app)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            for repeat in range(repeats):
                for case in cases:
                    visitor = Visitor(server.server_port)
                    model_calls = []
                    def measured_generate(system: str, user: str, model: str) -> dict:
                        started = time.perf_counter()
                        answer = baseline_answer(system, user, model) if arm == "keyword_faq" else original(system, user, model)
                        model_calls.append({"duration_ms": round((time.perf_counter() - started) * 1000, 1),
                                            "input_tokens": answer.get("_usage", {}).get("input_tokens") or 0,
                                            "output_tokens": answer.get("_usage", {}).get("output_tokens") or 0})
                        return answer
                    start_body = {key: case[key] for key in ("entry", "country", "language", "alias")}
                    if "campaign_id" in case:
                        start_body["campaign_id"] = case["campaign_id"]
                    statuses, routes, latencies, checks, answers = [], [], [], [], []
                    expected_steps = 0
                    with patch("advisor.service._generate", side_effect=measured_generate):
                        status, state, duration = visitor.call("/api/start", start_body)
                        statuses.append(status)
                        latencies.append(duration)
                        for step in case["steps"] if status == 200 else []:
                            if step.get("only_if_previous_route") != (routes[-1] if routes else None) and "only_if_previous_route" in step:
                                continue
                            expected_steps += 1
                            if case.get("fault") == "model_unavailable":
                                with patch("advisor.service._generate", side_effect=RuntimeError("injected outage")):
                                    status, state, duration = visitor.call("/api/chat", {"message": step["message"]})
                            else:
                                status, state, duration = visitor.call("/api/chat", {"message": step["message"]})
                            statuses.append(status)
                            latencies.append(duration)
                            if status != 200:
                                checks.append(False)
                                break
                            last = state["events"][-1]
                            routes.append(last["route"])
                            answers.append({"text": last["text"],
                                            "citations": last.get("citations") or [],
                                            "route": last["route"]})
                            response = normalize(last["text"])
                            terms = step.get("answer_terms", [])
                            accepted = step.get("accepted_routes", [step["route"]])
                            checks.append(last["route"] in accepted and
                                          set(step.get("citations", [])) <= set(last.get("citations") or []) and
                                          (not terms or any(normalize(term) in response for term in terms)))
                    application = state.get("application") if status == 200 else None
                    handoff = state.get("handoff") if status == 200 else None
                    prechecks = state.get("prechecks", {}) if status == 200 else {}
                    expected_app = case["outcome"] == "application"
                    expected_handoff = case["outcome"] == "handoff"
                    action_ok = bool(application) == expected_app and bool(handoff) == expected_handoff
                    if application:
                        action_ok &= application.get("status") == "PENDING_REVIEW"
                    if handoff:
                        action_ok &= handoff.get("status") == "PENDING_REVIEW"
                    # Re-read the persisted action independently of the browser snapshot.
                    sid = visitor.cookie.split("=", 1)[1] if visitor.cookie else None
                    stored_session = app.sessions.get(sid) if sid else None
                    conversation_id = stored_session.conversation_id if stored_session else None
                    if application:
                        stored = app.applications.read(conversation_id, application["card"]) if conversation_id else None
                        action_ok &= bool(stored and stored["application_id"] == application["application_id"])
                    if handoff:
                        stored = app.applications.read_handoff(conversation_id, "CUSTOMER_REQUEST") if conversation_id else None
                        action_ok &= bool(stored and stored["handoff_id"] == handoff["handoff_id"])
                    if "precheck" in case:
                        action_ok &= bool(prechecks) == case["precheck"]
                    # This is a narrow deterministic disclosure check, not a general
                    # answer-safety judgment.
                    other_profile_disclosed = (case["family"] == "other_customer_pt" and
                                               any(secret in " ".join(event.get("text", "") for event in state.get("events", [])
                                                                      if event.get("role") == "assistant")
                                                   for secret in ("12000000", "12.000.000", "680")))
                    case_ok = (len(checks) == expected_steps and all(checks) and action_ok
                               and not other_profile_disclosed and all(s == 200 for s in statuses))
                    observations.append({"id": case["id"], "repeat": repeat + 1,
                                         "observed_at_utc": datetime.now(timezone.utc).isoformat(),
                                         "language": case["language"], "country": case["country"],
                                         "entry": case["entry"], "family": case["family"],
                                         "expected_outcome": case["outcome"], "pass": case_ok,
                                         "step_checks": checks, "action_ok": bool(action_ok),
                                         "other_profile_disclosed": other_profile_disclosed,
                                         "precheck_count": len(prechecks),
                                         "routes": routes, "statuses": statuses,
                                         "assistant_answers": answers,
                                         "journey_ms": round(sum(latencies), 1),
                                         "request_ms": [round(ms, 1) for ms in latencies],
                                         "model_calls": model_calls})
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)
    return summarize(observations, arm)


def summarize(rows: list[dict], arm: str) -> dict:
    eligible = [r for r in rows if r["expected_outcome"] in {"resolve", "application", "decline"}]
    safe_resolution = [r for r in eligible if r["pass"] and r["expected_outcome"] != "decline"]
    attempted = [r for r in rows if any(route not in {"FALLBACK", "SERVICE_BOUNDARY"} for route in r["routes"])]
    handoff_required = [r for r in rows if r["expected_outcome"] == "handoff"]
    missed = [r for r in handoff_required if "HANDOFF_RECORDED" not in r["routes"]]
    unnecessary = [r for r in rows if r["expected_outcome"] != "handoff" and "HANDOFF_RECORDED" in r["routes"]]
    all_calls = [call for row in rows for call in row["model_calls"]]
    route_counts = Counter(route for row in rows for route in row["routes"])
    input_tokens = sum(call["input_tokens"] for call in all_calls)
    output_tokens = sum(call["output_tokens"] for call in all_calls)
    # Anthropic Sonnet 5 public list price, USD per million tokens. This is
    # provider-only estimated cost, excluding infrastructure and taxes.
    provider_cost_usd = round((input_tokens * 2 + output_tokens * 10) / 1_000_000, 6)
    by_language = {lang: {"n": sum(r["language"] == lang for r in rows),
                          "pass": sum(r["language"] == lang and r["pass"] for r in rows)}
                   for lang in ("es", "pt")}
    return {"arm": arm, "n": len(rows), "pass": sum(r["pass"] for r in rows),
            "eligible_n": len(eligible), "safe_resolution_proxy_n": len(safe_resolution),
            "automation_attempted_n": len(attempted),
            "handoff_required_n": len(handoff_required), "missed_handoff_n": len(missed),
            "unnecessary_handoff_n": len(unnecessary),
            "action_mismatch_n": sum(not r["action_ok"] for r in rows),
            "other_profile_disclosure_n": sum(r["other_profile_disclosed"] for r in rows),
            "http_error_n": sum(any(status >= 400 for status in r["statuses"]) for r in rows),
            "event_counts": {"chat_starts": len(rows), "prechecks": sum(r["precheck_count"] for r in rows),
                "verified_applications": route_counts["APPLICATION_RECORDED"],
                "verified_handoffs": route_counts["HANDOFF_RECORDED"],
                "customer_declines": sum(route_counts[name] for name in
                                         ("APPLICATION_CANCELLED", "PRECHECK_DECLINED", "HANDOFF_DECLINED")),
                "fallbacks": route_counts["FALLBACK"]},
            "p50_journey_ms": percentile([r["journey_ms"] for r in rows], .5),
            "p95_journey_ms": percentile([r["journey_ms"] for r in rows], .95),
            "p50_request_ms": percentile([ms for r in rows for ms in r["request_ms"]], .5),
            "p95_request_ms": percentile([ms for r in rows for ms in r["request_ms"]], .95),
            "p50_public_answer_ms": percentile([call["duration_ms"] for call in all_calls], .5),
            "p95_public_answer_ms": percentile([call["duration_ms"] for call in all_calls], .95),
            "public_answer_calls": len(all_calls),
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "provider_cost_usd_estimate": provider_cost_usd,
            "cost_per_attempted_case_usd": round(provider_cost_usd / len(attempted), 6) if attempted else None,
            "cost_per_successful_proxy_resolution_usd": round(provider_cost_usd / len(safe_resolution), 6) if safe_resolution else None,
            "by_language": by_language, "observations": rows}


def run_fault_checks() -> dict:
    """Separate deterministic regression probes; excluded from paired scores."""
    with tempfile.TemporaryDirectory() as tmp:
        app = WebApp(applications=ApplicationStore(Path(tmp) / "faults.sqlite"), hosted=True)
        server = AdvisorServer(("127.0.0.1", 0), app)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            visitor = Visitor(server.server_port)
            started = visitor.call("/api/start", {"entry": "direct", "country": "México",
                                                   "language": "es", "alias": "P05"})[0] == 200
            switch = visitor.call("/api/start", {"entry": "direct", "country": "México",
                                                  "language": "es", "alias": "P08"})[0]
            outsider = Visitor(server.server_port)
            outsider_state = outsider.call("/api/state")[1]
            review_status = outsider.call("/api/review")[0]
            sid = visitor.cookie.split("=", 1)[1]
            app.sessions[sid].last_active_at -= SESSION_SECONDS + 1
            expired_status, expired_body, _ = visitor.call("/api/chat", {"message": "sí"})

            action_visitor = Visitor(server.server_port)
            action_visitor.call("/api/start", {"entry": "direct", "country": "México",
                                               "language": "es", "alias": "P05"})
            action_visitor.call("/api/chat", {"message": "Quiero solicitar Horizon sin evaluación previa"})
            with patch.object(app.applications, "create_and_verify",
                              side_effect=ApplicationStorageError("injected storage failure")):
                failure_status, failed, _ = action_visitor.call("/api/chat", {"message": "sí"})
            retry_status, retried, _ = action_visitor.call("/api/chat", {"message": "sí"})
            stored = app.applications.read(app.sessions[action_visitor.cookie.split("=", 1)[1]].conversation_id,
                                           "Horizon")
            return {"started": started,
                    "cross_fixture_start_denied": switch == 400,
                    "outsider_state_empty": outsider_state.get("conversation") is None,
                    "review_denied": review_status == 401,
                    "expired_session_denied": expired_status == 400 and not expired_body.get("application"),
                    "storage_failure_no_false_success": failure_status == 200 and
                        failed.get("last_result", {}).get("route") == "APPLICATION_UNVERIFIED" and
                        failed.get("application") is None,
                    "retry_persisted_one_application": retry_status == 200 and
                        retried.get("last_result", {}).get("route") == "APPLICATION_RECORDED" and
                        bool(stored and retried.get("application", {}).get("application_id") == stored["application_id"])}
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--arm", choices=("keyword_faq", "advisor", "both"), default="both")
    parser.add_argument("--case-version", choices=("original", "adjudicated"), default="original")
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument("--output", type=Path, default=Path("/tmp/automated_advisor_eval.json"))
    args = parser.parse_args()
    if not 1 <= args.repeats <= 3:
        parser.error("repeats must be 1..3")
    cases_path, expected_digest = ((CASES, FROZEN_SHA256) if args.case_version == "original"
                                   else (ADJUDICATED_CASES, ADJUDICATED_SHA256))
    digest = hashlib.sha256(cases_path.read_bytes()).hexdigest()
    if digest != expected_digest:
        raise RuntimeError("Frozen case file changed; preserve the original evaluation version")
    cases = [json.loads(line) for line in cases_path.read_text(encoding="utf-8").splitlines()]
    if len(cases) != len({case["id"] for case in cases}):
        raise RuntimeError("Duplicate case ID")
    load_local_key()
    if args.arm in {"advisor", "both"} and not os.environ.get("ANTHROPIC_API_KEY"):
        raise RuntimeError("ANTHROPIC_API_KEY unavailable for live advisor arm")
    os.environ.setdefault("ADVISOR_REVIEW_CODE", "evaluation-only-code-1234567890")
    arms = ("keyword_faq", "advisor") if args.arm == "both" else (args.arm,)
    result = {"case_sha256": digest, "case_version": args.case_version,
              "fact_version": service.FACT_VERSION,
              "case_count": len(cases), "repeats": args.repeats,
              "label_provenance": "agent-authored, deterministic assertions; no bilingual human review",
              "measurement": "local loopback HTTP, fictional fixtures, sequential warm server per arm",
              "arms": {name: evaluate_arm(cases, name, args.repeats) for name in arms},
              "supplemental_fault_regression": run_fault_checks()}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"case_sha256": digest, "output": str(args.output),
                      "arms": {name: {key: value for key, value in data.items() if key != "observations"}
                               for name, data in result["arms"].items()},
                      "supplemental_fault_regression": result["supplemental_fault_regression"]},
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
