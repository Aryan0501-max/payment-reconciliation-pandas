"""
reconcile.py
Automated reconciliation of a company's transaction log against a payment
gateway statement, plus a recurring monthly finance summary.

Steps
  1. Load both files
  2. Clean: standardise transaction IDs, parse dates, remove duplicate entries
  3. Reconcile: match on txn_id and classify every record
  4. Summarise: monthly model and payment-method summary (pandas groupby)
  5. Export: Excel report for stakeholder review

Run:  python generate_data.py   (once, to create the sample data)
      python reconcile.py
"""
from pathlib import Path
import logging
import numpy as np
import pandas as pd

BASE = Path(__file__).parent
DATA = BASE / "data"
OUT = BASE / "output"
OUT.mkdir(exist_ok=True)
TOLERANCE = 0.01   # amounts within 1 paisa are treated as equal

logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
log = logging.getLogger("reconcile")


# ---------------------------------------------------------------- 1. LOAD
def load_data():
    txn = pd.read_csv(DATA / "transactions.csv", parse_dates=["txn_date"])
    gw = pd.read_csv(DATA / "gateway_statement.csv", parse_dates=["txn_date", "settlement_date"])
    log.info("Loaded %d log rows and %d gateway rows", len(txn), len(gw))
    return txn, gw


# ---------------------------------------------------------------- 2. CLEAN
def clean(df, name):
    """Standardise IDs and remove duplicate transaction IDs.
    Returns (clean_df, removed_duplicates_df)."""
    df = df.copy()
    df["txn_id"] = df["txn_id"].astype(str).str.strip().str.upper()   # " txn100001 " -> "TXN100001"
    dup_mask = df.duplicated(subset="txn_id", keep="first")
    removed = df[dup_mask].assign(source=name)
    df = df[~dup_mask].reset_index(drop=True)
    log.info("%s: removed %d duplicate rows, %d remain", name, len(removed), len(df))
    return df, removed


# ---------------------------------------------------------------- 3. RECONCILE
def reconcile(txn, gw):
    txn = txn.rename(columns={"amount": "amount_log", "txn_date": "date_log", "payment_method": "method_log"})
    gw = gw.rename(columns={"amount": "amount_gw", "txn_date": "date_gw", "payment_method": "method_gw"})

    m = txn.merge(gw, on="txn_id", how="outer", indicator=True)   # keep every record from both sides

    m["difference"] = (m["amount_log"] - m["amount_gw"]).round(2)  # NaN when a record is on one side only
    conditions = [
        (m["_merge"] == "left_only"),
        (m["_merge"] == "right_only"),
        (m["_merge"] == "both") & (m["difference"].abs() > TOLERANCE),
    ]
    labels = ["Missing in gateway", "Missing in log", "Amount mismatch"]
    m["status"] = np.select(conditions, labels, default="Matched")

    m["txn_date"] = m["date_log"].combine_first(m["date_gw"])
    m["payment_method"] = m["method_log"].combine_first(m["method_gw"])
    m["month"] = m["txn_date"].dt.to_period("M").astype(str)
    m["customer_id"] = m["customer_id"].fillna("UNKNOWN")
    cols = ["txn_id", "order_id", "customer_id", "payment_method", "month", "txn_date",
            "amount_log", "amount_gw", "difference", "fee", "net_settlement", "settlement_date", "status"]
    return m[cols].sort_values(["month", "txn_id"]).reset_index(drop=True)


# ---------------------------------------------------------------- 4. SUMMARISE
def monthly_summary(rec):
    g = rec.groupby("month")
    out = pd.DataFrame({
        "records": g.size(),
        "log_amount": g["amount_log"].sum(),
        "gateway_amount": g["amount_gw"].sum(),
        "matched": g["status"].apply(lambda s: (s == "Matched").sum()),
        "exceptions": g["status"].apply(lambda s: (s != "Matched").sum()),
        "gateway_fees": g["fee"].sum(),
        "net_settlement": g["net_settlement"].sum(),
    })
    out["match_rate_%"] = (out["matched"] / out["records"] * 100).round(2)
    out["fee_%_of_gateway_amount"] = (out["gateway_fees"] / out["gateway_amount"] * 100).round(2)
    mism = rec[rec["status"] == "Amount mismatch"].groupby("month")["difference"].sum()
    out["net_amount_mismatch"] = mism.reindex(out.index).fillna(0)
    out.loc["TOTAL"] = out.sum(numeric_only=True)
    out.loc["TOTAL", "match_rate_%"] = round(out.loc["TOTAL", "matched"] / out.loc["TOTAL", "records"] * 100, 2)
    out.loc["TOTAL", "fee_%_of_gateway_amount"] = round(
        out.loc["TOTAL", "gateway_fees"] / out.loc["TOTAL", "gateway_amount"] * 100, 2)
    return out.round(2).reset_index()


