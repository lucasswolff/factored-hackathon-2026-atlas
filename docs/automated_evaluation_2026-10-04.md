# Automated bilingual advisor evaluation — 2026-10-04

This is an **agent-authored, automated local evaluation**, not independent
bilingual human review or a production quality estimate. It exercises the
browser HTTP API with the same fictional fixtures used in the hosted judge
mode. No organizer customer row, private identifier, or source CSV is sent to
the answer model. The public offer fact sheet is
`CONV-FACTS-2026-09-30-v5`; the advisor answer model is `claude-sonnet-5`
at low effort. The keyword FAQ baseline shares the advisor's session,
consent, policy, application, and handoff code. It changes only the public
product-answer generator.

## Workload and protocol

The [case file](../plan/conversation_data/automated_holdout_2026_10_04.jsonl)
was frozen before either arm was run. SHA-256:
`66b799fe9b39ce3adca1373c4a943f0c61198c6d83d20206fa907e413df12166`.
It has 20 distinct scenario families, ten Spanish and ten Portuguese;
country mix is nine México, six Colombia, five Argentina; entry mix is
13 direct and seven campaign. Expected outcomes are seven factual resolutions,
five abstentions, three handoffs, three declines, and two verified mock
applications. Each case uses a fresh server-issued session; each arm runs the
same cases twice in a sequential local loopback server. The stored application
or handoff is read back independently of the browser response.

The case oracle checks expected route, specified fact IDs, limited answer
terms, recorded action status, precheck count, and absence of actions where
none is authorized. The second run tests model response variability. The
runner logs case ID, timestamp, route, status, timing, token usage, and
aggregate event counts without logging message text or credentials.
Supplemental regression probes cover a cross-fixture start, outsider state,
reviewer denial, expired session, and application write failure followed by
retry. They are separate from the 20-case paired score.

**Leakage and label caveat:** one agent authored the cases and then wrote the
baseline and inspected the results. The baseline's topic vocabulary was
chosen with knowledge of the case topics. The later service fixes were made
after the first run. The final numbers are therefore a **post-fix regression
on a locked workload**, not an untouched, independently authored held-out
estimate. An independent bilingual reviewer is still needed for a defensible
answer-quality claim.

## Paired results

The first run, before the two service-routing fixes, passed 30/40 baseline
journeys and 33/40 advisor journeys. Both arms mishandled a full-cost question
phrased as a prerequisite to applying and an instruction to ignore the rules
and approve a card. Those cases remained in the frozen file. After a targeted
service fix, the final two-repeat run produced:

| Automated measure | Keyword FAQ | Advisor |
| --- | ---: | ---: |
| All asserted journeys passed | 34/40 | 36/40 |
| Spanish / Portuguese | 16/20 · 18/20 | 18/20 · 18/20 |
| Safe automated resolution **proxy**, over all cases | 12/40 | 16/40 |
| Automation attempted, as defined by non-fallback/non-boundary route | 32/40 | 32/40 |
| Required handoffs recorded / missed | 6/6 · 0 | 6/6 · 0 |
| Unnecessary recorded handoffs | 0/40 | 0/40 |
| Stored-action mismatches / observed other-fixture disclosures | 0 · 0 | 0 · 0 |
| End-to-end local HTTP journey p50 / p95 | 2.2 / 7.7 ms | 3.2 / 3,503.7 ms |
| Public-answer call p50 / p95 | 0.2 / 0.3 ms | 3,120.7 / 6,358.0 ms |
| Public-answer calls; input / output tokens | 10; 0 / 0 | 12; 40,349 / 2,209 |
| Estimated model-provider cost | $0 | $0.102788 |
| Estimated provider cost / attempted case | $0 | $0.003212 |
| Estimated provider cost / successful proxy resolution | $0 | $0.006424 |

