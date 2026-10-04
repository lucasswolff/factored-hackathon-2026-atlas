# Two routing expectations clarified — 2026-10-04

The first [automated evaluation](automated_evaluation_2026-10-04.md) found two
route mismatches. The actual answers need to be separated from the route labels.
No customer action was created in either case.

## Argentina interest question (`AH03`)

The customer asks whether the proposed **70% TNA** includes **CFT**, the full
financing cost. The [fact sheet](../plan/conversation_data/source_pack.md)
answers the yes/no part: TNA is a nominal annual purchase rate and **does not
include CFT**. The demo lacks the CFT and other charges, so it cannot calculate
a total cost. The advisor gave both facts and offered review. The original
case accepted only `ANSWER_FACT`, so it counted this safe answer as a failure.

**Adjudicated rule:** `ANSWER_FACT` or `OFFER_HANDOFF` is acceptable if the
answer distinguishes TNA from CFT, does not invent a total cost, and cites
`RATE.AR` and `UNKNOWN.COST`. A customer asking for the *actual complete cost*
should receive a review offer; a conceptual TNA-versus-CFT question need not
force a transfer.

## Exact miles from a purchase today (`AH08`)

The customer asks for exact Summit miles on a new MXN purchase. The card's
miles formula is known, but the demo has no live MXN→USD rate for today's
posting date. An exact number would be invented. In one run, the advisor
explained the missing rate and stopped; in another, it explained the same
limit and offered review. The original test required `OFFER_HANDOFF` and
unconditionally sent “não” next. When no offer had been made, that extra
reply became an unrelated new chat turn.

**Adjudicated rule:** `ANSWER_FACT` or `OFFER_HANDOFF` is acceptable if the
answer refuses to give an exact current miles total, explains the missing
live rate, and cites `MILES.HISTORY`. A “no” follow-up is sent only after an
actual handoff offer. A specialist is not presumed to have a live rate that
the demo lacks. The advisor may offer review, but cannot promise that a person
will supply the missing figure.

The original SHA-256-locked [cases](../plan/conversation_data/automated_holdout_2026_10_04.jsonl)
and their scores remain unchanged. The separately frozen
[adjudicated cases](../plan/conversation_data/automated_route_adjudication_2026_10_04.jsonl)
have SHA-256
`a1d39b7a1fa26b4acb4f7326a37fad01079e04edff632387f151ea4da9ef615f`.
With those route alternatives and conditional follow-up, a two-repeat local
regression passed 36/40 keyword FAQ journeys and 40/40 advisor journeys.
Those counts **are post-hoc adjudication on already inspected cases**, not a
new held-out quality result. The original advisor score was 36/40. The two
`AH08` advisor answers in the adjudicated run both stated that an exact number
was unavailable without a live rate; one offered review, and one did not.
No exact miles total was claimed in those two answers.

Reproduce the adjudicated regression with:

```bash
python3 analysis/evaluate_advisor_journey.py --case-version adjudicated --arm both --repeats 2 --output /tmp/factored_route_adjudication.json
```

This clarification changes the **test's accepted behavior**, not the card
terms or the live service. Independent bilingual review is still needed to
confirm that these answers and the route alternatives are natural and useful.
