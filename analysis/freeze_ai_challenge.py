"""Validate and freeze AI-authored prompts plus AI-judged labels before scoring."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from evaluate_conversation_retrieval import CASES, SOURCE, VERSION, load_facts
from run_offline_rag import ROUTES

ROOT = SOURCE.parent.parent
PROMPTS = ROOT / "ai_challenge_prompts.jsonl"
LABELS = ROOT / "ai_challenge_labels.json"
OUTPUT = ROOT / "ai_challenge_cases.jsonl"


def digest(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def freeze(prompts=PROMPTS, labels=LABELS, output=OUTPUT):
    if output.exists():
        raise ValueError("Frozen challenge file already exists; do not overwrite it")
    prompt_text = prompts.read_text(encoding="utf-8")
    manifest = json.loads(prompts.with_suffix(".manifest.json").read_text(encoding="utf-8"))
    if manifest["prompts_sha256"] != digest(prompt_text):
        raise ValueError("Prompt file changed after author freeze")
    source_path = SOURCE if manifest["fact_version"] == VERSION else \
        ROOT / "snapshots" / f"source_pack_{manifest['fact_version'].rsplit('-', 1)[-1]}.md"
    if not source_path.exists() or manifest["source_sha256"] != digest(source_path.read_text(encoding="utf-8")):
        raise ValueError("Frozen source snapshot is missing or changed")
    cases = [json.loads(line) for line in prompt_text.splitlines() if line.strip()]
    gold = json.loads(labels.read_text(encoding="utf-8"))
    ids = [case["case_id"] for case in cases]
    if len(cases) != 24 or len(set(ids)) != 24 or set(gold) != set(ids):
        raise ValueError("Expected exactly 24 unique prompts and labels")
    facts = {fid for fid, _ in load_facts(source_path, manifest["fact_version"])}
    pilot_families = {json.loads(line)["scenario_family"] for line in CASES.read_text().splitlines() if line.strip()}
    for case in cases:
        label = gold[case["case_id"]]
        if case["scenario_family"] in pilot_families:
            raise ValueError(f"Pilot scenario family reused: {case['case_id']}")
        if label["route"] not in ROUTES or not set(label["relevant_fact_ids"]) <= facts:
            raise ValueError(f"Invalid route or fact IDs: {case['case_id']}")
        if not all(label.get(key) for key in ("required_points", "forbidden_points", "answerability")):
            raise ValueError(f"Incomplete label: {case['case_id']}")
        case.update(label)
        case["review_status"] = "AI_JUDGED_UNVALIDATED"
    content = "".join(json.dumps(case, ensure_ascii=False) + "\n" for case in cases)
    output.write_text(content, encoding="utf-8")
    freeze_manifest = {
        "status": "AI-authored and AI-judged challenge set; no human validation",
        "fact_version": manifest["fact_version"],
        "author_model": manifest["author_model"],
        "prompt_sha256": manifest["prompts_sha256"],
        "labels_sha256": digest(labels.read_text(encoding="utf-8")),
        "cases_sha256": digest(content),
        "case_count": len(cases),
        "caveat": "Semantic overlap with development scenarios remains possible; do not claim independent human held-out performance.",
    }
    output.with_suffix(".manifest.json").write_text(json.dumps(freeze_manifest, indent=2) + "\n")
    return len(cases)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    print(f"Frozen {freeze(output=args.output)} AI challenge cases")


if __name__ == "__main__":
    main()
