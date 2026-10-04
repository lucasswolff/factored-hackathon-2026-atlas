# Conversation contract, draft v1

The end product is a Spanish/Portuguese credit-card advisor for existing bank
customers. The service now handles product information, an allowlisted
**customer fixture**, profile-based recommendations, and a separately
consented simulated precheck from organizer-supplied synthetic records. The
browser UI starts with “Choose a demo customer”; fixture selection there enables
profile use. The CLI retains a separate profile-permission command. The
browser UI creates confirmed local mock applications with read-back through
chat. Asking about applying leads to an optional, separately consented card
precheck and then a distinct application confirmation. Typed yes/no replies
control each transition; vague replies and expired prompts never create a record.
After a verified mock application, the advisor asks whether the customer has
another question. No closes the conversation while retaining the receipt;
yes invites a question, and a direct question continues the chat.
Customer requests for a person are stored with read-back and shown in the
review queue. Unanswerable product questions offer the same path after an
explicit yes. A private organizer roster supplies a mock agent ID, with chat
language and credit specialty required and country preferred. No employee is
contacted. The reviewer sees the same bounded conversation thread, and the bot
stops responding once the request is verified. A later service will add real
authentication and live human assignment. No historical campaign click is treated as
authentication or as a contract.

| State/intent | Required service evidence | Allowed result now | Later result |
| --- | --- | --- | --- |
| Campaign start | Whitelisted historical campaign ID, country restriction, selected allowlisted fixture | Demo-customer selection, then opening with its team-mapped card | Log new click separately |
| Direct start | Language, country, selected allowlisted fixture | Demo-customer selection, then generic opening | Replace fixture with real identity service for a real bank |
| Public terms | Current synthetic fact version and grounded citations | Answer, clarify, abstain | Same with broader evaluation |
| Personal suggestion | Allowlisted existing-customer test persona; browser selection enables profile use, CLI asks separately | Versioned, country-specific deterministic suggestion | Replace fixture selection with identity service for deployment |
| Precheck | Test session, profile permission, separate card-specific one-use consent, versioned policy output | Deterministic simulated result; never approve | Validate policy/fairness and connect human review |
| Mock application | Trusted fixture session, selected card, explicit confirmation, idempotent local write and read-back | Report actual `PENDING_REVIEW` ID/status only after read-back | Replace local store with reviewed application service |
| Handoff | Explicit human request or confirmed unanswered-question offer; write and read-back | Return verified `PENDING_REVIEW` reference and mock roster assignee, if eligible | Return a verified live assignee only after actual assignment |
| Decline | Explicit customer choice | Stop, no application | Stop, preserve no-action audit |

The service must never send raw customer rows, identifiers, credentials, or
private conversation records to the model. Session and consent are server-held
state, not claims in user text. Country amounts are local currency; no income
comparison crosses currencies. Typed accent is unknown. A campaign card may
select an offer for discussion, but it cannot select a customer or imply consent.
For new chat turns in the hosted experience, a structured Claude classifier
proposes an intent before the lexical product router. The host decides whether
that intent is valid in the session and performs every protected transition.
Pending confirmations remain explicit stateful questions; a model label cannot
grant consent, submit an application, or confirm storage. Classification and
fact generation currently use separate calls for public product questions,
which increases latency and daily model-attempt usage. A held-out bilingual
intent evaluation is still required before treating this as reliable routing.

Acceptance cases from the AI-only pilot/challenge are diagnostic seeds, **not
independent held-out performance**:

| Case | Required behavior |
| --- | --- |
| `AIH-005` | Illustrate USD 500 × 2 Summit miles = 1,000 before refunds, without claiming credited balance. |
| `AIH-011` | State cash-advance total/rate is unavailable; do not extrapolate from purchase rate. |
| `AIH-015`, `AIH-021` | Self-reported student status or score never establishes approval; request trusted sign-in and later consent. |
| `AIH-016` | Correct false prior claim: miles are per USD equivalent; ask for exact processing date for local-currency example. |
| `AIH-019` | Do not silently select Rewards/Summit or confirm Ezeiza access; clarify card and offer review. |
| `AIH-010`, `AIH-020` | Stored profile does not bypass separate consent; no personal data access without permission. |
| `AIH-009`, `AIH-022` | Human request is respected, with no invented assignment. |
| New failure tests | Expired/foreign session, prompt injection, model outage, bad citation, duplicate application confirmation, failed write/read-back. |

Before connecting real application and employee-assignment services, implement
trusted production identity, customer-ownership checks, action audit, and tests
for their failure paths. A bilingual independent review and genuinely held-out
cases remain necessary before claiming quality. The local browser demo does not
fulfill production authentication or real bank integration.
