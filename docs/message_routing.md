# What happens when a customer sends a message

This is the hosted `/api/chat` flow. The [architecture diagram](architecture.svg)
shows components; this page shows **routing decisions**. The browser first has
to start a session and select one of the fictional demo customers. The service
keeps that selection, the active card, pending questions, and any stored mock
application. A typed message or campaign link cannot grant consent by itself.

```mermaid
flowchart TD
    A["Customer sends /api/chat"] --> B{"Valid session, input and rate limits?"}
    B -- No --> X["Reject request; no action"]
    B -- Yes --> C{"Direct human request?"}
    C -- Yes --> H["Service writes and reads back a mock handoff"]
    C -- No --> D{"Pending card choice or yes/no question?"}
    D -- Yes --> P["Service checks the pending action, expiry and reply"]
    P --> PA["Answer, precheck with consent, or confirmed action"]
    D -- No --> E{"Safety boundary or exact catalog rule?"}
    E -- Yes --> R["Service answers, clarifies or declines the request"]
    E -- No --> F["Haiku chooses a bounded intent from the latest message"]
    F --> G{"Intent?"}
    G -- Public fact --> Q["Exact service rule or Sonnet answer from public facts"]
    G -- Recommend --> I["Deterministic suggestion from selected fixture"]
    G -- Compare --> J["Service compares versioned offer terms"]
    G -- Apply or precheck --> K["Choose card, then follow action flow below"]
    G -- Cancel held card --> N["Explain this acquisition chat cannot cancel it"]
    G -- Human, end or unclear --> O["Offer review, end, or ask a clarifying question"]
    F -. Model or quota failure .-> Z["Safe fallback; no new action"]
    Q --> U{"Answer unresolved?"}
    U -- Yes --> V["Offer human review; write only after customer agrees"]
    U -- No --> W["Return grounded answer and source IDs"]
```

Haiku returns a structured choice from `PUBLIC_FACT`, `RECOMMEND`, `COMPARE`,
`APPLY`, `PRECHECK`, `CANCEL_EXISTING`, `HUMAN`, `END`, or `CLARIFY`, plus a card
reference and comparison preferences. It sees the latest message, chat
language, country, and selected card. It does **not** receive the fictional
customer's score, income, or policy result. A model choice proposes a route;
the service decides what is permitted in the session. Some exact catalog facts
and safety boundaries are handled before classification. The offline CLI has
a legacy local router when no model key is configured.

## Application and precheck branch

```mermaid
flowchart TD
    A["APPLY or PRECHECK intent"] --> B{"Card identified?"}
    B -- No --> C["Ask which card; wait for a named card"]
    C --> B
    B -- Yes --> D{"APPLY and application already recorded here?"}
    D -- Yes --> E["Same card: read back; different card: start a new conversation"]
    D -- No --> F{"APPLY request explicitly skips optional precheck?"}
    F -- No --> G["Ask for card-specific precheck consent"]
    G --> H{"Customer answers yes?"}
    H -- Yes --> I["Run deterministic synthetic policy with selected fixture"]
    H -- No --> J["No precheck runs"]
    F -- Yes --> J
    I --> K{"Was this an application request?"}
    J --> K
    K -- No --> L["Return precheck outcome or decline; no application"]
    K -- Yes --> M["Ask separate application confirmation"]
    M --> N{"Customer confirms?"}
    N -- No --> O["No application is written"]
    N -- Yes --> P["Idempotent mock write, then read back stored result"]
    P --> Q["Return reference and PENDING_REVIEW only after verification"]
    P -. Write or read-back uncertain .-> R["Report uncertainty; retry same request, no false success"]
```

A standalone `PRECHECK` request ends after its consented policy result. For an
`APPLY` request, declining the optional precheck still leads to a **separate**
application confirmation. A second application for a different card requires
a new conversation; product questions and standalone prechecks can continue.
The synthetic policy never approves credit.

The current router can still make mistakes. In the [4 October live
checks](live_conversation_checks_2026-10-04.md), a cheaper-card request after
discussing two cards did not reliably clarify the price reference. The tree
describes the service's control flow, not a guarantee that every model intent
choice or product answer is correct.

Implementation: [browser service](../advisor/web.py), [intent and answer
service](../advisor/service.py), [synthetic policy](../advisor/session.py), and
[mock-action storage](../advisor/aws_state.py).
