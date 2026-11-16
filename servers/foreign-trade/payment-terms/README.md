# Vic Payment Terms MCP · 外贸收款方式 MCP

> Pick, compare and screen export payment terms (T/T, L/C, D/P, D/A, O/A): what each really costs you, which is safe for this buyer, and which words in a clause or L/C should make you stop. Built to the official Model Context Protocol spec (revision 2026-07-28, Python SDK v2). Fully offline.
>
> 帮外贸人选对、比准、审清收款方式：赊销 60 天到底吃掉多少利润，这个客户该给什么条款，信用证或合同里哪句话是陷阱。

**Direction 方向:** 外贸 Foreign trade · **Version:** 1.0.0 · **License:** MIT · **Transport:** stdio, Streamable HTTP (stateless)

---

## 解决什么痛点 · Pain points

| 外贸人常见的坑 | 后果 | 这个 MCP 怎么解决 |
|---|---|---|
| 新客户要 O/A、D/A 赊销，不知道怎么回 | 货出去收不回，整单亏损 | `recommend_payment_terms` 按客户历史、金额、国家风险给出排序和还价话术 |
| 以为“D/A 有银行经手就安全” | 银行只是传递单据，不担保付款（URC 522） | `explain_payment_term` 说清楚谁承担风险 |
| 信用证里的软条款（买方签署的验货证书、船名由买方指定、买方通知后生效） | 货发了，银行不付款 | `check_payment_clause` 识别并给出修改建议，中英文都能查 |
| “见提单副本付尾款” | 如果提单正本已放行，等于赊销 | 条款审查会提示：正本或电放必须等尾款到账 |
| 账期的真实成本没算过 | 60 天账期吃掉利润却报了同样价格 | `compare_payment_terms` 逐种算资金占用利息、手续费、净利润和发货时无保障金额 |
| 信用证交单超期 | UCP 600 第 14(c) 条：运输单据须在装运后 21 天内交单；银行审单最多 5 个银行日（第 14(b) 条） | 比价时用交单天数参数，超过 21 天会警告 |

## Tools · 工具

| Tool | 做什么 | 只读 |
|---|---|---|
| `explain_payment_term` | 8 种收款方式的风险归属、流程、适用规则、常见坑 | ✅ |
| `compare_payment_terms` | 现金到账时间、资金成本、手续费、净利润、发货时无保障金额 | ✅ |
| `recommend_payment_terms` | 按客户情况给出排序建议，并回应客户提出的条款 | ✅ |
| `check_payment_clause` | 筛查合同/信用证文本：软条款、赊销、模糊 T/T、缺币种等 | ✅ |

**Resource:** `payment-terms://matrix`. **Prompt:** `credit_terms_reply`（客户要账期时的回复草稿，只生成草稿，不发送）。

## Install · 安装

Requires Python 3.10+ and [uv](https://docs.astral.sh/uv/):

```bash
git clone https://github.com/voidgazer009/vic-mcp-servers.git
cd vic-mcp-servers/servers/foreign-trade/payment-terms
uv run vic-payment-terms-mcp          # stdio
uv run vic-payment-terms-mcp --http   # Streamable HTTP on http://127.0.0.1:8000/mcp
```

### Claude Desktop / Claude Code

```json
{
  "mcpServers": {
    "vic-payment-terms": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/vic-mcp-servers/servers/foreign-trade/payment-terms", "vic-payment-terms-mcp"]
    }
  }
}
```

Claude Code: `claude mcp add vic-payment-terms -- uv run --directory /path/to/payment-terms vic-payment-terms-mcp`

### Cursor (`.cursor/mcp.json`) · VS Code / Copilot (`.vscode/mcp.json`)

Same `command` and `args` as above. For VS Code use the key `"servers"` instead of `"mcpServers"`.

### Codex CLI (`~/.codex/config.toml`)

```toml
[mcp_servers.vic-payment-terms]
command = "uv"
args = ["run", "--directory", "/path/to/payment-terms", "vic-payment-terms-mcp"]
```

## Try it · 试试这样问

- 「新客户，订单 5 万美元，定制产品，他要 O/A 60 天，我该怎么回？」
- 「订单 1 万美元，成本占 70%，生产 30 天，海运 25 天，资金成本 8%，对比 T/T、L/C 和赊销 60 天。」
- 「帮我看这条付款条款有没有坑：L/C at sight, payment against inspection certificate signed by the applicant.」
- 「付款条款写“尾款见提单副本付清”，有什么风险？」
- 「D/P 和 D/A 的区别是什么，哪个对卖家更危险？」

## How it works · 计算与规则

- **资金成本**：假设成本在下单日（第 0 天）全部垫付（偏保守）；未收回的成本余额按时间积分，乘以年化资金成本。
- **到账日**：T/T 预付第 0 天；定金加尾款按装运日；L/C 即期 = 装运日 + 备单天数 + 5 个银行日（UCP 600 第 14(b) 条上限）；远期再加账期；D/P 假设到港后 7 天提单；D/A、O/A 从提单日起算账期。
- **发货时无保障金额**：发货时未收款且没有银行承诺的部分（D/P、D/A、O/A、发货后付尾款）。
- **条款审查**：关键词和模式匹配，按 critical / high / medium / low 排序。依据：ICC UCP 600（信用证）、URC 522（托收）和行业对软条款的通行定义。

## Limitations · 局限

- 手续费、保险费率是参数，默认值只是假设（L/C 1%、托收 0.3%），请向银行、中信保询价。
- 条款审查是文本匹配，没提示不代表安全；L/C 请让银行审核，不构成法律或信用建议。
- 不查客户资信、不查国家风险评级；请用买家背调和信保评级。
- Network access: none. 完全离线，数据不离开你的机器。

## Development · 开发

```bash
uv run --extra dev pytest
python tools/audit.py servers/foreign-trade/payment-terms   # from repo root
```

Review report: [`reports/payment-terms-1.0.0.md`](../../../reports/payment-terms-1.0.0.md)
