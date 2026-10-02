"""Offline fact retrieval pilot. No answer generation or customer-data access.

Keyword mode uses only the standard library. E5 mode needs the optional
requirements-retrieval.txt and downloads public model weights for local use.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import unicodedata
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "plan/conversation_data/snapshots/source_pack_v4.md"
CASES = ROOT / "plan/conversation_data/pilot_cases.jsonl"
VERSION = "CONV-FACTS-2026-09-29-v4"
MODEL = "intfloat/multilingual-e5-small"
ROW = re.compile(r"^\| `([A-Z]+\.[A-Z_]+)` \| (.*?) \| .* \|$")
WORD = re.compile(r"[a-z0-9]+")
STOP = set("a al and as at com con da das de del do dos e el en es esta este for from in is la las lo los o of on or os por que se si the to um uma un una y".split())


def load_facts(source_path=SOURCE, expected_version=VERSION):
    raw = Path(source_path).read_text(encoding="utf-8")
    if expected_version not in raw:
        raise ValueError("Fact sheet version mismatch")
    facts = [(match[1], re.sub(r"[*`]", "", match[2]))
             for line in raw.splitlines() if (match := ROW.match(line))]
    if not facts or len(facts) != len({fact_id for fact_id, _ in facts}):
        raise ValueError("Empty or duplicate fact IDs")
    return facts


def is_retrievable(fact_id):
    """Access control and the universal draft disclaimer are always supplied by the service."""
    return fact_id != "CATALOG.STATUS" and not fact_id.startswith("ACCESS.")


def load_cases(path: Path, fact_ids: set[str]):
    cases = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not cases or len(cases) != len({case["case_id"] for case in cases}):
        raise ValueError("Empty or duplicate case IDs")
    for case in cases:
        if not set(case["relevant_fact_ids"]) <= fact_ids:
            raise ValueError(f"Unknown fact label: {case['case_id']}")
    return cases


def query(case):
    """Retrieve from the question and topic context; workflow state is not a fact-search hint."""
    lines = [value for value in (case["country"], case["selected_card"]) if value]
    lines += [f"{turn['role']}: {turn['text']}" for turn in case["prior_turns"][-2:]]
    lines.append(f"user: {case['user_utterance']}")
    return "\n".join(lines)


def tokens(value):
    value = unicodedata.normalize("NFKD", value.casefold())
    value = "".join(char for char in value if not unicodedata.combining(char))
    return {word for word in WORD.findall(value) if len(word) > 1 and word not in STOP}


def keyword_rank(facts, cases):
    terms = {fact_id: tokens(body) for fact_id, body in facts}
    frequencies = Counter(word for words in terms.values() for word in words)
    n = len(facts)
    ranked = {}
    for case in cases:
        words = tokens(query(case))
        scores = []
        for fact_id, _ in facts:
            overlap = words & terms[fact_id]
            score = sum(math.log((n + 1) / (frequencies[word] + 1)) + 1 for word in overlap)
            score /= math.sqrt(max(len(terms[fact_id]), 1))
            scores.append((score, fact_id))
        ranked[case["case_id"]] = [fact_id for _, fact_id in sorted(scores, key=lambda x: (-x[0], x[1]))]
    return ranked


def e5_rank(facts, cases, cache_dir):
    try:
        import numpy as np
        from fastembed import TextEmbedding
        from fastembed.common.model_description import ModelSource, PoolingType
    except ImportError as exc:
        raise RuntimeError("Install analysis/requirements-retrieval.txt to use E5") from exc
    if MODEL not in {item["model"] for item in TextEmbedding.list_supported_models()}:
        TextEmbedding.add_custom_model(model=MODEL, pooling=PoolingType.MEAN,
                                       normalization=True, sources=ModelSource(hf=MODEL),
                                       dim=384, model_file="onnx/model.onnx")
    model = TextEmbedding(model_name=MODEL, cache_dir=cache_dir)
    # The model card requires query:/passage: prefixes for asymmetric retrieval.
    passage_vectors = np.stack(list(model.embed(["passage: " + body for _, body in facts])))
    query_vectors = np.stack(list(model.embed(["query: " + query(case) for case in cases])))
    similarities = query_vectors @ passage_vectors.T
    return {case["case_id"]: [facts[j][0] for j in sorted(range(len(facts)),
             key=lambda j: (-float(similarities[i, j]), facts[j][0]))]
            for i, case in enumerate(cases)}


def metrics(cases, ranked, k):
    def score(group):
        if not group:
            return {"n": 0}
        hit = recall = reciprocal = 0.0
        for case in group:
            gold = {fact_id for fact_id in case["relevant_fact_ids"] if is_retrievable(fact_id)}
            found = ranked[case["case_id"]]
            hit += bool(found and found[0] in gold)
            recall += len(gold & set(found[:k])) / len(gold)
            reciprocal += next((1 / (i + 1) for i, fact_id in enumerate(found) if fact_id in gold), 0.0)
        return {"n": len(group), "hit_at_1": round(hit / len(group), 4),
                "recall_at_k": round(recall / len(group), 4),
                "mrr": round(reciprocal / len(group), 4)}
    return {"all": score(cases),
            "by_language": {lang: score([c for c in cases if c["language"] == lang])
                            for lang in sorted({c["language"] for c in cases})},
            "by_route": {route: score([c for c in cases if c["route"] == route])
                         for route in sorted({c["route"] for c in cases})}}


def evaluate(method, cases_path, k, cache_dir, source_path=SOURCE, fact_version=VERSION):
    all_facts = load_facts(source_path, fact_version)
    facts = [(fact_id, body) for fact_id, body in all_facts if is_retrievable(fact_id)]
    all_cases = load_cases(cases_path, {fact_id for fact_id, _ in all_facts})
    cases = [case for case in all_cases if any(is_retrievable(fact_id)
             for fact_id in case["relevant_fact_ids"])]
    if not 1 <= k <= len(facts):
        raise ValueError(f"top-k must be between 1 and {len(facts)}")
    names = ("keyword", "e5") if method == "both" else (method,)
    result = {"fact_version": fact_version, "case_file": str(cases_path),
              "case_count": len(all_cases), "retrieval_case_count": len(cases),
              "workflow_only_case_ids": [case["case_id"] for case in all_cases if case not in cases],
              "fact_count": len(all_facts), "retrievable_fact_count": len(facts), "top_k": k,
              "status": "development draft; not independently held out",
              "scope": "product-fact retrieval only; universal disclaimer and ACCESS facts are supplied by rules; no route, generated answer, or action assessed", "methods": {}}
    for name in names:
        ranked = keyword_rank(facts, cases) if name == "keyword" else e5_rank(facts, cases, cache_dir)
        result["methods"][name] = {
            "model": "exact-token IDF overlap" if name == "keyword" else MODEL,
            "metrics": metrics(cases, ranked, k),
            "cases": [{"case_id": case["case_id"], "language": case["language"],
                       "route": case["route"], "gold_retrieval": [fact_id for fact_id in case["relevant_fact_ids"] if is_retrievable(fact_id)],
                       "top_k": ranked[case["case_id"]][:k],
                       "missing_at_k": sorted({fact_id for fact_id in case["relevant_fact_ids"] if is_retrievable(fact_id)} - set(ranked[case["case_id"]][:k]))}
                      for case in cases]}
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--method", choices=("keyword", "e5", "both"), default="keyword")
    parser.add_argument("--cases", type=Path, default=CASES)
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--cache-dir", default=None)
    parser.add_argument("--source", type=Path, default=SOURCE)
    parser.add_argument("--fact-version", default=VERSION)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = evaluate(args.method, args.cases, args.top_k, args.cache_dir,
                      args.source, args.fact_version)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    else:
        print(json.dumps({"fact_version": result["fact_version"], "case_count": result["case_count"],
                          "retrieval_case_count": result["retrieval_case_count"],
                          "top_k": result["top_k"], "metrics": {name: data["metrics"]
                          for name, data in result["methods"].items()}}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