def method_summary(rec):
    pt = rec.pivot_table(index="payment_method", columns="status", values="txn_id",
                         aggfunc="count", fill_value=0)
    pt["total"] = pt.sum(axis=1)
    pt["match_rate_%"] = (pt.get("Matched", 0) / pt["total"] * 100).round(2)
    fees = rec.groupby("payment_method")[["amount_gw", "fee"]].sum()
    pt["fee_%"] = (fees["fee"] / fees["amount_gw"] * 100).round(2)
    return pt.reset_index()


def key_metrics(raw_txn, raw_gw, rem_txn, rem_gw, rec):
    c = rec["status"].value_counts()
    rows = [
        ("Log rows (raw)", len(raw_txn)), ("Duplicates removed from log", len(rem_txn)),
        ("Gateway rows (raw)", len(raw_gw)), ("Duplicates removed from gateway", len(rem_gw)),
        ("Matched", int(c.get("Matched", 0))), ("Amount mismatch", int(c.get("Amount mismatch", 0))),
        ("Missing in gateway", int(c.get("Missing in gateway", 0))),
        ("Missing in log", int(c.get("Missing in log", 0))),
        ("Match rate %", round(c.get("Matched", 0) / len(rec) * 100, 2)),
        ("Amount at risk: missing in gateway (INR)", round(rec.loc[rec.status == "Missing in gateway", "amount_log"].sum(), 2)),
        ("Amount at risk: missing in log (INR)", round(rec.loc[rec.status == "Missing in log", "amount_gw"].sum(), 2)),
        ("Net amount mismatch (INR)", round(rec.loc[rec.status == "Amount mismatch", "difference"].sum(), 2)),
    ]
    return pd.DataFrame(rows, columns=["Metric", "Value"])


# ---------------------------------------------------------------- 5. EXPORT
def autofit(ws):
    for col in ws.columns:
        width = max(len(str(c.value)) if c.value is not None else 0 for c in col)
        ws.column_dimensions[col[0].column_letter].width = min(max(width + 2, 10), 40)
    ws.freeze_panes = "A2"


def export(sheets, path):
    with pd.ExcelWriter(path, engine="openpyxl") as xw:
        for name, df in sheets.items():
            df.to_excel(xw, sheet_name=name, index=False)
            autofit(xw.sheets[name])
    log.info("Report saved: %s", path)


def main():
    raw_txn, raw_gw = load_data()
    txn, rem_txn = clean(raw_txn, "log")
    gw, rem_gw = clean(raw_gw, "gateway")
    rec = reconcile(txn, gw)

    # control checks: every cleaned record must be classified exactly once
    left = rec["status"].isin(["Matched", "Amount mismatch", "Missing in gateway"]).sum()
    right = rec["status"].isin(["Matched", "Amount mismatch", "Missing in log"]).sum()
    assert left == len(txn) and right == len(gw), "Control check failed: record counts do not tie"
    log.info("Control checks passed")

    sheets = {
        "Summary": key_metrics(raw_txn, raw_gw, rem_txn, rem_gw, rec),
        "Monthly": monthly_summary(rec),
        "By Payment Method": method_summary(rec),
        "Exceptions": rec[rec["status"] != "Matched"],
        "Duplicates Removed": pd.concat([rem_txn, rem_gw], ignore_index=True),
        "All Reconciled": rec,
    }
    export(sheets, OUT / "reconciliation_report.xlsx")
    rec[rec["status"] != "Matched"].to_csv(OUT / "exceptions.csv", index=False)
    print(sheets["Summary"].to_string(index=False))


if __name__ == "__main__":
    main()
