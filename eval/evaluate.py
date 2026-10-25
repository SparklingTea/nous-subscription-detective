"""Score the detector against hand labels: merchant cleanup, subscription detection, cadence, and each flag.

    python -m eval.evaluate                      # synthetic seed 42 + robustness over seeds 1-5
    python -m eval.evaluate --data data/mine     # your own labelled export (same three-file layout)
"""
import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "data"))

from detective.loader import load  # noqa: E402
from detective.pipeline import run  # noqa: E402

FLAGS = ["price_rise", "duplicate", "trial_converted", "forgotten"]


def key(s) -> str:
    return re.sub(r"[^a-z0-9]", "", str(s).lower())


def prf(tp, fp, fn):
    p = tp / (tp + fp) if tp + fp else None
    r = tp / (tp + fn) if tp + fn else None
    f = 2 * p * r / (p + r) if p and r else None
    return dict(tp=tp, fp=fp, fn=fn, precision=p and round(p, 3), recall=r and round(r, 3), f1=f and round(f, 3))


def as_bool(v) -> bool:
    return str(v).strip().lower() in ("true", "1", "yes", "y")


def evaluate(txn_df: pd.DataFrame, lab_txn: pd.DataFrame, lab_streams: pd.DataFrame, threshold=2) -> dict:
    result, txns = run(txn_df, threshold)
    pred_merchant = {t.id: t.merchant for t in txns}
    lab_txn = lab_txn.fillna("")
    known = {t.id: t.entry is not None for t in txns}

    # 1. Merchant cleanup, transaction level
    rows = [(r.id, r.merchant, pred_merchant[r.id]) for r in lab_txn.itertuples()]
    ok = [key(a) == key(b) for _, a, b in rows]
    distinct_wrong = Counter((a, b) for (_, a, b), good in zip(rows, ok) if not good)
    merchant = dict(
        accuracy=round(sum(ok) / len(ok), 3), n=len(ok),
        accuracy_catalogue=round(sum(g for (i, *_), g in zip(rows, ok) if known[i]) / max(1, sum(known[i] for i, *_ in rows)), 3),
        accuracy_long_tail=round(sum(g for (i, *_), g in zip(rows, ok) if not known[i]) / max(1, sum(not known[i] for i, *_ in rows)), 3),
        distinct_merchants=len({key(a) for _, a, _ in rows}),
        distinct_merchants_correct=len({key(a) for (_, a, b), g in zip(rows, ok) if g}),
        errors=[dict(label=a, predicted=b, count=c) for (a, b), c in distinct_wrong.most_common()],
    )

    # 2. Stream matching by transaction overlap
    label_members = defaultdict(set)
    for r in lab_txn.itertuples():
        if r.stream_id:
            label_members[r.stream_id].add(r.id)
    labels = {r.stream_id: r for r in lab_streams.itertuples()}
    matches = {}  # pred id -> label id
    for s in result["streams"]:
        ids = set(s["txn_ids"])
        best = max(label_members, key=lambda l: len(ids & label_members[l]) / len(ids | label_members[l]))
        jac = len(ids & label_members[best]) / len(ids | label_members[best])
        if jac >= 0.5:
            matches[s["id"]] = best
    preds = {s["id"]: s for s in result["streams"]}
    matched_labels = defaultdict(list)
    for p, l in matches.items():
        matched_labels[l].append(p)

    def detected_as(label_id, kind):
        return any(preds[p]["kind"] == kind for p in matched_labels.get(label_id, []))

    sub_labels = [l for l, r in labels.items() if r.kind == "subscription"]
    tp = sum(detected_as(l, "subscription") for l in sub_labels)
    pred_subs = [s for s in result["streams"] if s["kind"] == "subscription"]
    fp_list = [s for s in pred_subs if s["id"] not in matches or labels[matches[s["id"]]].kind != "subscription"]
    fn_list = [l for l in sub_labels if not detected_as(l, "subscription")]
    detection = prf(tp, len(fp_list), len(fn_list))
    detection["false_positives"] = [dict(label=s["label"], cadence=s["cadence"], n=s["n"],
                                         truth=labels[matches[s["id"]]].kind if s["id"] in matches else "not recurring")
                                    for s in fp_list]
    detection["false_negatives"] = [dict(stream=l, merchant=labels[l].merchant, note=labels[l].note) for l in fn_list]

    kinds = Counter()
    for l, r in labels.items():
        ps = matched_labels.get(l)
        kinds[(r.kind, preds[ps[0]]["kind"] if ps else "missed")] += 1
    for s in result["streams"]:
        if s["id"] not in matches:
            kinds[("not recurring", s["kind"])] += 1

    cad = [(labels[l].cadence, preds[p]["cadence"]) for p, l in matches.items()]
    act = [(as_bool(labels[l].active), preds[p]["active"]) for p, l in matches.items()]

    # 3. Flags at stream level
    flags = {}
    for f in FLAGS:
        tpf = fpf = fnf = 0
        fps, fns = [], []
        for l, r in labels.items():
            truth = as_bool(getattr(r, f))
            pred = any(f in preds[p]["flags"] for p in matched_labels.get(l, []))
            if truth and pred:
                tpf += 1
            elif truth:
                fnf += 1
                fns.append(r.merchant + (f" ({r.note})" if r.note else ""))
            elif pred:
                fpf += 1
                fps.append(r.merchant)
        for s in result["streams"]:
            if s["id"] not in matches and f in s["flags"]:
                fpf += 1
                fps.append(s["label"])
        flags[f] = prf(tpf, fpf, fnf) | {"false_positives": fps, "false_negatives": fns}

    return dict(
        merchant=merchant,
        subscription_detection=detection,
        kind_confusion=[dict(truth=a, predicted=b, count=c) for (a, b), c in sorted(kinds.items())],
        cadence_accuracy=round(sum(a == b for a, b in cad) / max(1, len(cad)), 3),
        active_accuracy=round(sum(a == b for a, b in act) / max(1, len(act)), 3),
        flags=flags,
        summary=result["summary"],
    )


