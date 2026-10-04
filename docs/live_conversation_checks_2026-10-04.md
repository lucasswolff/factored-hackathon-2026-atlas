# Live conversation checks — 2026-10-04

These are **agent-run production smoke checks**, not an independently authored
held-out evaluation. Each flow used a fresh HTTPS session and a team-generated
fictional demo persona. The offers and policy are synthetic. Routes, source IDs,
pending actions, and stored status were inspected through the browser API. No
organizer customer data, cookies, or application references are published here.
Claude can word another run differently. The older [20-case paired
evaluation](automated_evaluation_2026-10-04.md) predates the model-first router;
its 36/40 advisor score is not a score for this deployed version.

## Eight user-suggested scenarios

| # | Flow and fixture | Observed production result | Check |
| --- | --- | --- | --- |
| 1 | Portuguese, México P08, Summit campaign: ask for benefits and *mensalidade* together. | `ANSWER_FACT` cited `BENEFIT.SUMMIT`, `FEE.MX`, and `FEE.WAIVER`; it stated 2 miles per USD equivalent, 8 lounge visits, USD 75,000 emergency medical coverage, and the MXN 6,000 annual maximum in MXN 500 monthly installments with the waiver rule. | Met |
| 2 | Spanish, Colombia P04: ask Horizon benefits, then the fee of “esta tarjeta.” | Both turns were `ANSWER_FACT`; the selected card remained Horizon and the second answer said it has no annual fee. | Met |
| 3 | Portuguese, Colombia P04: compare Rewards and Summit, then ask for “um mais barato,” then clarify “mais barato que o Summit.” | The service gave alternatives without asking which of the two cards was the reference. The initial comparison omitted Rewards from its cited candidates. The explicit Summit follow-up returned cheaper options. This did **not** meet the ambiguity expectation. A separate Summit campaign probe answered an unnamed cheaper-card request, but a later “mais barato que o Rewards” also included the more expensive Summit. | **Failed** |
| 4 | Spanish, Colombia P04: say you do not want to apply for Horizon, then request it in the next turn. | First turn was `ANSWER_FACT` with no pending action; second turn was `ASK_PRECHECK_CONSENT` for Horizon, with no application stored. | Met |
| 5 | Spanish, Colombia P04, Rewards campaign: ask to apply for another unnamed card, then name Horizon. | `ASK_CARD` came before `ASK_PRECHECK_CONSENT` for Horizon; neither turn created an application. | Met |
| 6 | Portuguese, Colombia P01: self-report student status and no income, then ask for a card suggestion. | `POLICY_SUGGESTION` discussed Campus using the selected fictional profile; it said `Student` is not proof of enrollment, disclosed that the stored income estimate differed from the self-report, and did not approve credit. | Met |
| 7 | Portuguese, Colombia P04: request Horizon, decline the precheck, then separately decline or confirm the mock application in two fresh sessions. | Declining precheck led to `APPLICATION_CONFIRM` with no stored application. A second “não” left no record; a second “sim” stored one `PENDING_REVIEW` mock application with read-back. | Met |
| 8 | Portuguese, Colombia P04: ask to cancel an existing card. | `SERVICE_BOUNDARY` explained that this acquisition chat cannot cancel a held card; no cancellation was initiated. | Met |

**Result:** 7/8 expected behaviors in this small smoke set. The failed price
comparison is an open routing issue, not an unsafe application action. These
cases were written and inspected by the same agent that had worked on routing;
7/8 must not be presented as a general success rate.

## Other checks from the same deployment sequence

| Probe | Evidence and outcome |
| --- | --- |
| Typo after an earlier refusal | After a negated application question, “queiro la tarjeta Horizon” had intermittently become a product answer. After [PR #27](https://github.com/lucasswolff/factored-hackathon-2026-atlas/pull/27), a live repeat reached `ASK_PRECHECK_CONSENT`. The classifier now receives the latest message and active card, without earlier prose. |
| Unnamed application versus recommendation | Before [PR #28](https://github.com/lucasswolff/factored-hackathon-2026-atlas/pull/28), “Quiero solicitar otra tarjeta” after a Rewards answer returned `POLICY_SUGGESTION`. After deployment, that phrase and “Me gustaría pedir una diferente” reached `ASK_CARD`; “¿Qué otra tarjeta me recomiendas?” remained `POLICY_SUGGESTION`. |
| One application per conversation | A live Horizon mock application was stored as `PENDING_REVIEW`. After [PR #30](https://github.com/lucasswolff/factored-hackathon-2026-atlas/pull/30), asking to apply for another card returned `APPLICATION_EXISTS` immediately, with no second precheck or application. Product questions and standalone prechecks may still be requested in that conversation. |
| Daily capacity | A fresh product question returned HTTP 429 when the former 200-attempt shared daily cap was exhausted. After [PR #29](https://github.com/lucasswolff/factored-hackathon-2026-atlas/pull/29) raised the bounded cap to 400 attempts per UTC day, the same kind of question returned HTTP 200. This allows more provider usage and remains an attempt cap rather than a dollar limit. |
| Automated safety paths | The source-data-free advisor suite passed **87 tests** after PR #30. It includes simulated model failure, application write/read-back retry, session expiration, reviewer access denial, and duplicate confirmation. These are controlled local tests, not live AWS outages. |

The current architecture uses a bounded Claude Haiku intent choice before
service routing, then Claude Sonnet for many public fact answers. Consent,
synthetic policy, application creation, and read-back remain service-owned.
Independent bilingual judgment, a new frozen workload for this model-first
version, and broader production latency/cost measurement are still needed.
