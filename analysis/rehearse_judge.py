"""Bounded live judge rehearsal using only fictional fixtures and local policy paths.

Set ADVISOR_JUDGE_URL. Optionally set ADVISOR_REVIEW_CODE for queue read-back.
The script prints aggregates only; it never prints cookies or application IDs.
"""

from __future__ import annotations

import base64
import json
import os
import statistics
import time
from concurrent.futures import ThreadPoolExecutor
from http.cookiejar import CookieJar
from urllib.error import HTTPError
from urllib.request import HTTPCookieProcessor, Request, build_opener

COUNTRIES = {"Colombia": "P04", "México": "P05", "Argentina": "P06"}
CAMPAIGN = "CMP-I5TGQ4SXP4EG"  # Source context mapped to fictional Horizon.


class Visitor:
    def __init__(self, url: str):
        self.url = url.rstrip("/")
        self.opener = build_opener(HTTPCookieProcessor(CookieJar()))

    def call(self, path: str, body: dict | None = None, authorization: str | None = None):
        headers = {"Content-Type": "application/json"}
        if authorization:
            headers["Authorization"] = authorization
        request = Request(self.url + path, data=json.dumps(body).encode() if body is not None else None,
                          headers=headers, method="POST" if body is not None else "GET")
        started = time.perf_counter()
        try:
            with self.opener.open(request, timeout=25) as response:
                status, raw = response.status, response.read()
        except HTTPError as exc:
            status, raw = exc.code, exc.read()
        elapsed = 1000 * (time.perf_counter() - started)
        try:
            data = json.loads(raw)
        except ValueError:
            data = {}
        return status, data, elapsed


def percentile(values, fraction):
    ordered = sorted(values)
    return round(ordered[max(0, int(len(ordered) * fraction + 0.999999) - 1)], 1)


def main():
    url = os.environ["ADVISOR_JUDGE_URL"]
    metrics = []
    references = set()
    matrix = []
    for entry in ("campaign", "direct"):
        for country, alias in COUNTRIES.items():
            for language in ("es", "pt"):
                visitor = Visitor(url)
                body = {"entry": entry, "country": country, "language": language, "alias": alias}
                if entry == "campaign":
                    body["campaign_id"] = CAMPAIGN
                steps = [("start", "/api/start", body),
                         ("intent", "/api/chat", {"message": "Quiero solicitar Horizon" if language == "es" else "Quero solicitar Horizon"}),
                         ("consent", "/api/chat", {"message": "sí" if language == "es" else "sim"}),
                         ("confirmation", "/api/chat", {"message": "sí" if language == "es" else "sim"}
                          if entry == "direct" and language == "es" else
                          {"message": "no" if language == "es" else "não"})]
                routes = []
                ok = True
                for label, path, payload in steps:
                    status, result, elapsed = visitor.call(path, payload)
                    metrics.append((label, status, elapsed))
                    if status != 200:
                        ok = False
                        routes.append(f"HTTP_{status}")
                        break
                    if label == "start":
                        ok &= result["conversation"]["entry_kind"] == entry
                        ok &= result["conversation"]["country"] == country
                        continue
                    route = result["events"][-1]["route"]
                    routes.append(route)
                    if label == "consent":
                        ok &= result["prechecks"].get("Horizon") is not None
                    if label == "confirmation" and entry == "direct" and language == "es":
                        app = result.get("application")
                        ok &= app is not None and app["status"] == "PENDING_REVIEW"
                        if app:
                            references.add(app["application_id"])
                    elif label == "confirmation":
                        ok &= result.get("application") is None
                matrix.append({"entry": entry, "country": country, "language": language,
                               "ok": bool(ok), "routes": routes})

    # New visitor cannot read a prior visitor's active state or reviewer queue.
    outsider = Visitor(url)
    outsider_state = outsider.call("/api/state")
    queue_denied = outsider.call("/api/review")
    code = os.environ.get("ADVISOR_REVIEW_CODE")
    queue_verified = None
    if code:
        token = base64.b64encode(("reviewer:" + code).encode()).decode()
        status, queue, _ = outsider.call("/api/review", authorization="Basic " + token)
        queue_verified = status == 200 and references.issubset(
            {row["application_id"] for row in queue.get("applications", [])})

    def concurrent_visitor(index):
        visitor = Visitor(url)
        timings = []
        for path, payload in (("/api/start", {"entry": "direct", "country": "México", "language": "pt", "alias": "P05"}),
                              ("/api/chat", {"message": "Quero solicitar Horizon"}),
                              ("/api/chat", {"message": "não"}),
                              ("/api/chat", {"message": "não"})):
            status, result, elapsed = visitor.call(path, payload)
            timings.append((status, elapsed))
            if status != 200:
                break
        return timings

    with ThreadPoolExecutor(max_workers=6) as pool:
        concurrent = list(pool.map(concurrent_visitor, range(6)))
    concurrent_flat = [item for visit in concurrent for item in visit]
    report = {
        "matrix": matrix,
        "matrix_passed": sum(case["ok"] for case in matrix),
        "matrix_total": len(matrix),
        "applications_verified": len(references),
        "outsider_state_empty": outsider_state[0] == 200 and outsider_state[1]["conversation"] is None,
        "review_denied_status": queue_denied[0],
        "review_queue_verified": queue_verified,
        "concurrent_visitors": 6,
        "concurrent_requests": len(concurrent_flat),
        "concurrent_http_errors": sum(status >= 400 for status, _ in concurrent_flat),
        "concurrent_throttles": sum(status == 429 for status, _ in concurrent_flat),
        "concurrent_p50_ms": percentile([ms for _, ms in concurrent_flat], .5),
        "concurrent_p95_ms": percentile([ms for _, ms in concurrent_flat], .95),
        "matrix_p50_ms": percentile([ms for _, _, ms in metrics], .5),
        "matrix_p95_ms": percentile([ms for _, _, ms in metrics], .95),
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
