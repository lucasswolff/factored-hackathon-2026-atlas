"""AWS Lambda Function URL adapter for the hosted advisor.

The existing HTTP handler is reused on a loopback-only server. DynamoDB is the
source of truth for each request, so warm Lambda processes never own a session.
"""

from __future__ import annotations

import base64
import http.client
import json
import os
import threading
import time
from http.cookies import SimpleCookie
from typing import Any

from .aws_state import DynamoAnswerCounter, DynamoApplicationStore, DynamoSessionStore
from .agents import DynamoAgentDirectory
from .synthetic_data import SyntheticDirectory
from .web import AdvisorServer, WebApp, MAX_ANSWERS_PER_DAY, model_attempt_limit

_server: AdvisorServer | None = None
_app: WebApp | None = None
_sessions: DynamoSessionStore | None = None
_VISIBLE_PATHS = {"/", "/healthz", "/review", "/api/state", "/api/review",
                  "/api/start", "/api/home", "/api/signout", "/api/chat",
                  "/api/persona-preview", "/api/application-prepare",
                  "/api/application-submit", "/api/application-cancel",
                  "/assets/app.css", "/assets/app.js", "/assets/review.js"}


def _emit(event: dict[str, Any]) -> None:
    """CloudWatch receives only fixed operational fields, never request content."""
    print(json.dumps(event, separators=(",", ":")), flush=True)


def _initialize() -> None:
    global _server, _app, _sessions
    if _server is not None:
        return
    import boto3

    region = os.environ.get("AWS_REGION", "us-east-2")
    parameter = os.environ["ADVISOR_SECRET_PARAMETER"]
    secret = boto3.client("ssm", region_name=region).get_parameter(
        Name=parameter, WithDecryption=True)["Parameter"]["Value"]
    values = json.loads(secret)
    if not isinstance(values, dict) or len(values.get("ANTHROPIC_API_KEY", "")) < 20 or len(values.get("ADVISOR_REVIEW_CODE", "")) < 20:
        raise RuntimeError("Hosted credentials are missing")
    os.environ["ANTHROPIC_API_KEY"] = values["ANTHROPIC_API_KEY"]
    os.environ["ADVISOR_REVIEW_CODE"] = values["ADVISOR_REVIEW_CODE"]

    answer_budget = int(os.environ.get("ADVISOR_MAX_ANSWERS_PER_DAY", str(MAX_ANSWERS_PER_DAY)))
    try:
        limit = model_attempt_limit(answer_budget)
    except ValueError as exc:
        raise RuntimeError("Invalid answer limit") from exc
    table = boto3.resource("dynamodb", region_name=region).Table(os.environ["ADVISOR_TABLE_NAME"])
    _sessions = DynamoSessionStore(table)
    _app = WebApp(directory=SyntheticDirectory(), applications=DynamoApplicationStore(table),
                  hosted=True, answer_limit=limit, answer_counter=DynamoAnswerCounter(table),
                  on_model_attempt=lambda: _emit({"event": "model_attempt"}),
                  agent_directory=DynamoAgentDirectory(table))
    _server = AdvisorServer(("127.0.0.1", 0), _app)
    threading.Thread(target=_server.serve_forever, daemon=True).start()


def _sid(cookie_header: str) -> str | None:
    try:
        cookie = SimpleCookie()
        cookie.load(cookie_header)
        return cookie["advisor_session"].value if "advisor_session" in cookie else None
    except Exception:
        return None


def _response(status: int, body: str, *, content_type: str = "application/json") -> dict[str, Any]:
    return {"statusCode": status, "headers": {"Content-Type": content_type,
            "Cache-Control": "no-store"}, "body": body, "isBase64Encoded": False}