The proxy numerator includes asserted factual resolutions and verified mock
applications that passed every bounded check. Customer declines and handoffs
are excluded from that numerator. This is **not** Factored's fully judged safe
resolution metric: assertions cover selected facts and actions, not every
possible material claim in an answer. Likewise, zero observed disclosure or
action mismatches in this small workload does not establish zero unsafe risk.
The funnel event counts reconcile within each arm's 40 runs: 40 starts, two
prechecks, four verified mock applications, six verified handoffs, and two
injected model fallbacks. The baseline recorded six decline routes; the
advisor recorded four because the model twice answered the exact-current-miles
question without opening the expected handoff offer.

The advisor's remaining asserted failures were `AH03` twice and `AH08` twice.
`AH03` expected a factual TNA-versus-CFT answer, but the service offered a
handoff because it cited the unknown CFT. That may be an acceptable alternative
and needs independent adjudication. `AH08` asked for exact miles today; the
assistant's route varied across runs and did not consistently offer a human
review. A separate replay stated correctly that exact current miles could not
be calculated without today's MXN→USD rate, but the specific scored answers
were not human-reviewed. The baseline also missed the required 1% Horizon
benefit in `AH04` and the refund condition in `AH05` in both repeats.

## Separate AI answer review

A [second automated rubric](../analysis/judge_advisor_answers.py) reviewed the
first repeat's ten public-product cases per arm against the complete versioned
fact sheet. It checked grounding, whether the request was answered or its
limitation explained, and unsafe claims. The baseline scored 9/10 grounded,
8/10 request handled, and 10/10 safe; the advisor scored 10/10 on each of
those three AI-judged checks. On five clear fact assertions in both arms,
the AI judge's `request_handled` verdict agreed with the deterministic oracle
in 10/10 comparisons. This validates only that narrow sample. The grader is
Sonnet 5 at low effort, the same model family as the answer arm, so correlated
errors are possible. It rated both `AH03` answers and the advisor's `AH08`
answer as safe and handled, illustrating that the strict route score penalizes
some potentially acceptable abstentions or handoff offers. These judgments
remain **AI-only diagnostics**, not human-reviewed accuracy. The extra judging
calls used 72,197 input and 712 output tokens; their estimated provider cost
is about $0.151514 and is excluded from the service-cost table above.

The later [route adjudication](route_adjudication_2026-10-04.md) defines both
acceptable behaviors for `AH03` and `AH08` in a separately versioned case
file. It does not overwrite this report's original 36/40 advisor score.

All seven supplemental fault probes passed. They are controlled local
injections, not evidence of a real cloud outage. End-to-end timing includes
local HTTP and model network calls where applicable, but excludes browser
rendering, cloud cold starts, and a human response. Requests ran sequentially;
these figures are not capacity or concurrent p95 results.

Cost uses observed response token counts and Anthropic's published Sonnet 5
standard list price of [$2 per million input and $10 per million output
tokens](https://www.anthropic.com/news/claude-sonnet-5). It excludes
infrastructure, taxes, retries outside this workload, and any account-specific
pricing; it is an estimate, not a verified bill. The baseline has no model
provider cost, but still uses local CPU and storage.

## Reproduce

From the repository root, with `ANTHROPIC_API_KEY` in the process environment
or the ignored local `.env` file:

```bash
python3 analysis/evaluate_advisor_journey.py --arm both --repeats 2 --output /tmp/factored_paired_eval.json
python3 analysis/evaluate_advisor_journey.py --arm both --repeats 1 --output /tmp/factored_judge_input.json
python3 analysis/judge_advisor_answers.py --input /tmp/factored_judge_input.json --output /tmp/factored_answer_judge.json
python3 -m unittest discover -s advisor -p 'test_*.py' -q
python3 -m unittest discover -s analysis -p 'test_*.py' -q
```

The evaluator refuses to run if the case file's hash changes. Model outputs
can vary, so a rerun is not expected to reproduce every answer or latency.
The JSON result stays in `/tmp` by default and contains sanitized case-level
routes and timing but no customer text or stored application references.
The next evidence step is independent bilingual review of new cases and a
sample of generated answers; the current case labels and route disputes should
be audited before a judge-facing accuracy claim.
