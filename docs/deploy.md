# Hosted judge prototype

This document describes the single-container hosting option. The active
[AWS Lambda deployment](../infra/aws/README.md) instead stores sessions,
mock actions, and its shared daily answer counter in DynamoDB. Its URL is
currently enabled for browser testing.

This deployment is a **controlled demo**, not an online bank or a real credit
application. It uses only the ten [team-written fixtures](../advisor/synthetic_data.py),
the team-created card catalog and policy, and a local mock-action database. The
organizer CSVs and Snowflake credentials are not needed in the container. Local
development without `ADVISOR_HOSTED=1` still uses the organizer-synthetic CSVs.
The hosted P01–P10 aliases represent the same *types of scenarios* as local
P01–P10; their invented values are deliberately different and must not be
described as actual source rows.

## Required configuration

Set the following as private environment variables on a single container
instance. [`.env.example`](../.env.example) lists the names without secrets.

| Variable | Purpose |
| --- | --- |
| `ADVISOR_HOSTED=1` | Selects the synthetic-fixture mode. |
| `ADVISOR_REVIEW_CODE` | Reviewer-only code, at least 20 characters. |
| `ANTHROPIC_API_KEY` | Server-side model key; never exposed to JavaScript. |
| `ADVISOR_DB_PATH` | Absolute path to the mock-action SQLite file on a persistent volume, e.g. `/state/mock_applications.sqlite`. |
| `ADVISOR_MAX_ANSWERS_PER_DAY` | Optional per-process provider-attempt cap, default 200, permitted 1–200. |
| `PORT` | HTTP listener inside the container, default 8765. |

Generate the reviewer code with `python3 -c 'import secrets; print(secrets.token_urlsafe(32))'`.
Store it in the hosting platform's secret manager. Hosted mode deliberately
does not read the repository `.env`; startup fails if required settings are
missing. Do not put live values in `.env.example`, shell history, commits, or
the public submission.

## Container and edge

The [Dockerfile](../Dockerfile) copies only application code and the public
offer-fact sheet. It runs as an unprivileged user, exposes port 8765, and checks
`/healthz`. Build with `docker build -t card-atlas-demo .`. Attach a writable,
persistent volume at `/state`; a lost volume loses mock applications. Use **one
replica**: browser sessions, limits, and fixture tokens are in process memory.
For a local container smoke run, put private values in an ignored `.env.hosted`
file (`chmod 600 .env.hosted`), then run:

```bash
docker volume create card-atlas-state
docker run --rm --env-file .env.hosted \
  -p 127.0.0.1:8765:8765 \
  -v card-atlas-state:/state card-atlas-demo
```

Place the service behind HTTPS with a trusted reverse proxy or managed platform
TLS termination. Do not expose the container's bare HTTP port publicly. Enable
edge request/connection limits as well as the in-app caps. The app does not
support trusted proxy headers and does not need to infer a client IP.
For a direct local preview without HTTPS, run the Python server with
`--host 127.0.0.1 --local-http-preview`; that explicit loopback-only option
omits the `Secure` cookie flag so the browser retains the test session. Never
use it for a deployed URL.

The judge-facing app opens without a code and asks the visitor to choose a
fictional demo customer. `/review` shows a sign-in form without exposing queue
data. After the operator enters `ADVISOR_REVIEW_CODE`, the page sends HTTP Basic
username `reviewer` and that code to the protected `/api/review` endpoint.
The code stays only in the page's memory and is cleared on reload. Share it
only with the demo operator and use the queue only behind HTTPS.

Choosing a demo customer is **not** authentication. The public app contains no
source customer records. Within a conversation, the server binds the chosen
fixture; switching requires ending the session and starting a new one. The
separate precheck consent and application confirmation still apply. Real bank
identity verification would require a different service.

## Local smoke check

Use an ignored private env file with the variables above and an absolute
`ADVISOR_DB_PATH` writable by the container user. For a local container, one
option is to mount a host directory as `/state` and bind the HTTP port to
`127.0.0.1` only. Then check:

1. `GET /healthz` returns `ok` without credentials.
2. `GET /`, `/api/state`, and the empty `/review` sign-in shell work without
   credentials. `/api/review` rejects visitors without the reviewer code.
3. Run direct and campaign starts, Spanish and Portuguese, consent and decline,
   and one confirmed mock application. Verify its reference in the queue.
4. Restart the container with the same volume. The application stays in the
   review queue. In-progress browser sessions reset; this is a documented
   single-instance limitation, not a resumed conversation.
5. Check that the deployment image has no CSVs or `.env` and that the browser
   never receives a source customer ID or model API key.

## Capacity and remaining limits

Sessions expire after two hours without a POST action and are capped at 500 in
this one process.
Each session can make 60 API POSTs per ten minutes. At most three answer calls
run concurrently, and the default daily provider-attempt cap is 200 **per process**.
The model request has a 45-second timeout and a 900-token output cap. These
limits control a short judging demo; they are not a currency-denominated budget
and reset on process restart. Set a separate hard account spend limit with the
model provider. Since the public session limit can be bypassed by clearing
cookies, also apply edge/IP rate limits and abuse protection. The service does
not yet resume conversations after restart,
distribute state across replicas, run a true human-assignment tool, or provide
production monitoring/retention controls. The [release plan](release_readiness.md)
tracks the remaining evaluation and operational work.
