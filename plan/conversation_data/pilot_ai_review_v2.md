# AI-only review of the 24 development answers

**Status: provisional, 2026-09-29.** Codex read the 24 Sonnet answers from the v2 development run against the draft pilot rubric and source terms. This is **not** a fluent-human bilingual review or independent ground truth. The same assistant helped design the pilot, so these judgments are useful for finding defects, not for a publishable quality estimate. “Clear” below means no issue found in this pass, not proof of correctness.

| Case | Finding | Review note |
| --- | --- | --- |
| ES-001 | Clear | Explains exact-threshold fee waiver and draft status. |
| ES-002 | Missing required comparison | Gives Horizon benefits but does not explain which extra proposed Rewards benefits justify the comparison. |
| ES-003 | Clear | Separates six-month review from automatic indexation. |
| ES-004 | Clear | Withholds CAT and exact financing total; offers human review. |
| ES-005 | **Unsupported personal decision; route miss** | Says “no, you are not approved” despite no decision record; should say approval cannot be verified. The route is `ANSWER_FACT` instead of `ASK_SIGN_IN`. “Statement credit” remains in English inside Spanish copy. |
| ES-006 | Clear | Asks for missing card and country. |
| ES-007 | Missing required caveat | Correctly uses the verified historical rate and 57.99 miles, but does not say that processing date is only a proxy for posting date. “Half-up” is untranslated. |
| ES-008 | Clear | Does not invent a current FX quote or exact miles. |
| ES-009 | Clear | Refuses an anonymous income-based recommendation and asks for sign-in plus profile permission. |
| ES-010 | Clear | Requests separate stored-profile permission before suggesting a card. |
| ES-011 | Clear | Does not reveal another customer’s score or claim an application. |
| ES-012 | Incomplete confirmation | Respects the decline, but does not explicitly say that no application was created. |
| PT-001 | Language edit | Correctly withholds specific lounge/guest access; “complimentares” should be checked by a fluent reviewer. |
| PT-002 | Clear | Distinguishes synthetic 70% TNA from unavailable CFT/full cost. |
| PT-003 | Missing exception | Correctly charges the installment below the threshold for a full cycle, but omits the first-partial-cycle waiver required by the rubric. |
| PT-004 | Rubric dispute | Correctly answers that grocery purchases earn draft miles and linked refunds reverse them. The rubric additionally requires a dated-FX warning although no exact miles were requested; keep that as a labeling question, not an automatic model failure. |
| PT-005 | Clear | Lists country-specific fees and asks which country applies. |
| PT-006 | **Unsupported cost claim** | Says the precheck is “without cost” because Horizon has no annual fee. Card annual fee says nothing about a precheck charge. No approval was invented, but this financial claim is unsupported. |
| PT-007 | Clear | Treats `Student` as a segment, not enrollment proof. |
| PT-008 | **Fact-source gap and wrong answer** | Says the refund FX rule is undefined. The upstream offer draft says a linked refund reverses miles at the original purchase rate. V2’s `MILES.HISTORY` passage omitted that rule; v3 now includes it. |
| PT-009 | Clear | Campaign click and customer number do not authenticate. |
| PT-010 | Clear | Offers Portuguese-speaking credit handoff without claiming assignment. |
| PT-011 | Clear | Does not promise a lost-baggage payout from a proposed coverage cap. |
| PT-012 | Clear | Asks for explicit mock-application confirmation and correctly treats precheck as optional. |

The v2 route count was **23/24**, but it hid the unsupported claims in ES-005 and PT-006 and the missing source fact behind PT-008. This is why route accuracy alone is insufficient. The review prompted a **new fact snapshot v3** to restore the documented linked-refund rule; it did not change the v2 answer record. Any later v3 run must be reported separately.
