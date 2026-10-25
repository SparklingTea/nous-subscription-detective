"""Synthetic 13-month current-account statement for one London household, plus ground-truth labels.

The detector only ever sees transactions.csv (date, description, amount, type). The two
labels_*.csv files play the role of a hand-labelled answer key.

Prices are illustrative, not quotes of current UK pricing.
"""
import argparse
import csv
import random
import string
from calendar import monthrange
from datetime import date, timedelta
from pathlib import Path

START = date(2025, 10, 1)
END = date(2026, 10, 20)

CARD, DD, SO, FP, CREDIT = "CARD PAYMENT", "DIRECT DEBIT", "STANDING ORDER", "FASTER PAYMENT", "CREDIT"


def months(start: date, end: date):
    y, m = start.year, start.month
    while date(y, m, 1) <= end:
        yield y, m
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)


def next_business_day(d: date) -> date:
    while d.weekday() >= 5:
        d += timedelta(days=1)
    return d


class Household:
    def __init__(self, seed: int):
        self.r = random.Random(seed)
        self.txns: list[dict] = []
        self.streams: list[dict] = []

    def ref(self, n=8, digits_only=False):
        alphabet = string.digits if digits_only else string.ascii_uppercase + string.digits
        return "".join(self.r.choice(alphabet) for _ in range(n))

    def add(self, d, desc, amount, ttype, merchant, stream=""):
        if START <= d <= END:
            self.txns.append(dict(date=d, description=desc, amount=round(amount, 2), type=ttype,
                                  merchant=merchant, stream=stream))

    def label(self, sid, merchant, kind, cadence, active, flags=(), note=""):
        self.streams.append(dict(stream_id=sid, merchant=merchant, kind=kind, cadence=cadence, active=active,
                                 price_rise="price_rise" in flags, duplicate="duplicate" in flags,
                                 trial_converted="trial_converted" in flags, forgotten="forgotten" in flags,
                                 note=note))

    def monthly(self, sid, merchant, descs, amount, ttype, day, start=START, end=END, jitter=1,
                business=False, skip_months=()):
        """amount: float or callable(charge_index, date) -> float. descs: list of templates using {ref}."""
        i = 0
        for y, m in months(start, end):
            if m in skip_months:
                continue
            d = date(y, m, min(day, monthrange(y, m)[1])) + timedelta(days=self.r.randint(0, jitter))
            if business:
                d = next_business_day(d)
            if d < start or d > end:
                continue
            amt = amount(i, d) if callable(amount) else amount
            desc = self.r.choice(descs).format(ref=self.ref(), ref10=self.ref(10), num=self.ref(4, True))
            self.add(d, desc, -amt, ttype, merchant, sid)
            i += 1

    def scatter(self, merchant, descs, lo, hi, per_month, start=START, end=END, weekdays=None, ttype=CARD):
        d = start
        while d <= end:
            if weekdays is None or d.weekday() in weekdays:
                if self.r.random() < per_month / 30:
                    desc = self.r.choice(descs).format(ref=self.ref(), num=self.ref(4, True))
                    self.add(d, desc, -round(self.r.uniform(lo, hi), 2), ttype, merchant)
            d += timedelta(days=1)


def price_step(old, new, from_date):
    return lambda i, d: new if d >= from_date else old


