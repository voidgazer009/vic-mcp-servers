# Changelog · vic-billable-weight

## 1.0.0 · 2026-11-13

First release.

- `calculate_chargeable_weight`: 8 billing profiles (UPS, FedEx, DHL express per package; IATA air cargo 1:6000; sea LCL W/M; EU road 1:333; US domestic 139; custom), side rounding, 0.5 kg / whole-kg shipment bands, per-piece minimums (FBA lines), volume split (分泡), cm/in and kg/lb input.
- `check_express_surcharges`: UPS, FedEx, DHL 2026 international surcharge lines, minimum billable weights, over-max detection, China list prices where published.
- `audit_weight_adjustment`: re-rates declared vs audited data, verdict per tracking number, money at stake, new surcharges, Chinese/English dispute drafts (draft only).
- `optimize_box_size`: volume ceiling, single-side cuts, saving per 1 cm, tightest box around the product, near-threshold warnings.
- `compare_freight_options`: ranks real quotes across modes by total, cost per real kg and cost per day saved.
- Resource `freight://billable-weight-rules`, prompt `audit_freight_invoice`.
- stdio and stateless Streamable HTTP. Offline, no API key.
