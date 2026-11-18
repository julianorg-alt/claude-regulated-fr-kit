"""Benchmark of the detectors on the synthetic data set (backlog E4.3).

Strict match: a gold span counts as found only if a detection has the same type and the same
boundaries. Overlap match: same type and any character in common (useful for addresses and names,
where boundaries are a matter of convention). Hard negatives (numbers with a wrong key) must not be
detected at all; each detection on one counts as a false positive of its type.

    python -m crfr_pseudo.benchmark --data ../datasets/pii-fr/v1.jsonl --out ../datasets/pii-fr/results
"""

from __future__ import annotations

import argparse
import json
import platform
from collections import defaultdict
from pathlib import Path

from .detectors import IDENTIFIER_TYPES, Detector


def _overlaps(a: dict, b) -> bool:
    return a["start"] < b.end and b.start < a["end"]


def score(docs: list[dict], detector: Detector) -> dict:
    counts = {m: defaultdict(lambda: defaultdict(int)) for m in ("strict", "overlap")}
    negatives_hit = defaultdict(int)
    for doc in docs:
        found = detector.find(doc["text"])
        for mode in ("strict", "overlap"):
            per_type = counts[mode]
            matched = set()
            for gold in doc["spans"]:
                keys = (("all", gold["label"]), (doc["sector"], gold["label"]))
                hit = next(
                    (
                        i
                        for i, s in enumerate(found)
                        if i not in matched
                        and s.type == gold["label"]
                        and (
                            (s.start, s.end) == (gold["start"], gold["end"]) if mode == "strict" else _overlaps(gold, s)
                        )
                    ),
                    None,
                )
                for key in keys:
                    per_type[key]["gold"] += 1
                    per_type[key]["tp"] += hit is not None
                if hit is not None:
                    matched.add(hit)
            for i, s in enumerate(found):
                if i not in matched:
                    per_type[("all", s.type)]["fp"] += 1
                    per_type[(doc["sector"], s.type)]["fp"] += 1
        for negative in doc.get("negatives", []):
            if any(_overlaps(negative, s) and s.type == negative["kind"] for s in found):
                negatives_hit[negative["kind"]] += 1
    result = {"documents": len(docs), "negatives_detected": dict(negatives_hit), "modes": {}}
    for mode, per_type in counts.items():
        table = {}
        for (sector, label), c in sorted(per_type.items()):
            tp, gold, fp = c["tp"], c["gold"], c["fp"]
            precision = tp / (tp + fp) if tp + fp else None
            recall = tp / gold if gold else None
            f1 = 2 * precision * recall / (precision + recall) if precision and recall else None
            table.setdefault(sector, {})[label] = {
                "gold": gold, "tp": tp, "fp": fp,
                "precision": round(precision, 4) if precision is not None else None,
                "recall": round(recall, 4) if recall is not None else None,
                "f1": round(f1, 4) if f1 is not None else None,
            }  # fmt: skip
        ids = [table["all"][t] for t in IDENTIFIER_TYPES if t in table.get("all", {})]
        gold = sum(c["gold"] for c in ids)
        table["identifiers_recall"] = round(sum(c["tp"] for c in ids) / gold, 4) if gold else None
        result["modes"][mode] = table
    return result


def markdown(result: dict, label: str) -> str:
    lines = [
        f"# Benchmark: {label}",
        "",
        f"{result['documents']} documents. Hard negatives detected (wrong key, must be 0): "
        f"{sum(result['negatives_detected'].values())}.",
        "",
    ]
    for mode in ("strict", "overlap"):
        table = result["modes"][mode]
        recall = table["identifiers_recall"]
        lines += [f"## {mode.capitalize()} match", "", f"Recall on identifiers with a key: {recall}", ""]
        lines += ["| Type | Gold | Precision | Recall | F1 |", "|---|---|---|---|---|"]
        for label_, c in table["all"].items():
            lines.append(f"| {label_} | {c['gold']} | {c['precision']} | {c['recall']} | {c['f1']} |")
        sectors = [s for s in table if s not in ("all", "identifiers_recall")]
        header = "| Type | " + " | ".join(sectors) + " |"
        lines += ["", "Recall by sector:", "", header, "|---|" + "---|" * len(sectors)]
        for label_ in table["all"]:
            row = [str(table[s].get(label_, {}).get("recall")) for s in sectors]
            lines.append(f"| {label_} | " + " | ".join(row) + " |")
        lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--backend", choices=("spacy", "gliner"), default="spacy")
    args = parser.parse_args(argv)
    docs = [json.loads(line) for line in args.data.read_text(encoding="utf-8").splitlines() if line.strip()]
    extra = []
    if args.backend == "gliner":
        from .backends import GLINER_MODEL, GLINER_REVISION, GlinerBackend

        extra = [GlinerBackend()]
        label = f"spaCy fr_core_news_md + GLiNER {GLINER_MODEL}@{GLINER_REVISION[:8]}"
    else:
        label = "spaCy fr_core_news_md (default)"
    result = score(docs, Detector(extra=extra))
    result["detector"] = label
    result["python"] = platform.python_version()
    args.out.mkdir(parents=True, exist_ok=True)
    stem = f"{args.data.stem}-{args.backend}"
    (args.out / f"{stem}.json").write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (args.out / f"{stem}.md").write_text(markdown(result, label) + "\n", encoding="utf-8")
    print(json.dumps({"identifiers_recall": result["modes"]["strict"]["identifiers_recall"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
