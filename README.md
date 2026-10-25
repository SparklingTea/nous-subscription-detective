# Subscription detective

A working prototype of the logic behind a subscription-cancelling agent: read a bank statement, find the
recurring payments, clean up the merchant names, flag what's worth acting on, work out how each one is
actually cancelled, and cancel the ones that can be automated safely. It finishes with a **£ back in pocket** figure.

Built as a take-home for the Product Builder role at Nous.

```bash
pip install -r requirements.txt
python data/generate.py && python data/generate.py --holdout      # two synthetic households + labels
python -m detective.pipeline data/synthetic/transactions.csv      # detect, flag, recommend
python -m eval.evaluate                                           # precision / recall vs labels
python -m cancellation.demo                                       # agent vs four mock cancellation flows
python -m pytest -q tests
streamlit run app.py                                              # everything above, plus upload your own CSV
```

## Results

### £ back in pocket (dev household, 13 months, 967 transactions)

| | |
|---|---|
| Active subscriptions found | 20, costing **£4,937/yr** (£2,339 of that is one HelloFresh box a week) |
| Suggested cancellations | Apple Music (left running next to Spotify after its trial), an old Netflix account still billing through PayPal, Deliveroo Plus with no orders since April, Google One next to iCloud+ |
| **Back in pocket** | **£265/yr identified, £240/yr expected** once each cancellation is discounted by an assumed success rate for its route |
| Also surfaced, not counted | 3 "trial converted, still want it?" checks (NOW, Audible, HelloFresh) and £190/yr of price rises across 3 subscriptions and 4 bills. The bill rises are the trigger for Nous's switching products |

### Precision / recall

Each household was hand-labelled at transaction level (merchant, stream) and stream level (kind, cadence, flags).
A predicted stream counts as a match when it shares at least 50% of its transactions with a labelled one.

| | Dev household | **Held-out: first run (blind)** | Held-out: after one fix round |
|---|---|---|---|
| Subscription detection P / R | 1.00 / 1.00 | **0.88 / 0.78** | 0.95 / 1.00 |
| Price rise F1 | 1.00 | **1.00** | 1.00 |
| Duplicate F1 | 1.00 | **0.00** (0 of 4 found) | 0.80 |
| Trial converted F1 | 1.00 | **0.29** | 0.86 |
| Probably forgotten F1 | 0.89 | **0.40** | 0.33 |
| Distinct merchants named correctly | 40 / 42 | **17 / 32** | 27 / 32 |

**Read the middle column.** I wrote the detector against the dev household, so its perfect scores mostly show
that I wrote both halves. The held-out household (a Manchester family, Lloyds-style descriptors) was written
to break the detector and scored once before I changed anything. The right-hand column is after one round of
error analysis, so it's no longer blind. Its value is the list of what broke:

| Failure class (held-out) | Example | Fix |
|---|---|---|
| Bank formatting | `GREGGS PLC CD 4471` card suffix; `DELIVEROO PLU` truncated, so it matched Deliveroo *orders* | Strip card suffixes; prefix patterns for truncated names |
| Trading vs brand names | `THE GYM LTD`, `MANCHESTER CITY COUNCIL`, `UBER *ONE` | Aliases in the catalogue. Done properly this is a merchant DB that keeps growing, not regexes |
| Looks like a sub, isn't | Klarna pay-in-3 (fixed monthly card payment), weekly £6 junior football | BNPL is now its own kind. **Football is still a false positive**: nothing in the bank data separates pay-as-you-go from a subscription |
| Platform billers hide the product | `APPLE.COM/BILL £8.99`: iCloud 2TB, Apple TV+, or a second Disney+ bought on a child's iPad? | Flag a platform charge at the exact price of another sub as "possibly bought twice". Weak signal: it also fired on Roblox (£4.99) vs Paramount+ (£4.99) |
| Same biller, two products | British Gas energy + boiler cover merged into one irregular stream | Split bills only where charges overlap in time |

### What the numbers say about the product

1. **"Probably forgotten" can't be inferred from bank data well, so don't try too hard.** It stayed at
   0.33 F1 on the held-out household. In the misses, the child stopped playing PlayStation and
   the old Dropbox is the forgotten one, not Google One. Both are facts about use, and a statement doesn't show use. The product
   answer is to ask: *"You're paying for Dropbox and Google One. Which do you actually use?"* That costs the member one
   reply, and the agent stops acting on a guess. The signals that did work are duplicates, and membership with no
   matching spend (Deliveroo Plus with no Deliveroo orders).
2. **Where you set the threshold is a product decision.** On the dev set, a forgotten-score of 1 or more catches every forgotten sub
   at 0.62 precision, and 2 or more gets 1.00 precision at 0.80 recall. A false flag costs a tap and a missed one costs money, so
   for a *suggest* step I'd run it loose. For an *act* step it has to be strict, with the member confirming first.
