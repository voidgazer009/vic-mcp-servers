# Vic Demurrage & Detention MCP · 滞港费/滞箱费计算 MCP

> Last free day, tiered demurrage and detention charges, what-if pick-up dates and invoice audit, offline. Built to the official Model Context Protocol spec (revision 2026-07-28, Python SDK v2).
>
> 柜子到港后免费期哪天截止？哪天提柜最省钱？账单多收了一天是怎么算出来的？一个工具把天数算清楚。

**Direction 方向:** 国际物流 Logistics · **Version:** 1.0.0 · **License:** MIT · **Transport:** stdio, Streamable HTTP (stateless)

---

## 解决什么痛点 · Pain points

| 货代/外贸人常见的坑 | 后果 | 这个 MCP 怎么解决 |
|---|---|---|
| 不清楚免费期哪天结束，周末、假日算不算 | 周一才去提柜，周末已经开始收费 | `find_last_free_day` 按日历日或工作日（跳过周末和你列出的假日）算最后免费日 |
| 滞港费阶梯涨价，手算容易错 | 低估成本，报价时没算进去 | `calculate_charges` 按阶梯费率逐日计费，输出逐日表 |
| 今天提还是周一提 | 多一天贵很多 | `compare_exit_dates` 并排比较多个提柜/还箱日期 |
| 账单比自己算的多，不知道对方怎么数的 | 被多收一天甚至几天 | `audit_invoice` 试遍起算日/结束日/工作日组合，找出哪种算法等于账单金额，并给出申请更正的邮件草稿 |
| 美国航线发票来得很晚 | 不知道可以拒付 | `us_trade=true` 给出 FMC 规则下 30 天发票期限 |

## Tools · 工具

| Tool | 做什么 | 只读 |
|---|---|---|
| `find_last_free_day` | 最后免费日、首个收费日、剩余天数 | ✅ |
| `calculate_charges` | 滞港费或滞箱费总额、阶梯拆分、逐日表 | ✅ |
| `compare_exit_dates` | 比较多个提柜/还箱日期的费用 | ✅ |
| `audit_invoice` | 核对账单，找出差异原因，生成更正申请草稿（不发送） | ✅ |

**Resource:** `demurrage://counting-checklist`. **Prompt:** `invoice_check`.

## Install · 安装

Requires Python 3.10+ and [uv](https://docs.astral.sh/uv/):

```bash
git clone https://github.com/voidgazer009/vic-mcp-servers.git
cd vic-mcp-servers/servers/logistics/demurrage-detention
uv run vic-demurrage-mcp          # stdio
uv run vic-demurrage-mcp --http   # Streamable HTTP on http://127.0.0.1:8000/mcp
```

### Claude Desktop / Claude Code

```json
{
  "mcpServers": {
    "vic-demurrage": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/vic-mcp-servers/servers/logistics/demurrage-detention", "vic-demurrage-mcp"]
    }
  }
}
```

Claude Code: `claude mcp add vic-demurrage -- uv run --directory /path/to/demurrage-detention vic-demurrage-mcp`

### Cursor (`.cursor/mcp.json`) · VS Code / Copilot (`.vscode/mcp.json`)

Same `command` and `args` as above. For VS Code use the key `"servers"` instead of `"mcpServers"`.

### Codex CLI (`~/.codex/config.toml`)

```toml
[mcp_servers.vic-demurrage]
command = "uv"
args = ["run", "--directory", "/path/to/demurrage-detention", "vic-demurrage-mcp"]
```

## Try it · 试试这样问

- 「柜子 11 月 16 日卸船，免费 5 天按日历日算，最后免费日是哪天？」
- 「免费 4 个工作日，11 月 23 日是码头假日，从 11 月 16 日起算，什么时候开始收费？」
- 「滞港费前 3 天每天 150、第 4 天起每天 300，11 月 16 日到 25 日提柜，一共多少钱？」
- 「11 月 20 日、23 日、24 日提柜，哪天最划算，每多一天多多少钱？」
- 「船公司账单收了 1350 美元，我算出来是 1050，帮我看看他们是怎么数的，并写一封申请更正的邮件草稿」

## How it works · 计算与规则

- **Clock:** start day (discharge/availability for demurrage, gate-out for detention) is day 1 if you say so; free days are consumed first (calendar days, or working days that skip weekends and listed holidays); each following day is a chargeable day, priced by the rate tier whose `from_day` it has reached. Example: 10 days inclusive, 5 free, tiers 150 (days 1-3) and 300 (day 4+) gives 3×150 + 2×300 = 1050.
- **Working-day free time, calendar-day charges:** supported (a common US pattern, e.g. CMA CGM US import free time in working days, then calendar days).
- **US trade:** with `us_trade=true`, the tool reports the date 30 calendar days after the last charged day; per 46 CFR 541.7 a later invoice is not payable, and 541.8 gives 30 days to ask for mitigation. Source: eCFR Title 46 Part 541.
- **Invoice audit:** recalculates all 16 combinations of clock start (same day or one day earlier), start-day, end-day and free-day type and lists those equal to the billed amount.

## Limitations · 局限

- Estimates from the rule you give. Tariffs differ by carrier, port and contract; start time-of-day, gate closures, strikes, government holds and combined per-diem rules are not modelled. No tariff database is included.
- Holidays must be listed by you; no holiday calendar is built in.
- Not legal advice; the dispute note is a draft only and nothing is sent.
- Network domains accessed: none (fully offline).

## Development

```bash
pip install -e ".[dev]" && pytest
python tools/audit.py servers/logistics/demurrage-detention   # from the repo root
```
