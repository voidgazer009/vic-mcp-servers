# Vic Cashflow Forecast MCP · 一人公司现金流预测 MCP

> Will the cash last? A 13-week weekly cash forecast, a runway calculator and a "what if my biggest client pays 30 days late" stress test. Official MCP spec (revision 2026-07-28, Python SDK v2). Offline, no API key.
>
> 自由职业者 / 一人公司现金流工具：按周预测 13 周余额、算还能撑几个月、模拟大客户晚付款会不会断粮。

**Direction 方向:** AI 一人公司 One-person company · **Version:** 1.0.0 · **License:** MIT · **Transport:** stdio, Streamable HTTP

---

## 解决什么痛点 · Pain points

目标用户：自由职业者、独立开发者、接海外订单的一人公司。收入是一笔笔到账的，支出却按月固定，账面“赚钱”不等于账上有钱。

| 常见的坑 | 后果 | 这个 MCP 怎么解决 |
|---|---|---|
| 只看利润，不看哪一周账上会空 | 项目赚钱却发不出房租、工具费、税 | `forecast_cashflow` 按周滚动余额，标出第一周变负和低于安全垫的周 |
| 发票默认客户准时付款 | 客户拖 30 天，当月直接断粮 | `confidence` 和 `delay_days` 把不确定的收入打折、延后 |
| 不知道一个大客户晚付的影响有多大 | 没有备用金，临时刷信用卡 | `stress_test_cashflow` 并排对比基准与压力情景 |
| 想辞职或接受淡季，不知道能撑多久 | 拍脑袋决定 | `calculate_runway` 算月数，支持收入逐月增长 |

Compared with registry servers: the existing cash-flow MCPs are hosted SaaS connectors (e.g. Cashflow Frog), personal-finance ledgers, or bank-CSV categorisers. This one is a stateless, offline forecasting calculator with a late-payment stress test; nothing to sign up for and no bank data needed.

## Tools · 工具

| Tool | 做什么 | 只读 |
|---|---|---|
| `forecast_cashflow` | 按周现金流预测（默认 13 周），支持周期性收支、概率、延迟、安全垫 | ✅ |
| `calculate_runway` | 现金能撑几个月 | ✅ |
| `stress_test_cashflow` | 基准 vs 延迟/打折收款的对比 | ✅ |

**Resource:** `cashflow://method`. **Prompt:** `thirteen_week_cash_check`.

## Install · 安装

Python 3.10+, with [uv](https://docs.astral.sh/uv/):

```bash
git clone https://github.com/voidgazer009/vic-mcp-servers.git
cd vic-mcp-servers/servers/one-person-company/cashflow-forecast
uv run vic-cashflow-forecast-mcp          # stdio
uv run vic-cashflow-forecast-mcp --http   # Streamable HTTP on http://127.0.0.1:8000/mcp
```

### Claude Desktop / Claude Code

```json
{
  "mcpServers": {
    "vic-cashflow-forecast": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/vic-mcp-servers/servers/one-person-company/cashflow-forecast", "vic-cashflow-forecast-mcp"]
    }
  }
}
```

Claude Code: `claude mcp add vic-cashflow-forecast -- uv run --directory /path/to/cashflow-forecast vic-cashflow-forecast-mcp`

### Cursor (`.cursor/mcp.json`) · VS Code / Copilot (`.vscode/mcp.json`)

Same `command` and `args`. For VS Code use the key `"servers"` instead of `"mcpServers"`.

### Codex CLI (`~/.codex/config.toml`)

```toml
[mcp_servers.vic-cashflow-forecast]
command = "uv"
args = ["run", "--directory", "/path/to/cashflow-forecast", "vic-cashflow-forecast-mcp"]
```

## Try it · 试试这样问

- 「我账上现在有 8000 美元，每月 5 号房租 1200，工具订阅每月 300，Acme 1 月 20 日付 4000 的发票，帮我预测 13 周现金流。」
- 「如果 Acme 的发票晚 30 天才付，我会不会在哪一周断粮？」
- 「我有 6 万人民币存款，每月花 1 万，副业月收入 2000 每月涨 5%，能撑几个月？」
- 「这笔 5000 的款只有 70% 把握到账，帮我按概率算预期现金流，并留一个月开销做安全垫。」
- 「我每季度要交一次预估税 3000，帮我放进预测里看哪一周最紧。」

## How the numbers work · 计算规则

- **Week** = 7 days from the start date. Closing balance = opening + expected inflows − outflows, cumulative.
- **Expected inflow** = amount × confidence × (1 − stress haircut). Outflows always count in full (prudent).
- **Delay**: the whole series shifts by the delay days and lands in the week of the shifted date; a delayed monthly retainer is late every month.
- **Monthly / quarterly / yearly** repeats keep the original day of month, clamped to month end (31 Jan → 28 Feb → 31 Mar).
- **Runway**: month by month, balance + income − expenses until below zero; the last month is pro-rated. Capped at 120 months.
- Method: direct-method 13-week cash flow, the standard small-business and lender format.

## Limitations · 局限

- One currency per call; no FX and no tax logic: enter tax payments as outflows yourself.
- Items before the start date are ignored; repeats run only through the forecast window.
- No bank connection and nothing stored; the forecast is only as good as the inputs. Not financial advice.
- Network access: none. Everything runs locally; no data leaves your machine.

## Development · 开发

```bash
uv run --extra dev pytest
python tools/audit.py servers/one-person-company/cashflow-forecast   # from repo root
```

Review report: [`reports/cashflow-forecast-1.0.0.md`](../../../reports/cashflow-forecast-1.0.0.md)