def load_dir(d: Path):
    return (load(d / "transactions.csv"), pd.read_csv(d / "labels_transactions.csv", dtype=str),
            pd.read_csv(d / "labels_streams.csv"))


def seed_frames(seed: int):
    import generate
    h = generate.build(seed)
    tx = pd.DataFrame([dict(id=t["id"], date=t["date"], description=t["description"], amount=t["amount"],
                            type=t["type"]) for t in h.txns])
    lt = pd.DataFrame([dict(id=t["id"], merchant=t["merchant"], stream_id=t["stream"]) for t in h.txns])
    return tx, lt, pd.DataFrame(h.streams)


def fmt(x):
    return "n/a" if x is None else f"{x:.2f}"


def markdown(main: dict, thresholds: dict, seeds: dict | None) -> str:
    d, m = main["subscription_detection"], main["merchant"]
    out = ["# Subscription detective: evaluation", "",
           "## Headline", "",
           "| Task | Precision | Recall | F1 | TP / FP / FN |", "|---|---|---|---|---|",
           f"| Subscription detection (stream level) | {fmt(d['precision'])} | {fmt(d['recall'])} | {fmt(d['f1'])} | {d['tp']} / {d['fp']} / {d['fn']} |"]
    for f, v in main["flags"].items():
        out.append(f"| Flag: {f} | {fmt(v['precision'])} | {fmt(v['recall'])} | {fmt(v['f1'])} | {v['tp']} / {v['fp']} / {v['fn']} |")
    out += ["", f"- Merchant cleanup accuracy: **{m['accuracy']:.1%}** of {m['n']} transactions "
            f"(catalogue merchants {m['accuracy_catalogue']:.1%}, long tail {m['accuracy_long_tail']:.1%}); "
            f"{m['distinct_merchants_correct']}/{m['distinct_merchants']} distinct merchants named exactly as labelled",
            f"- Cadence correct on matched streams: {main['cadence_accuracy']:.1%}; active/cancelled correct: {main['active_accuracy']:.1%}",
            "", "## Forgotten-subscription threshold trade-off", "",
            "| Score threshold | Precision | Recall | Flagged |", "|---|---|---|---|"]
    for t, v in thresholds.items():
        out.append(f"| ≥ {t} | {fmt(v['precision'])} | {fmt(v['recall'])} | {v['tp'] + v['fp']} |")
    out += ["", "## Where it goes wrong", "", "**Subscription false positives**", ""]
    out += [f"- {e['label']} ({e['cadence']}, {e['n']} charges), truth: {e['truth']}" for e in d["false_positives"]] or ["- none"]
    out += ["", "**Subscription false negatives**", ""]
    out += [f"- {e['merchant']}: {e['note']}" for e in d["false_negatives"]] or ["- none"]
    for f, v in main["flags"].items():
        if v["false_positives"] or v["false_negatives"]:
            out += ["", f"**{f}**: FP {v['false_positives'] or '-'}; FN {v['false_negatives'] or '-'}"]
    out += ["", "**Merchant-name mismatches** (label → predicted)", ""]
    out += [f"- {e['label']} → {e['predicted']} ({e['count']} txns)" for e in m["errors"]] or ["- none"]
    out += ["", "## Kind confusion (truth → predicted)", "", "| Truth | Predicted | Streams |", "|---|---|---|"]
    out += [f"| {k['truth']} | {k['predicted']} | {k['count']} |" for k in main["kind_confusion"]]
    if seeds:
        out += ["", "## Robustness across 5 re-generated households", "",
                "Seeds change descriptor variants, payment-day jitter and amounts; the persona is fixed, so this tests "
                "stability, not generalisation.", "", "| Metric | Mean | Min |", "|---|---|---|"]
        out += [f"| {k} | {v['mean']:.3f} | {v['min']:.3f} |" for k, v in seeds.items()]
    return "\n".join(out) + "\n"


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--data", type=Path, default=ROOT / "data" / "synthetic")
    p.add_argument("--out", type=Path, default=ROOT / "outputs")
    p.add_argument("--no-seeds", action="store_true")
    a = p.parse_args()
    frames = load_dir(a.data)
    main_eval = evaluate(*frames)
    thresholds = {t: evaluate(*frames, threshold=t)["flags"]["forgotten"] for t in (1, 2, 3)}
    seeds = None
    if not a.no_seeds and a.data == ROOT / "data" / "synthetic":
        runs = [evaluate(*seed_frames(s)) for s in range(1, 6)]
        metrics = {"subscription precision": lambda e: e["subscription_detection"]["precision"],
                   "subscription recall": lambda e: e["subscription_detection"]["recall"],
                   "merchant accuracy": lambda e: e["merchant"]["accuracy"],
                   **{f"{f} F1": (lambda f: lambda e: e["flags"][f]["f1"] or 0.0)(f) for f in FLAGS}}
        seeds = {k: dict(mean=sum(fn(r) for r in runs) / len(runs), min=min(fn(r) for r in runs))
                 for k, fn in metrics.items()}
    a.out.mkdir(parents=True, exist_ok=True)
    (a.out / "eval.json").write_text(json.dumps(dict(main=main_eval, forgotten_thresholds=thresholds, seeds=seeds),
                                                indent=2, default=str), encoding="utf-8")
    md = markdown(main_eval, thresholds, seeds)
    (a.out / "eval.md").write_text(md, encoding="utf-8")
    print(md)


if __name__ == "__main__":
    main()
