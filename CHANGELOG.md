# Changelog

How the public product grew. Each entry is the *why*, not a file list. The README thesis stays locked.

## Unreleased

Reviewers needed a CI shield and a short map of pure vs product layers, plus the seams a later pricer or asset class would use, without turning those seams into features. Architecture names `reprice_book` as the mark and `demo-build` as the `book_metrics` writer.

CRR tests needed to show the early-exercise *decision*: an American put holds intrinsic when the European is below it, and a no-dividend American call is not exercised.

## 0.1.0 — 2026-08-13

Shipped P0–P7 as a narrow book-operations stack, then set the GitHub repo public.

### P7 — Public launch

Reviewers needed a data contract, layout, methods, and limitations on the README, and a tree free of private-source names, before the repo could be public. The thesis paragraph did not change.

### P6 — Slim Streamlit

Operators needed to inspect local Parquet (DQ, ledger, scenarios) without a pricer, VaR, or IV-smile gallery. Three pages, localhost, `optledger[web]`.

### P5 — Thin TWR

Snapshot NLV plus deposits needed a flow-adjusted return path that is not a QuantStats clone: TWR, max drawdown, time-to-recovery. No first-party Sharpe family.

### P4 — Lifecycle ledger

Position diffs are not a ledger. Fill, expire-worthless, assignment, deposit, and fee rows exist so recon can report quantity, cash, and NLV breaks instead of inferring or silently fixing them.

### P3 — Snapshots and DQ

The product surface is joinable Parquet pins, not a notebook. Seeded XYZ snapshots plus fail-closed pin/join/schema checks (`demo-build`, `dq`) are what a reviewer can run offline.

### P2 — Small-grid book reprice

Later pins needed a mark-to-model P/L grid from the same book. Supporting math only; not a VaR engine.

### P1 — Thin BS and CRR

Book metrics need prices. European BSM and American CRR exist so pins can be marked; this is not a QuantLib or vollib replacement.

### P0 — Skeleton

A public repo needed a locked thesis, MIT license, Python 3.12+, uv/ruff/mypy/pytest/CI, and `data/` gitignored, before any math or Parquet.
