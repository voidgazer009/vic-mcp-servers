# Changelog · vic-cashflow-forecast

## 1.0.0 · 2026-11-22

First release.

- `forecast_cashflow`: weekly forecast (1-52 weeks, default 13) with repeats, confidence, delays, buffer and negative-week warnings.
- `calculate_runway`: months of cash left with optional income growth.
- `stress_test_cashflow`: base vs delayed/haircut inflows side by side.
- Resource `cashflow://method`, prompt `thirteen_week_cash_check`. Offline, stdio and stateless Streamable HTTP.
