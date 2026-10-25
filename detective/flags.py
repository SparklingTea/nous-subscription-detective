"""Flags on detected subscriptions: price rises, duplicates, converted trials, 'probably forgotten'."""
from collections import defaultdict
from datetime import date, timedelta

from .streams import PER_YEAR, Stream, Txn

INTERMEDIARIES = {"paypal", "apple", "google_play"}
FORGOTTEN_THRESHOLD = 2
TRIAL_PRODUCTS = {"Apple Music", "Apple One Individual", "Kindle Unlimited", "Amazon Music Unlimited"}


def last_price_change(s: Stream):
    amounts = s.amounts
    if len({round(a, 2) for a in amounts}) > max(3, len(amounts) // 2):
        return None  # FX- or usage-driven amounts: no meaningful "price"
    last = amounts[-1]
    j = len(amounts) - 1
    while j > 0 and abs(amounts[j - 1] - last) <= 0.01:
        j -= 1
    if j == 0:
        return None
    return amounts[j - 1], last, s.txns[j].date, j


def apply_flags(streams: list[Stream], txns: list[Txn], data_start: date, data_end: date,
                threshold: int = FORGOTTEN_THRESHOLD):
    for s in streams:
        s.flags, s.forgotten_score, s.forgotten_reasons = {}, 0, []
        change = last_price_change(s)
        # A lone annual charge always lands "inside" a 13-month window, so it says nothing about being new
        new_in_window = s.first >= data_start + timedelta(days=35) and not (s.cadence_inferred and s.cadence == "annual")
        intro = False
        if change:
            old, new, when, j = change
            intro = new_in_window and j <= 2 and new >= old * 1.3
            if new > old * 1.02 and not intro and when >= data_end - timedelta(days=365):
                s.flags["price_rise"] = {"old": old, "new": new, "from": when.isoformat(),
                                         "pct": round(100 * (new / old - 1), 1),
                                         "annual_increase": round((new - old) * PER_YEAR[s.cadence], 2)}
        has_trial = s.entry is not None and s.entry.free_trial
        if s.entry is not None and s.entry.multi_product:
            has_trial = s.product in TRIAL_PRODUCTS  # "new Apple charge" alone says nothing about a trial
        if s.kind == "subscription" and new_in_window and (has_trial or intro):
            s.flags["trial_converted"] = {"first_charge": s.first.isoformat(), "intro_price": intro}

    active_subs = [s for s in streams if s.kind == "subscription" and s.active]
    dup_sets: list[tuple[str, list[Stream]]] = []
    by_merchant = defaultdict(list)
    by_group = defaultdict(list)
    for s in active_subs:
        if not (s.entry is not None and s.entry.multi_product):
            by_merchant[s.merchant].append(s)
        if s.exclusive_group:
            by_group[s.exclusive_group].append(s)
    for m, ss in by_merchant.items():
        if len(ss) > 1:
            dup_sets.append((f"{m} is being paid for twice", ss))
    for g, ss in by_group.items():
        if len({s.merchant for s in ss}) > 1:
            dup_sets.append((f"two {g.replace('_', ' ')} services", ss))
    # An unidentified platform charge at exactly another subscription's price is often the same service bought
    # twice (e.g. Disney+ direct, and again in-app on a child's iPad). Weak signal: ask, don't act.
    for s in active_subs:
        if s.entry is not None and s.entry.multi_product and s.exclusive_group is None:
            twins = [o for o in active_subs if o is not s and not (o.entry and o.entry.multi_product)
                     and abs(o.latest_amount - s.latest_amount) < 0.01]
            if twins:
                dup_sets.append((f"{s.merchant} charge matches {twins[0].merchant}'s price: possibly bought twice",
                                 [s, *twins]))
    for reason, ss in dup_sets:
        for s in ss:
            s.flags["duplicate"] = {"reason": reason, "with": [o.label for o in ss if o is not s]}
        # The one billed through an intermediary (less visible on a statement), then the cheaper, is likelier forgotten
        weakest = sorted(ss, key=lambda s: (s.channel not in INTERMEDIARIES, s.latest_amount))[0]
        weakest.forgotten_score += 2
        weakest.forgotten_reasons.append(f"duplicate: {reason}")

    last_seen = defaultdict(lambda: None)
    for t in txns:
        if t.amount > 0 and (last_seen[t.merchant] is None or t.date > last_seen[t.merchant]):
            last_seen[t.merchant] = t.date
    for s in active_subs:
        um = s.entry.usage_merchant if s.entry is not None else None
        if um:
            seen = last_seen[um]
            if seen is None or seen < data_end - timedelta(days=60):
                s.forgotten_score += 2
                s.forgotten_reasons.append(f"no {um} spend since {seen.isoformat() if seen else 'ever'}")
        if "trial_converted" in s.flags:
            s.forgotten_score += 1
            s.forgotten_reasons.append("started as a free trial / intro offer")
        if s.channel in INTERMEDIARIES:
            s.forgotten_score += 1
            s.forgotten_reasons.append(f"billed via {s.channel}, easy to miss on a statement")
        if s.forgotten_score >= threshold:
            s.flags["forgotten"] = {"score": s.forgotten_score, "reasons": s.forgotten_reasons}
