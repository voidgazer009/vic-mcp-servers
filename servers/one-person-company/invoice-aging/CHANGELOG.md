# Changelog · vic-invoice-aging

## 1.0.0 · 2026-11-18

First release.

- `calculate_due_date`: Net N / EOM+N due dates with weekend and over-60-day warnings.
- `age_invoices`: receivables aging buckets, per-client balances, chase list, concentration warnings.
- `calculate_late_interest`: EU Directive 2011/7/EU, UK Late Payment Act and contract-rate interest plus fixed recovery sums.
- `draft_payment_reminder`: escalating EN/ZH reminder drafts (never sent).
- Resource `receivables://rules`, prompt `weekly_receivables_review`. Offline, stdio and stateless Streamable HTTP.
