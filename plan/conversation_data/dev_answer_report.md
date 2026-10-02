# Claude Sonnet development answer check

**Status: draft development run, 2026-09-28.** The 24 team-written pilot cases were sent with the synthetic fact snapshot to `claude-sonnet-5`, using multilingual E5 top-five retrieval plus mandatory access/unknown facts. No customer CSV or credential was sent in the prompt. Raw responses and a review sheet were written only under `/tmp/`, outside the repository. This run is not a held-out evaluation or bilingual factual review.

The first pass returned 23 parseable answers and one truncated JSON response (`ES-007`). After increasing the output limit, a separate retry of `ES-007` returned parseable JSON. Across one answer per case, **21/24 route labels matched** the draft labels; three did not:

| Case | Draft route | Sonnet route | What to review |
| --- | --- | --- | --- |
| `ES-005` | `ASK_SIGN_IN` | `ANSWER_FACT` | Correctly withheld approval but failed to direct the anonymous visitor to trusted sign-in before any personal path. |
| `ES-007` | `ANSWER_FACT` | `HANDOFF` | The draft label expects an exact historical MXN→USD example, but the rate `0.057989` is in the source CSV and gold rubric, **not in the fact snapshot passed to the model**. The handoff is safer than inventing a rate; fix the evidence pack or relabel before judging. |
| `PT-012` | `ASK_PERMISSION` | `ROUTE_TO_APPLICATION` | Asked for explicit application confirmation while saying no precheck consent had been given. Review whether a precheck is mandatory before a mock application; the current draft label assumes it is. |

The 23 first-pass parseable responses cited only fact IDs supplied in their prompts. That checks citation *membership*, not whether each sentence is supported. No bilingual reviewer has yet scored groundedness, language, unsupported claims, or safety. Do not interpret the route count as product quality or a model comparison.

The local Ollama run was stopped after 14 cases at the user's request and cannot provide a complete comparison. Next, resolve the `ES-007` evidence gap and the `PT-012` route rule, have a bilingual reviewer assess factual answers, then evaluate a separately authored held-out set. Keep API credentials in the ignored `.env` or process environment and keep raw answer files outside the repository.
