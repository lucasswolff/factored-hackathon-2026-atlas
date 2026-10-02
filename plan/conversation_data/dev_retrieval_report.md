# Development retrieval comparison

**Status:** offline development pilot, 2026-09-28. The [24 team-written cases](pilot_cases.jsonl) and [fact snapshot](source_pack.md) were approved for this development exercise, but they are not an independently written, held-out test set. The queries and retrieval scope were adjusted after inspecting pilot behavior. These figures cannot establish production answer quality, safe resolution, or a measured benefit from training on organizer conversations.

The [evaluation script](../../analysis/evaluate_conversation_retrieval.py) ranks the same **16 retrievable product/unknown fact passages** for each method. Seven of the 24 cases only test workflow rules and are excluded from retrieval metrics. `ACCESS.*` rules and the universal `CATALOG.STATUS` disclaimer are controlled by the service, not searched as optional passages. Both methods receive the same country, selected-card, recent-turn, and user-utterance text. Neither method sees relevance labels or rubric text. Retrieval is scored against the pilot's fact IDs at `k=5`; no responses, routes, prechecks, applications, or handoffs were generated or scored.

| Method | Retrieval cases | Hit@1 | Mean recall@5 | MRR | All required product facts in top 5 |
| --- | ---: | ---: | ---: | ---: | ---: |
| Exact-token IDF keyword baseline | 17 | 7/17 (41.2%) | 55.9% | 53.8% | 6/17 |
| Pretrained multilingual E5 small | 17 | 10/17 (58.8%) | 66.2% | 72.2% | 7/17 |

| Language | Cases | Keyword hit@1 / recall@5 | E5 hit@1 / recall@5 |
| --- | ---: | ---: | ---: |
| Spanish | 9 | 55.6% / 61.1% | 44.4% / 58.3% |
| Portuguese | 8 | 25.0% / 50.0% | 75.0% / 75.0% |

**Context-size check:** The script ranks every fact and reports five passages by default. `Hit@1` asks whether the *first* passage is relevant; it is not a one-passage limit. With E5, the top three contain all labeled product facts for **5/17** cases (mean recall **58.8%**); the top five do so for **7/17** (mean recall **66.2%**). The keyword baseline reaches **4/17** and **6/17** respectively. These passages are offer facts, not example conversations, and no LLM has read or answered from them yet.

E5 helps on this small pilot overall, especially Portuguese, but it is **worse on Spanish** for these labels. Its top five omit `UNKNOWN.TRAVEL` in both Portuguese questions asking for a specific lounge/companion (`PT-001`) or baggage-insurance payout (`PT-011`). It also omits `MILES.HISTORY` in several miles questions, including `ES-007`, `ES-008`, and `PT-004`. The keyword baseline has similar or worse misses. A generated advisor must not treat a top-five passage list as permission to promise travel coverage, current FX, an exact miles total, or a full borrowing cost. Those boundary checks need explicit routing/answer rules and later end-to-end evaluation.

The keyword method uses an untrained exact-token overlap score with IDF and no translation dictionary. E5 uses local [multilingual-e5-small](https://huggingface.co/intfloat/multilingual-e5-small) embeddings with the model-card `query:` and `passage:` prefixes, cosine-equivalent dot-product ranking of normalized vectors, and `fastembed==0.8.0`. The local model cache resolved snapshot `614241f622f53c4eeff9890bdc4f31cfecc418b3` for this run. This model was **pretrained elsewhere**, not trained or fine-tuned on organizer data. The public weights are downloaded locally; case text is not sent to a model API. [Per-case rankings and misses](dev_retrieval_results.json) are saved for inspection.

Reproduce from the repository root with Python 3.12:

```bash
python3 -m unittest discover -s analysis -p 'test_*.py' -v
python3 -m venv /tmp/factored-retrieval-venv
/tmp/factored-retrieval-venv/bin/python -m pip install -r analysis/requirements-retrieval.txt
/tmp/factored-retrieval-venv/bin/python analysis/evaluate_conversation_retrieval.py --method both --cache-dir /tmp/factored-e5-cache --output /tmp/factored-retrieval-results.json
```

**Next evidence needed:** obtain a bilingual review of a pilot sample and a separately written held-out set with new scenario families, following the [annotation guide](annotation_guide.md). Freeze the test cases and model/corpus versions before any further tuning. Then measure routing, factual answer grounding, abstention/handoff, and unsafe claims, not retrieval alone. This pilot supports continuing the research; it does **not** justify shipping a customer-facing advisor.
