"""Local stand-ins for four real cancellation flows, each with the obstacle that makes it interesting:

  netflix  simple: login > account > cancel > finish
  prime    retention maze: "Keep my benefits" is the big button, cancel is a small link, three pages deep
  apple    2FA: a code is "sent to the member's iPhone"; the agent must pause and ask for it
  adobe    money at stake: an early termination fee appears on the final page

These are mocks for developing and testing the agent safely. They imitate the shape of each flow, not the real HTML.
"""
import random
import threading
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

SESSIONS: dict[str, dict] = {}
LAST_CODE: dict[str, str] = {}  # what "arrived on the member's phone"
TEST_ACCOUNTS = {"member@example.test": "test-password-123"}

STYLE = "<style>.primary{font-size:20px;background:#ff9900;padding:12px}.link{font-size:11px;background:none;border:none;color:#06c}</style>"


def page(title, body):
    return f"<html><head><title>{title}</title>{STYLE}</head><body><h1>{title}</h1>{body}</body></html>"


def form(action, buttons, fields=""):
    btns = "".join(f'<button name="choice" value="{v}" class="{cls}">{text}</button>' for v, text, cls in buttons)
    return f'<form method="post" action="{action}">{fields}{btns}</form>'


LOGIN = ('<form method="post" action="/{site}/login"><label>Email <input type="email" name="email"></label>'
         '<label>Password <input type="password" name="password"></label><button>Sign in</button></form>')


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def session(self):
        c = SimpleCookie(self.headers.get("Cookie", ""))
        sid = c["sid"].value if "sid" in c else None
        if sid not in SESSIONS:
            sid = f"{random.getrandbits(64):x}"
            SESSIONS[sid] = {}
            self._new_sid = sid
        return SESSIONS[sid]

    def send(self, html, status=200, location=None):
        self.send_response(status)
        if getattr(self, "_new_sid", None):
            self.send_header("Set-Cookie", f"sid={self._new_sid}; Path=/")
        if location:
            self.send_header("Location", location)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(html.encode())

    def redirect(self, to):
        self.send("", 303, to)

    def do_GET(self):
        self._new_sid = None
        self.route("GET", {})

    def do_POST(self):
        self._new_sid = None
        n = int(self.headers.get("Content-Length", 0))
        data = {k: v[0] for k, v in parse_qs(self.rfile.read(n).decode()).items()}
        self.route("POST", data)

    def route(self, method, data):
        path = urlparse(self.path).path.rstrip("/")
        parts = path.strip("/").split("/")
        site, step = parts[0], "/".join(parts[1:]) or "start"
        s = self.session().setdefault(site, {})
        handler = getattr(self, f"site_{site}", None)
        if handler is None:
            return self.send(page("Not found", ""), 404)
        if step == "login" and method == "POST":
            if TEST_ACCOUNTS.get(data.get("email")) != data.get("password"):
                return self.send(page("Sign in", "<p>Incorrect password.</p>" + LOGIN.format(site=site)))
            s["auth"] = "password"
            return self.redirect(f"/{site}/home")
        if not s.get("auth"):
            return self.send(page("Sign in", LOGIN.format(site=site)))
        return handler(s, step, method, data)

    # ---- Netflix-like: straightforward ----
    def site_netflix(self, s, step, method, data):
        if step == "home":
            return self.send(page("Home", '<a href="/netflix/browse">Browse</a> <a href="/netflix/account">Account</a>'))
        if step == "account":
            return self.send(page("Account", "<p>Standard plan, £12.99/month</p>"
                                  '<a href="/netflix/plan">Change plan</a> <a href="/netflix/cancel">Cancel membership</a>'))
        if step == "cancel" and method == "GET":
            return self.send(page("Cancel your membership?", "<p>You can restart any time.</p>" +
                                  form("/netflix/cancel", [("finish", "Finish cancellation", ""), ("back", "Go back", "")])))
        if step == "cancel" and data.get("choice") == "finish":
            s["cancelled"] = True
            return self.send(page("Membership cancelled", "<p>Your membership has been cancelled. "
                                  "It ends on 7 November 2026.</p>"))
        return self.redirect("/netflix/account")

    # ---- Prime-like: dark-pattern retention maze ----
    def site_prime(self, s, step, method, data):
        if step == "home":
            return self.send(page("Your Account", '<a href="/prime/orders">Your orders</a> '
                                  '<a href="/prime/membership">Prime membership</a>'))
        if step == "membership":
            return self.send(page("Prime membership", "<p>You've saved £214 this year.</p>"
                                  '<a href="/prime/benefits">Explore benefits</a> '
                                  '<a href="/prime/manage">Manage membership</a>'))
        if step == "manage":
            return self.send(page("Manage membership", '<a href="/prime/switch">Switch to monthly</a> '
                                  '<a href="/prime/end/1">End membership</a>'))
        flow = {
            "end/1": ("Before you go, don't lose your benefits", "<p>Members like you watched 41 hours of Prime Video.</p>",
                      [("keep", "Keep my benefits", "primary"), ("remind", "Remind me 3 days before", "primary"),
                       ("next", "Continue to cancel", "link")]),
            "end/2": ("Would you like a cheaper option?", "<p>Switch to monthly for £8.99 or pay with student pricing.</p>",
                      [("offer", "Switch to monthly and keep Prime", "primary"), ("next", "Continue to cancel", "link")]),
            "end/3": ("Your benefits end on 11 March 2027", "<p>You will lose free delivery and Prime Video.</p>",
                      [("keep", "Keep my membership", "primary"), ("next", "End my benefits", "link")]),
        }
        if step in flow and method == "GET":
            title, body, buttons = flow[step]
            return self.send(page(title, body + form(f"/prime/{step}", buttons)))
        if step in flow and method == "POST":
            if data.get("choice") != "next":
                s["retained"] = data.get("choice")
                return self.send(page("Great, you're keeping Prime", "<p>Your membership continues.</p>"))
            n = int(step.split("/")[1])
            if n < 3:
                return self.redirect(f"/prime/end/{n + 1}")
            s["cancelled"] = True
            return self.send(page("Membership cancelled", "<p>Your Prime membership has been cancelled. "
                                  "Benefits end on 11 March 2027.</p>"))
        return self.redirect("/prime/home")

    # ---- Apple-like: needs a code from the member's device ----
    def site_apple(self, s, step, method, data):
        if s.get("auth") == "password" and step != "verify":
            LAST_CODE["apple"] = f"{random.randint(0, 999999):06d}"
            return self.redirect("/apple/verify")
        if step == "verify" and method == "GET":
            return self.send(page("Two-factor authentication",
                                  "<p>A verification code has been sent to your iPhone.</p>"
                                  '<form method="post" action="/apple/verify"><label>Verification code '
                                  '<input name="code" inputmode="numeric"></label><button>Continue</button></form>'))
        if step == "verify":
            if data.get("code") == LAST_CODE.get("apple"):
                s["auth"] = "2fa"
                return self.redirect("/apple/home")
            return self.send(page("Two-factor authentication", "<p>Incorrect code.</p>"), 401)
        if step == "home":
            return self.send(page("Apple Account", '<a href="/apple/devices">Devices</a> '
                                  '<a href="/apple/subscriptions">Subscriptions</a>'))
        if step == "subscriptions":
            items = "".join(f'<li><a href="/apple/sub/{k}">{name} {price}</a></li>' for k, (name, price) in APPLE_SUBS.items())
            return self.send(page("Subscriptions", f"<ul>{items}</ul>"))
        if step.startswith("sub/"):
            k = step.split("/")[1]
            name, price = APPLE_SUBS[k]
            if method == "GET":
                return self.send(page(name, f"<p>{price}. Renews 3 November 2026.</p>" +
                                      form(f"/apple/sub/{k}", [("cancel", "Cancel Subscription", ""),
                                                                ("annual", "Change to annual and save", "primary")])))
            if data.get("choice") == "cancel" and not data.get("confirm"):
                return self.send(page("Confirm cancellation", f"<p>If you confirm, {name} ends on 3 November 2026.</p>" +
                                      form(f"/apple/sub/{k}", [("cancel", "Confirm", "")],
                                           '<input type="hidden" name="confirm" value="1">')))
            if data.get("choice") == "cancel":
                s.setdefault("cancelled", []).append(name)
                return self.send(page("Subscription cancelled", f"<p>{name} has been cancelled. "
                                      "Access continues until 3 November 2026.</p>"))
        return self.redirect("/apple/home")

    # ---- Adobe-like: fee disclosed at the last step ----
    def site_adobe(self, s, step, method, data):
        if step == "home":
            return self.send(page("Adobe account", '<a href="/adobe/plans">Plans</a> <a href="/adobe/billing">Billing</a>'))
        if step == "plans":
            return self.send(page("Plans", "<p>Photography plan (annual, paid monthly) £9.98/mo</p>"
                                  '<a href="/adobe/manage">Manage plan</a>'))
        if step == "manage":
            return self.send(page("Manage plan", '<a href="/adobe/upgrade">Upgrade</a> '
                                  '<a href="/adobe/cancel/reason">Cancel your plan</a>'))
        if step == "cancel/reason" and method == "GET":
            radios = "".join(f'<label><input type="radio" name="reason" value="{v}" required> {t}</label>'
                             for v, t in [("price", "Too expensive"), ("tech", "Technical issues"),
                                          ("noneed", "I no longer need it")])
            return self.send(page("Why are you cancelling?", form("/adobe/cancel/reason", [("next", "Continue", "")], radios)))
        if step == "cancel/reason":
            if not data.get("reason"):
                return self.send(page("Why are you cancelling?", "<p>Please choose a reason.</p>"), 400)
            return self.send(page("Wait! Here's 2 months free", "<p>Stay and get two months at no cost.</p>" +
                                  form("/adobe/cancel/review", [("accept", "Accept offer", "primary"),
                                                                ("next", "No thanks", "link")])))
        if step == "cancel/review" and data.get("choice") == "next" and not data.get("confirm"):
            return self.send(page("Review and confirm", "<p>Because you are cancelling an annual plan early, an early "
                                  "termination fee of £29.94 will be charged to your card.</p>" +
                                  form("/adobe/cancel/review", [("next", "Confirm cancellation", ""),
                                                                ("keep", "Keep my plan", "primary")],
                                       '<input type="hidden" name="confirm" value="1">')))
        if step == "cancel/review" and data.get("choice") == "next":
            s["cancelled"], s["fee_charged"] = True, 29.94
            return self.send(page("Plan cancelled", "<p>Your plan has been cancelled. A fee of £29.94 has been charged.</p>"))
        if step == "cancel/review":
            s["retained"] = data.get("choice")
            return self.send(page("Thanks for staying", "<p>Your plan continues.</p>"))
        return self.redirect("/adobe/home")


APPLE_SUBS = {"music": ("Apple Music", "£10.99/month"), "icloud": ("iCloud+ 200GB", "£2.99/month")}


def serve(port=0):
    srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://127.0.0.1:{srv.server_address[1]}"


def reset():
    SESSIONS.clear()
    LAST_CODE.clear()
