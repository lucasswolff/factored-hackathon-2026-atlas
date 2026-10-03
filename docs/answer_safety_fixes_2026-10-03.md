# Follow-up to the AI-only answer review — 2026-10-03

The [frozen comparison](../plan/conversation_data/ai_review_2026_10_03_comparison.md)
used a separate offline harness: Claude saw synthetic questions, a fact-sheet
snapshot, and no profile or action tools. OpenAI agents wrote, blindly labeled,
and judged the cases. Its scores are development diagnostics, not human-reviewed
or live-browser accuracy. The answers and labels were kept unchanged after
the work below.

I replayed the reported questions through the browser advisor's conversation
service before editing. The refund-fee question repeated an unconditional
charge claim, and the first-partial-cycle question repeated a contradictory
affirmative opening. The guest, specific medical-coverage, personal-limit,
billing-FX, and Argentina-rate replays were safe in that single run. One safe
run does not guarantee the model will respond the same way again.

| Review cases | Service response after follow-up | Boundary |
| --- | --- | --- |
| AIRO-002, AIRO-017 | Fee/refund and first-partial-cycle questions use fixed conditions and clarify missing card/cycle information; no charge is claimed from pending spend. | `FEE.WAIVER`; no account billing tool |
| AIRO-015, AIRO-007 | Singular guest-quota and missing-card remaining-visit questions use the published same-allowance rule and ask for card/prior usage when needed. | `TRAVEL.RULES` and card benefit facts; no live visit balance |
| AIRO-003 | A question about a specific treatment receives general emergency/exclusion rules and a human-review path without classifying the claim. | No issued policy certificate or verified claim decision |
| AIRO-008, AIRO-014 | A personal credit limit or request to mark Campus approved receives a controlled refusal with the applicable identity, student, and consent limits. | No credit limit or approval service |
| AIRO-012 | The advisor states that a precheck is optional. An explicit request to apply without one skips that step but still requires separate application confirmation and stored read-back. | Local mock application only |
| AIRO-018, AIRO-022 | Billing FX/spread and Argentina TNA/CFT answers state their exact known limits. | No live billing FX, spread, or CFT source |

The model prompt also names these boundaries for related questions. The
server-owned responses are deliberately narrow; other phrasings can still go
to the model. The service does not prove every model claim from a citation,
and the offline harness does not exercise the complete browser workflow.

An observed Portuguese follow-up exposed a separate conversation bug: after
suggesting Summit, a request for a cheaper card repeated the same profile
suggestion. The advisor now compares the lower-fee Rewards and zero-annual-fee
Horizon options using the country-specific offer facts, explains that Summit's
spend threshold is for a monthly fee waiver, and leaves the selected card
unchanged until the customer names another card. Generic requests for another
card receive a factual comparison instead of reusing the profile suggestion.

The advisor suite passed 86 tests and the analysis suite passed 11 after these
changes. The hosted version of this follow-up depends on a successful
protected-main deployment. A new independently human-reviewed bilingual set,
including paraphrases outside these patterns, is still needed before making a
quality or safety claim.