3. **The billing channel matters more than the brand.** Netflix through PayPal, Disney+ through Apple and YouTube
   through Google each cancel somewhere different. Every stream records its channel because that decides the route.
4. **Price rises are the most reliable signal (F1 1.00 on both households) and the least glamorous.** They're
   also where subscriptions overlap with Nous's bills products: 4 of the 7 rises on the dev set were council tax,
   broadband, mobile and TV licence.

## The hard half: how UK subscriptions actually get cancelled

[`cancellation/uk_subscriptions.yaml`](cancellation/uk_subscriptions.yaml) maps 29 UK subscriptions: route, notice,
dark patterns, gotchas, whether it can be automated, and how confident the research is.

- **17 automatable** (online self-serve), **10 automatable with a hand-off** (2FA code, or consent because
  money or credits are at stake), **2 not automatable** (Sky by phone, The Times by phone or chat).
- Recurring dark patterns: retention mazes where "keep" is the primary button (Amazon Prime), cancel only on desktop and
  not in the app (Spotify, Audible, Disney+), fees disclosed on the last page (Adobe's annual-paid-monthly early
  termination fee), weekly cut-offs that quietly charge you one more box (HelloFresh, Gousto), lost credits (Audible).
- Backstops that work for any merchant: stopping a continuous payment authority at the bank, cancelling a
  Direct Debit (which stops the money but not the contract), and PayPal automatic payments.
- **Caveat:** this is desk research, and 16 of the 29 entries are medium or low confidence. Flows change constantly. Before an
  agent runs a flow for real members, someone should walk it by hand or with the agent in record mode.

### The agent prototype

[`cancellation/agent.py`](cancellation/agent.py) runs against four local mocks
([`mock_sites.py`](cancellation/mock_sites.py)). Each mock is built around the obstacle that makes its real flow hard:

| Flow | Obstacle | Outcome |
|---|---|---|
| Netflix-like | none | cancelled in 5 steps |
| Prime-like | 3 retention screens, "Keep my benefits" styled as the big button | cancelled; ignored 6 retention options along the way |
| Apple-like | 2FA code sent to the member's phone; two products on one account | paused, asked the member over chat, carried on, cancelled **Apple Music, not iCloud** |
| Adobe-like | £29.94 early termination fee on the final page | **stopped and asked**, quoting the fee. With consent, it cancelled |

It's rule-based on purpose. Picking "Continue to cancel" over "Keep my benefits" is word-list
classification, and the mistakes that cost money (paying a fee, losing credits, typing a 2FA code) are hard stops,
not judgement calls. An LLM is the obvious upgrade for *navigating* unfamiliar sites, but it shouldn't own the stop
conditions. The first run of the demo caught a broken guardrail: the agent paid the Adobe fee. There's now a test
for exactly that (`test_agent_never_pays_a_fee_without_consent`).

For the routes it doesn't automate, it produces the hand-off instead: a phone script with a walk-away price for Sky,
a cancellation email, and a request to stop a continuous payment authority at the bank.

## How it works

```
CSV ─► loader (Monzo / Starling / Barclays / Lloyds / HSBC layouts)
    ─► normalise: strip processors (PAYPAL *, GOOGLE *, SQ *), record billing channel,
                  catalogue match (58 merchants) → fuzzy match → cleaned fallback
    ─► streams:   group by merchant + channel, split by amount (so Apple's £2.99 and £10.99 stay
                  separate), re-join price changes and intro offers, detect cadence that tolerates
                  skipped weeks and months, drop unstable amounts for unknown merchants
    ─► flags:     price rise · duplicate (same service twice / same exclusive need / price twin) ·
                  trial converted · forgotten score
    ─► actions:   cancel · pick one · still want it? → £ identified and £ expected
```

## Limitations, honestly

- **Synthetic data.** Both households are generated, and I wrote both the labels and the detector. The held-out
  first run is the fairest number here, and it's still mine. The next step is real statements:
  `streamlit run app.py` → *Upload my own CSV*, then label in the same three-file layout and run
  `python -m eval.evaluate --data <dir>`.
- **One household per set.** n=21 and n=18 subscription streams. A single error moves recall by about 5 points.
- **The success rates behind "expected £" are assumptions** (online 95%, phone 70% and so on), not measured.
- **The agent runs on mocks, not real sites.** Production would drive Playwright through the same `fetch`/`submit` interface.

## What I'd do in week one at Nous

1. Run the detector over a sample of real Open Banking data and hand-label 200 streams, oversampling platform
   billers (Apple, Google, PayPal, Amazon), BNPL, and long-tail merchants.
2. Measure how often a member says "I still use that" to each suggestion. That's the real precision of "forgotten",
   and it would tell us whether to suggest or act.
3. Rank the cancellation map by £ flowing through each merchant multiplied by how hard it is to cancel, and automate from the top.
