# Subscription detective: evaluation

## Headline

| Task | Precision | Recall | F1 | TP / FP / FN |
|---|---|---|---|---|
| Subscription detection (stream level) | 0.88 | 0.78 | 0.82 | 14 / 2 / 4 |
| Flag: price_rise | 1.00 | 1.00 | 1.00 | 4 / 0 / 0 |
| Flag: duplicate | n/a | 0.00 | n/a | 0 / 0 / 4 |
| Flag: trial_converted | 0.33 | 0.25 | 0.29 | 1 / 2 / 3 |
| Flag: forgotten | 0.50 | 0.33 | 0.40 | 1 / 1 / 2 |

- Merchant cleanup accuracy: **37.2%** of 804 transactions (catalogue merchants 89.3%, long tail 3.1%); 17/32 distinct merchants named exactly as labelled
- Cadence correct on matched streams: 100.0%; active/cancelled correct: 100.0%

## Forgotten-subscription threshold trade-off

| Score threshold | Precision | Recall | Flagged |
|---|---|---|---|
| ≥ 1 | 0.17 | 0.33 | 6 |
| ≥ 2 | 0.50 | 0.33 | 2 |
| ≥ 3 | n/a | 0.00 | 0 |

## Where it goes wrong

**Subscription false positives**

- Junior Football Club Cd (weekly, 46 charges), truth: other
- Klarna (monthly, 3 charges), truth: other

**Subscription false negatives**

- Amazon Kindle Unlimited: Shares the generic AMZN descriptor with shopping
- Duolingo: Annual via Google Play, single charge
- Uber One: Descriptor is 'UBER *ONE', not 'UBER ONE'
- Deliveroo Plus: Descriptor truncated by the bank

**duplicate**: FP -; FN ['Disney+ (nan)', "Apple (Second Disney+ bought in-app on a child's iPad (statement just says Apple, £8.99))", 'Dropbox (Old Dropbox Plus alongside Google One)', 'Google One (nan)']

**trial_converted**: FP ['Apple', 'Apple']; FN ['Apple (Calm annual after 7-day trial; single charge)', 'Deliveroo Plus (Descriptor truncated by the bank)', 'New York Times (USD-billed intro rate; not in catalogue)']

**forgotten**: FP ['Apple']; FN ['Dropbox (Old Dropbox Plus alongside Google One)', 'PlayStation Plus (Child stopped playing in spring: no signal in bank data)']

**Merchant-name mismatches** (label → predicted)

- Bee Network → Bee Network Bus (142 txns)
- Greggs → Greggs Cd (92 txns)
- Costa → Costa Coffee Cd (60 txns)
- Junior Football Club → Junior Football Club Cd (46 txns)
- Aldi → Aldi Cd (44 txns)
- Nationwide → Nationwide Mortgage (13 txns)
- The Gym Group → Gym (13 txns)
- M Kowalski → M Kowalski Cleaning (13 txns)
- Uber One → Uber (13 txns)
- Dropbox → Dropbox Cd (13 txns)
- YouTube Premium → Youtube (12 txns)
- Amazon Kindle Unlimited → Amazon (12 txns)
- Council Tax → Manchester City Council (11 txns)
- New York Times → Nytimes (10 txns)
- Deliveroo Plus → Deliveroo (9 txns)
- Klarna → Klarna Zara (2 txns)

## Kind confusion (truth → predicted)

| Truth | Predicted | Streams |
|---|---|---|
| bill | bill | 2 |
| bill | missed | 2 |
| bill | other | 1 |
| other | missed | 1 |
| other | other | 2 |
| other | subscription | 2 |
| subscription | missed | 4 |
| subscription | subscription | 14 |
