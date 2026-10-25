# Subscription detective: evaluation

## Headline

| Task | Precision | Recall | F1 | TP / FP / FN |
|---|---|---|---|---|
| Subscription detection (stream level) | 1.00 | 1.00 | 1.00 | 21 / 0 / 0 |
| Flag: price_rise | 1.00 | 1.00 | 1.00 | 7 / 0 / 0 |
| Flag: duplicate | 1.00 | 1.00 | 1.00 | 6 / 0 / 0 |
| Flag: trial_converted | 1.00 | 1.00 | 1.00 | 4 / 0 / 0 |
| Flag: forgotten | 1.00 | 0.80 | 0.89 | 4 / 0 / 1 |

- Merchant cleanup accuracy: **81.5%** of 967 transactions (catalogue merchants 100.0%, long tail 36.3%); 40/42 distinct merchants named exactly as labelled
- Cadence correct on matched streams: 100.0%; active/cancelled correct: 100.0%

## Forgotten-subscription threshold trade-off

| Score threshold | Precision | Recall | Flagged |
|---|---|---|---|
| ≥ 1 | 0.62 | 1.00 | 8 |
| ≥ 2 | 1.00 | 0.80 | 4 |
| ≥ 3 | 1.00 | 0.60 | 3 |

## Where it goes wrong

**Subscription false positives**

- none

**Subscription false negatives**

- none

**forgotten**: FP -; FN ['NOW (7-day trial for one series, never cancelled)']

**Merchant-name mismatches** (label → predicted)

- Gail's → Gails Bakery (167 txns)
- Savings transfer → Transfer To Savings (12 txns)

## Kind confusion (truth → predicted)

| Truth | Predicted | Streams |
|---|---|---|
| bill | bill | 6 |
| other | other | 3 |
| subscription | subscription | 21 |

## Robustness across 5 re-generated households

Seeds change descriptor variants, payment-day jitter and amounts; the persona is fixed, so this tests stability, not generalisation.

| Metric | Mean | Min |
|---|---|---|
| subscription precision | 0.991 | 0.955 |
| subscription recall | 1.000 | 1.000 |
| merchant accuracy | 0.816 | 0.806 |
| price_rise F1 | 1.000 | 1.000 |
| duplicate F1 | 1.000 | 1.000 |
| trial_converted F1 | 1.000 | 1.000 |
| forgotten F1 | 0.889 | 0.889 |
