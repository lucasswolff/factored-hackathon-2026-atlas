# Release and evaluation plan

The organizer asks for a **deployed, working prototype**, not a live bank. The
[kickoff](factored_docs/datathon_kickoff.pdf) (pages 10–15, 18, 20) calls for a
focused end-to-end workflow, Spanish and Portuguese, verified actions, a public
repository link, a deployed-tool link, 4–6 slides, and a short video pitch. The
[problem statement](factored_docs/problem_statement.pdf) (pages 2–6) asks for
data-backed problem selection, a baseline against the proposed system on the
same held-out workload, controlled automation, human escalation, and evidence
of operational readiness. It explicitly says the ten-day submission is **not**
expected to operate a live banking service.

Our focused workflow remains credit-product information and simulated
eligibility. The local browser app demonstrates campaign/direct entry,
Spanish/Portuguese product conversation, fixture-based suggestions, consented
precheck, and verified mock-application read-back. A separate [AWS judge
deployment](../infra/aws/README.md) is now public over HTTPS with team-written
fictional fixtures, a protected reviewer queue, expiring DynamoDB sessions,
shared daily model-attempt limits, and durable mock actions. It passed the
[12-combination judge rehearsal](judge_rehearsal_2026-10-02.md) and a small
six-visitor concurrency check, but still needs independent conversation
evaluation. The current regional Lambda concurrency quota is ten; peak
capacity has not been load-tested. The [single-container
option](deploy.md) remains documented separately and retains per-process limits
and SQLite storage.

The Lambda adapter's local fault-injection suite covers the key failure paths
without disrupting the public URL. A simulated model outage returns a safe
`FALLBACK` and creates no action. An application write failure returns 503 with
an unverified outcome; retrying the same confirmation creates one record. An
expired session cannot confirm its draft. Repeating the confirmation, including
an extra chat `sí`, leaves one stored application. If the action was committed
but its read-back or subsequent session save failed, retrying finds that same
record and reference. These are controlled simulations, not live AWS outages.

The [2026-10-04 automated paired evaluation](automated_evaluation_2026-10-04.md)
adds a locked 20-case bilingual browser workload, a keyword FAQ baseline,
verified action read-back, local end-to-end latency, token-based provider cost,
and supplemental access/storage fault probes. Its cases and labels were
agent-authored, and a safety fix followed the first run. Treat the final
numbers as a post-fix regression, not independent held-out quality evidence.
The next gate remains independent bilingual review of new cases and answers.

## Priority 0 — make a judge-accessible prototype safely

1. **Choose the data boundary.** Confirm the organizer's data-use terms before
   hosting. Keep source CSVs, customer IDs, contact fields, and credentials out
   of the public repository and browser responses. Prefer a small, sanitized,
   synthetic deployment fixture derived from the ten scenarios; retain source
   rows only in the private local/Snowflake environment. Label generated
   fixtures and synthetic offer/policy data in the UI and documentation.
2. **Keep the public fixture boundary explicit.** The judge chooses a fictional
   demo customer, then an expiring server session binds that fixture for the
   conversation. Switching requires ending that test session. This is a
   scenario selector, not bank authentication. Keep separate precheck consent
   and application confirmation; a real customer deployment needs an identity
   service.
3. **Protect operations.** The `/review` shell may load publicly, but
   `/api/review` must require the separate reviewer code before returning any
   queue data. Keep the reviewer view separate from customer sessions. Bound
   public and per-session request rate, concurrent Claude
   calls, session count/lifetime, and total demo spend; return a safe fallback
   when limits or the model API fail. Never expose API keys to the browser.
4. **Deploy one reproducible instance.** Package the Python service with pinned
   dependencies, a health check, TLS at the edge, environment-managed secrets,
   and a persistent application store. Start with a single instance and a
   managed persistent database or volume; do not claim horizontal scaling while
   session state remains in memory. Provide a deployment README and perform a
   clean deployment from the public commit.
