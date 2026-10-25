"""Load UK bank CSV exports (Monzo, Starling, Barclays, Lloyds, HSBC, Nationwide-style) into one shape."""
from pathlib import Path

import pandas as pd

DATE = ["date", "transaction date", "posted date", "posting date", "completed date"]
DESC = ["name", "description", "transaction description", "merchant", "payee", "counter party", "counterparty",
        "details", "narrative", "memo", "reference"]
AMOUNT = ["amount", "amount (gbp)", "amount(gbp)", "value", "paid amount"]
OUT = ["paid out", "money out", "debit", "debit amount", "out"]
IN = ["paid in", "money in", "credit", "credit amount", "in"]
TYPE = ["type", "transaction type"]
TYPE_CODES = {"DD": "DIRECT DEBIT", "DDR": "DIRECT DEBIT", "DIRECT DEBIT": "DIRECT DEBIT", "SO": "STANDING ORDER",
              "STO": "STANDING ORDER", "STANDING ORDER": "STANDING ORDER", "DEB": "CARD PAYMENT", "POS": "CARD PAYMENT",
              "CARD PAYMENT": "CARD PAYMENT", "CARD": "CARD PAYMENT", "FPO": "FASTER PAYMENT", "FPI": "CREDIT",
              "BGC": "CREDIT", "FASTER PAYMENT": "FASTER PAYMENT", "CREDIT": "CREDIT"}


def _pick(cols: dict, options: list[str]):
    return next((cols[o] for o in options if o in cols), None)


def load(path: str | Path, flip_sign: bool = False) -> pd.DataFrame:
    """Returns id, date, description, amount (negative = money out), type."""
    df = pd.read_csv(path)
    cols = {c.strip().lower(): c for c in df.columns}
    dcol, ncol = _pick(cols, DATE), _pick(cols, DESC)
    if dcol is None or ncol is None:
        raise ValueError(f"Couldn't find date/description columns in {list(df.columns)}")
    out = pd.DataFrame()
    iso = df[dcol].astype(str).str.match(r"^\d{4}-\d{2}-\d{2}").all()
    out["date"] = (pd.to_datetime(df[dcol].astype(str).str[:10], format="%Y-%m-%d") if iso
                   else pd.to_datetime(df[dcol], dayfirst=True, format="mixed")).dt.date
    out["description"] = df[ncol].astype(str).str.strip()
    acol = _pick(cols, AMOUNT)
    if acol is not None:
        amt = pd.to_numeric(df[acol].astype(str).str.replace(r"[£,]", "", regex=True), errors="coerce")
    else:
        o, i = _pick(cols, OUT), _pick(cols, IN)
        num = lambda c: pd.to_numeric(df[c].astype(str).str.replace(r"[£,]", "", regex=True), errors="coerce").fillna(0)
        amt = (num(i) if i else 0) - (num(o) if o else 0)
    out["amount"] = -amt if flip_sign else amt
    tcol = _pick(cols, TYPE)
    if tcol is not None:
        out["type"] = df[tcol].astype(str).str.upper().str.strip().map(lambda t: TYPE_CODES.get(t, t))
    else:
        out["type"] = ["CREDIT" if a > 0 else "CARD PAYMENT" for a in out["amount"]]
    out["id"] = df[cols["id"]].astype(str) if "id" in cols else [f"r{i:05d}" for i in range(len(df))]
    return out.dropna(subset=["amount"])[["id", "date", "description", "amount", "type"]]
