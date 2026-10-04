# Credit advisor

For the local browser experience, run `python3 -m advisor.web` from the repository
root and open `http://127.0.0.1:8765/`. A campaign click or direct visit opens a
“Choose a demo customer” screen. Choosing one of the ten allowlisted customer fixtures
shows location, occupation, segment, score, estimated local-currency monthly
income, an indicative USD equivalent, and current card holding before chat.
For a source-data-free hosted judge build, see the [deployment guide](../docs/deploy.md).
The USD figure uses the latest available **historical** source-table rate and
shows its date; it is not a live conversion. Selecting a fixture enables
profile-based suggestions in this local experience, without a second profile
permission step. Precheck consent remains separate and card-specific. Chat
replies use customer-facing language; the UI keeps the demo and policy
limitations visible outside the chat.
The entry screen lets customers explore Campus in Colombia, México, or
Argentina. Colombia's Campus card uses the selected Colombia-targeted
historical campaign context; México and Argentina open a Campus-focused direct
offer conversation with no campaign ID. The other card tiles use their mapped
campaigns, while “Start without a campaign” opens a general conversation.

For public product questions, Claude receives the latest question, up to six
previous public product-chat turns, language/country/entry/selected-card
context, and relevant card facts. A simple benefits question uses the selected
card's benefit fact; the general lounge-card comparison is answered directly
from the two supporting benefit facts. Customer profile fields, policy outputs,
and private identifiers are excluded from Claude requests. An explicit card
mention updates the active card, so a customer can move from a Horizon campaign
to Rewards. When comparing Rewards and Summit, the browser keeps those two cards
as the active topic for short follow-ups such as “Cuéntame más” or “sí”; the
original Horizon entry card does not silently replace them.

With a model key available, a fresh turn first goes to a small Claude intent
classifier. Its bounded choices distinguish public facts, profile suggestions,
catalog comparisons, application requests, prechecks, existing-card cancellation,
human help, conversation end, and clarification. The model sees only the latest
question, language, country, and active card, never fixture score,
income, or policy output. It does not generate the action reply. The service
validates the choice against the session and handles consent, policy, and
storage. Security boundaries and pending consent/application questions remain
service-owned. On classifier failure in the hosted build, the service stops
before starting an action; the offline CLI retains its legacy local router.
Public product questions can require a Haiku classification followed by a
Sonnet fact answer, using two shared model attempts. This reduces the number
of conversations supported by the hosted daily model-attempt cap until the
route and answer are combined or a separately budgeted classifier is adopted.
The classifier still needs independent bilingual paraphrase evaluation.
"Best card for me" questions use the selected demo fixture's profile. The
service reads it after persona selection and applies the synthetic policy
locally; these answers do not call Claude or send score, income, or policy
outputs to it. A no-suggestion answer identifies the selected fixture and
states the relevant rule, including the score threshold when that is the
reason. If that explanation names Horizon, a subsequent "this card" question
refers to Horizon even when the visitor entered from another card campaign;
the no-suggestion result remains unchanged. A claim to be a student is called
out when the selected fixture does not record the Student segment. This is a
conversation suggestion, not a credit decision. When a
visitor says they have no income but the fixture has a positive estimate, the
answer calls out that difference. An acknowledgement after no automatic
suggestion opens a general card overview. Requests to cancel an existing card
are directed to bank servicing; this acquisition demo cannot cancel a card.
The hosted demo allows 120 POST requests per session in a moving ten-minute
window, alongside a separate shared daily limit of 200 model attempts.

