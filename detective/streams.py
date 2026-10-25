"""Group normalised debits into payment streams and decide which are genuinely recurring."""
import statistics
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta

from .catalogue import Merchant, apple_like_product

CADENCES = {"weekly": (7, 2), "fortnightly": (14, 3), "monthly": (30.44, 4), "quarterly": (91.3, 10),
            "annual": (365.25, 20)}
MIN_CHARGES = {"weekly": 4, "fortnightly": 3, "monthly": 3, "quarterly": 3, "annual": 2}
PER_YEAR = {"weekly": 52, "fortnightly": 26, "monthly": 12, "quarterly": 4, "annual": 1}

SUB_KEYWORDS = ("GYM", "FITNESS", "CLIMB", "YOGA", "CLUB", "MEMBERSHIP", "SUBSCR", "PREMIUM", "MAGAZINE")
OTHER_KEYWORDS = ("RENT", "SAVINGS", "TRANSFER", "LOAN", "MORTGAGE", "CHARITY", "OXFAM", "DONATION", "SALARY")


@dataclass
class Txn:
    id: str
    date: date
    description: str
    amount: float  # positive = money out
    type: str
    merchant: str
    channel: str
    entry: Merchant | None
    cleaned: str


@dataclass
class Stream:
    id: str
    merchant: str
    channel: str
    entry: Merchant | None
    txns: list[Txn]
    cadence: str | None = None
    cadence_inferred: bool = False
    regularity: float = 0.0
    kind: str = "other"
    active: bool = False
    product: str | None = None
    exclusive_group: str | None = None
    confidence: float = 0.0
    flags: dict = field(default_factory=dict)
    forgotten_score: int = 0
    forgotten_reasons: list[str] = field(default_factory=list)

    @property
    def dates(self):
        return [t.date for t in self.txns]

    @property
    def amounts(self):
        return [t.amount for t in self.txns]

    @property
    def first(self):
        return self.txns[0].date

    @property
    def last(self):
        return self.txns[-1].date

    @property
    def latest_amount(self):
        return self.txns[-1].amount

    @property
    def annual_cost(self):
        return round(self.latest_amount * PER_YEAR.get(self.cadence or "", 0), 2)

    @property
    def label(self):
        return f"{self.merchant} ({self.product})" if self.product else self.merchant


def detect_cadence(dates: list[date]) -> tuple[str | None, float]:
    intervals = [(b - a).days for a, b in zip(dates, dates[1:])]
    if not intervals:
        return None, 0.0
    best, best_score = None, 0.0
    for name, (period, tol) in CADENCES.items():
        if len(dates) < MIN_CHARGES[name]:
            continue
        ones = sum(abs(iv - period) <= tol for iv in intervals)
        # A skipped week/month (HelloFresh skip, council tax's Feb/Mar gap) shouldn't break the pattern
        skips = sum(abs(iv - period) > tol and any(abs(iv - k * period) <= tol * k for k in (2, 3)) for iv in intervals)
        if ones / len(intervals) >= 0.5:
            score = (ones + skips) / len(intervals)
            if score >= 0.8 and score > best_score:
                best, best_score = name, score
    return best, best_score


