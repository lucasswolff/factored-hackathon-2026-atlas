# Project plan: credit-card advisor

**Update, 2026-10-02:** The public repository is published under the Atlas name.
The hosted [judge rehearsal](judge_rehearsal_2026-10-02.md) passed 12/12 entry,
country, and language combinations, with three verified mock applications and
a bounded six-visitor concurrency check. User-supplied conversation examples
now have regression coverage and fixes in the deployed app. Independent
bilingual answer evaluation against a baseline remains open; the existing
AI-authored challenge is development evidence only. Submission slides and
video are still pending.

**Update, 2026-10-03:** The browser service now offers review for unanswered
questions, waits for confirmation, and stores the bounded conversation thread,
structured review packet, and a mock agent assignment from an eligible roster
snapshot. The protected queue shows the packet and assignment. This does not
verify live employee availability or deliver a message to an employee. A new
[AI-only bilingual comparison](../plan/conversation_data/ai_review_2026_10_03_comparison.md)
used 24 frozen AI-authored cases, separately AI-labeled before Claude answered,
and a separate OpenAI answer judge. It found material guest-quota and fee-answer
errors. The advisor now has deterministic answers for the high-impact
fee, guest-quota, coverage, and credit-limit cases and an explicit no-precheck
application path; these changes were made after the frozen evaluation. This is
development evidence, not independent human validation or a full
hosted-journey evaluation. The [answer-safety follow-up](answer_safety_fixes_2026-10-03.md)
records the replay, service boundaries, and remaining limitations. Submission
slides and video remain pending.

**Current priority:** obtain independent bilingual judgments and prepare submission evidence. The [automated paired evaluation](automated_evaluation_2026-10-04.md) now runs a frozen 20-case Spanish/Portuguese workload twice through the browser API against a keyword FAQ baseline, with route/action checks, local end-to-end timing, token-based provider cost, and supplemental fault probes. It is a post-fix automated regression, not independent held-out quality evidence. The [campaign mapping](../plan/campaign_cards.md), [four-card demo catalog](card_catalog_draft.md), and [synthetic policy](../plan/demo_credit_policy.md) are drafted. The UI exposes campaign/direct entry, a “Choose a demo customer” screen, Spanish/Portuguese product chat, suggestions, chat-consented prechecks, chat-confirmed mock applications with verified `PENDING_REVIEW` read-back, and confirmed handoffs with a mock roster assignment. The hosted judge flow is public and uses separate fictional fixtures; the review queue requires a code. Selecting a fixture permits profile use but is not authentication. Independent bilingual judgments, real authentication, and an actual employee-service integration remain open. The user chose conversation quality over campaign-click prediction. The earlier synthetic prototype was removed.

## Scope and evidence

The MVP is a **Credit-Product Info & Eligibility Support** journey with two starts: the judge clicks a supplied campaign card mapped to a named offer, or visits the advisor directly with no campaign context. The click is newly simulated; no historical clicked chat is selected. Both paths lead to “Choose a demo customer” before Spanish or Portuguese chat. Fixture selection enables profile-based suggestions; it is not real authentication. A later separately consented simulated precheck may lead to a customer decline, confirmed mock application, or human handoff. A/B testing follows only after the service works. The earlier dispute proposal is archived in [transaction_dispute_plan.md](transaction_dispute_plan.md).

The [marketing feasibility audit](credit_marketing_feasibility.md) reports 1,746,801 sends and 97,793 clicks in the supplied synthetic dataset. Those figures establish campaign engagement only. Historical click-to-chat attribution is unverified, and `had_conversion` is not a verified product contract. Future offer terms, policy, conversations, and mock applications will be **team-created**, clearly separated from supplied records.

**Agreed data-backed demo:** The local mode uses selected supplied campaign, customer, product, and agent rows, focusing on customers without a credit card; the public hosted mode uses separate fictional customer fixtures and a private, filtered agent-roster snapshot. Map selected generic `Tarjeta Crédito` campaign rows to four clearly team-created named offers; a new UI click creates a new conversation and is not recorded as a historical campaign send click. All three customer countries—Colombia, México, and Argentina—are in scope, so income remains in local currency and recommendation bands/offer terms are country-specific. Local `CUSTOMERS` fields support permitted profile inputs, `PRODUCTS` helps avoid duplicate offers, and `SERVICE_AGENTS` supplies a language- and credit-specialty-matched mock handoff. Offer terms, eligibility rules, new chat, and application records are team-created.

The historical data supports a real backtest of **recorded campaign engagement**, separate from the new UI click. It does not support a historical approval or contract backtest: no approved policy, decision labels, or point-in-time customer feature history is supplied. Replaying historical clicked sends through a new synthetic policy is a retrospective simulation, which must be labeled as such. The public judge demo accepts unscripted chat with fictional customer fixtures and a team-created card mapping; unsupported requests need safe clarification or handoff. The text-only advisor uses an LLM for public free-form questions; versioned offer facts, consent, recommendation/precheck results, and mock actions remain outside the model. Transcript translations are a tone reference, not offer knowledge.

## Next steps

The [release and evaluation plan](release_readiness.md) prioritizes held-out
evidence, submission materials, and a credible scaling path based on the
organizer briefs. The public judge prototype is deployed with fictional
fixtures and a protected reviewer queue; it is not a live banking service.

1. **Review more unscripted journeys.** Capture exact turns, persona, entry path, language, expected behavior, and observed behavior in [conversation review notes](../plan/conversation_review_notes.md). P01/P04/P02 development cases now have fixes and regression tests; keep looking for new failure patterns.
2. **Evaluate answer quality independently.** Obtain new Spanish/Portuguese cases by scenario family, freeze them before tuning, and have a bilingual reviewer judge relevance, grounding, and safe abstention. The existing keyword/E5 comparison and AI-authored cases are development diagnostics only, not held-out performance.
3. **Measure and prepare the demo.** Reconcile new chat starts, prechecks, declines, mock applications, and handoffs; run both entry paths and failure cases in both languages. The review queue records confirmed unanswered-question requests and mock roster assignments; no employee is contacted and no bank integration exists. Decide whether learned retrieval or fine-tuning improves on a baseline only after independently judged cases exist. A/B testing and click prediction remain optional later work.

The [organizer problem statement](factored_docs/problem_statement.pdf) remains the submission source of truth. Historical campaign template comparisons remain descriptive; A/B testing is deferred.
