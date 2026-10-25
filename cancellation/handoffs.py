"""What the agent produces for routes it shouldn't (or can't) automate: phone scripts, emails, bank requests."""
from datetime import date, timedelta


def phone_script(name: str, monthly: float, notice_days: int = 31, walk_away: float | None = None) -> str:
    end = date.today() + timedelta(days=notice_days)
    lines = [f"CALL SCRIPT: cancel {name}",
             f"1. 'I'm calling to give notice to cancel my {name} subscription, effective {end:%d %B %Y}.'",
             "2. Have ready: account number, postcode, last payment amount "
             f"(£{monthly:.2f}).",
             "3. If offered a retention deal: " + (f"only accept if the new price is £{walk_away:.2f}/month or less "
                                                   "with no new minimum term." if walk_away else
                                                   "decline unless the member asked to stay at a lower price."),
             "4. Ask for: a cancellation reference, the final bill date, and any early termination charge in writing.",
             "5. If the agent refuses or stalls, ask for the complaints procedure; note time and name."]
    return "\n".join(lines)


def cancellation_email(name: str, member: str, account_ref: str = "[account number]") -> str:
    return (f"Subject: Notice of cancellation: {name} ({account_ref})\n\n"
            f"Hello,\n\nPlease cancel my {name} subscription, account {account_ref}, at the earliest date my terms "
            "allow, and confirm in writing the end date, any final charge, and that no further payments will be taken.\n\n"
            f"Thank you,\n{member}")


def bank_cpa_request(merchant: str, last_amount: float, last_date: str) -> str:
    return (f"I'd like to stop the recurring card payment (continuous payment authority) to {merchant}. "
            f"The most recent payment was £{last_amount:.2f} on {last_date}. I have withdrawn my consent for future "
            "payments, so please block any further payments to this merchant on my card.")