def build(seed: int) -> Household:
    h = Household(seed)
    r = h.r

    # --- Income and transfers (not subscriptions) ---
    for y, m in months(START, END):
        d = date(y, m, 25)
        while d.weekday() >= 5:
            d -= timedelta(days=1)
        h.add(d, "ACME ANALYTICS LTD SALARY", 3450.00, CREDIT, "Acme Analytics")
    h.monthly("rent", "J Smith", ["J SMITH RENT"], 1650.00, SO, 1, jitter=0, business=True)
    h.label("rent", "J Smith", "other", "monthly", True, note="Rent standing order")
    h.monthly("savings", "Savings transfer", ["TRANSFER TO SAVINGS 20-11-44 4471{num}"], 300.00, SO, 26, jitter=0, business=True)
    h.label("savings", "Savings transfer", "other", "monthly", True)
    h.monthly("oxfam", "Oxfam", ["OXFAM"], 10.00, DD, 5, jitter=0, business=True)
    h.label("oxfam", "Oxfam", "other", "monthly", True, note="Charity direct debit: recurring but not a subscription")

    # --- Household bills (switchable, but not 'subscriptions') ---
    h.monthly("ctax", "Council Tax", ["LB ISLINGTON CTAX"], price_step(152.40, 160.10, date(2026, 4, 1)), DD, 15,
              jitter=0, business=True, skip_months=(2, 3))
    h.label("ctax", "Council Tax", "bill", "monthly", True, flags=("price_rise",), note="10 instalments: Feb/Mar gap")
    h.monthly("energy", "Octopus Energy", ["OCTOPUS ENERGY"],
              lambda i, d: round({1: 138, 2: 131, 12: 129, 11: 112, 3: 115, 10: 96}.get(d.month, 84) + r.uniform(-4, 4), 2),
              DD, 3, jitter=0, business=True)
    h.label("energy", "Octopus Energy", "bill", "monthly", True, note="Seasonal variable direct debit")
    h.monthly("broadband", "Virgin Media", ["VIRGIN MEDIA PYMTS"], price_step(38.00, 40.50, date(2026, 4, 1)), DD, 12,
              jitter=0, business=True)
    h.label("broadband", "Virgin Media", "bill", "monthly", True, flags=("price_rise",), note="April mid-contract rise")
    h.monthly("mobile", "EE", ["EE LIMITED"], price_step(22.00, 23.20, date(2026, 4, 1)), DD, 8, jitter=0, business=True)
    h.label("mobile", "EE", "bill", "monthly", True, flags=("price_rise",))
    h.monthly("tvl", "TV Licence", ["TV LICENCE MBP"], price_step(14.54, 14.95, date(2026, 4, 1)), DD, 1, jitter=0, business=True)
    h.label("tvl", "TV Licence", "bill", "monthly", True, flags=("price_rise",))
    h.monthly("water", "Thames Water", ["THAMES WATER"], 38.00, DD, 20, jitter=0, business=True)
    h.label("water", "Thames Water", "bill", "monthly", True)

    # --- Subscriptions ---
    h.monthly("netflix", "Netflix", ["NETFLIX.COM 866-579-7172", "NETFLIX.COM AMSTERDAM NL", "Netflix.com"],
              price_step(12.99, 14.99, date(2026, 6, 1)), CARD, 7)
    h.label("netflix", "Netflix", "subscription", "monthly", True, flags=("price_rise", "duplicate"))
    h.monthly("netflix_pp", "Netflix", ["PAYPAL *NETFLIX.COM 35314369001", "PAYPAL *NETFLIX COM"], 5.99, CARD, 18)
    h.label("netflix_pp", "Netflix", "subscription", "monthly", True, flags=("duplicate", "forgotten"),
            note="Old ad-tier account still billing via PayPal")
    h.monthly("spotify", "Spotify", ["Spotify P{ref10}", "SPOTIFY UK", "Spotify Stockholm SE"],
              price_step(11.99, 12.99, date(2026, 4, 1)), CARD, 22)
    h.label("spotify", "Spotify", "subscription", "monthly", True, flags=("price_rise", "duplicate"))
    h.monthly("apple_music", "Apple", ["APPLE.COM/BILL ITUNES.COM", "APPLE.COM/BILL CORK IE"], 10.99, CARD, 3,
              start=date(2026, 1, 3))
    h.label("apple_music", "Apple", "subscription", "monthly", True,
            flags=("duplicate", "trial_converted", "forgotten"), note="Apple Music: 1-month trial left running next to Spotify")
    h.monthly("icloud", "Apple", ["APPLE.COM/BILL ITUNES.COM", "APPLE.COM/BILL CORK IE"], 2.99, CARD, 14)
    h.label("icloud", "Apple", "subscription", "monthly", True, flags=("duplicate",), note="iCloud+ 200GB")
    h.monthly("google_one", "Google One", ["GOOGLE *Google One g.co/helppay#", "GOOGLE *Google One"], 1.59, CARD, 9)
    h.label("google_one", "Google One", "subscription", "monthly", True, flags=("duplicate", "forgotten"),
            note="Second cloud storage plan alongside iCloud+")
    h.add(date(2026, 3, 11), f"AMAZON PRIME*{h.ref(9)}", -95.00, CARD, "Amazon Prime", "prime")
    h.label("prime", "Amazon Prime", "subscription", "annual", True, note="Single annual charge in window")
    h.monthly("audible", "Audible", ["AUDIBLE UK ADBL.CO/PYMT", "AUDIBLE LTD"], 7.99, CARD, 2, start=date(2026, 5, 2))
    h.label("audible", "Audible", "subscription", "monthly", True, flags=("trial_converted",), note="Trial converted; actively used")
    h.monthly("now", "NOW", ["NOWTV.COM", "NOW TV LONDON GB"], 9.99, CARD, 16, start=date(2026, 2, 16))
    h.label("now", "NOW", "subscription", "monthly", True, flags=("trial_converted", "forgotten"),
            note="7-day trial for one series, never cancelled")
    h.monthly("disney", "Disney+", ["DISNEY PLUS", "DISNEYPLUS LONDON"], price_step(4.99, 5.99, date(2026, 9, 1)), CARD, 11,
              start=date(2025, 12, 11))
    h.label("disney", "Disney+", "subscription", "monthly", True, flags=("price_rise",), note="Started mid-window, no trial")
    h.monthly("puregym", "PureGym", ["PUREGYM LTD"], 24.99, DD, 1, jitter=0, business=True)
    h.label("puregym", "PureGym", "subscription", "monthly", True)
    h.add(date(2025, 11, 20), "MICROSOFT*365 PERSONAL MSBILL.INFO", -59.99, CARD, "Microsoft 365", "m365")
    h.label("m365", "Microsoft 365", "subscription", "annual", True)
    h.monthly("adobe", "Adobe", ["ADOBE *PHOTOGPHY PLAN ADOBE.LY/ENIE", "ADOBE *ADOBE IE"], 9.98, CARD, 27)
    h.label("adobe", "Adobe", "subscription", "monthly", True, note="Annual plan paid monthly: exit fee applies")
    h.monthly("chatgpt", "ChatGPT", ["OPENAI *CHATGPT SUBSCR", "OPENAI *CHATGPT SUBSCR OPENAI.COM US"],
              lambda i, d: round(20 * r.uniform(0.735, 0.79) * 1.0275, 2), CARD, 4)
    h.label("chatgpt", "ChatGPT", "subscription", "monthly", True, note="USD-billed: amount moves with FX + non-sterling fee")
    h.monthly("deliveroo_plus", "Deliveroo Plus", ["DELIVEROO PLUS"], 3.49, CARD, 12)
    h.label("deliveroo_plus", "Deliveroo Plus", "subscription", "monthly", True, flags=("forgotten",),
            note="No Deliveroo orders since May")
    h.scatter("Deliveroo", ["DELIVEROO", "DELIVEROO.CO.UK"], 14, 38, 3, end=date(2026, 5, 15))
    h.monthly("club_pret", "Club Pret", ["PRET A MANGER CLUB"], 30.00, CARD, 5, end=date(2026, 3, 6))
    h.label("club_pret", "Club Pret", "subscription", "monthly", False, note="Cancelled in March")
    h.scatter("Pret A Manger", ["PRET A MANGER {num} LONDON"], 3.5, 9.5, 5)

    hf_start = date(2026, 6, 6)
    for k in range(25):
        d = hf_start + timedelta(weeks=k)
        if d > END or k in (7, 15):
            continue
        amt = 18.49 if k == 0 else 29.99 if k == 1 else 44.99
        h.add(d, "HELLOFRESH", -amt, CARD, "HelloFresh", "hellofresh")
    h.label("hellofresh", "HelloFresh", "subscription", "weekly", True, flags=("trial_converted",),
            note="Intro discount boxes, then full price; two skipped weeks")

    h.monthly("patreon", "Patreon", ["PATREON* MEMBERSHIP", "PATREON* MEMBERSHIP INTERNET"],
              lambda i, d: round(6 * r.uniform(0.735, 0.79) * 1.0275, 2), CARD, 1)
    h.label("patreon", "Patreon", "subscription", "monthly", True)
    h.monthly("substack", "Substack", ["SUBSTACK *THE BROWSER"], 5.00, CARD, 10, start=date(2026, 3, 10))
    h.label("substack", "Substack", "subscription", "monthly", True)
    h.monthly("ironworks", "Ironworks Climbing", ["IRONWORKS CLIMBING LTD"], 52.00, DD, 1, jitter=0, business=True)
    h.label("ironworks", "Ironworks Climbing", "subscription", "monthly", True, note="Long-tail: not in merchant catalogue")
    h.monthly("coffee", "Coffee Collective", ["SQ *COFFEE COLLECTIVE"], 14.00, CARD, 15, start=date(2026, 4, 15))
    h.label("coffee", "Coffee Collective", "subscription", "monthly", True, note="Long-tail bean subscription via Square")

    # --- Hard negatives: regular-looking but not subscriptions ---
    d = START + timedelta(days=3)
    while d <= END:
        h.add(d, "SQ *FADE BROTHERS BARBERS", -25.00, CARD, "Fade Brothers Barbers")
        d += timedelta(days=r.randint(26, 36))
    h.scatter("Gail's", ["GAILS BAKERY {num}"], 3.60, 3.60, 18, weekdays={0, 1, 2, 3, 4})
    h.scatter("TfL", ["TFL TRAVEL CH", "TFL.GOV.UK/CP"], 2.80, 8.90, 14)
    d = START
    while d <= END:
        if d.weekday() == 5 and r.random() < 0.85:
            h.add(d, f"TESCO STORES {r.randint(2000, 6999)}", -round(r.uniform(42, 96), 2), CARD, "Tesco")
        d += timedelta(days=1)
    h.scatter("Sainsbury's", ["SAINSBURYS S/MKTS", "SAINSBURY'S LOCAL {num}"], 4, 25, 4)
    h.scatter("Amazon", ["AMZNMKTPLACE*{ref}", "AMAZON.CO.UK*{ref}", "AMZN MKTP UK*{ref}"], 6, 80, 3)
    h.scatter("Uber", ["UBER *TRIP HELP.UBER.COM", "UBER* TRIP"], 9, 32, 2)
    h.scatter("Dishoom", ["DISHOOM KINGS CROSS"], 40, 95, 0.6)
    h.scatter("Flat White", ["FLAT WHITE SOHO"], 3, 7, 1.5)
    h.add(date(2026, 1, 10), "IKEA LTD", -214.50, CARD, "IKEA")
    h.add(date(2026, 8, 2), "JOHN LEWIS 0294", -89.00, CARD, "John Lewis")

    h.txns.sort(key=lambda t: (t["date"], t["description"]))
    for i, t in enumerate(h.txns, 1):
        t["id"] = f"t{i:05d}"
    return h


