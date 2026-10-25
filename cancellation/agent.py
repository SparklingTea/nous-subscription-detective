"""A small rule-based browser agent for cancellation flows, with hard guardrails.

Deliberately not an LLM: choosing "Continue to cancel" over a big orange "Keep my benefits" is a
classification problem a word list handles reliably, and the expensive mistakes (paying a fee, losing
credits, typing a 2FA code) are handled by rules that stop and hand over to the member. An LLM is the
obvious upgrade for *navigation* on unfamiliar sites; it should never own the stop conditions.

Production would drive a real browser (Playwright) through the same interface; here it speaks HTTP + HTML
so it runs anywhere against the local mocks.
"""
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from html.parser import HTMLParser
from http.cookiejar import CookieJar
from typing import Callable

CANCEL_WORDS = ["cancel", "end membership", "end my", "finish cancellation", "turn off", "no thanks", "confirm"]
RETAIN_WORDS = ["keep", "stay", "remind", "offer", "switch", "upgrade", "save", "pause", "change to", "accept",
                "explore"]
NAV_WORDS = {"subscriptions": 3, "membership": 3, "manage": 3, "plans": 2, "plan": 2, "account": 2, "settings": 1}
REASON_PREFERENCE = ["no longer need", "don't need", "not using", "other", "too expensive"]

SUCCESS = re.compile(r"(has been cancelled|membership cancelled|subscription cancelled|plan cancelled|cancellation confirmed)", re.I)
RETAINED = re.compile(r"(you're keeping|thanks for staying|membership continues|plan continues)", re.I)
# Hard stop: any money leaving, or value lost, needs the member's explicit yes
MONEY_RISK = re.compile(r"\b(fee|penalty|charged|charge of|lose[^.]{0,20}credits?|unused credits)\b", re.I)
END_DATE = re.compile(r"(?:ends on|until|end on)\s+(\d{1,2} \w+ \d{4})", re.I)


@dataclass
class Form:
    action: str
    method: str
    fields: list = field(default_factory=list)  # (name, type, value, label)
    buttons: list = field(default_factory=list)  # (name, value, text)


class Page(HTMLParser):
    def __init__(self, url, html):
        super().__init__()
        self.url, self.title, self.text_parts = url, "", []
        self.links: list[tuple[str, str]] = []
        self.forms: list[Form] = []
        self._in = None
        self._buf = ""
        self._label = ""
        self._pending_btn = None
        self.feed(html)
        self.text = " ".join(" ".join(self.text_parts).split())

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "title":
            self._in = "title"
        elif tag in ("style", "script"):
            self._in = "skip"
        elif tag == "a":
            self._in, self._buf, self._href = "a", "", a.get("href", "")
        elif tag == "form":
            self.forms.append(Form(urllib.parse.urljoin(self.url, a.get("action", self.url)), a.get("method", "get").lower()))
        elif tag == "label":
            self._label = ""
        elif tag == "input" and self.forms:
            self.forms[-1].fields.append((a.get("name"), a.get("type", "text"), a.get("value", ""), self._label.strip()))
        elif tag == "button" and self.forms:
            self._in, self._buf, self._pending_btn = "button", "", (a.get("name"), a.get("value"))

    def handle_endtag(self, tag):
        if tag in ("title", "style", "script"):
            self._in = None
        elif tag == "a" and self._in == "a":
            self.links.append((self._buf.strip(), urllib.parse.urljoin(self.url, self._href)))
            self._in = None
        elif tag == "button" and self._in == "button":
            self.forms[-1].buttons.append((*self._pending_btn, self._buf.strip()))
            self._in = None
        elif tag == "label" and self.forms and self.forms[-1].fields:
            name, typ, val, lab = self.forms[-1].fields[-1]
            if not lab:
                self.forms[-1].fields[-1] = (name, typ, val, self._label.strip())

    def handle_data(self, data):
        if self._in == "title":
            self.title += data
        elif self._in != "skip":
            self.text_parts.append(data)
            self._label += data
            if self._in in ("a", "button"):
                self._buf += data


@dataclass
class Playbook:
    merchant: str
    start_url: str
    email: str
    password: str
    target: str | None = None  # which subscription on a multi-product account
    consent_to_fee: bool = False
    max_steps: int = 20


@dataclass
class Result:
    merchant: str
    status: str  # cancelled | handoff_code | handoff_consent | retained | stuck
    steps: int
    trace: list
    evidence: str = ""
    ends_on: str | None = None
    retention_screens_declined: int = 0
    handoff_message: str | None = None


