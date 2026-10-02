"""Extract the distinct Spanish agent templates and translate them for tone study.

These short, repetitive templates are not product-answer or eligibility labels.
Portuguese translations are team-created and require bilingual review before use.
"""

import csv
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "data" / "call_transcripts"
OUTPUT = ROOT / "data" / "derived" / "tone_examples_es_pt.json"

BASES = {
    "Buenos días, con gusto le ayudo. Permítame un momento para verificar su saldo. Su saldo actual es de {monto} {moneda}.":
        "Bom dia, terei prazer em ajudar. Vou verificar seu saldo. Seu saldo atual é de {monto} {moneda}.",
    "Buenas tardes, claro que sí. Déjeme revisar esa información. Su saldo actual es {monto} {moneda} y su límite disponible es de {limite} {moneda}.":
        "Boa tarde, claro. Vou consultar essas informações. Seu saldo atual é de {monto} {moneda} e seu limite disponível é de {limite} {moneda}.",
}

CLOSINGS = {
    "Claro, estoy para servirle.": "Claro, estou à disposição.",
    "Perfecto, ¿necesita algo más?": "Perfeito, precisa de mais alguma coisa?",
    "No hay problema, que tenga buen día.": "Sem problema, tenha um bom dia.",
    "Con gusto. ¿Hay algo más en lo que pueda ayudarle?":
        "Com prazer. Há mais alguma coisa em que eu possa ajudar?",
}


def translate_template(spanish: str) -> str:
    for source_base, translated_base in BASES.items():
        if spanish == source_base or spanish.startswith(source_base + " "):
            suffix = spanish[len(source_base):].strip()
            parts = [translated_base]
            while suffix:
                match = next((item for item in CLOSINGS.items() if suffix.startswith(item[0])), None)
                if match is None:
                    raise ValueError(f"Unrecognized agent-text suffix: {suffix!r}")
                source_closing, translated_closing = match
                parts.append(translated_closing)
                suffix = suffix[len(source_closing):].strip()
            return " ".join(parts)
    raise ValueError(f"Unrecognized agent-text template: {spanish!r}")


def main() -> None:
    unique_texts = set()
    for path in sorted(SOURCE.rglob("*.csv")):
        with path.open(newline="", encoding="utf-8-sig") as file:
            for row in csv.DictReader(file):
                if row.get("agent_text"):
                    unique_texts.add(row["agent_text"].strip())

    if len(unique_texts) != 42:
        raise ValueError(f"Expected 42 distinct agent-text templates, found {len(unique_texts)}")

    examples = [
        {"id": f"tone-{index:03d}", "es": spanish, "pt": translate_template(spanish)}
        for index, spanish in enumerate(sorted(unique_texts), start=1)
    ]
    payload = {
        "source": "data/call_transcripts/**/call_transcripts_*.csv:agent_text",
        "source_language": "es",
        "translation_language": "pt",
        "translation_provenance": "TEAM_CREATED; BILINGUAL_REVIEW_PENDING",
        "purpose": "tone_examples_only; not product facts, eligibility labels, or training ground truth",
        "distinct_full_templates": len(examples),
        "base_template_count": len(BASES),
        "closing_phrase_count": len(CLOSINGS),
        "examples": examples,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {len(examples)} translated tone templates to {OUTPUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
