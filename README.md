# Credit-product advisor

Public repository: https://github.com/lucasswolff/factored-hackathon-2026-atlas.
The organizer PDFs are excluded from the public repository because a supplied
data dictionary contains participant-only source access credentials. References
to those PDFs in planning documents refer to local participant copies. The
[judge rehearsal](docs/judge_rehearsal_2026-10-02.md) records the latest deployed
workflow and bounded concurrency results.
The [AWS deployment guide](infra/aws/README.md#automatic-code-deployment-from-protected-main)
describes the pull-request test and automatic deployment triggered by a push
to protected `main`.

The deployed project is an AI-assisted **Credit-Product Info & Eligibility Support** demo. A visitor clicks a campaign card tied to a named offer or opens the advisor directly, then chooses a fictional demo customer before asking questions in Spanish or Portuguese. That choice enables profile-based suggestions; it is not real authentication. A card-specific precheck needs separate chat consent. An anonymous income entry does not produce a suggestion. After a separate chat confirmation, the browser can record a **mock application** with verified `PENDING_REVIEW` read-back. For an unanswered question, the advisor offers human review and waits for confirmation. It then stores the same bounded conversation thread, a review packet, and a mock roster assignment for the protected reviewer queue. The advisor does not approve credit or create a real product. The roster is a snapshot, so it does not establish live agent availability or deliver a message to an employee.

## Hosted architecture

![Architecture of the hosted advisor: visitor entry and fixture selection lead to a Lambda-hosted conversation service; Claude classifies fresh intent and answers grounded public questions, while the service controls policy, consent, and verified DynamoDB actions.](docs/architecture.svg)

The [architecture diagram](docs/architecture.svg) shows the deployed AWS path. The browser uses an HTTPS Lambda Function URL. A server-bound session holds the chosen fictional fixture and active card. Claude Haiku classifies fresh chat intent into bounded choices; Claude Sonnet answers many public product questions using a versioned fact sheet. The service handles consent, recommendations, prechecks, application confirmation, and handoff confirmation. DynamoDB stores expiring sessions, the shared model-attempt counter, verified mock applications and handoffs, and the filtered agent roster. A confirmed handoff includes the conversation thread and pauses the bot in that chat. The `/review` page asks for a separate code before loading protected queue data; there is no employee reply interface. The local browser mode uses organizer-data demo personas and SQLite mock actions; it is distinct from the public fictional-fixture deployment.

**Current priority:** evaluate Spanish/Portuguese product answers and prepare submission evidence. The [AWS deployment](infra/aws/README.md) has passed a [judge rehearsal](docs/judge_rehearsal_2026-10-02.md); check its live status before sharing the URL. The local browser advisor remains available with `python3 -m advisor.web` at `http://127.0.0.1:8765/`. Its public-answer default is Sonnet 5 at low effort after a [development latency comparison](plan/conversation_data/latency_model_comparison.md); the deterministic customer and precheck flow stays local. Read the [project plan](docs/project_plan.md), [MVP requirements](docs/mvp_requirements.md), and [AGENTS.md](AGENTS.md) before extending scope.

The six-slide [Atlas presentation](presentation/README.md) includes a real Spanish conversation capture, architecture, data sources, operational checks, and the path from prototype to a customer-facing service.

The [release and evaluation plan](docs/release_readiness.md) maps the organizer
requirements to the remaining evaluation, measurement, and submission work.
The [automated bilingual journey evaluation](docs/automated_evaluation_2026-10-04.md)
compares the browser advisor with a keyword FAQ baseline on a locked fictional
case set and reports action read-back, failures, local latency, and estimated
provider cost. It is agent-authored post-fix regression evidence, not
independent bilingual human validation.
The later [production conversation smoke checks](docs/live_conversation_checks_2026-10-04.md)
cover eight unscripted flow families plus earlier routing, quota, and
one-application regressions. One two-card price comparison failed; these checks
are development evidence, not a new held-out score.

- `docs/factored_docs/`: organizer brief and data dictionaries.
- `docs/mvp_requirements.md`: workflow and demo acceptance criteria.
- `docs/card_catalog_draft.md`: four proposed named cards, the two conversation entry paths, and open offer/policy decisions.
- `docs/project_plan.md`: implementation phases and next steps.
- `docs/credit_marketing_feasibility.md`: what the supplied data can and cannot support.
- `docs/training_data_assessment.md`: candidate learning tasks, label quality, and the current research-first sequence.
- `plan/`: ordered work plan, audited campaign mapping, and country-specific card-offer design draft.
- `plan/conversation_data/`: versioned demo fact sheet, bilingual annotation guide, 24 draft Spanish/Portuguese pilot cases, and a development-only retrieval comparison for the conversation-quality research phase.
- `data/derived/tone_examples_es_pt.json`: 42 distinct transcript reply templates with team-created Portuguese translations for tone study, generated by `analysis/prepare_tone_examples.py`.
- `docs/transaction_dispute_plan.md` and `docs/data_audit.md`: preserved notes from the earlier dispute concept.
- `data/`: supplied local CSVs; the same AWS source has already been loaded into Snowflake.
- `snowflake/`: landing-table setup, load scripts, and the earlier dispute audit worksheet; see its [setup guide](snowflake/README.md).

A/B testing is a later enhancement, after the core conversation, policy, action, and evaluation paths work. Keep credentials out of repository files; the Snowflake SQL retains placeholders.

The earlier synthetic prototype was removed. A [local browser advisor](advisor/README.md) exercises both entry paths, demo-customer selection with 10 allowlisted organizer-data personas, product answers, profile-based suggestions, a [simulated precheck policy](plan/demo_credit_policy.md), confirmed mock applications, and queued human-review handoffs. The public hosted mode uses separate fictional fixtures. Real authentication and live employee handoff remain future service requirements.
