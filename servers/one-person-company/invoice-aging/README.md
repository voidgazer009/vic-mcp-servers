# Vic Invoice Aging MCP · 一人公司收款追款 MCP

> Get paid on time: due dates, an aging report of unpaid invoices, EU/UK statutory late-payment interest, and reminder drafts that escalate with lateness. Official MCP spec (revision 2026-07-28, Python SDK v2). Offline, no API key.
>
> 自由职业者 / 一人公司收款工具：算到期日、给未收发票做账龄分析、算欧盟/英国法定逾期利息、按逾期天数生成催款邮件草稿。

**Direction 方向:** AI 一人公司 One-person company · **Version:** 1.0.0 · **License:** MIT · **Transport:** stdio, Streamable HTTP

---

## 解决什么痛点 · Pain points

目标用户：自由职业者、独立开发者、给海外客户开票的一人公司。

| 常见的坑 | 后果 | 这个 MCP 怎么解决 |
|---|---|---|
| 到期日靠心算，EOM、Net 30 搞混 | 追款过早或过晚，落在周末白等 | `calculate_due_date` 精确算出并提示周末、超 60 天条款 |
| 不知道谁欠多久、欠多少 | 小额逾期拖成坏账，一个大客户占了一半应收 | `age_invoices` 账龄分桶、客户汇总、追款清单、集中度提示 |
| 不知道可以收逾期利息和固定赔偿 | 白白放弃欧盟 €40 起、英国 £40/70/100 的固定追款费 | `calculate_late_interest` 按参考利率+8% 和固定金额计算 |
| 催款邮件写得太软或太硬，拖着不敢写 | 越拖越难收 | `draft_payment_reminder` 五档语气，中英文，只出草稿不发送 |

Compared with registry servers: most invoice MCPs create or transmit invoices through one country's tax portal or accounting API. This one is offline receivables maths (aging, statutory interest, reminders) that works with any invoicing tool.

## Tools · 工具

| Tool | 做什么 | 只读 |
|---|---|---|
| `calculate_due_date` | Net N / EOM+N 到期日 | ✅ |
| `age_invoices` | 应收账龄报告和追款清单 | ✅ |
| `calculate_late_interest` | 欧盟 / 英国 / 合同约定逾期利息 | ✅ |
| `draft_payment_reminder` | 催款邮件草稿（不发送） | ✅ |

**Resource:** `receivables://rules`. **Prompt:** `weekly_receivables_review`.

## Install · 安装

Python 3.10+, with [uv](https://docs.astral.sh/uv/):

```bash
git clone https://github.com/voidgazer009/vic-mcp-servers.git
cd vic-mcp-servers/servers/one-person-company/invoice-aging
uv run vic-invoice-aging-mcp          # stdio
uv run vic-invoice-aging-mcp --http   # Streamable HTTP on http://127.0.0.1:8000/mcp
```

### Claude Desktop / Claude Code

```json
{
  "mcpServers": {
    "vic-invoice-aging": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/vic-mcp-servers/servers/one-person-company/invoice-aging", "vic-invoice-aging-mcp"]
    }
  }
}
```

Claude Code: `claude mcp add vic-invoice-aging -- uv run --directory /path/to/invoice-aging vic-invoice-aging-mcp`

### Cursor (`.cursor/mcp.json`) · VS Code / Copilot (`.vscode/mcp.json`)

Same `command` and `args`. For VS Code use the key `"servers"` instead of `"mcpServers"`.

### Codex CLI (`~/.codex/config.toml`)

```toml
[mcp_servers.vic-invoice-aging]
command = "uv"
args = ["run", "--directory", "/path/to/invoice-aging", "vic-invoice-aging-mcp"]
```

## Try it · 试试这样问

- 「1 月 15 日开的发票，月结 30 天（EOM+30），到期日是哪天？」
- 「今天 11 月 18 日，我有这几张未收发票，帮我做账龄分析，告诉我先追谁。」
- 「欧盟客户欠我 10000 欧，1 月 31 日到期，3 月 2 日才付，ECB 利率 2%，能要多少利息和赔偿？」
- 「英国客户 500 英镑逾期 61 天，英格兰银行基准利率 4%，法定利息多少？」
- 「客户逾期 45 天，帮我写一封中文催款邮件，语气要正式但不撕破脸。」

## How the numbers work · 计算规则

- **Due date** = invoice date + N days; EOM = end of invoice month + N days.
- **Interest** = principal × (reference rate + 8%) × days overdue ÷ 365, from the day after the due date (simple interest).
- **EU:** Directive 2011/7/EU Art. 3(1)(d) interest, Art. 6 fixed compensation of at least EUR 40, Art. 3(5) terms over 60 days may be unfair.
- **UK:** Late Payment of Commercial Debts (Interest) Act 1998: 8% over base rate; fixed sum GBP 40 (< 1,000), 70 (1,000 to 9,999.99), 100 (≥ 10,000).
- **Aging buckets:** not due, 1-30, 31-60, 61-90, over 90 days overdue; part payments reduce the open balance.
- Reference rates change twice a year and are not hard-coded: you supply the ECB or Bank of England rate.

## Limitations · 局限

- Statutory interest is for business-to-business debts; consumers, public bodies and national variants (e.g. stricter local rates) are not modelled. Use `custom` for a contract rate.
- Single currency per call; no FX.
- Not stored: invoices live in your conversation or files; nothing is persisted.
- Reminders are drafts; nothing is sent. Not legal advice.
- Network access: none. Everything runs locally; no data leaves your machine.

## Development · 开发

```bash
uv run --extra dev pytest
python tools/audit.py servers/one-person-company/invoice-aging   # from repo root
```

Review report: [`reports/invoice-aging-1.0.0.md`](../../../reports/invoice-aging-1.0.0.md)
