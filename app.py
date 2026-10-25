"""Subscription detective: streamlit run app.py"""
import json
import tempfile
from pathlib import Path

import pandas as pd
import streamlit as st

from detective.loader import load
from detective.pipeline import run
from detective.savings import load_kb

ROOT = Path(__file__).parent
OUT = ROOT / "outputs"
FLAG_LABELS = {"price_rise": "Price rise", "duplicate": "Duplicate", "trial_converted": "Trial converted",
               "forgotten": "Probably forgotten"}

st.set_page_config(page_title="Subscription detective", layout="wide")
st.title("Subscription detective")

datasets = {"Dev household (London, synthetic)": ROOT / "data/synthetic/transactions.csv",
            "Held-out household (Manchester, synthetic)": ROOT / "data/holdout/transactions.csv"}
choice = st.sidebar.radio("Statement", [*datasets, "Upload my own CSV"])
threshold = st.sidebar.slider("'Probably forgotten' score threshold", 1, 4, 2,
                              help="Lower = catch more forgotten subs, more false alarms")
if choice == "Upload my own CSV":
    up = st.sidebar.file_uploader("Bank CSV export", type="csv")
    flip = st.sidebar.checkbox("Purchases are positive numbers in my export")
    st.sidebar.caption("Processed locally in this session; nothing is stored.")
    if up is None:
        st.info("Upload a CSV export (Monzo, Starling, Barclays, Lloyds, HSBC and Nationwide layouts are recognised).")
        st.stop()
    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
        f.write(up.getvalue())
    df = load(f.name, flip)
else:
    df = load(datasets[choice])

result, _ = run(df, threshold)
summary, streams = result["summary"], result["streams"]

tab_money, tab_subs, tab_eval, tab_map, tab_agent = st.tabs(
    ["£ back in pocket", "Subscriptions", "Precision / recall", "UK cancellation map", "Cancellation agent"])

with tab_money:
    c = st.columns(4)
    c[0].metric("Active subscriptions", summary["active_subscriptions"])
    c[1].metric("Subscription spend", f"£{summary['annual_subscription_spend']:,.0f}/yr")
    c[2].metric("Back in pocket (identified)", f"£{summary['back_in_pocket_identified']:,.0f}/yr")
    c[3].metric("Expected after cancel success rates", f"£{summary['back_in_pocket_expected']:,.0f}/yr")
    st.caption(f"{result['period']['start']} to {result['period']['end']}, {result['period']['transactions']} transactions. "
               "'Expected' discounts each cancellation by an assumed success rate for its route "
               "(online 95%, 2FA 90%, in-app 85%, phone 70%).")
    acts = pd.DataFrame(summary["actions"])
    if not acts.empty:
        order = {"cancel": 0, "review_duplicate": 1, "confirm_keep": 2}
        acts = acts.sort_values(by="action", key=lambda s: s.map(order))
        st.subheader("What Nora would say")
        for a in acts.itertuples():
            verb = {"cancel": "💸 Cancel", "review_duplicate": "🔁 Pick one", "confirm_keep": "❓ Still want"}[a.action]
            st.markdown(f"**{verb} {a.label}**: £{a.annual:,.2f}/yr. _{a.why}_. Route: `{a.method}`, "
                        f"automatable: `{a.automatable}`")
    if summary["price_rises"]:
        st.subheader(f"Price rises: £{summary['price_rise_exposure']:,.2f}/yr extra")
        st.dataframe(pd.DataFrame(summary["price_rises"]).drop(columns="stream"), hide_index=True)

with tab_subs:
    rows = [dict(subscription=s["label"], kind=s["kind"], active=s["active"], cadence=s["cadence"] + ("*" if s["cadence_inferred"] else ""),
                 latest=s["latest_amount"], per_year=s["annual_cost"], channel=s["channel"], charges=s["n"],
                 confidence=s["confidence"], flags=", ".join(FLAG_LABELS[f] for f in s["flags"]),
                 descriptors=" | ".join(s["descriptions"])) for s in streams]
    kinds = st.multiselect("Show", ["subscription", "bill", "bnpl", "other"], default=["subscription"])
    st.dataframe(pd.DataFrame([r for r in rows if r["kind"] in kinds]), hide_index=True, use_container_width=True)
    st.caption("* cadence inferred from one or two charges of a known subscription merchant")

with tab_eval:
    st.markdown("Scored against hand labels at stream level (a predicted stream matches a labelled one when they share "
                "≥50% of transactions). The held-out household was written to stress the detector and scored **once** "
                "before any fixes; that first run is the honest number.")
    runs = {"Dev household": OUT / "eval.json", "Held-out: first run (blind)": OUT / "holdout_first_run/eval.json",
            "Held-out: after one fix round": OUT / "holdout_after_fixes/eval.json"}
    table = []
    for name, p in runs.items():
        if p.exists():
            e = json.loads(p.read_text(encoding="utf-8"))["main"]
            row = {"run": name, "subs P": e["subscription_detection"]["precision"],
                   "subs R": e["subscription_detection"]["recall"]}
            for f in FLAG_LABELS:
                row[f"{f} F1"] = e["flags"][f]["f1"]
            row["merchant acc."] = e["merchant"]["accuracy"]
            table.append(row)
    if table:
        st.dataframe(pd.DataFrame(table), hide_index=True, use_container_width=True)
    pick = st.selectbox("Error analysis for", [n for n, p in runs.items() if p.exists()])
    md = runs[pick].with_name("eval.md")
    if md.exists():
        st.markdown(md.read_text(encoding="utf-8"))

with tab_map:
    kb = load_kb()
    kb.pop("_fallbacks")
    m = pd.DataFrame([dict(service=v["name"], method=v["method"], automatable=v["automatable"], route=v["route"],
                           notice=v.get("notice"), dark_patterns="; ".join(v.get("dark_patterns") or []),
                           gotchas="; ".join(v.get("gotchas") or []), confidence=v["confidence"]) for v in kb.values()])
    c = st.columns(3)
    for col, val in zip(c, ["yes", "with_handoff", "no"]):
        col.metric(f"Automatable: {val}", int((m.automatable == val).sum()))
    st.dataframe(m, hide_index=True, use_container_width=True)
    st.caption("Desk research; flows change often. Anything below 'high' confidence should be re-walked before an "
               "agent runs it for a member.")

with tab_agent:
    p = OUT / "cancellation_runs.json"
    if not p.exists():
        st.info("Run `python -m cancellation.demo` first.")
    else:
        data = json.loads(p.read_text(encoding="utf-8"))
        for r in data["runs"]:
            with st.expander(f"{r['scenario']}: **{r['status']}**", expanded=r["status"] != "cancelled"):
                st.table(pd.DataFrame(r["trace"])[["step", "title", "action"]])
                if r["handoff_message"]:
                    st.chat_message("assistant").write(r["handoff_message"])
        st.subheader("Routes the agent doesn't automate")
        for k, v in data["handoffs"].items():
            st.markdown(f"**{k}**")
            st.code(v, language=None)
