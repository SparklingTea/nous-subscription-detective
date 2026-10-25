"""Run the cancellation agent against the local mock flows and write outputs/cancellation_runs.json.

    python -m cancellation.demo
"""
import json
from dataclasses import asdict
from pathlib import Path

from . import mock_sites
from .agent import CancellationAgent, Playbook
from .handoffs import bank_cpa_request, cancellation_email, phone_script

OUT = Path(__file__).resolve().parent.parent / "outputs"


def member_replies_with_code(message: str) -> str:
    """Stands in for the member answering on WhatsApp: reads the code the mock 'sent to their phone'."""
    print(f"    Nora -> member: {message}")
    code = mock_sites.LAST_CODE.get("apple")
    print(f"    member -> Nora: {code}")
    return code


def main():
    mock_sites.reset()
    srv, base = mock_sites.serve()
    email, pw = next(iter(mock_sites.TEST_ACCOUNTS.items()))
    agent = CancellationAgent(ask_member=member_replies_with_code)
    scenarios = [
        ("Netflix: plain flow", Playbook("Netflix", f"{base}/netflix", email, pw)),
        ("Amazon Prime: retention maze", Playbook("Amazon Prime", f"{base}/prime", email, pw)),
        ("Apple Music via Apple: 2FA hand-off", Playbook("Apple", f"{base}/apple", email, pw, target="Apple Music")),
        ("Adobe: early termination fee, no consent", Playbook("Adobe", f"{base}/adobe", email, pw)),
        ("Adobe: member said yes to the fee", Playbook("Adobe", f"{base}/adobe", email, pw, consent_to_fee=True)),
    ]
    runs = []
    for title, pb in scenarios:
        print(f"\n== {title}")
        r = agent.run(pb)
        for t in r.trace:
            print(f"   {t['step']:>2}. [{t['title']}] {t.get('action', '')}")
        print(f"   => {r.status.upper()}" + (f", ends {r.ends_on}" if r.ends_on else "")
              + (f"\n   message to member: {r.handoff_message}" if r.handoff_message else ""))
        runs.append({"scenario": title, **asdict(r)})
    srv.shutdown()

    handoffs = {
        "Sky (phone only)": phone_script("Sky TV", 38.00, walk_away=25.00),
        "The Times (email notice)": cancellation_email("The Times digital subscription", "A. Member"),
        "Any card subscription (bank backstop)": bank_cpa_request("NOWTV.COM", 9.99, "16 October 2026"),
    }
    print("\n== Non-automatable routes: generated hand-offs")
    for k, v in handoffs.items():
        print(f"\n-- {k}\n{v}")
    OUT.mkdir(exist_ok=True)
    (OUT / "cancellation_runs.json").write_text(json.dumps({"runs": runs, "handoffs": handoffs}, indent=2),
                                                encoding="utf-8")


if __name__ == "__main__":
    main()
