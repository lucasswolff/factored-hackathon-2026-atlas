# Text advisor latency and model choice, development check

**Date:** 2026-09-29. These are small, sequential API measurements on
AI-authored development prompts, not a controlled production latency study or
an independently judged bilingual quality score. No organizer customer rows
or secrets were sent in model prompts.

## Data-access timing

The original startup scan of `products.csv` and `customers.csv` took a median
**1.60 s** across three local starts. An authorized profile read for these
early selected records was below the timing printout's millisecond resolution.
The advisor now creates an owner-only, Git-ignored index containing the ten
selected source IDs and card flags. Five warm starts took **0.03–0.10 ms**
(median 0.04 ms) in this environment. A cold start still scans and builds the
index; changed source file size/mtime invalidates it. No score or income is
read at startup or stored in the index. Static type annotations help validate
the data contract, but do not replace an index or reduce CSV scan cost.

## Model comparison

All three runs used the same 24 frozen AI-authored Spanish/Portuguese cases and
the full v4 synthetic fact sheet. Sonnet high is the earlier default run;
Sonnet low uses `output_config.effort=low`; Haiku is the pinned
`claude-haiku-4-5-20251001` snapshot. Route labels are AI-assigned and some
are debatable.

| Model setting | Parsed | Draft route matches | Median latency | p95 latency | Output tokens |
| --- | ---: | ---: | ---: | ---: | ---: |
| Sonnet 5, default/high | 24/24 | 18/24 | 5.41 s | 12.14 s | 12,061 |
| Sonnet 5, low effort | 24/24 | 18/24 | 4.02 s | 7.35 s | 7,473 |
| Haiku 4.5 | 24/24 | 12/24 | 3.00 s | 4.70 s | 4,421 |

These runs used different model tokenizers and produced different answer
lengths, so the latency differences cannot be assigned solely to model size
or effort. Haiku's faster run missed the USD 500 × 2 miles illustration and
several human-review routes. The low-effort Sonnet run preserved the route
count but made a false local-currency miles-unit claim in one case. Targeted
prompt changes then corrected that case and asked for its missing processing
day in a three-case follow-up; this does not revalidate all 24 answers. Other
unsupported claims remain possible. The raw [Haiku
run](v4_haiku_full_answers.jsonl), [low-effort Sonnet
run](v4_sonnet_low_answers.jsonl), and [targeted
follow-up](v4_sonnet_low_targeted_answers.jsonl) are retained for review.

The advisor now defaults to **Sonnet 5 at low effort** for public free-form
questions and asks for concise replies. Haiku is available through
`python3 -m advisor --language es --model claude-haiku-4-5-20251001` for
testing, but is not the default. Profile recommendations, simulated prechecks,
consent responses, and cash-advance-cost limitations use local deterministic
code and avoid a model call. A two-question smoke test of the revised live
advisor gave Sonnet 7.05/3.99 s and Haiku 4.58/2.70 s; those four calls are too
few to estimate p95 latency or answer quality.

The next evaluation should use independently written and reviewed bilingual
questions, repeat model runs, and measure end-to-end latency and error rates
before choosing a faster default or another provider. OpenAI and Google both
offer faster-oriented models, but this repository has no configured keys or
same-case measurements for those APIs yet. See the official
[Anthropic model comparison](https://platform.claude.com/docs/en/models/overview),
[Anthropic effort guidance](https://platform.claude.com/docs/en/build-with-claude/effort),
[OpenAI model selection](https://developers.openai.com/api/docs/guides/model-selection),
and [Gemini models](https://ai.google.dev/gemini-api/docs/models) for current
provider capabilities rather than inferring performance from names alone.
