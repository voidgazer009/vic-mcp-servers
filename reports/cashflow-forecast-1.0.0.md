# Review report · cashflow-forecast 1.0.0 (2026-11-22)

Direction: AI 一人公司 · Standard: REVIEW_STANDARD v1.5

## 1. 选题理由
Freelancers are profitable on paper but run out of cash in specific weeks: income arrives in lumps, rent, tools and tax are fixed, and clients pay late. The standard answer is the weekly "13-week cash flow" used by lenders and small businesses. A stateless calculator with confidence-weighted and delayed inflows, plus a late-payment stress test and a runway check, is deterministic and useful today (roadmap item cashflow-forecast).

## 2. 竞品检查
Registry search "cashflow" / "cash flow": Cashflow Frog (hosted SaaS scenarios and bank accounts), adam-messinger/cashflow (personal finance ledger), theluckystrike/cashflow (bank CSV categoriser), mycashflow (shop orders). None is an offline weekly forecaster with a late-payer stress test. Different niche, so proceed.

## 3. 自动审核
Hard gates G2-G9 pass; automated 61/61 once this report exists (59/61 before, F4 pending). 14 tests pass (10 logic, 4 protocol-level).

## 4. 人工评分
| 项 | 得分 | 说明 |
|---|---|---|
| G1/A1 real pain | 6/6 | cash gaps and late clients are the top solo-business killer |
| A2 value | 4/5 | shows the exact week cash turns negative; savings depend on user inputs |
| A3 differentiation | 4/4 | see section 2 |
| A4 granularity | 5/5 | 3 tools, one job each |
| C1 golden/edge tests | 5/6 | 6 hand-checked goldens (balances, month-end clamp, confidence, delay, stress, runway), error paths; no property tests |
| C2 authority | 4/5 | standard 13-week method, documented in README and resource; no single statutory source applies |
| D1/D2/D4 | 8/8 | no network, nothing stored, nothing sent |
Manual 36/39 + automated 61 = 97 nominal; **scored 94**: deducted 3 because the method was not validated against a real freelancer's bank history.

## 5. 实测发现并修复
1. `date` field name shadowed the `date` type in the pydantic model (schema build crashed): switched to `datetime as dt`.
2. Output descriptions claimed the opening balance could count as the lowest point, but code only scans weekly closings: descriptions corrected.
3. Stress-test warnings repeated "run stress_test_cashflow" inside the stress tool itself: filtered out.
Tricky inputs checked: bad month, empty items, negative amount, unknown direction (all return isError, no crash).

## 6. 标准迭代
No change. Doc/code mismatch (finding 2) cannot be caught mechanically.

## 7. 局限
Single currency, no FX or tax logic, no bank connection, nothing stored; items before the start date are ignored; runway assumes flat expenses.
