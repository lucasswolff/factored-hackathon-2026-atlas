# Atlas pitch deck

- [Editable PowerPoint](atlas_factored_hackathon_2026.pptx)
- [PDF preview](atlas_factored_hackathon_2026.pdf)
- [Spanish conversation capture](assets/spanish_conversation.png)

The six slides cover the customer goal, the supplied data and its limits, a live
Spanish conversation, the deployed architecture, operating controls and measured
checks, and the work needed before serving real bank customers. The screenshot
was captured from the public judge app on 2026-10-03 using fictional fixture
P02, México, a Rewards campaign entry, and two unscripted Spanish questions.
The cropped image on slide 3 comes from that full capture. A new model run may
word the answers differently.

## Evidence behind the slides

| Slide | Source and interpretation |
| --- | --- |
| 2 | [Marketing feasibility audit](../docs/credit_marketing_feasibility.md): 52 generic credit-card campaigns; 1,746,801 sends and 97,793 clicks across **all** campaigns. These are engagement counts, not verified card sales. [Campaign mapping](../plan/campaign_cards.md) documents which historical rows seed the demo entry cards. `CUSTOMERS` and `PRODUCTS` inform local test scenarios; `SERVICE_AGENTS` supplies a private, filtered roster snapshot; `SERVICE.CALL_TRANSCRIPTS` is a Spanish tone reference. The public hosted customer fixtures, offers, policy, and actions are team-created. |
| 3 | [Full screenshot](assets/spanish_conversation.png) captured from the [deployed app](https://55p7p6snz2nmfwiust5i5k7kmi0mjbqc.lambda-url.us-east-2.on.aws/). The visible source IDs are the demo's versioned public fact references. |
| 4 | [Detailed hosted architecture](../docs/architecture.svg), [advisor behavior](../advisor/README.md), and [AWS deployment](../infra/aws/README.md). |
| 5 | [Judge rehearsal](../docs/judge_rehearsal_2026-10-02.md): 12/12 entry/country/language combinations, 3/3 confirmed mock application read-backs, and a separate 24/24-request, six-visitor check. The [AI-only answer comparison](../plan/conversation_data/ai_review_2026_10_03_comparison.md) found 17/24 full required-point answers with full context versus 13/24 with keyword-selected context, plus 2/24 forbidden claims in the full-context arm, **before** follow-up fixes. On 18 cases with relevant facts, pretrained multilingual E5 recall@5 was 84.3% versus 38.9% for keyword retrieval; E5 is not deployed. These are development diagnostics, not independent bilingual accuracy claims or peak-capacity results. |
| 6 | [Release and evaluation plan](../docs/release_readiness.md) and organizer `problem_statement.pdf` (pages 2–6). |

The organizer `datathon_kickoff.pdf` (page 18) asks for a public repository,
deployed tool, 4–6 slides, and a short mandatory video pitch. The video is a
separate deliverable.

## Rebuild

The deck uses editable PowerPoint shapes and text; only the live chat capture is
an image. To regenerate the PPTX and PDF from the checked-in content:

```bash
python3 -m venv /tmp/atlas-presentation-venv
/tmp/atlas-presentation-venv/bin/pip install python-pptx reportlab Pillow
/tmp/atlas-presentation-venv/bin/python presentation/build_deck.py
```

The build requires a system DejaVu Sans font for the matching PDF preview.
Changing the PowerPoint text or shapes does not automatically change the PDF;
edit `build_deck.py` and rebuild both outputs to keep them aligned.
