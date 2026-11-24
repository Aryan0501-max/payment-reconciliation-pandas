# Payment Gateway Reconciliation and Monthly Finance Report (Python, pandas)

Automates the reconciliation of a company's internal transaction log against a payment gateway
statement, removes duplicate entries before ledger posting, and produces a monthly summary
for stakeholder review.

> **Note:** This is a self-initiated learning project. All data is randomly generated sample data
> for a fictional business (Jun 2026 - Nov 2026). No real company or customer data is used.

## Problem

Online payments are recorded twice: in the company's own transaction log and in the payment
gateway's settlement statement. The two should match. In practice they do not: records are duplicated,
IDs are formatted inconsistently, some transactions exist on one side only, and some amounts differ.
Finance teams reconcile these by hand every month. This project automates it.

## What the script does

1. **Load** `transactions.csv` (company log) and `gateway_statement.csv` (gateway).
2. **Clean:** standardise `txn_id` (trim spaces, upper-case) and remove duplicate transaction IDs.
3. **Reconcile:** outer-merge both files on `txn_id` and classify every record as
   `Matched`, `Amount mismatch`, `Missing in gateway` or `Missing in log`.
4. **Control check:** assert that every cleaned record is classified exactly once.
5. **Summarise:** monthly model (`groupby`) and payment-method summary (`pivot_table`) with
   match rate, fees, net settlement and mismatch value.
6. **Export:** one Excel report with 6 sheets plus `exceptions.csv`.

## Project structure

```
generate_data.py     creates the sample input files (run once)
reconcile.py         cleaning, reconciliation, summaries, Excel export
data/                transactions.csv, gateway_statement.csv
output/              reconciliation_report.xlsx, exceptions.csv
requirements.txt
```

## How to run

```
pip install -r requirements.txt
python generate_data.py
python reconcile.py
```

Google Colab: upload the project files, then run `!pip install openpyxl`, `!python generate_data.py`
and `!python reconcile.py`.

## Sample results (from the generated data)

| Metric | Value |
|---|---|
| Log rows (raw) / duplicates removed | 1,225 / 25 |
| Gateway rows (raw) / duplicates removed | 1,199 / 5 |
| Matched | 1,162 |
| Amount mismatches | 20 |
| Missing in gateway | 18 (INR 26,778 at risk) |
| Missing in log | 12 (INR 9,188 unbooked) |
| Overall match rate | 95.87% |
| Gateway fees | INR 19,319 (about 1.15% of gateway amount) |

The data was generated with known problems (25 + 5 duplicates, 20 mismatches, 18 + 12 missing records),
and the script finds exactly those, which is how the logic was validated.

## Report sheets

- **Summary:** key counts and amounts at risk
- **Monthly:** records, matched, exceptions, match rate, fees, net settlement, mismatch by month
- **By Payment Method:** status counts, match rate and effective fee % for UPI, Card, NetBanking, Wallet
- **Exceptions:** every record that needs follow-up
- **Duplicates Removed:** audit trail of rows dropped before reconciliation
- **All Reconciled:** full record-level result

## Key pandas concepts used

`read_csv`, `str.strip/upper`, `duplicated / drop_duplicates`, `merge(how="outer", indicator=True)`,
`np.select`, `combine_first`, `groupby`, `pivot_table`, `to_period`, `ExcelWriter`.

## Assumptions and limitations

- Records are matched on `txn_id` only; amounts within INR 0.01 are treated as equal.
- Duplicates are defined as repeated `txn_id`; the first occurrence is kept.
- Sample data is simplified. Real gateways add refunds, chargebacks, GST on fees and batch settlements.
- Possible next steps: handle refunds, match on order ID as a fallback, schedule the script monthly,
  and add unit tests.
