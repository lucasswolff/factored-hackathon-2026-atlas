# Conversation-data pilot

**Status: development evaluation, 2026-09-29.** This folder holds Spanish and Portuguese conversation diagnostics. It is **not** a trained model, an independently judged test set, or an active offer. A separate [anonymous text-only advisor](../../advisor/README.md) now exercises public offer questions. The four cards and the offer facts are team-created; organizer data supplies campaign/customer context but no reliable product-question labels or card terms.

| File | Purpose |
| --- | --- |
| [source_pack.md](source_pack.md) | Current evaluation snapshot `CONV-FACTS-2026-09-29-v4` with fact IDs, provenance, answerable claims, and explicit unknowns. Earlier v2/v3 reports retain their original versions. |
| [annotation_guide.md](annotation_guide.md) | Case schema, route/relevance labels, judging rubric, review procedure, and split rules. |
| [pilot_cases.jsonl](pilot_cases.jsonl) | Team-written Spanish/Portuguese draft scenarios for a bilingual reviewer to correct and extend. |
| [dev_retrieval_report.md](dev_retrieval_report.md) | Keyword versus local pretrained multilingual E5 development comparison, with limitations and reproduction steps. |
| [dev_retrieval_results.json](dev_retrieval_results.json) | Aggregate scores and per-case ranked fact IDs/misses from that run. |
| [dev_answer_report.md](dev_answer_report.md) | Claude Sonnet development answer check and unresolved route/evidence issues. |
| [dev_retrieval_results_v2.json](dev_retrieval_results_v2.json) | Retrieval rerun after the v2 fact/route clarification. |
| [dev_answer_report_v2.md](dev_answer_report_v2.md) | Updated Sonnet development check after the two evidence/route fixes. |
| [pilot_ai_review_v2.md](pilot_ai_review_v2.md) | Codex's provisional Spanish/Portuguese answer review, including unsupported claims. |
| [ai_challenge_report.md](ai_challenge_report.md) | AI-authored and AI-judged 24-case diagnostic comparison; not an independent human benchmark. |
| [latency_model_comparison.md](latency_model_comparison.md) | Warm-start cache timing and Sonnet-high, Sonnet-low, Haiku latency/quality diagnostic. |
| [v4_context_comparison.md](v4_context_comparison.md) | Same-case full-fact-sheet versus E5 answer comparison on the v4 source, with known failure examples. |
| [snapshots/source_pack_v3.md](snapshots/source_pack_v3.md) | Exact fact snapshot used to author and score the AI challenge before the later USD-rule correction. |
| [heldout_author_brief.md](heldout_author_brief.md) | Instructions for a different writer and bilingual reviewer to create a leakage-resistant final test set. |
| [ai_review_2026_10_03_comparison.md](ai_review_2026_10_03_comparison.md) | New 24-case AI-authored, AI-blind-labeled, AI-judged development comparison of full and keyword context, with a separate E5 retrieval result and known answer failures. It is not human-validated held-out performance. |

The snapshot pins [card offer draft `CARD-CATALOG-DRAFT-2026-09-28`](../card_offer_terms.md) and the [MVP requirements](../../docs/mvp_requirements.md). It freezes **what the offline pilot may evaluate**, not when an offer becomes effective. Changing a rate, fee, benefit, or access rule requires a new snapshot ID and re-review of affected labels. Cases in `pilot_cases.jsonl` are all `development_draft`; none may be reported as held-out performance or independent ground truth.

The draft cases have been used to exercise the harness and compare two retrieval methods **for development only**. At the user's request, Codex performed a provisional answer review and used a separate Haiku request to author a 24-case challenge set, then froze AI-assigned labels before scoring keyword retrieval, E5, and Sonnet. This replaces the immediate manual-review task but **does not meet independent human-validation criteria**; scenario overlap and AI labeling limit conclusions. The [training-data assessment](../../docs/training_data_assessment.md) explains why the supplied call transcripts are a tone reference rather than conversation training labels.

The [answer-generation harness](../../analysis/run_offline_rag.py) can use Claude with a key supplied as `ANTHROPIC_API_KEY` in the environment of the process running it. A multi-workspace key can also use `ANTHROPIC_WORKSPACE_ID`. Do not put either secret in the repository or paste it into a chat. This sends only the team-written pilot case and synthetic fact snapshot to Claude; it does not read customer CSVs. For a one-case smoke test after configuring the environment:

```bash
python3 analysis/run_offline_rag.py --provider anthropic --mode keyword --limit 1 --output /tmp/factored-claude-smoke.jsonl --review-csv /tmp/factored-claude-smoke-review.csv
```

The runner records token counts and per-case answers for manual review. It does not assign a pass rate or substitute for bilingual, held-out judging. The local Ollama attempt was stopped partway through and has no complete answer-quality score.

The ignored `review_exports/` folder contains three separate archives: `01_heldout_writer.zip`, `02_pilot_blind_labels.zip`, and `03_pilot_answer_review.zip`. With one bilingual collaborator, send the writer archive first and freeze their new prompts before they see the pilot. Then have them label the held-out and pilot cases without model answers. Release the Sonnet answer archive only after both label sets are frozen. This is single-reviewer judgment, so report the lack of independent writer/reviewer agreement. The [packet builder](../../analysis/prepare_conversation_review.py) recreates these exports from synthetic cases and the local development answer JSONL; neither credentials nor customer CSVs belong in them.
