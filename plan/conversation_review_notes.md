# Browser conversation review notes

These are observed local-demo conversations, not held-out evaluation labels. Keep
the exact customer intent and expected route here while collecting more examples;
do not tune on these cases and then report them as independent test results.

## P04, Colombia, Basic — Horizon application

The customer requested Horizon, consented to a simulated precheck, received
`DOES_NOT_MEET_DEMO_RULES` under policy v1 because the source-fixture score was below the
synthetic Horizon threshold, and chose to request human review. The local mock
application was stored as `PENDING_REVIEW`. When asked whether to register it,
the customer answered “desejo”; the old yes/no parser rejected that clear
affirmation and required “sim”. The router now accepts “desejo” only in the context
of an explicit, card-specific application confirmation. It must not count as
consent to a different action or create a record without that pending question.
Under policy v2, this fixture's score of 541 enters Horizon's 540–559 human-review band.

## P01, Colombia, Student — direct visit, Portuguese

The customer asked for a day-to-day card without fees. The advisor described
Campus and Horizon, then asked whether the customer wanted to know more about a
fee or condition. After the customer said “sou estudante”, it described Campus
and again invited questions about fees or conditions. The next “quero” meant
“yes, tell me more about those terms”. The old router instead asked whether
the customer wanted to apply. The router now expands this follow-up into a
grounded terms question without entering the application path.

The advisor then asked “Você quer solicitar um cartão ou prefere conhecer as
opções?”. The customer chose “conhecer as opções”. The current pending-action
handler treated this as an invalid yes/no reply and kept the application branch
alive; a later “sim” led to card selection for an application. Expected: treat
“conhecer as opções” as the information branch, clear the pending application
intent, and leave later affirmations unable to authorize an application without
a new explicit proposal. This branch now returns a card overview and clears the
pending action.

Also review two answer-quality details in this case: “sem taxas” is broader
than “sem anuidade”, so the answer should distinguish annual fee from purchase
interest and other unavailable charges; and “Campus é a opção ideal” is too
strong when student enrollment is not verified by the supplied segment or chat
claim. The advisor may discuss Campus as a possible fit while preserving the
enrollment check.

## P08/P10, México — product-answer routing

P08 selected Campus and asked “qual a taxa do cartão?”. P10 selected Summit,
asked “quais os beneficios? ele da acesso a sala VIP?”, then “Me fale sobre o
Summit”. The first and third questions received the generic action-boundary
reply instead of product information. That reply is emitted only when the
model's answer trips the unverified-action guard; the exact rejected model
answers from these browser sessions were not retained. A local replay produced
grounded product answers, so this appears intermittent. The service now retries
once with a stricter product-only instruction and still blocks a second unsafe
answer. This is a development mitigation, not evidence of reliable quality.

The combined Summit benefits/lounge question also hit a deterministic routing
error: “quais” in “quais os benefícios” triggered the shortcut for “which cards
offer a lounge?”, returning a Rewards/Summit comparison instead of describing
Summit. The shortcut now requires an explicit “which card(s)” question; a
selected-card benefits question uses that card's benefit fact and the relevant
travel-access unknowns. Regression tests and one live model replay cover this
case. Continue checking broad questions and follow-ups in both languages.

## P02, México, Student — Campus precheck policy review

The customer explored Campus and consented to a simulated precheck. P02 has a
stored score of 539; the original synthetic Campus minimum was 540. Its positive
stored income satisfies Campus's no-minimum-income rule, and the `Student`
segment is present but does not verify enrollment. Thus the original v1 policy
returned `DOES_NOT_MEET_DEMO_RULES` solely for one score point. This was expected
from the code but may be too rigid for the intended student-card journey.

**Implemented in policy v2:** make Campus a conversation
option for `Student`-segment profiles with usable data, and route a low score
to `REVIEW_REQUIRED` rather than suggesting an automated denial. Campus still
requires human enrollment review and never receives automated approval. For
Horizon, introduce a 540–559 score review band when its country-specific income
floor is met; scores at 560+ keep the current numeric result and scores below
540 retain the below-rule result. This moves P04 (score 541) to review.
These numbers are team-created demo policy, not thresholds learned from credit
outcomes. The policy version, fixture outcomes, and tests were updated together.

## Implemented local fixes and remaining review

Short replies now use the prior assistant turn when it asks about product terms.
The informational branch and a context-specific “desejo” application confirmation
have regression tests. An explicit request for a person is stored with read-back;
the local `/review` queue shows mock applications and human requests with reasons.
It does not assign or contact an employee.

Continue unscripted Spanish/Portuguese testing, especially the broad “no fees”
question and student-card wording. The prompt now distinguishes no annual fee
from no fees and avoids calling Campus ideal merely because of a student claim,
but these answer-quality changes are not independently judged. Collect new
held-out cases before claiming measured conversation quality.

## Later browser examples: application, travel, and comparison context

In a Portuguese Horizon chat, “ok vou querer esse” reached the product-answer
model, which repeatedly asked for application confirmation without a server-side
pending action. The explicit “Quero solicitar este cartão” finally entered the
correct precheck and mock-application flow. The router now recognizes the
colloquial first phrase as application intent and goes directly to the local
card-specific precheck consent question. The model prompt also bars it from
collecting its own application confirmation.

In a Spanish Rewards/Summit comparison that began from Horizon, “Cuéntame más”
and later “sí” eventually fell back to Horizon because the entry card remained
selected even while the active topic was two other cards. The browser now tracks
the pair being compared separately from the entry card. Short follow-ups ask
about both cards' benefits or exact fees/rates as appropriate; an explicit card
mention replaces that topic. Regression tests cover the three-turn follow-up.

The user asked for more concrete Rewards/Summit travel terms while leaving
partner names unspecified. [The offer draft](card_offer_terms.md) now defines
visit counting, guest use, rollover, participating-lounge capacity, covered
emergency medical expenses, trip payment/duration, exclusions, and claim
documents. Named lounge network, insurer, policy certificate, claims channel,
geographic exclusions, and effective coverage status remain unresolved. These
are team-created terms, not supplied organizer facts. The advisor can explain
the defined general rules and still avoids promising a particular lounge or
claim. The visible model-name badge was removed from the chat header.