def build_holdout(seed: int) -> Household:
    """A different household (Manchester family, Lloyds-style descriptors) written to stress the detector with
    quirks it was NOT developed against. Its first-run score is the honest one."""
    h = Household(seed)
    r = h.r
    cd = " CD 4471"

    for y, m in months(START, END):
        d = date(y, m, 28)
        while d.weekday() >= 5:
            d -= timedelta(days=1)
        h.add(d, "NHS BSA SALARY", 2890.00, CREDIT, "NHS BSA")
    h.monthly("mortgage", "Nationwide", ["NATIONWIDE MORTGAGE"], 1120.00, DD, 1, jitter=0, business=True)
    h.label("mortgage", "Nationwide", "other", "monthly", True)
    h.monthly("cleaner", "M Kowalski", ["M KOWALSKI CLEANING"], 80.00, FP, 3, jitter=1)
    h.label("cleaner", "M Kowalski", "other", "monthly", True, note="Bank transfer to cleaner")
    h.monthly("ctax", "Council Tax", ["MANCHESTER CITY COUNCIL"], price_step(171.00, 179.50, date(2026, 4, 1)), DD, 1,
              jitter=0, business=True, skip_months=(2, 3))
    h.label("ctax", "Council Tax", "bill", "monthly", True, flags=("price_rise",), note="Descriptor lacks 'council tax'")
    h.monthly("energy", "British Gas", ["BRITISH GAS"], lambda i, d: round(110 + r.uniform(-6, 6), 2), DD, 14,
              jitter=0, business=True)
    h.label("energy", "British Gas", "bill", "monthly", True)
    h.monthly("homecare", "British Gas", ["BRITISH GAS HOMECARE"], 19.50, DD, 22, jitter=0, business=True)
    h.label("homecare", "British Gas", "bill", "monthly", True, note="Boiler cover, same merchant as energy")
    h.monthly("bt", "BT", ["BT GROUP PLC"], price_step(45.99, 49.49, date(2026, 4, 1)), DD, 6, jitter=0, business=True)
    h.label("bt", "BT", "bill", "monthly", True, flags=("price_rise",))
    h.monthly("o2", "O2", ["O2 UK"], 18.00, DD, 17, jitter=0, business=True)
    h.label("o2", "O2", "bill", "monthly", True)

    h.monthly("sky", "Sky", ["SKY DIGITAL"], price_step(35.00, 38.00, date(2026, 4, 1)), DD, 9, jitter=0, business=True)
    h.label("sky", "Sky", "subscription", "monthly", True, flags=("price_rise",))
    h.monthly("prime", "Amazon Prime", ["AMAZON PRIME*{ref}" + cd, "AMZN PRIME UK*{ref}"],
              price_step(8.99, 9.99, date(2026, 2, 1)), CARD, 19)
    h.label("prime", "Amazon Prime", "subscription", "monthly", True, flags=("price_rise",))
    h.monthly("kindle", "Amazon Kindle Unlimited", ["AMZN DIGITAL*{ref}" + cd], 9.49, CARD, 23)
    h.label("kindle", "Amazon Kindle Unlimited", "subscription", "monthly", True,
            note="Shares the generic AMZN descriptor with shopping")
    h.scatter("Amazon", ["AMZNMKTPLACE*{ref}" + cd, "AMAZON.CO.UK*{ref}" + cd], 5, 60, 5)

    # Spotify family with one failed payment: charge, reversal, retry three days later
    for i, (y, m) in enumerate(months(START, END)):
        d = date(y, m, 2)
        h.add(d, "SPOTIFY P{}".format(h.ref(10)) + cd, -19.99, CARD, "Spotify", "spotify")
        if (y, m) == (2026, 5):
            h.add(d + timedelta(days=1), "SPOTIFY P{} REVERSAL".format(h.ref(10)), 19.99, CREDIT, "Spotify", "")
            h.add(d + timedelta(days=3), "SPOTIFY P{}".format(h.ref(10)) + cd, -19.99, CARD, "Spotify", "spotify")
    h.label("spotify", "Spotify", "subscription", "monthly", True, note="Failed payment reversed and retried in May")

    h.monthly("disney", "Disney+", ["DISNEY PLUS" + cd], 8.99, CARD, 13)
    h.label("disney", "Disney+", "subscription", "monthly", True, flags=("duplicate",))
    h.monthly("disney_apple", "Apple", ["APPLE.COM/BILL"], 8.99, CARD, 25, start=date(2026, 1, 25))
    h.label("disney_apple", "Apple", "subscription", "monthly", True, flags=("duplicate", "forgotten"),
            note="Second Disney+ bought in-app on a child's iPad (statement just says Apple, £8.99)")
    h.monthly("roblox", "Apple", ["APPLE.COM/BILL"], 4.99, CARD, 6, start=date(2026, 3, 6))
    h.label("roblox", "Apple", "subscription", "monthly", True, note="Roblox Premium via Apple")
    h.add(date(2026, 7, 30), "APPLE.COM/BILL", -39.99, CARD, "Apple", "calm")
    h.label("calm", "Apple", "subscription", "annual", True, flags=("trial_converted",),
            note="Calm annual after 7-day trial; single charge")
    h.monthly("dropbox", "Dropbox", ["DROPBOX*{ref}" + cd], 9.99, CARD, 11)
    h.label("dropbox", "Dropbox", "subscription", "monthly", True, flags=("duplicate", "forgotten"),
            note="Old Dropbox Plus alongside Google One")
    h.monthly("google_one", "Google One", ["GOOGLE *Google One"], 7.99, CARD, 15)
    h.label("google_one", "Google One", "subscription", "monthly", True, flags=("duplicate",))
    h.monthly("yt", "YouTube Premium", ["GOOGLE *YouTube"], 19.99, CARD, 20)
    h.label("yt", "YouTube Premium", "subscription", "monthly", True, note="Family plan; descriptor lacks 'Premium'")
    h.add(date(2026, 2, 14), "GOOGLE *Duolingo", -79.99, CARD, "Duolingo", "duolingo")
    h.label("duolingo", "Duolingo", "subscription", "annual", True, note="Annual via Google Play, single charge")
    h.monthly("psplus", "PlayStation Plus", ["PLAYSTATION NETWORK"], 6.99, CARD, 4)
    h.label("psplus", "PlayStation Plus", "subscription", "monthly", True, flags=("forgotten",),
            note="Child stopped playing in spring: no signal in bank data")
    h.monthly("paramount", "Paramount+", ["PARAMOUNT+"], 4.99, CARD, 27, start=date(2026, 6, 27))
    h.label("paramount", "Paramount+", "subscription", "monthly", True, flags=("trial_converted",))
    h.monthly("uber_one", "Uber One", ["UBER *ONE MEMBERSHIP"], 5.99, CARD, 8)
    h.label("uber_one", "Uber One", "subscription", "monthly", True, note="Descriptor is 'UBER *ONE', not 'UBER ONE'")
    h.scatter("Uber", ["UBER *EATS", "UBER *TRIP"], 12, 35, 3)
    h.monthly("deliveroo_plus", "Deliveroo Plus", ["DELIVEROO PLU"], 3.49, CARD, 16, start=date(2026, 2, 16))
    h.label("deliveroo_plus", "Deliveroo Plus", "subscription", "monthly", True, flags=("trial_converted",),
            note="Descriptor truncated by the bank")
    h.scatter("Deliveroo", ["DELIVEROO"], 18, 40, 2)
    h.monthly("thegym", "The Gym Group", ["THE GYM LTD"], 23.99, DD, 1, jitter=0, business=True)
    h.label("thegym", "The Gym Group", "subscription", "monthly", True, note="Trades as THE GYM LTD")
    h.monthly("nyt", "New York Times", ["NYTIMES*NYTDIGITALSUBSCRIP"], lambda i, d: round(4 * r.uniform(0.73, 0.79), 2),
              CARD, 12, start=date(2026, 1, 12))
    h.label("nyt", "New York Times", "subscription", "monthly", True, flags=("trial_converted",),
            note="USD-billed intro rate; not in catalogue")

    # Hard negatives
    h.monthly("klarna", "Klarna", ["KLARNA*CURRYS"], 66.33, CARD, 10, start=date(2026, 3, 10), end=date(2026, 5, 31))
    h.label("klarna", "Klarna", "other", "monthly", False, note="Pay-in-3 instalments: fixed monthly, not a subscription")
    h.monthly("klarna2", "Klarna", ["KLARNA*ZARA"], 29.00, CARD, 21, start=date(2026, 8, 21))
    h.label("klarna2", "Klarna", "other", "monthly", True, note="BNPL instalments still running")
    d = date(2025, 10, 4)
    while d <= END:
        if not (date(2025, 12, 20) <= d <= date(2026, 1, 5)) and not (date(2026, 7, 20) <= d <= date(2026, 9, 1)):
            h.add(d, "SQ *JUNIOR FOOTBALL CLUB" + cd, -6.00, CARD, "Junior Football Club", "football")
        d += timedelta(days=7)
    h.label("football", "Junior Football Club", "other", "weekly", True, note="Pay-as-you-go weekly session fee")
    d = START
    while d <= END:
        if d.weekday() == 6 and r.random() < 0.8:
            h.add(d, f"ALDI {r.randint(100, 999)}" + cd, -round(r.uniform(55, 110), 2), CARD, "Aldi")
        d += timedelta(days=1)
    h.scatter("Greggs", ["GREGGS PLC" + cd], 2.5, 6, 6)
    h.scatter("Bee Network", ["BEE NETWORK BUS"], 2.0, 2.0, 10)
    h.scatter("Costa", ["COSTA COFFEE {num}" + cd], 3, 7, 4)

    h.txns = [t for t in h.txns if t["description"]]
    h.txns.sort(key=lambda t: (t["date"], t["description"]))
    for i, t in enumerate(h.txns, 1):
        t["id"] = f"h{i:05d}"
    return h


def write(h: Household, out: Path):
    out.mkdir(parents=True, exist_ok=True)
    with open(out / "transactions.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["id", "date", "description", "amount", "type"])
        for t in h.txns:
            w.writerow([t["id"], t["date"].isoformat(), t["description"], f"{t['amount']:.2f}", t["type"]])
    with open(out / "labels_transactions.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["id", "merchant", "stream_id"])
        for t in h.txns:
            w.writerow([t["id"], t["merchant"], t["stream"]])
    with open(out / "labels_streams.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(h.streams[0]))
        w.writeheader()
        w.writerows(h.streams)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--holdout", action="store_true", help="the held-out household instead of the dev one")
    p.add_argument("--out", type=Path)
    a = p.parse_args()
    a.out = a.out or Path(__file__).parent / ("holdout" if a.holdout else "synthetic")
    hh = build_holdout(a.seed) if a.holdout else build(a.seed)
    write(hh, a.out)
    print(f"{len(hh.txns)} transactions, {len(hh.streams)} labelled streams -> {a.out}")