Acquisition intent stays in chat: the advisor asks whether it may
run a card-specific simulated precheck using the selected profile. A typed yes
grants one-use consent and runs the check; a typed no skips it. Either way, the
advisor then asks separately whether to record a mock application for human
review. A typed yes to that second question writes one local
mock application with `PENDING_REVIEW`, reads it back, and displays the verified
reference. The receipt asks whether the customer has another question. A typed
no closes the chat and leaves the receipt visible; a typed yes invites the
question, and a question can be asked directly. Asking about applying or
running a precheck does not write a record.
Asking whether a precheck is mandatory receives an informational answer. An
explicit request to apply without a precheck goes straight to the separate
mock-application confirmation; it does not run a policy check or write a record
until that confirmation is accepted and verified.
Vague replies do not authorize an action, and pending confirmations expire after
ten minutes. The browser no longer needs precheck or application buttons.
Requests that name two cards ask the customer to choose one before a precheck or
application path begins. Ending the conversation clears a pending confirmation
without denying a mock application that was already recorded.
An isolated "quero"/"quiero" after card discussion prompts a short clarification;
after an explicit offer to explain fees or conditions, it instead continues
that product explanation, including offers phrased as a statement rather than
a question. "Conhecer as opções" exits a pending application
choice, and "desejo" confirms only an explicit pending mock-application question.
"gostei, vou querer" proceeds to the consent question without a model call.
Questions such as "eu teria crédito para o Summit?" route to the local,
card-specific precheck consent flow, including after an application for another
card. An unprompted "sim" or "pode prosseguir" asks what the customer means;
it never confirms an action that the server has not offered. Only one card
application can be recorded in a conversation; another request needs a new
conversation. Model-generated claims that an application was sent or a person
was assigned are rejected before display. A customer can request a person in
chat. When source facts cannot establish an answer, the server offers a
handoff and waits for a yes/no reply. After yes, it records a mock roster
assignment with read-back; no employee is contacted. Eligible agents are
Active Digital/Hybrid credit specialists who list the chat language. A
same-country agent is preferred; the selected country is a routing proxy,
not an inferred accent. The customer-facing reply gives the reference and
pending status, and the bot stops replying in that conversation. A verified
handoff stores a reviewer packet: selected fixture and card, authorized profile context, consented
precheck outcomes and policy version, any verified mock application reference,
offer/fact versions, the unresolved question when one prompted review, the
mock agent ID, open review questions, and the conversation thread up to the
customer's confirmation. The thread comes from bounded session history (at
most 50 displayed events), with obvious email/long-number patterns redacted.
It contains no contact fields or raw source rows. The reviewer queue shows
the thread; there is no employee-facing reply tool.
Retrying the same confirmation reuses the record. The SQLite store lives at
`advisor/.local/mock_applications.sqlite` (ignored by Git and mode 0600); it
contains fixture aliases and action metadata, not raw customer records or
financial fields. It never changes the supplied `PRODUCTS` table. No credit
approval or actual application is sent to a bank.
The local `/review` page displays confirmed mock applications and customer
requests for a person, including precheck reason summaries and handoff packets. It is accessible
on the local demo server without reviewer authentication and contains fixture
aliases and synthetic workflow records only. Existing local SQLite files are
migrated automatically; older records may lack reason summaries. No reviewer
action or live human assignment is connected.
In hosted mode the judge-facing app is public and uses fictional fixtures;
`/review` displays a reviewer-code form, while `/api/review` requires that code
before returning queue data. The code stays only in the page's memory. See the
[deployment guide](../docs/deploy.md).

The short consent → precheck → application confirmation sequence uses an
explicit server-side state machine. If the workflow grows to include an actual
human assignment, resumable review, or multiple tool steps, LangGraph can replace
this orchestration layer without letting the language model decide consent or
write outcomes.

The command-line interface below retains its explicit profile-permission step.
If the model key is absent or the model service is unavailable, the browser
keeps local card-selection, precheck, and mock-application chat actions usable;
public product questions return an unavailable-answer fallback.

Run from the repository root after setting `ANTHROPIC_API_KEY` in the process environment:

```bash
python3 -m advisor --language es --country México
python3 -m advisor --language pt --country Colombia --campaign CMP-YYT37NY1CZS7
python3 -m advisor --language es --model claude-haiku-4-5-20251001  # experimental faster model
```

A campaign start uses a historical campaign ID mapped to a team-created card;
a direct start has no campaign. Both use the synthetic
`CONV-FACTS-2026-10-04-v7` fact sheet for public Spanish/Portuguese product
questions. Do not enter personal identifiers or account details. Public
questions and recent public turns go to Anthropic. Customer profile fields,
recommendation rules, and simulated precheck results stay in local code and
are not sent to the model.
The default public-answer model is Sonnet 5 at low effort; Haiku is optional
because its [development comparison](../plan/conversation_data/latency_model_comparison.md)
was faster but less reliable on the current challenge.

To use organizer-supplied synthetic customer records, type `:personas` and
select one permitted fixture with `:persona P05`. Then type
`:profile-consent yes` to allow use of its stored score and estimated
local-currency income. Use `:profile` to see that profile or `:recommend` for
a card suggestion. For an optional simulated precheck, type
`:precheck-consent Horizon`, then `:precheck Horizon`. Consent is card-specific
and consumed once. `:sign-out` clears the test session and permissions. These
aliases are trusted demo fixtures, **not real customer authentication**. A
typed customer ID cannot open a profile. The [versioned synthetic
policy](../plan/demo_credit_policy.md) records the thresholds and ten-record
test.

The first launch builds `advisor/.local/persona_index.json` from the source
CSVs; later launches reuse this small index while source size and modification
time match. It contains ten selected source IDs and current-card flags, is
owner-readable only, and is ignored by Git. It never stores score or income.
Delete the index to rebuild it after replacing the source files. The service
reads a selected customer's financial fields only after test-session selection
and separate profile-use permission.

Real authentication and live human assignment are not connected. The mock
application is available in the browser UI, not the CLI. No precheck result is
an approval. This CLI is for testing, not
final judge deployment. See the [conversation contract](../plan/conversation_contract.md)
for remaining actions and boundaries.

Tests: `python3 -m unittest discover -s advisor -p 'test_*.py'`.
