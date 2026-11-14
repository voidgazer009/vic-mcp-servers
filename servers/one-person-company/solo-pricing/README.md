# Vic Solo Pricing MCP · 一人公司定价 MCP

> Price like a business, not a guess: minimum hourly rate from the income you want, fixed-fee quotes that survive overruns, payment-fee gross-up, discount impact, and the real hourly rate of finished jobs. Official MCP spec (revision 2026-07-28, Python SDK v2). Offline, no API key.
>
> 一人公司 / 自由职业者定价：从想拿到手的收入倒推最低时薪，报固定价不怕超时，算平台手续费，算打折要多卖多少，复盘一单到底赚了多少钱一小时。

**Direction 方向:** AI 一人公司 One-person company · **Version:** 1.0.0 · **License:** MIT · **Transport:** stdio, Streamable HTTP

---

## 解决什么痛点 · Pain points

目标用户：自由职业者、独立开发者、一人公司创始人。

| 常见的坑 | 后果 | 这个 MCP 怎么解决 |
|---|---|---|
| 想要到手 6 万，用「6 万 ÷ 工作小时」当时薪 | 税、成本、休假、非计费时间全没算，时薪低估一半以上 | `calculate_hourly_rate` 倒推：税按除法、成本、缓冲、可计费小时 |
| 把 40 小时/周当作全是可开票时间 | 销售、沟通、改稿占 30 到 50%，实际收入远低于预期 | 用「计费占比」算可计费小时，并提示偏高 |
| 税按「加 25%」而不是「除以 0.75」 | 每年少算几千，报税时才发现 | 按除法计算，并显示 naive 做法差多少 |
| 固定价项目不留缓冲、不限改稿 | 超时 50% 时时薪暴跌 | `quote_fixed_project` 含风险缓冲、改稿轮数，并给出超时 25/50/100% 的真实时薪 |
| 收款手续费、汇率差没加进报价 | 到手少于报价 | `gross_up_for_fees` 倒推开票金额，并显示直接加百分比会少多少 |
| 客户砍价，随手答应打 10% | 利润 60% 的服务，要多卖 20% 才回本 | `analyze_discount` 算出所需增量 |
| 做完不复盘 | 不知道哪类客户在亏 | `check_real_hourly_rate` 对比目标时薪 |

Compared with existing registry servers (a plain hourly-rate calculator, a service-package builder): this one adds tax as a division, utilization, fixed-price overrun scenarios, fee/FX gross-up, discount break-even and post-job review in one coherent toolset.

## Tools · 工具

| Tool | 做什么 | 只读 |
|---|---|---|
| `calculate_hourly_rate` | 目标净收入 → 最低时薪和日薪 | ✅ |
| `quote_fixed_project` | 工时估算 → 固定价报价 + 超时情景 | ✅ |
| `gross_up_for_fees` | 手续费 / 汇率差倒推开票金额 | ✅ |
| `analyze_discount` | 打折后要多卖多少才不亏利润 | ✅ |
| `check_real_hourly_rate` | 做完一单的真实时薪 | ✅ |

**Resource:** `pricing://formulas`. **Prompt:** `price_a_project`.

## Install · 安装

Python 3.10+, with [uv](https://docs.astral.sh/uv/):

```bash
git clone https://github.com/voidgazer009/vic-mcp-servers.git
cd vic-mcp-servers/servers/one-person-company/solo-pricing
uv run vic-solo-pricing-mcp          # stdio
uv run vic-solo-pricing-mcp --http   # Streamable HTTP on http://127.0.0.1:8000/mcp
```

### Claude Desktop / Claude Code

```json
{
  "mcpServers": {
    "vic-solo-pricing": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/vic-mcp-servers/servers/one-person-company/solo-pricing", "vic-solo-pricing-mcp"]
    }
  }
}
```

Claude Code: `claude mcp add vic-solo-pricing -- uv run --directory /path/to/solo-pricing vic-solo-pricing-mcp`

### Cursor (`.cursor/mcp.json`) · VS Code / Copilot (`.vscode/mcp.json`)

Same `command` and `args`. For VS Code use the key `"servers"` instead of `"mcpServers"`.

### Codex CLI (`~/.codex/config.toml`)

```toml
[mcp_servers.vic-solo-pricing]
command = "uv"
args = ["run", "--directory", "/path/to/solo-pricing", "vic-solo-pricing-mcp"]
```

## Try it · 试试这样问

- 「我想一年到手 6 万美元，税率 25%，每年工具和保险花 6000，每年休 6 周，我的最低时薪是多少？」
- 「预估 40 小时的网站项目，时薪 80，含 2 轮修改，Stripe 收款，帮我报个固定价。」
- 「我想到手 100 美元，手续费 2.9% + 0.30，加上 0.5% 换汇差，该开多少钱的发票？」
- 「客户要我打 10% 折扣，我的利润是 60%，要多卖多少才不亏？」
- 「这单收了 5000，花了 70 小时，扣 3% 手续费和 100 成本，真实时薪多少？我的目标是 80。」

## How the numbers work · 计算规则

- **Revenue** = net ÷ (1 − tax) + expenses, × (1 + buffer), ÷ (1 − payment fee). Tax is on pre-tax profit; expenses are deductible.
- **Billable hours** = (52 − weeks off) × hours per week × utilization.
- **Fixed price** = ((hours × (1 + risk) + rounds × hours per round) × rate + costs) ÷ (1 − fee).
- **Discount volume** = old margin ÷ new margin − 1.
- **Real rate** = (revenue − fees − costs) ÷ hours worked.
- Sources: standard freelance-pricing practice (income target ÷ billable hours, tax as a gross-up), cross-checked against published guides from Harvest and free-invoice.com.

## Limitations · 局限

- The tax rate is yours to supply; the server does not know your country's rules, deductions or social contributions.
- Output is a floor, not a market price; it cannot see what clients pay in your niche.
- Fee rates change; enter the rates from your own payment dashboard.
- Network access: none. Everything runs locally; no data leaves your machine.
- A calculator, not tax or legal advice.

## Development · 开发

```bash
uv run --extra dev pytest
python tools/audit.py servers/one-person-company/solo-pricing   # from repo root
```

Review report: [`reports/solo-pricing-1.0.0.md`](../../../reports/solo-pricing-1.0.0.md)
