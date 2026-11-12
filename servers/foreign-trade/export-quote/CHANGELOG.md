# Changelog · vic-export-quote

## 1.0.0 · 2026-11-12

First release.

- `calculate_export_quote`: EXW, FOB/FCA, CFR/CPT, CIF/CIP, DDP in one call. FOB anchored to the target margin, CIF insurance on 110% of CIF, duty on CIF or FOB basis, import VAT on CIF + duty, warnings for margin floor, DDP margin squeeze, small-order fixed-cost drag, missing freight or duty.
- `price_by_quantity`: MOQ / tier price table.
- `plan_container_loading`: 20GP / 40GP / 40HQ fit by space and weight, cheapest box mix by lane rate ratio, LCL suggestion, oversize and heavy-cargo warnings.
- `explain_incoterm`: Incoterms 2020 matrix with pitfalls and misuse detection (FOB/CIF for air or containers).
- `convert_currency`: ECB reference rates via frankfurter.dev, no API key.
- Resource `incoterms://2020`, prompt `quotation_reply`.
- stdio and stateless Streamable HTTP. 29 tests.