def score(text: str, target: str | None) -> int:
    t = text.lower()
    if any(w in t for w in RETAIN_WORDS):
        return -10
    s = 0
    if any(w in t for w in CANCEL_WORDS):
        s += 10
    s += sum(v for w, v in NAV_WORDS.items() if w in t.split() or w in t)
    if target and target.lower() in t:
        s += 6
    return s


class CancellationAgent:
    def __init__(self, ask_member: Callable[[str], str | None]):
        self.ask_member = ask_member  # e.g. a WhatsApp message to the member; returns their reply or None

    def run(self, pb: Playbook) -> Result:
        opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(CookieJar()))
        trace, visited, declined = [], set(), 0

        def fetch(url, data=None):
            body = urllib.parse.urlencode(data).encode() if data is not None else None
            try:
                with opener.open(url, body) as r:
                    return Page(r.geturl(), r.read().decode())
            except urllib.error.HTTPError as e:
                return Page(e.geturl(), e.read().decode())

        page = fetch(pb.start_url)
        for step in range(1, pb.max_steps + 1):
            entry = {"step": step, "url": urllib.parse.urlparse(page.url).path, "title": page.title}
            trace.append(entry)
            if SUCCESS.search(page.text) or SUCCESS.search(page.title):
                m = END_DATE.search(page.text)
                entry["action"] = "done"
                return Result(pb.merchant, "cancelled", step, trace, page.text[:200], m and m.group(1), declined)
            if RETAINED.search(page.text) or RETAINED.search(page.title):
                entry["action"] = "ended up retained"
                return Result(pb.merchant, "retained", step, trace, page.text[:200])
            risk = MONEY_RISK.search(page.text)
            if risk and not pb.consent_to_fee and any(score(b[2], None) > 0 for f in page.forms for b in f.buttons):
                sentence = next(x for x in re.split(r"(?<=[.!?])\s+", page.text) if MONEY_RISK.search(x))
                msg = (f"Before I confirm cancelling {pb.merchant}: the site says \"{sentence}\" "
                       "Do you want me to go ahead?")
                entry["action"] = "STOP: money at stake, asking member"
                return Result(pb.merchant, "handoff_consent", step, trace, page.text[:200], handoff_message=msg,
                              retention_screens_declined=declined)

            form_with_password = next((f for f in page.forms if any(t == "password" for _, t, _, _ in f.fields)), None)
            if form_with_password:
                data = {n: pb.email if t == "email" else pb.password for n, t, _, _ in form_with_password.fields}
                entry["action"] = "sign in"
                page = fetch(form_with_password.action, data)
                continue
            code_form = next((f for f in page.forms if any(re.search(r"code|otp", (n or "") + l, re.I)
                                                           for n, _, _, l in f.fields)), None)
            if code_form:
                msg = f"{pb.merchant} has just sent a verification code to your phone. Reply with it and I'll carry on."
                entry["action"] = "pause: asked member for 2FA code"
                code = self.ask_member(msg)
                if not code:
                    return Result(pb.merchant, "handoff_code", step, trace, handoff_message=msg)
                name = next(n for n, _, _, l in code_form.fields if re.search(r"code|otp", (n or "") + l, re.I))
                page = fetch(code_form.action, {name: code.strip()})
                continue

            options = []
            for text, href in page.links:
                options.append((score(text, pb.target), text, ("link", href)))
            for f in page.forms:
                for name, value, text in f.buttons:
                    options.append((score(text, pb.target) or (1 if len(f.buttons) == 1 else 0), text, ("button", f, name, value)))
            options = [o for o in options if (page.url, o[1]) not in visited]
            if not options or max(o[0] for o in options) <= 0:
                entry["action"] = "stuck: no safe next step"
                return Result(pb.merchant, "stuck", step, trace, page.text[:200])
            best = max(options, key=lambda o: o[0])
            visited.add((page.url, best[1]))
            if any(o[0] < 0 for o in options):
                declined += 1
            entry["action"] = f"click '{best[1]}'" + (f" (ignored: {', '.join(o[1] for o in options if o[0] < 0)})"
                                                       if any(o[0] < 0 for o in options) else "")
            if best[2][0] == "link":
                page = fetch(best[2][1])
            else:
                _, f, name, value = best[2]
                data = {n: v for n, t, v, _ in f.fields if t == "hidden" and n}
                radios = [(n, v, l) for n, t, v, l in f.fields if t == "radio"]
                if radios:
                    pick = next((r for p in REASON_PREFERENCE for r in radios if p in r[2].lower()), radios[0])
                    data[pick[0]] = pick[1]
                    entry["action"] += f", reason '{pick[2]}'"
                if name:
                    data[name] = value
                page = fetch(f.action, data)
        return Result(pb.merchant, "stuck", pb.max_steps, trace)
