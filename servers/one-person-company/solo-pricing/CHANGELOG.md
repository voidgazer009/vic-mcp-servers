# Changelog · vic-solo-pricing

## 1.0.0 · 2026-11-14

First release.

- `calculate_hourly_rate`: target net income to minimum hourly and day rate (tax gross-up as a division, expenses, buffer, billable utilization, payment fees).
- `quote_fixed_project`: fixed-fee quote with risk buffer, included revisions, pass-through costs, fees, and overrun scenarios.
- `gross_up_for_fees`: invoice amount that nets the wanted amount after percentage fee, fixed fee and FX spread.
- `analyze_discount`: extra volume a discount needs to keep profit.
- `check_real_hourly_rate`: what a finished job really paid per hour.
- Resource `pricing://formulas`, prompt `price_a_project`. Offline, stdio and stateless Streamable HTTP.
