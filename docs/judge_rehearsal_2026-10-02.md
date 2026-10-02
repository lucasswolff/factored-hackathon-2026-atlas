# Judge rehearsal and bounded concurrency check — 2026-10-02

The public AWS Lambda judge app was tested at its HTTPS Function URL after the
conversation fixes were deployed. All personas in this run were fictional,
team-generated fixtures. The offer and precheck policy are synthetic. No real
credit decision or bank application was created.

Run `ADVISOR_JUDGE_URL=<judge URL> python3 analysis/rehearse_judge.py` to repeat
the core matrix. Setting `ADVISOR_REVIEW_CODE` in the process environment also
checks the protected queue. The script prints aggregates only; it does not log
cookies or application references. Repeating the run creates three more mock
applications in the reviewer queue.

| Check | Result |
| --- | ---: |
| Campaign/direct × Colombia/México/Argentina × Spanish/Portuguese | 12/12 passed |
| Card-specific precheck consent and stored precheck result | 12/12 |
| Confirmed mock applications with `PENDING_REVIEW` read-back | 3/3 |
| Confirmed references present in reviewer queue | 3/3 |
| Unauthenticated reviewer-queue request | HTTP 401 |
| New visitor sees another visitor's conversation | No |
| Matrix request latency, median / p95 | 450.5 / 479.1 ms |
| Six concurrent visitors, four requests each | 24/24 HTTP 200 |
| Concurrent request latency, median / p95 | 454.6 / 1553.5 ms |
| Concurrent HTTP errors / HTTP 429 throttles | 0 / 0 |

The parallel run used deterministic start, intent, decline, and confirmation
paths. It did **not** measure concurrent Claude calls, cold-start variance,
long-duration throughput, peak capacity, or cost. The account's regional Lambda
concurrency quota is ten. These 24 requests are a small judge-workload check,
not a capacity claim.

Two supplied conversation failures were replayed against the live app. After
a declined Rewards precheck in Portuguese, asking for another card returned a
Horizon profile suggestion and cleared the pending Rewards application. After
a Summit precheck in Spanish, a benefits question was answered; asking for a
recommendation selected Horizon, and “Quiero solicitar esta tarjeta” began a
new Horizon-specific consent step. Neither replay recorded an application.
Local P06 and hosted P06 have different fixture values: the source-backed local
P06 lacks a credit score and gets `REVIEW_REQUIRED`; the fictional hosted P06
has numeric values below Summit's synthetic thresholds. Missing-data results
now identify the missing field, state that the simulation cannot determine
whether thresholds are met, and say there is no preapproval.

The local fault-injection suite covers model failure, action write/read-back
failure, expired sessions, and duplicate confirmation recovery. See
`advisor/test_lambda_app.py` and `advisor/test_hosted.py`; these are controlled
tests, not live AWS outages. `python3 -m unittest discover -s advisor -p
'test_*.py' -q` passed 74 tests after the fixes.

The existing [AI-authored challenge](../plan/conversation_data/ai_challenge_report.md)
compares keyword retrieval with pretrained multilingual E5 on the same 20
relevance-labeled cases (mean recall@5: 42.5% versus 85.0%). It is a
development diagnostic, not an independent held-out advisor-versus-baseline
answer evaluation. The same report documents Sonnet's 19/24 frozen route
agreement and answer failures. An independent bilingual reviewer still needs
to judge a newly frozen case set and compare baseline and full advisor answers
before final quality claims or submission slides use a success rate.
