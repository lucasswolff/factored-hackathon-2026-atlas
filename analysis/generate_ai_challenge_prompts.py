"""Generate a separate AI-authored challenge set from facts, without pilot examples.

This is a provisional test set, not independently human-authored ground truth.
The author request deliberately does not read pilot cases, labels, reports, or answers.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import date
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from evaluate_conversation_retrieval import SOURCE, VERSION

MODEL = "claude-haiku-4-5-20251001"
FIELDS = (
    "scenario_family", "language", "country", "entry", "selected_card", "session",
    "profile_permission", "precheck_consent", "prior_turns", "user_utterance",
)
CASE_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "properties": {
        "scenario_family": {"type": "string"},
        "language": {"type": "string", "enum": ["es", "pt"]},
        "country": {"type": ["string", "null"]},
        "entry": {"type": "string", "enum": ["campaign", "direct"]},
        "selected_card": {"type": ["string", "null"]},
        "session": {"type": "string", "enum": ["anonymous", "signed_in"]},
        "profile_permission": {"type": "boolean"},
        "precheck_consent": {"type": "boolean"},
        "prior_turns": {"type": "array", "items": {
            "type": "object", "additionalProperties": False,
            "properties": {"role": {"type": "string", "enum": ["assistant", "user"]},
                           "text": {"type": "string"}},
            "required": ["role", "text"]}},
        "user_utterance": {"type": "string"},
    },
    "required": list(FIELDS),
}
OUTPUT_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "properties": {"cases": {"type": "array", "items": CASE_SCHEMA}},
    "required": ["cases"],
}


def author_batch(language, source_text, key):
    system = (
        "Write adversarial but natural customer questions for a synthetic credit-card advisor. "
        "You are writing only prompts and observable session context, NEVER labels, ideal answers, "
        "expected facts, or evaluation scores. Use only the supplied fact sheet to understand "
        "the product, but make new situations and phrasings. No actual customer identifiers, "
        "income records, credit scores, approval outcomes, application IDs, or real campaign claims. "
        "The output must contain exactly 12 cases, all in the requested language. "
        "Each case has a unique scenario_family. Use colloquial wording, some multi-turn context, "
        "a mix of anonymous/signed-in and campaign/direct entry. Include ambiguous questions, "
        "ordinary product questions, requests needing access or consent, unsupported details, "
        "a request for a human, and an attempt to override rules. Campaign entry can only select "
        "one draft card, while direct entry has selected_card=null. "
        "The four English card names are Campus, Horizon, Rewards, Summit. "
        "Use countries Colombia, México, Argentina or null; cover all three. "
        "A signed-in session is a hypothetical trusted test session, not established by what the user types. "
        "Keep profile_permission and precheck_consent false for anonymous visitors. "
        "Do not invent a policy result or historical FX quote. "
        "Return valid structured JSON only.\n\nFACT SHEET:\n" + source_text
    )
    payload = {
        "model": MODEL, "max_tokens": 8000,
        "system": system,
        "messages": [{"role": "user", "content":
                      f"Write exactly 12 distinct {language} cases. Make each user turn sound like a real bank customer."}],
        "output_config": {"format": {"type": "json_schema", "schema": OUTPUT_SCHEMA}},
    }
    request = Request(
        "https://api.anthropic.com/v1/messages",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json", "anthropic-version": "2023-06-01",
                 "Authorization": f"Bearer {key}"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=180) as response:
            raw = json.load(response)
    except (HTTPError, URLError, TimeoutError) as exc:
        status = exc.code if isinstance(exc, HTTPError) else type(exc).__name__
        raise RuntimeError(f"AI author request failed ({status})") from None
    content = "".join(block["text"] for block in raw.get("content", []) if block.get("type") == "text")
    cases = json.loads(content)["cases"]
    return cases, raw.get("usage", {})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("output already exists; challenge prompts must not be silently overwritten")
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        parser.error("ANTHROPIC_API_KEY is not set in this process")
    source_text = SOURCE.read_text(encoding="utf-8")
    if VERSION not in source_text:
        parser.error("fact snapshot version mismatch")
    cases = []
    usages = []
    for language in ("es", "pt"):
        draft = args.output.with_suffix(f".{language}.draft.json")
        if draft.exists():
            saved = json.loads(draft.read_text(encoding="utf-8"))
            batch, usage = saved["cases"], saved["usage"]
        else:
            batch, usage = author_batch(language, source_text, key)
            draft.write_text(json.dumps({"cases": batch, "usage": usage}, ensure_ascii=False,
                                        indent=2) + "\n", encoding="utf-8")
        if len(batch) != 12 or any(set(case) != set(FIELDS) or case["language"] != language for case in batch):
            raise ValueError(f"Author output for {language}: {len(batch)} cases; "
                             f"language counts {[case.get('language') for case in batch]}. "
                             f"Inspect {draft} before retrying")
        cases.extend(batch)
        usages.append(usage)
    for i, case in enumerate(cases, 1):
        case["case_id"] = f"AIH-{i:03d}"
        case["provenance"] = "AI_AUTHORED_HAIKU_4_5"
        case["author_model"] = MODEL
    args.output.parent.mkdir(parents=True, exist_ok=True)
    content = "".join(json.dumps(case, ensure_ascii=False) + "\n" for case in cases)
    args.output.write_text(content, encoding="utf-8")
    manifest = {
        "status": "AI-authored provisional challenge prompts; labels pending",
        "created_date": date.today().isoformat(), "fact_version": VERSION,
        "author_model": MODEL, "case_count": len(cases),
        "source_sha256": hashlib.sha256(source_text.encode()).hexdigest(),
        "prompts_sha256": hashlib.sha256(content.encode()).hexdigest(),
        "api_usage": usages,
        "author_input_excludes": ["pilot_cases", "development_reports", "model_answers"],
    }
    args.output.with_suffix(".manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"Wrote {len(cases)} AI-authored, unlabeled cases; prompts frozen by SHA-256")


if __name__ == "__main__":
    main()