5. **Smoke-test the actual URL.** Verify both entry paths, all three countries,
   Spanish and Portuguese, consent, decline, application read-back, handoff,
   restart recovery, and access denial for another fixture and the reviewer
   route. Test from a fresh browser with only the instructions a judge receives.

Release gate: a judge can open the URL and finish the core journeys; a visitor
cannot view another fixture's active conversation, the review queue, or any
source record; a model or
storage failure produces no false success claim. The judge-facing app must
   still state outside the chat that offers, policy, and applications are
   simulated. Do not connect actual lending, live employee assignment, or bank writes.

## Priority 1 — prove the system works

1. **Review the operational handoff.** For an unanswered question, the advisor
   offers a human review and waits for customer confirmation. A confirmed
   handoff stores the same bounded conversation thread, selected card,
   permitted profile context, offer/policy versions, consented precheck results,
   verified application outcome, and open questions. It records a mock agent
   assignment selected from a filtered roster snapshot: active Digital/Hybrid
   credit specialists matching the chat language, with the same country
   preferred when available. The protected hosted reviewer can inspect the
   packet and assignment; the bot pauses that conversation. Roster status does
   not verify live availability, no employee is contacted, and there is no
   employee reply interface. Validate this flow with final judge cases and
   describe it as queued review.
2. **Freeze a held-out workload.** Use new Spanish and Portuguese cases covering
   normal, ambiguous, decline, missing data, borderline, cross-customer,
   expired session, prompt injection, and model/storage failure. Keep tuning
   cases separate. Have a bilingual reviewer label at least a sample and audit
   AI-assisted labels against the written rubric. Compare the same cases with a
   simple baseline and the advisor; include failures and repeated-run variance
   where model behavior matters.
3. **Measure rather than infer.** Instrument sanitized event IDs and timestamps
   for starts, questions, policy calls, consent, confirmations, verified
   applications, handoffs, failures, and model usage. Report safe automated
   resolution separately from containment, attempted automation, unsafe
   outcomes with denominators, missed/unnecessary handoffs, p50/p95 latency,
   and cost per attempted case and successful resolution. Break out language
   and authorized segments, with small-sample caveats. Reconcile the demo
   funnel to stored events; do not describe retrospective simulations as
   production lift.
4. **Make data preparation repeatable.** Record source-to-fixture lineage,
   schema/quality checks, offer and policy versions, freshness rules, and a
   fixture update test. Keep the supplied campaign click history distinct from
   new demo clicks and mock applications.

Evidence gate: a reviewer can rerun preparation and evaluation from documented
commands and see the baseline, case mix, failures, cost, and limitations.

## Priority 2 — credible scale and reliability story

Load-test a stated judge workload first (for example, concurrent short chats)
and set an explicit response-time and spend budget. Then move server-side
sessions to a shared store if multiple replicas are needed, use a durable
database for idempotent applications and handoffs, and apply global rather than
per-process rate/concurrency limits. Add timeouts, bounded retries for safe
read-only calls, circuit-breaking/fallback for model outages, monitoring for
latency/error/spend, backups, and a retention/deletion policy. Do not add a
queue, streaming pipeline, or multiple agents solely to claim scalability; the
organizer explicitly makes those optional.

## Submission checklist

- Public GitHub repository with the required `factored-hackathon-2026-...`
  naming, documented setup, no restricted data or secrets, and a reproducible
  evaluation command.
- Reachable deployed-tool link with judge access instructions and a tested
  health check.
- 4–6 slides: problem/data evidence, workflow and controls, architecture,
  baseline/evaluation with failures, and limits/route to operation.
- Short video demonstrating normal, ambiguous, and human-required paths in
  Spanish and Portuguese, with the mock action verified on screen.
- Send the deliverables to the organizer address listed on kickoff page 18.

Before claiming production readiness, real authentication, approved product
terms and credit policy, verified human assignment, privacy/legal review,
security testing, and operational support remain necessary. The submission can
be strong without claiming those pieces already exist.
