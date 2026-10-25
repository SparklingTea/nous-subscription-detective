"""End to end: CSV -> normalised transactions -> streams -> flags -> actions -> outputs/."""
import argparse
import json
from pathlib import Path

import pandas as pd

from .flags import FORGOTTEN_THRESHOLD, apply_flags
from .loader import load
from .normalise import normalise
from .savings import cancel_route, load_kb, recommend
from .streams import Stream, Txn, build_streams


def to_txns(df: pd.DataFrame) -> list[Txn]:
    txns = []
    for row in df.itertuples(index=False):
        n = normalise(row.description)
        txns.append(Txn(id=str(row.id), date=row.date, description=row.description, amount=-float(row.amount),
                        type=row.type, merchant=n.merchant, channel=n.channel, entry=n.entry, cleaned=n.cleaned))
    return txns


def stream_record(s: Stream, kb: dict) -> dict:
    route = cancel_route(s, kb) if s.kind == "subscription" else None
    return dict(id=s.id, merchant=s.merchant, label=s.label, product=s.product, channel=s.channel, kind=s.kind,
                category=s.entry.category if s.entry is not None else None, known_merchant=s.entry is not None,
                cadence=s.cadence, cadence_inferred=s.cadence_inferred, regularity=round(s.regularity, 2),
                active=s.active, confidence=s.confidence, n=len(s.txns), first=s.first.isoformat(),
                last=s.last.isoformat(), latest_amount=s.latest_amount, annual_cost=s.annual_cost,
                flags=s.flags, forgotten_score=s.forgotten_score,
                cancel=route and {k: route.get(k) for k in ("key", "name", "method", "route", "automatable",
                                                            "dark_patterns", "gotchas", "confidence", "fallback")},
                txn_ids=[t.id for t in s.txns], descriptions=sorted({t.description for t in s.txns})[:4])


def run(df: pd.DataFrame, threshold: int = FORGOTTEN_THRESHOLD):
    txns = to_txns(df)
    start, end = min(t.date for t in txns), max(t.date for t in txns)
    streams = build_streams(txns, end)
    apply_flags(streams, txns, start, end, threshold)
    kb = load_kb()
    streams.sort(key=lambda s: (s.kind != "subscription", not s.active, -s.annual_cost))
    return dict(period={"start": start.isoformat(), "end": end.isoformat(), "transactions": len(txns)},
                streams=[stream_record(s, kb) for s in streams],
                summary=recommend(streams, kb)), txns


def main():
    p = argparse.ArgumentParser()
    p.add_argument("csv", type=Path)
    p.add_argument("--out", type=Path, default=Path("outputs"))
    p.add_argument("--flip-sign", action="store_true", help="for exports where purchases are positive")
    p.add_argument("--threshold", type=int, default=FORGOTTEN_THRESHOLD)
    a = p.parse_args()
    result, txns = run(load(a.csv, a.flip_sign), a.threshold)
    a.out.mkdir(parents=True, exist_ok=True)
    (a.out / "result.json").write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    pd.DataFrame([dict(id=t.id, date=t.date, description=t.description, amount=-t.amount, merchant=t.merchant,
                       channel=t.channel) for t in txns]).to_csv(a.out / "transactions_normalised.csv", index=False)
    s = result["summary"]
    print(f"{s['active_subscriptions']} active subscriptions, £{s['annual_subscription_spend']:.2f}/yr")
    print(f"£ back in pocket: £{s['back_in_pocket_identified']:.2f}/yr identified, "
          f"£{s['back_in_pocket_expected']:.2f}/yr expected after cancellation success rates")
    for st in result["streams"]:
        if st["kind"] == "subscription":
            fl = ",".join(st["flags"]) or "-"
            print(f"  {'ON ' if st['active'] else 'off'} {st['label']:<34} {st['cadence']:<8} £{st['latest_amount']:>7.2f}  {fl}")


if __name__ == "__main__":
    main()
