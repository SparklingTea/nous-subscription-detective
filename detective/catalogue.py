"""Known-merchant catalogue. Order matters: more specific patterns must come before broader ones
(e.g. 'DELIVEROO PLUS' before 'DELIVEROO', 'PRET...CLUB' before 'PRET')."""
import re
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Merchant:
    name: str
    patterns: tuple[str, ...]
    kind: str  # subscription | bill | retail | transport
    category: str
    exclusive_group: str | None = None  # two active subs in the same group = paying twice for one need
    free_trial: bool = False
    usage_merchant: str | None = None  # spend at this merchant shows the membership is being used
    cancel_key: str | None = None
    multi_product: bool = False  # one descriptor, many products (Apple, Google): concurrent streams aren't duplicates
    annual_ok: bool = False  # a single large charge is plausibly an annual renewal
    price_hints: dict = field(default_factory=dict)  # amount -> (product, exclusive_group)

    def __hash__(self):
        return hash(self.name)


M = Merchant
CATALOGUE: list[Merchant] = [
    # Subscriptions
    M("Netflix", (r"NETFLIX",), "subscription", "video", cancel_key="netflix"),
    M("Amazon Prime", (r"AMAZON PRIME", r"AMZN PRIME", r"PRIME VIDEO"), "subscription", "shopping_membership",
      free_trial=True, usage_merchant="Amazon", cancel_key="amazon_prime", annual_ok=True),
    M("Amazon Digital", (r"AMZN DIGITAL", r"KINDLE UNL", r"AMAZON DIGITAL"), "subscription", "platform",
      free_trial=True, cancel_key="amazon_prime", multi_product=True,
      price_hints={9.49: ("Kindle Unlimited", None), 10.99: ("Amazon Music Unlimited", "music")}),
    M("Audible", (r"AUDIBLE", r"ADBL\.CO"), "subscription", "audiobooks", free_trial=True, cancel_key="audible"),
    M("Spotify", (r"SPOTIFY",), "subscription", "music", exclusive_group="music", free_trial=True, cancel_key="spotify"),
    M("Apple", (r"APPLE\.COM", r"ITUNES"), "subscription", "platform", free_trial=True, cancel_key="apple",
      multi_product=True, annual_ok=True,
      price_hints={0.99: ("iCloud+ 50GB", "cloud_storage"), 2.99: ("iCloud+ 200GB", "cloud_storage"),
                   8.99: ("iCloud+ 2TB or Apple TV+", None), 10.99: ("Apple Music", "music"),
                   18.95: ("Apple One Individual", None)}),
    M("Google One", (r"GOOGLE ?ONE",), "subscription", "cloud_storage", exclusive_group="cloud_storage",
      free_trial=True, cancel_key="google_play"),
    M("Dropbox", (r"DROPBOX",), "subscription", "cloud_storage", exclusive_group="cloud_storage", cancel_key="dropbox"),
    M("YouTube Premium", (r"YOUTUBE ?PREMIUM", r"YOUTUBEPREMIUM", r"^YOUTUBE\b"), "subscription", "video", free_trial=True,
      cancel_key="youtube_premium"),
    M("Google Play", (r"GOOGLE PLAY", r"^GOOGLE\b"), "subscription", "platform", free_trial=True,
      cancel_key="google_play", multi_product=True, annual_ok=True),
    M("Disney+", (r"DISNEY ?PLUS", r"DISNEY\+"), "subscription", "video", cancel_key="disney_plus"),
    M("NOW", (r"NOW ?TV", r"^NOW\b"), "subscription", "video", free_trial=True, cancel_key="now"),
    M("Paramount+", (r"PARAMOUNT",), "subscription", "video", free_trial=True, cancel_key="paramount_plus"),
    M("DAZN", (r"DAZN",), "subscription", "video", cancel_key="dazn"),
    M("Sky", (r"SKY DIGITAL", r"^SKY\b"), "subscription", "pay_tv", cancel_key="sky"),
    M("PureGym", (r"PURE ?GYM",), "subscription", "fitness", cancel_key="puregym"),
    M("The Gym Group", (r"GYM GROUP", r"^THE GYM\b"), "subscription", "fitness", cancel_key="the_gym_group"),
    M("Microsoft 365", (r"MICROSOFT\s?\*?\s?365", r"MSFT\s?\*"), "subscription", "software",
      cancel_key="microsoft_365", annual_ok=True),
    M("Xbox Game Pass", (r"XBOX",), "subscription", "gaming", cancel_key="xbox_game_pass"),
    M("PlayStation Plus", (r"PLAYSTATION", r"SONY INTERACTIVE"), "subscription", "gaming",
      cancel_key="playstation_plus", annual_ok=True),
    M("Adobe", (r"ADOBE",), "subscription", "software", cancel_key="adobe"),
    M("ChatGPT", (r"OPENAI", r"CHATGPT"), "subscription", "ai", cancel_key="chatgpt"),
    M("Deliveroo Plus", (r"DELIVEROO PL",), "subscription", "delivery_membership", free_trial=True,
      usage_merchant="Deliveroo", cancel_key="deliveroo_plus"),
    M("Uber One", (r"UBER \*?\s?ONE",), "subscription", "delivery_membership", free_trial=True,
      usage_merchant="Uber", cancel_key="uber_one"),
    M("Club Pret", (r"PRET.*CLUB", r"CLUB PRET"), "subscription", "food_membership", usage_merchant="Pret A Manger",
      cancel_key="club_pret"),
    M("HelloFresh", (r"HELLO ?FRESH",), "subscription", "meal_kit", free_trial=True, cancel_key="hellofresh"),
    M("Gousto", (r"GOUSTO",), "subscription", "meal_kit", free_trial=True, cancel_key="gousto"),
    M("Patreon", (r"PATREON",), "subscription", "creator", cancel_key="patreon"),
    M("Substack", (r"SUBSTACK",), "subscription", "news", cancel_key="substack"),
    M("The Times", (r"TIMES NEWSPAPERS", r"THE TIMES"), "subscription", "news", cancel_key="the_times"),
    M("New York Times", (r"NYTIMES", r"\bNYT\b"), "subscription", "news", free_trial=True),
    M("The Telegraph", (r"TELEGRAPH",), "subscription", "news", cancel_key="the_telegraph"),
    M("Duolingo", (r"DUOLINGO",), "subscription", "education", free_trial=True, cancel_key="duolingo",
      annual_ok=True),
    M("Headspace", (r"HEADSPACE",), "subscription", "wellbeing", free_trial=True, cancel_key="headspace"),
    M("Peloton", (r"PELOTON",), "subscription", "fitness", free_trial=True, cancel_key="peloton"),
    # Bills
    M("Council Tax", (r"C(OUNCIL)?\s?TAX", r"(CITY|BOROUGH|DISTRICT|COUNTY|METROPOLITAN) COUNCIL", r"^LB "),
      "bill", "council_tax"),
    M("TV Licence", (r"TV LICEN[CS]E",), "bill", "tv_licence"),
    M("Octopus Energy", (r"OCTOPUS ENERGY",), "bill", "energy"),
    M("British Gas", (r"BRITISH GAS",), "bill", "energy"),
    M("EDF", (r"\bEDF\b",), "bill", "energy"),
    M("OVO", (r"\bOVO\b",), "bill", "energy"),
    M("Virgin Media", (r"VIRGIN MEDIA",), "bill", "broadband"),
    M("BT", (r"^BT\b", r"BT GROUP"), "bill", "broadband"),
    M("EE", (r"^EE\b",), "bill", "mobile"),
    M("Vodafone", (r"VODAFONE",), "bill", "mobile"),
    M("O2", (r"^O2\b", r"TELEFONICA"), "bill", "mobile"),
    M("Three", (r"^THREE\b", r"HUTCHISON 3G"), "bill", "mobile"),
    M("Thames Water", (r"THAMES WATER",), "bill", "water"),
    # Buy-now-pay-later: fixed monthly amounts that look exactly like subscriptions but end on their own
    M("Klarna", (r"KLARNA",), "bnpl", "instalments"),
    M("Clearpay", (r"CLEARPAY",), "bnpl", "instalments"),
    M("PayPal Pay in 3", (r"PAY ?IN ?3",), "bnpl", "instalments"),
    # Everyday spend (used for usage signals, never treated as subscriptions)
    M("Deliveroo", (r"DELIVEROO",), "retail", "takeaway"),
    M("Uber", (r"UBER",), "transport", "taxi"),
    M("Amazon", (r"AMZN", r"AMAZON"), "retail", "shopping"),
    M("Pret A Manger", (r"^PRET\b",), "retail", "food"),
    M("TfL", (r"^TFL\b", r"TFL\.GOV"), "transport", "public_transport"),
    M("Tesco", (r"^TESCO\b",), "retail", "groceries"),
    M("Sainsbury's", (r"SAINSBURY",), "retail", "groceries"),
]

_COMPILED = [(m, [re.compile(p) for p in m.patterns]) for m in CATALOGUE]
BY_NAME = {m.name: m for m in CATALOGUE}


def match(text: str) -> Merchant | None:
    for m, pats in _COMPILED:
        if any(p.search(text) for p in pats):
            return m
    return None


def apple_like_product(merchant: Merchant, amount: float) -> tuple[str | None, str | None]:
    """Platform billers hide the product; the price is often the only clue."""
    for price, (product, group) in merchant.price_hints.items():
        if abs(amount - price) < 0.015:
            return product, group
    return None, None