def amount_is_stable(amounts: list[float]) -> bool:
    if len(amounts) < 2:
        return True
    changes = sum(abs(b - a) > max(0.01 * a, 0.02) for a, b in zip(amounts, amounts[1:]))
    cv = statistics.pstdev(amounts) / statistics.mean(amounts)
    return changes <= max(1, len(amounts) // 4) or cv < 0.06  # step price changes, or FX wobble


def split_by_amount(txns: list[Txn], tol=0.25, min_gap=0) -> list[list[Txn]]:
    clusters: list[list[Txn]] = []
    for t in txns:
        best, best_diff = None, None
        for c in clusters:
            ref = c[-1].amount
            diff = abs(t.amount - ref) / max(ref, 0.01)
            if diff <= tol and (t.date - c[-1].date).days >= min_gap and (best_diff is None or diff < best_diff):
                best, best_diff = c, diff
        if best is None:
            clusters.append([t])
        else:
            best.append(t)
    return clusters


def merge_sequential(clusters: list[list[Txn]], max_gap=45) -> list[list[Txn]]:
    """Clusters that follow each other in time are one subscription changing price (intro offer, rise)."""
    clusters = sorted(clusters, key=lambda c: c[0].date)
    merged: list[list[Txn]] = []
    for c in clusters:
        for m in merged:
            if m[-1].date < c[0].date and (c[0].date - m[-1].date).days <= max_gap:
                m.extend(c)
                break
        else:
            merged.append(list(c))
    return merged


def infer_kind(s: Stream) -> str:
    if s.entry is not None:
        return s.entry.kind
    text = s.txns[-1].description.upper()
    if any(k in text for k in OTHER_KEYWORDS):
        return "other"
    if any(k in text for k in SUB_KEYWORDS):
        return "subscription"
    if s.txns[-1].type in ("STANDING ORDER", "FASTER PAYMENT"):
        return "other"
    if s.txns[-1].type == "DIRECT DEBIT":
        return "other"  # unknown DDs are usually bills/loans/donations; surface, don't assume
    return "subscription"  # fixed-amount, regular card payment to an unknown merchant


def build_streams(txns: list[Txn], data_end: date) -> list[Stream]:
    groups: dict[tuple, list[Txn]] = defaultdict(list)
    for t in txns:
        if t.amount <= 0:
            continue
        if t.entry is not None and t.entry.kind in ("retail", "transport"):
            continue
        groups[(t.merchant, t.channel)].append(t)

    streams: list[Stream] = []
    for (merchant, channel), group in groups.items():
        group.sort(key=lambda t: t.date)
        entry = group[0].entry
        if entry is not None and entry.kind == "bill":
            # Bills drift with usage, so split only where two products share a biller (energy + boiler cover)
            clusters = merge_sequential(split_by_amount(group, tol=0.35, min_gap=4))
        else:
            if entry is not None and entry.kind == "subscription":
                # min_gap lets two same-priced plans on one platform separate; for unknown merchants it would
                # carve a cadence out of daily habits (a coffee every morning), so it's known merchants only
                clusters = merge_sequential(split_by_amount(group, min_gap=4))
            else:
                clusters = split_by_amount(group)
        for i, c in enumerate(sorted(clusters, key=lambda c: c[0].date)):
            c.sort(key=lambda t: t.date)
            s = Stream(id=f"{merchant}|{channel}|{i}", merchant=merchant, channel=channel, entry=entry, txns=c)
            s.cadence, s.regularity = detect_cadence(s.dates)
            known_sub = entry is not None and entry.kind == "subscription"
            if s.cadence is None and known_sub:
                if len(c) == 2 and abs((c[1].date - c[0].date).days - 30.44) <= 4:
                    s.cadence, s.regularity, s.cadence_inferred = "monthly", 0.6, True  # new sub, only 2 charges so far
                elif len(c) == 1 and entry.annual_ok and c[0].amount >= 30:
                    s.cadence, s.regularity, s.cadence_inferred = "annual", 0.5, True
            if s.cadence is None:
                continue
            if entry is None and not amount_is_stable(s.amounts):
                continue
            s.kind = infer_kind(s)
            period, tol = CADENCES[s.cadence]
            s.active = s.last + timedelta(days=period + max(7, 2 * tol)) >= data_end
            if entry is not None and entry.multi_product:
                s.product, s.exclusive_group = apple_like_product(entry, s.latest_amount)
            elif entry is not None:
                s.exclusive_group = entry.exclusive_group
            s.confidence = round(min(0.99, 0.35 + 0.25 * (entry is not None) + 0.3 * s.regularity
                                     + 0.02 * min(len(c), 6) - 0.15 * s.cadence_inferred), 2)
            streams.append(s)
    return streams
