# AI-authored conversation challenge, fact snapshot v3

**Status: provisional diagnostic, 2026-09-29.** A fresh Claude Haiku 4.5 request saw the v3 synthetic fact sheet and wrote 24 unlabeled prompts (12 Spanish, 12 Portuguese). It did **not** receive the pilot cases, model answers, or development reports. Codex then labeled the cases before running retrieval or answer generation; hashes in the prompt and frozen-case manifests record that sequence. Claude Sonnet 5 answered the frozen cases. The author and judge were both AI systems, and some scenarios overlap pilot topics. This is **not independently human-written or bilingual-human-judged held-out performance**.

The same 20 cases with retrievable product facts were used for both retrieval methods; four cases were workflow-only. At five ranked passages:

| Method | Hit@1 | Mean recall@5 | MRR | Spanish recall@5 | Portuguese recall@5 |
| --- | ---: | ---: | ---: | ---: | ---: |
| Keyword IDF baseline | 4/20 (20%) | 42.5% | 37.8% | 55% | 30% |
| Pretrained multilingual E5 small | 12/20 (60%) | 85.0% | 73.4% | 90% | 80% |

These are **AI-assigned relevance labels**. E5 missed at least one labeled fact in six cases, notably fee-waiver rules and specific travel limitations. The answer runner supplies `FEE.WAIVER` and `UNKNOWN.TRAVEL` as mandatory context, so its results cannot be attributed solely to E5's top-five retrieval.

Sonnet returned parseable structured answers in **24/24** cases, with no citation ID outside the supplied context. It matched **19/24** frozen primary routes (Spanish 10/12, Portuguese 9/12). Median API latency was 7.90 seconds; p95 nearest-rank latency was 12.44 seconds for this small run. Total recorded usage was 64,318 input and 12,773 output tokens. The five route disagreements were `AIH-001`, `AIH-010`, `AIH-015`, `AIH-016`, and `AIH-023`. A route disagreement is not automatically an unsafe answer: `AIH-001` did give general comparisons and mentioned sign-in, while `AIH-010` refused to bypass consent despite selecting `ASK_PERMISSION` instead of `REFUSE_UNAUTHORIZED`.

Manual AI-only answer review found these more important issues:

| Case | Finding |
| --- | --- |
| `AIH-003` | Explained 70% TNA but omitted that an actual interest charge depends on unpaid balance and payment timing. |
| `AIH-005` | Declined an illustrative 500 USD × 2 miles calculation, saying live FX was needed. The upstream offer rule says a USD purchase uses a 1:1 USD conversion; that detail was missing from the v3 fact passage. This is both a source-pack defect and an unanswered example, not evidence of a real balance. |
| `AIH-011` | Asserted that the draft 36% purchase rate “does not apply the same way” to cash advances. The cash-advance rate is unspecified, so this distinction is unsupported; it should only say the total is unavailable. |
| `AIH-015` | Correctly withheld approval but did not guide the anonymous visitor to trusted sign-in for any personal precheck. |
| `AIH-016` | Claimed Rewards earns one mile per *local-currency* equivalent, contradicting the one-mile-per-USD-equivalent rule. It also failed to ask for the missing processing day and did not correct the misleading prior turn. |
| `AIH-019` | Named Rewards and its two lounge visits even though no card had been selected or mentioned. The named lounge remains unverified; the visit count should wait for card clarification. |
| `AIH-023` | Chose `REFUSE_UNAUTHORIZED` rather than `HANDOFF` for a request about an exception to a linked-refund rule. The answer itself refused to invent recovered miles and offered human review; the primary route label is debatable. |

No raw customer records, AWS credentials, or API key were sent to the author or answer model. This set is useful for finding defects before an MVP, but should be described publicly as an **AI-authored development challenge**, not an independent bilingual benchmark. A future trustworthy evaluation still needs new human-written or at least human-validated cases and human judgments of factual support, language, and safety.

**Post-run source correction:** The current fact snapshot is v4. It restores the upstream rule that a USD purchase needs no FX lookup. A separate one-case v4 development check gave the expected illustrative `500 × 2 = 1,000` Summit miles with a no-real-balance caveat; a separate v4 refund check correctly used the original purchase rate. Neither check changes the v3 challenge counts above. The exact v3 source is archived at [source_pack_v3.md](snapshots/source_pack_v3.md), and the retrieval metrics reproduce against that archive.
