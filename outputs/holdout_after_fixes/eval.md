# Subscription detective: evaluation

## Headline

| Task | Precision | Recall | F1 | TP / FP / FN |
|---|---|---|---|---|
| Subscription detection (stream level) | 0.95 | 1.00 | 0.97 | 18 / 1 / 0 |
| Flag: price_rise | 1.00 | 1.00 | 1.00 | 4 / 0 / 0 |
| Flag: duplicate | 0.67 | 1.00 | 0.80 | 4 / 2 / 0 |
| Flag: trial_converted | 1.00 | 0.75 | 0.86 | 3 / 0 / 1 |
| Flag: forgotten | 0.33 | 0.33 | 0.33 | 1 / 2 / 2 |

- Merchant cleanup accuracy: **70.1%** of 804 transactions (catalogue merchants 96.9%, long tail 46.0%); 27/32 distinct merchants named exactly as labelled
- Cadence correct on matched streams: 100.0%; active/cancelled correct: 100.0%

## Forgotten-subscription threshold trade-off

| Score threshold | Precision | Recall | Flagged |
|---|---|---|---|
| ≥ 1 | 0.11 | 0.33 | 9 |
| ≥ 2 | 0.33 | 0.33 | 3 |
| ≥ 3 | 0.33 | 0.33 | 3 |

## Where it goes wrong

**Subscription false positives**

- Junior Football Club (weekly, 46 charges), truth: other

**Subscription false negatives**

- none

**duplicate**: FP ['Apple', 'Paramount+']; FN -

**trial_converted**: FP -; FN ['Apple (Calm annual after 7-day trial; single charge)']

**forgotten**: FP ['Apple', 'Google One']; FN ['Dropbox (Old Dropbox Plus alongside Google One)', 'PlayStation Plus (Child stopped playing in spring: no signal in bank data)']

**Merchant-name mismatches** (label → predicted)

- Bee Network → Bee Network Bus (142 txns)
- Costa → Costa Coffee (60 txns)
- Nationwide → Nationwide Mortgage (13 txns)
- M Kowalski → M Kowalski Cleaning (13 txns)
- Amazon Kindle Unlimited → Amazon Digital (12 txns)

## Kind confusion (truth → predicted)

| Truth | Predicted | Streams |
|---|---|---|
| bill | bill | 5 |
| other | bnpl | 1 |
| other | missed | 1 |
| other | other | 2 |
| other | subscription | 1 |
| subscription | subscription | 18 |
