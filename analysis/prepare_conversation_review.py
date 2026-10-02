"""Prepare blind, synthetic conversation review packets without gold labels."""

from __future__ import annotations

import argparse
import csv
import json
import shutil
from pathlib import Path

from evaluate_conversation_retrieval import CASES, SOURCE, load_cases, load_facts
from run_offline_rag import historical_fx_fact


def write_csv(path, fieldnames, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def context_row(case):
    fx = historical_fx_fact(case)
    return {
        "case_id": case["case_id"],
        "language": case["language"],
        "country": case["country"] or "",
        "entry": case["entry"],
        "selected_card": case["selected_card"] or "",
        "session": case["session"],
        "profile_permission": case["profile_permission"],
        "precheck_consent": case["precheck_consent"],
        "prior_turns": json.dumps(case["prior_turns"], ensure_ascii=False),
        "user_utterance": case["user_utterance"],
        "verified_fx_evidence": f"[{fx[0]}] {fx[1]}" if fx else "",
    }


def prepare(out_dir, responses=None):
    cases = load_cases(CASES, {fact_id for fact_id, _ in load_facts()})
    contexts = [context_row(case) for case in cases]
    fields = list(contexts[0])
    phase1 = out_dir / "phase1_blind_labels"
    write_csv(phase1 / "cases.csv", fields + [
        "review_route", "review_answerability", "review_relevant_fact_ids",
        "review_required_points", "review_forbidden_points", "review_notes",
    ], contexts)
    shutil.copyfile(SOURCE, phase1 / "source_pack.md")
    shutil.copyfile(SOURCE.parent.parent / "annotation_guide.md", phase1 / "annotation_guide.md")
    (phase1 / "README.md").write_text(
        "# Phase 1: blind bilingual labels\n\n"
        "Give this folder to a reviewer fluent in Spanish and Portuguese. It contains only "
        "team-written synthetic questions, session flags, verified historical FX evidence where "
        "relevant, and the fact sheet. Do not provide pilot_cases.jsonl, model answers, retrieval "
        "results, or development reports until these labels are submitted and frozen.\n\n"
        "For each row, assign the next safe route, answerability, relevant fact IDs, required "
        "points, forbidden points, and notes. Routes: REFUSE_UNAUTHORIZED, HANDOFF, "
        "ASK_SIGN_IN, ASK_PERMISSION, ROUTE_TO_POLICY, ASK_APPLICATION_CONFIRMATION, "
        "ROUTE_TO_APPLICATION, CLARIFY, ANSWER_FACT, STOP. A precheck is optional before "
        "application; an application needs explicit confirmation. A historical FX row is tool "
        "evidence, not a live quote. Record your reviewer ID/date when returning the file.\n",
        encoding="utf-8",
    )
    writer = out_dir / "heldout_writer"
    writer.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(SOURCE, writer / "source_pack.md")
    shutil.copyfile(SOURCE.parent.parent / "heldout_author_brief.md", writer / "instructions.md")
    (writer / "README.md").write_text(
        "# Held-out author packet\n\nShare this packet with a writer who has not seen the "
        "pilot questions, pilot labels, model answers, or development failures. If the same "
        "bilingual person will also label the cases and review the pilot, have them write and "
        "freeze the held-out prompts **before** receiving the Phase 1 pilot packet. Then have "
        "them label both sets without seeing model answers. This is a single-reviewer design, "
        "not independent writer/reviewer agreement; report that limitation. The template has "
        "no labels so prompts can be frozen first. The FX lookup columns "
        "are for a dated historical currency question only; leave them blank otherwise.\n",
        encoding="utf-8",
    )
    write_csv(writer / "case_template.csv", [
        "case_id", "scenario_family", "language", "country", "entry", "selected_card",
        "session", "profile_permission", "precheck_consent", "prior_turns",
        "user_utterance", "fx_lookup_date", "fx_lookup_source_currency",
    ], [])
    if responses is not None:
        answer_rows = [json.loads(line) for line in responses.read_text(encoding="utf-8").splitlines()
                       if line.strip()]
        by_id = {row["case_id"]: row for row in answer_rows}
        if len(by_id) != len(cases) or set(by_id) != {case["case_id"] for case in cases}:
            raise ValueError("Response file must contain one row for every pilot case")
        phase2 = out_dir / "phase2_answer_review"
        write_csv(phase2 / "answers.csv", [
            "case_id", "model_route", "model_answer", "model_citations", "model_error",
            "route_correct", "facts_supported", "limitations_clear", "language_correct",
            "unsafe_claim", "review_notes",
        ], [{
            "case_id": case["case_id"],
            "model_route": (by_id[case["case_id"]].get("response") or {}).get("route", ""),
            "model_answer": (by_id[case["case_id"]].get("response") or {}).get("answer", ""),
            "model_citations": ", ".join((by_id[case["case_id"]].get("response") or {}).get("citations", [])),
            "model_error": by_id[case["case_id"]].get("error") or "",
        } for case in cases])
        (phase2 / "README.md").write_text(
            "# Phase 2: answer review\n\nShare this folder only after the reviewer has "
            "submitted and frozen pilot and held-out labels. Compare these model answers with the frozen "
            "labels and fact sheet. Mark route correctness, factual support, limitations, "
            "language quality, unsafe claims, and explanatory notes. An API or parsing error "
            "is a failure, not an omitted case. Do not treat this development pilot as a "
            "held-out score.\n", encoding="utf-8",
        )
    return len(cases)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--responses", type=Path)
    args = parser.parse_args()
    print(f"Prepared {prepare(args.output_dir, args.responses)} synthetic cases")


if __name__ == "__main__":
    main()
