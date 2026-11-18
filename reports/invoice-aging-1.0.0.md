# Review report · invoice-aging 1.0.0 (2026-11-18)

Direction: AI 一人公司 · Standard: REVIEW_STANDARD v1.4

## 1. 选题理由
Freelancers invoicing abroad lose money on late payments: they forget due dates, have no aging view, and do not know they can claim statutory interest plus a fixed recovery sum (EU Directive 2011/7/EU: reference rate + 8 points, at least EUR 40; UK Late Payment Act 1998: base + 8%, GBP 40/70/100). The roadmap's invoice-tracker needs storage; the stateless maths and reminder drafts are the part that is deterministic and useful today, so this version is stateless.

## 2. 竞品检查
Registry search "invoice": dozens of servers (app.wishpool country e-invoicing, solidinvoice, euinvoice, invoicetable). They create or transmit invoices through tax portals or one app. None does aging, statutory interest and escalating reminders offline. Different niche, so proceed.

## 3. 自动审核
Hard gates G2-G9 pass; automated score 61/61 after the fixes below (first run: B4 4.6/5 because date parameters had no constraint, F4 pending this report).

## 4. 人工评分
| 项 | 得分 | 说明 |
|---|---|---|
| G1/A1 real pain | 6/6 | late payment is a top freelancer complaint |
| A2 value | 4/5 | interest + fixed sum quantified; amounts depend on user-supplied rate |
| A3 differentiation | 4/4 | see section 2 |
| A4 granularity | 5/5 | 4 tools, one job each |
| C1 golden/edge tests | 5/6 | 5 hand-checked goldens, boundaries, errors; no property tests |
| C2 authority | 5/5 | Directive articles and UK Act cited in code and README (from the statutes, reference rates left to the user) |
| D1/D2/D4 | 8/8 | no network, no storage, reminders are drafts |
Manual 37/39, automated 61 → **98/100 nominal; scored 95 after deducting 3 for rules cited from memory of the statutes rather than re-fetched this run.**

## 5. 实测发现并修复
1. Test fixture tie (two clients equal balance) made a golden ambiguous: changed numbers so the ordering is deterministic.
2. Date parameters were unconstrained in the schema: added ISO length constraints (10 chars).
3. EU fixed-compensation warning wording was misleading about currency; reworded.

## 6. 标准迭代
No change. Note for later: audit B4 cannot constrain `date` types; left as is (loosening needs Vic).

## 7. 局限
B2B only; single currency; no storage; no consumer or national variants; reference rates must be supplied.