def lambda_handler(event: dict[str, Any], _context: Any) -> dict[str, Any]:
    """Handle one request and record a sanitized outcome for CloudWatch."""
    started = time.monotonic()
    response = None
    try:
        response = _handle_request(event)
        return response
    finally:
        method = event.get("requestContext", {}).get("http", {}).get("method")
        path = event.get("rawPath")
        report = {"event": "advisor_request",
                  "method": method if isinstance(method, str) and method in {"GET", "POST"} else "OTHER",
                  "endpoint": path if isinstance(path, str) and path in _VISIBLE_PATHS else "OTHER",
                  "status": response["statusCode"] if response else 500,
                  "duration_ms": round((time.monotonic() - started) * 1000)}
        if response and report["endpoint"] == "/api/chat" and response["statusCode"] == 200:
            try:
                route = json.loads(response["body"]).get("last_result", {}).get("route")
                if isinstance(route, str) and route.isupper() and route.replace("_", "").isalpha():
                    report["route"] = route[:48]
            except (ValueError, TypeError, AttributeError):
                pass
        _emit(report)


def _handle_request(event: dict[str, Any]) -> dict[str, Any]:
    """Handle one Function URL payload-v2 request, with conditional state save."""
    _initialize()
    assert _server is not None and _app is not None and _sessions is not None
    method = event.get("requestContext", {}).get("http", {}).get("method", "GET")
    if method not in {"GET", "POST"}:
        return _response(405, '{"error":"Method not allowed"}')
    path = event.get("rawPath", "/")
    if not isinstance(path, str) or not path.startswith("/"):
        return _response(400, '{"error":"Invalid path"}')
    raw_headers = event.get("headers") or {}
    headers = {key.lower(): value for key, value in raw_headers.items()}
    cookie_header = "; ".join(event.get("cookies") or []) or headers.get("cookie", "")
    sid = _sid(cookie_header)
    try:
        stored = _sessions.read(sid) if sid else None
    except Exception:
        return _response(503, '{"error":"Session storage unavailable"}')

    # Lambda execution environments handle one invocation at a time. A second
    # environment may run concurrently, so the eventual write uses a version
    # condition and refuses to return a response based on stale state.
    _app.sessions.clear()
    _app.directory = SyntheticDirectory()
    version = None
    if stored and sid:
        state, version = stored
        _app.sessions[sid] = state
        if state.chat and state.chat.demo_token and state.chat.demo_alias:
            _app.directory.restore_test_session(state.chat.demo_token, state.chat.demo_alias)

    try:
        raw_body = event.get("body") or ""
        body = base64.b64decode(raw_body, validate=True) if event.get("isBase64Encoded") else raw_body.encode("utf-8")
    except (ValueError, UnicodeError):
        return _response(400, '{"error":"Invalid request body"}')
    if len(body) > 8192:
        return _response(413, '{"error":"Request too large"}')
    forward = {key: value for key, value in headers.items()
               if key in {"host", "origin", "authorization", "content-type", "accept"}}
    if cookie_header:
        forward["cookie"] = cookie_header
    conn = http.client.HTTPConnection("127.0.0.1", _server.server_port, timeout=55)
    try:
        conn.request(method, path, body=body if method == "POST" else None, headers=forward)
        response = conn.getresponse()
        content = response.read()
        response_headers = {key: value for key, value in response.getheaders()
                            if key.lower() not in {"connection", "content-length", "set-cookie", "server", "date"}}
        set_cookies = [value for key, value in response.getheaders() if key.lower() == "set-cookie"]
        status = response.status
    except (OSError, TimeoutError):
        return _response(503, '{"error":"Advisor temporarily unavailable"}')
    finally:
        conn.close()

    saved_sid = _sid("; ".join(set_cookies)) or sid
    if saved_sid and saved_sid in _app.sessions and (method == "POST" or stored is None):
        try:
            _sessions.write(saved_sid, _app.sessions[saved_sid],
                            version if saved_sid == sid and stored else None)
        except Exception as exc:
            if getattr(exc, "response", {}).get("Error", {}).get("Code") == "ConditionalCheckFailedException":
                return _response(409, '{"error":"Conversation changed; refresh and try again"}')
            return _response(503, '{"error":"Session could not be saved; retry"}')
    result = {"statusCode": status, "headers": response_headers,
              "body": content.decode("utf-8"), "isBase64Encoded": False}
    if set_cookies:
        result["cookies"] = set_cookies
    return result
