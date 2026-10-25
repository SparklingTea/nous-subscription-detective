import sys
from datetime import date
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "data"))

from cancellation import mock_sites  # noqa: E402
from cancellation.agent import CancellationAgent, Playbook  # noqa: E402
from detective.normalise import normalise  # noqa: E402
from detective.streams import detect_cadence  # noqa: E402
from eval.evaluate import evaluate, seed_frames  # noqa: E402


@pytest.mark.parametrize("desc,merchant,channel", [
    ("NETFLIX.COM 866-579-7172", "Netflix", "direct"),
    ("PAYPAL *NETFLIX.COM 35314369001", "Netflix", "paypal"),
    ("APPLE.COM/BILL CORK IE", "Apple", "apple"),
    ("GOOGLE *Google One g.co/helppay#", "Google One", "google_play"),
    ("AMAZON PRIME*2K4LP9XZ5", "Amazon Prime", "direct"),
    ("AMZNMKTPLACE*AB12CD34", "Amazon", "direct"),
    ("DELIVEROO PLU", "Deliveroo Plus", "direct"),
    ("SQ *COFFEE COLLECTIVE", "Coffee Collective", "direct"),
    ("GREGGS PLC CD 4471", "Greggs", "direct"),
])
def test_normalise(desc, merchant, channel):
    n = normalise(desc)
    assert (n.merchant, n.channel) == (merchant, channel)


def test_cadence_tolerates_skipped_weeks():
    dates = [date(2026, 6, 6), date(2026, 6, 13), date(2026, 6, 27), date(2026, 7, 4), date(2026, 7, 11)]
    assert detect_cadence(dates)[0] == "weekly"


def test_daily_habit_is_not_a_cadence():
    assert detect_cadence([date(2026, 1, d) for d in (5, 6, 8, 9, 12, 13, 14)])[0] is None


def test_dev_set_does_not_regress():
    e = evaluate(*seed_frames(42))
    assert e["subscription_detection"]["precision"] >= 0.95
    assert e["subscription_detection"]["recall"] >= 0.95


@pytest.fixture(scope="module")
def site():
    mock_sites.reset()
    srv, base = mock_sites.serve()
    yield base, *next(iter(mock_sites.TEST_ACCOUNTS.items()))
    srv.shutdown()


def test_agent_ignores_retention_buttons(site):
    base, email, pw = site
    r = CancellationAgent(lambda m: None).run(Playbook("Prime", f"{base}/prime", email, pw))
    assert r.status == "cancelled" and r.retention_screens_declined >= 3


def test_agent_never_pays_a_fee_without_consent(site):
    base, email, pw = site
    r = CancellationAgent(lambda m: None).run(Playbook("Adobe", f"{base}/adobe", email, pw))
    assert r.status == "handoff_consent" and "£29.94" in r.handoff_message


def test_agent_hands_off_for_2fa_and_stops_without_code(site):
    base, email, pw = site
    asked = []
    r = CancellationAgent(lambda m: asked.append(m) or None).run(
        Playbook("Apple", f"{base}/apple", email, pw, target="Apple Music"))
    assert r.status == "handoff_code" and asked


def test_agent_cancels_the_right_apple_product(site):
    base, email, pw = site
    r = CancellationAgent(lambda m: mock_sites.LAST_CODE["apple"]).run(
        Playbook("Apple", f"{base}/apple", email, pw, target="Apple Music"))
    assert r.status == "cancelled" and "Apple Music" in r.evidence
