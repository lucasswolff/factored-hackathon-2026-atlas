# Full fact sheet vs E5 top-five, v4 development comparison

**Status:** AI-authored development diagnostic, not an independently written
or human-judged held-out evaluation. Both modes used the same frozen 24
Spanish/Portuguese challenge cases, Claude Sonnet 5, prompt/schema, and
`CONV-FACTS-2026-09-29-v4`. The model calls ran on 2026-09-29. The frozen case
labels originated against v3, before the v4 USD-mile fact correction. Each
answer still needs independent bilingual review.

| Context mode | Cases / parse errors | Draft route matches | Input tokens | Output tokens | Median / p95 API latency |
| --- | ---: | ---: | ---: | ---: | ---: |
| All 22 facts | 24 / 0 | 18/24 | 86,389 | 12,061 | 5.41 / 12.14 s |
| E5 top-five plus mandatory access/limitation facts | 24 / 0 | 19/24 | 64,733 | 12,656 | 6.59 / 11.60 s |

E5 reduced input tokens by 21,656 (25.1%). These are single, overlapping API
runs, so the latency difference is not a controlled speed result. Route match
does not establish answer correctness; several labels are debatable. The E5
runner always supplied 10 mandatory facts in addition to the retrieved five,
including access rules and key limitations. Thus its answer results cannot be
attributed to retrieval alone. Prompt, model, and source versions are fixed in
[the harness](../../analysis/run_offline_rag.py); raw results are in
[`v4_full_answers.jsonl`](v4_full_answers.jsonl) and
[`v4_e5_answers.jsonl`](v4_e5_answers.jsonl).

Manual spot-check of known failure cases:

- Both modes now calculate the hypothetical USD 500 Summit purchase as 1,000
  miles without claiming a verified account balance (`AIH-005`).
- Both correctly decline an exact cash-advance cost, but both add claims about
  cash advances not earning miles/benefits that are not explicitly established
  by the v4 facts (`AIH-011`). Full context also speculates about how real
  advances *normally* incur fees. This needs a tighter answer contract.
- Both withhold approval for self-declared student status, but neither gives
  the expected trusted-sign-in next step (`AIH-015`).
- Both correct the miles unit to USD equivalent but fail to ask for the exact
  historical processing day and to resolve the ARS/reais ambiguity (`AIH-016`).
- Both decline to verify Ezeiza lounge access. E5 silently chooses Rewards;
  full context lists both card visit counts without asking which card the user
  means (`AIH-019`).

The first text-only service uses all 22 public facts because the sheet is small
and the comparison shows no credible quality advantage for E5 yet. Its
deterministic boundary handles sensitive actions; it does not claim the model's
fact answers are already reliable. Next: tighten unsupported-claim and
clarification checks, obtain independent Spanish/Portuguese judgments, then
compare both modes again on fresh held-out cases before selecting retrieval.

To reproduce after setting `ANTHROPIC_API_KEY` in the process environment, use
the frozen challenge file and distinct fresh output paths:

```bash
python3 analysis/run_offline_rag.py --mode full --cases plan/conversation_data/ai_challenge_cases.jsonl --output /tmp/full-v4.jsonl
python3 analysis/run_offline_rag.py --mode e5 --cases plan/conversation_data/ai_challenge_cases.jsonl --cache-dir /tmp/factored-e5-cache --output /tmp/e5-v4.jsonl
```

E5 requires `analysis/requirements-retrieval.txt`; its weights are downloaded
locally on first use. The two calls incur model API usage and need a configured
key, but no customer CSV or secret is included in a model prompt.
