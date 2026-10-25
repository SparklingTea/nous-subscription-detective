"""Turn flags into actions and a '£ back in pocket' figure."""
from pathlib import Path

import yaml

from .streams import Stream

KB_PATH = Path(__file__).resolve().parent.parent / "cancellation" / "uk_subscriptions.yaml"

# Assumed probability a cancellation actually completes, by route. These are judgement calls, not data:
# phone/chat routes lose people to hold queues and retention offers.
SUCCESS_RATE = {"online": 0.95, "online_2fa": 0.9, "app_store": 0.9, "in_app": 0.85, "email": 0.8, "chat": 0.8,
                "phone": 0.7, None: 0.6}


def load_kb(path: Path = KB_PATH) -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def cancel_route(s: Stream, kb: dict) -> dict | None:
    if s.channel == "apple":
        key = "apple"
    elif s.channel == "google_play":
        key = "google_play"
    else:
        key = s.entry.cancel_key if s.entry is not None else None
    info = dict(kb.get(key) or {}) if key else {}
    if s.channel == "paypal":
        info["fallback"] = kb["_fallbacks"]["paypal"]["note"]
    elif s.txns[-1].type == "DIRECT DEBIT":
        info["fallback"] = kb["_fallbacks"]["direct_debit"]["note"]
    else:
        info["fallback"] = kb["_fallbacks"]["card_cpa"]["note"]
    info["key"] = key
    return info


def recommend(streams: list[Stream], kb: dict) -> dict:
    actions = []
    subs = [s for s in streams if s.kind == "subscription" and s.active]
    cancelling = {s.label for s in subs if "forgotten" in s.flags}
    for s in subs:
        if "forgotten" not in s.flags and set(s.flags.get("duplicate", {}).get("with", [])) & cancelling:
            continue  # the keeper in a duplicate pair whose other half we already suggest cancelling
        route = cancel_route(s, kb)
        p = SUCCESS_RATE.get(route.get("method"), SUCCESS_RATE[None])
        if "forgotten" in s.flags:
            actions.append(dict(stream=s.id, label=s.label, action="cancel", annual=s.annual_cost,
                                expected=round(s.annual_cost * p, 2), method=route.get("method"),
                                automatable=route.get("automatable", "unknown"),
                                why="; ".join(s.flags["forgotten"]["reasons"])))
        elif "duplicate" in s.flags:
            actions.append(dict(stream=s.id, label=s.label, action="review_duplicate", annual=s.annual_cost,
                                expected=0.0, method=route.get("method"), automatable=route.get("automatable", "unknown"),
                                why=s.flags["duplicate"]["reason"]))
        elif "trial_converted" in s.flags:
            actions.append(dict(stream=s.id, label=s.label, action="confirm_keep", annual=s.annual_cost, expected=0.0,
                                method=route.get("method"), automatable=route.get("automatable", "unknown"),
                                why=f"started {s.flags['trial_converted']['first_charge']} after a trial/intro offer"))
    rises = []
    for s in streams:
        if s.active and "price_rise" in s.flags and "forgotten" not in s.flags:
            pr = s.flags["price_rise"]
            rises.append(dict(stream=s.id, label=s.label, kind=s.kind, old=pr["old"], new=pr["new"], pct=pr["pct"],
                              annual_increase=pr["annual_increase"], since=pr["from"]))
    cancel = [a for a in actions if a["action"] == "cancel"]
    total_subs = sum(s.annual_cost for s in subs)
    return dict(
        actions=actions,
        price_rises=rises,
        active_subscriptions=len(subs),
        annual_subscription_spend=round(total_subs, 2),
        back_in_pocket_identified=round(sum(a["annual"] for a in cancel), 2),
        back_in_pocket_expected=round(sum(a["expected"] for a in cancel), 2),
        price_rise_exposure=round(sum(r["annual_increase"] for r in rises), 2),
        assumptions={"success_rate_by_route": {str(k): v for k, v in SUCCESS_RATE.items()},
                     "horizon": "next 12 months at latest price"},
    )
