"""Messy bank descriptor -> (canonical merchant, billing channel, catalogue entry)."""
import re
from dataclasses import dataclass

from rapidfuzz import fuzz, process

from .catalogue import CATALOGUE, Merchant, match

# Who actually holds the billing relationship. This decides how you cancel, not the brand name.
PROCESSORS = [
    (re.compile(r"^(PAYPAL|PP)\s?\*\s?"), "paypal"),
    (re.compile(r"^GOOGLE\s?\*\s?(?!GOOGLE ONE)"), "google_play"),
    (re.compile(r"^(SQ|SUMUP|ZTL|IZ|CRV|SP)\s?\*\s?"), None),
]

PLACES = {"LONDON", "LDN", "GB", "GBR", "UK", "IE", "IRL", "NL", "LU", "SE", "US", "USA", "CORK", "DUBLIN",
          "AMSTERDAM", "LUXEMBOURG", "STOCKHOLM", "SOHO", "SHOREDITCH", "ISLINGTON", "CAMDEN", "HACKNEY",
          "KINGS", "CROSS", "FARRINGDON", "CLERKENWELL", "INTERNET", "ONLINE"}
NOISE = {"LTD", "LIMITED", "PLC", "LLP", "CO", "THE", "PAYMENT", "PYMT", "PYMTS", "CARD", "DD", "SO", "REF",
         "SALARY", "RENT", "BILL", "HELP", "TRIP", "SUBSCR", "MEMBERSHIP"}

_FUZZY_CHOICES = {m.name.upper(): m for m in CATALOGUE}


@dataclass
class Normalised:
    merchant: str
    channel: str  # direct | paypal | google_play | apple
    entry: Merchant | None
    cleaned: str


def clean(desc: str) -> str:
    s = desc.upper().strip()
    s = re.sub(r"\bCD \d{4}\b", " ", s)  # Lloyds/Halifax card-number suffix
    s = re.sub(r"\b([A-Z0-9-]+)\.(COM|CO\.UK|NET|IO|INFO|LY|CO)(/\S*)?", r" \1 ", s)  # NETFLIX.COM -> NETFLIX
    s = re.sub(r"\*\s?[A-Z0-9]{5,}\b", " ", s)  # AMAZON PRIME*2K4LP9XZ5
    s = re.sub(r"[*#/]", " ", s)
    s = re.sub(r"\+?\d[\d -]{4,}\d", " ", s)  # phone numbers, sort codes, account refs
    tokens = [t for t in s.split() if not re.search(r"\d", t)]
    tokens = [t for t in tokens if t not in PLACES]
    meaningful = [t for t in tokens if t not in NOISE]
    return " ".join(meaningful or tokens).strip()


def normalise(desc: str) -> Normalised:
    raw = desc.upper().strip()
    channel = "direct"
    for pat, ch in PROCESSORS:
        m = pat.match(raw)
        if m:
            raw = raw[m.end():]
            channel = ch or channel
            break
    entry = match(raw)
    cleaned = clean(raw)
    if entry is None and cleaned:
        hit = process.extractOne(cleaned, list(_FUZZY_CHOICES), scorer=fuzz.ratio, score_cutoff=88)
        if hit:
            entry = _FUZZY_CHOICES[hit[0]]
    if entry is not None:
        if entry.name == "Apple":
            channel = "apple"
        elif entry.name in ("Google One", "Google Play"):
            channel = "google_play"
        return Normalised(entry.name, channel, entry, cleaned)
    return Normalised(cleaned.title() if cleaned else desc.strip(), channel, None, cleaned)
