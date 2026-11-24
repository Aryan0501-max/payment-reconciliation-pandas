"""
generate_data.py
Creates SAMPLE (fictional) data for the reconciliation project:
  data/transactions.csv      -> company's internal transaction log
  data/gateway_statement.csv -> payment gateway's settlement statement

The data is intentionally messy (duplicates, missing records, amount
mismatches, inconsistent IDs) so the reconciliation script has real work to do.
All data is randomly generated with a fixed seed. No real company or customer data.
"""
from pathlib import Path
import numpy as np
import pandas as pd

SEED = 42
N_TXN = 1200
FEE_RATE = {"UPI": 0.005, "Card": 0.02, "NetBanking": 0.018, "Wallet": 0.015}

rng = np.random.default_rng(SEED)
base = Path(__file__).parent / "data"
base.mkdir(exist_ok=True)

# ---- 1. Clean "truth" set of transactions (Jun 2026 - Nov 2026) ----
dates = pd.to_datetime("2026-06-01") + pd.to_timedelta(rng.integers(0, 183, N_TXN), unit="D")
methods = rng.choice(list(FEE_RATE), size=N_TXN, p=[0.50, 0.28, 0.12, 0.10])
amounts = np.round(rng.choice([199, 299, 499, 799, 999, 1499, 2499, 4999], size=N_TXN)
                   * rng.uniform(0.9, 1.1, N_TXN), 2)
truth = pd.DataFrame({
    "txn_id": [f"TXN{100000 + i}" for i in range(N_TXN)],
    "order_id": [f"ORD{500000 + i}" for i in range(N_TXN)],
    "customer_id": [f"CUST{rng.integers(1000, 1400)}" for _ in range(N_TXN)],
    "payment_method": methods,
    "amount": amounts,
    "txn_date": dates,
}).sort_values("txn_date").reset_index(drop=True)

# ---- 2. Gateway statement (starts as a copy of the truth) ----
gw = truth[["txn_id", "payment_method", "amount", "txn_date"]].copy()
gw["fee"] = (gw["amount"] * gw["payment_method"].map(FEE_RATE)).round(2)
gw["net_settlement"] = (gw["amount"] - gw["fee"]).round(2)
gw["settlement_date"] = gw["txn_date"] + pd.to_timedelta(rng.integers(1, 4, len(gw)), unit="D")

# (a) 18 transactions the gateway never received (missing in gateway)
drop_idx = rng.choice(gw.index, 18, replace=False)
gw = gw.drop(index=drop_idx)

# (b) 20 amount mismatches (gateway amount differs from company log)
mis_idx = rng.choice(gw.index, 20, replace=False)
gw.loc[mis_idx, "amount"] = (gw.loc[mis_idx, "amount"] - rng.choice([10, 25, 50, 100], 20)).round(2)
gw["fee"] = (gw["amount"] * gw["payment_method"].map(FEE_RATE)).round(2)
gw["net_settlement"] = (gw["amount"] - gw["fee"]).round(2)

# (c) 12 gateway records the company log never booked (missing in log)
extra = pd.DataFrame({
    "txn_id": [f"TXN{900000 + i}" for i in range(12)],
    "payment_method": rng.choice(list(FEE_RATE), 12),
    "amount": np.round(rng.choice([299, 499, 999, 1499], 12) * 1.0, 2),
    "txn_date": pd.to_datetime("2026-06-01") + pd.to_timedelta(rng.integers(0, 183, 12), unit="D"),
})
extra["fee"] = (extra["amount"] * extra["payment_method"].map(FEE_RATE)).round(2)
extra["net_settlement"] = (extra["amount"] - extra["fee"]).round(2)
extra["settlement_date"] = extra["txn_date"] + pd.Timedelta(days=2)
gw = pd.concat([gw, extra], ignore_index=True)

# (d) 5 duplicate rows inside the gateway file
gw = pd.concat([gw, gw.sample(5, random_state=SEED)], ignore_index=True)

# ---- 3. Company transaction log: start from truth, then make it messy ----
log = truth.copy()
# (e) 25 exact duplicate rows
log = pd.concat([log, log.sample(25, random_state=SEED)], ignore_index=True)
# (f) messy IDs: lowercase / trailing spaces on 30 rows
messy_idx = rng.choice(log.index, 30, replace=False)
log["txn_id"] = log["txn_id"].astype(object)
for i in messy_idx:
    log.at[i, "txn_id"] = (log.at[i, "txn_id"].lower() + " ") if i % 2 else (" " + log.at[i, "txn_id"])
# (g) a few missing customer IDs
log.loc[rng.choice(log.index, 8, replace=False), "customer_id"] = np.nan

log = log.sample(frac=1, random_state=SEED).reset_index(drop=True)   # shuffle
gw = gw.sample(frac=1, random_state=SEED).reset_index(drop=True)

log.to_csv(base / "transactions.csv", index=False)
gw.to_csv(base / "gateway_statement.csv", index=False)
print(f"transactions.csv: {len(log)} rows | gateway_statement.csv: {len(gw)} rows")
