# Vic Export Quote MCP · 外贸报价 MCP

> Turn a factory cost into a correct export quote across every Incoterm, size the container, convert currency, and explain terms to buyers. Built to the official Model Context Protocol spec (revision 2026-07-28, Python SDK v2).
>
> 把出厂成本变成一份算对的外贸报价：一次算出 EXW / FOB / CFR / CIF / DDP 全套价格，算装柜，查汇率，给客户解释贸易术语。

**Direction 方向:** 外贸 Foreign trade · **Version:** 1.0.0 · **License:** MIT · **Transport:** stdio, Streamable HTTP

---

## 解决什么痛点 · Pain points

| 外贸人常见的坑 | 后果 | 这个 MCP 怎么解决 |
|---|---|---|
| CIF 保险费用 FOB 乘费率来算 | 保额不足，按 Incoterms 应按 CIF 价的 110% 投保 | 用 `CIF = CFR ÷ (1 − 1.1 × 费率)` 精确反推 |
| 把“利润率”和“加价率”搞混 | 想赚 20%，实际只赚 16.7% | 统一按利润率（利润 ÷ 售价）计算，同时给出等价加价率 |
| 小单没摊固定费用（拖车、报关、文件费） | 小单越做越亏 | 固定费用按数量摊销，占比过高自动提醒设 MOQ 或小单费 |
| 报 CIF / DDP 时利润率被运费“稀释” | 以为 20%，DDP 只有 14% | 每个术语单独显示真实利润率，低于底线就警告 |
| DDP 关税算错基数 | 美国按 FOB 征税、欧盟按 CIF 征税，算错就亏 | `duty_basis` 参数区分 FOB / CIF 计税 |
| 装柜只算体积不算重量 | 瓷砖、钢材等重货超重被甩柜 | 同时按空间和限重计算，给出最省钱的柜型组合 |
| 空运也写 FOB、整柜还用 FOB | 风险转移点不清，出事扯皮 | `explain_incoterm` 自动指出误用并推荐 FCA / CPT / CIP |

## Tools · 工具

| Tool | 做什么 | 只读 |
|---|---|---|
| `calculate_export_quote` | 一次算出 EXW、FOB/FCA、CFR/CPT、CIF/CIP、DDP 全套报价、利润和警告 | ✅ |
| `price_by_quantity` | 阶梯价表：500 / 1000 / 5000 件各是多少钱 | ✅ |
| `plan_container_loading` | 20GP / 40GP / 40HQ 各装多少箱，按空间和重量双重限制，推荐最省钱组合或拼箱 | ✅ |
| `explain_incoterm` | Incoterms 2020 任一术语：谁付运费、谁买保险、谁报关、风险何时转移、常见坑 | ✅ |
| `convert_currency` | 欧洲央行参考汇率（免费、无需 API Key） | ✅ 联网 |

**Resource:** `incoterms://2020`, the full 11-rule matrix as JSON.
**Prompt:** `quotation_reply`, turns a buyer inquiry into a checked quotation draft using the tools above.

## Install · 安装

Requires Python 3.10+. With [uv](https://docs.astral.sh/uv/):

```bash
# from the repo
git clone https://github.com/voidgazer009/vic-mcp-servers.git
cd vic-mcp-servers/servers/foreign-trade/export-quote
uv run vic-export-quote-mcp          # stdio
uv run vic-export-quote-mcp --http   # Streamable HTTP on http://127.0.0.1:8000/mcp
```

### Claude Desktop / Claude Code

```json
{
  "mcpServers": {
    "vic-export-quote": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/vic-mcp-servers/servers/foreign-trade/export-quote", "vic-export-quote-mcp"]
    }
  }
}
```

Claude Code: `claude mcp add vic-export-quote -- uv run --directory /path/to/export-quote vic-export-quote-mcp`

### Cursor (`.cursor/mcp.json`) · VS Code / Copilot (`.vscode/mcp.json`)

Same `command` and `args` as above. For VS Code use the key `"servers"` instead of `"mcpServers"`.

### Codex CLI (`~/.codex/config.toml`)

```toml
[mcp_servers.vic-export-quote]
command = "uv"
args = ["run", "--directory", "/path/to/export-quote", "vic-export-quote-mcp"]
```

## Try it · 试试这样问

- 「出厂价 5 美元，1000 件，拖车报关 300 美元，海运费 1200 美元，保险费率 0.3%，要 20% 利润，报 FOB 和 CIF 给我。」
- 「同样的货，美国客户要 DDP，关税 3.9%，目的港费用 600 美元，我的利润底线 15%，还安全吗？」
- 「纸箱 60×40×40 cm，每箱 12 kg，一共 1500 箱，订什么柜最划算？」
- 「客户空运要 FOB 价，这样写有问题吗？」
- 「把 35,000 人民币换成美元。」

## Worked example · 计算示例

Unit cost USD 5, 1,000 pcs, origin costs 300, ocean freight 1,200, insurance 0.3%, duty 3.9% on FOB (US), destination costs 600, target margin 20%:

| Term | Total | Unit | Margin |
|---|---|---|---|
| EXW | 6,325.00 | 6.3250 | 20.95% |
| FOB/FCA | 6,625.00 | 6.6250 | 20.00% |
| CFR/CPT | 7,825.00 | 7.8250 | 16.93% |
| CIF/CIP | 7,850.91 | 7.8509 | 16.88% |
| DDP | 8,709.28 | 8.7093 | 15.21% |

FOB is the anchor and hits the target margin exactly. Every term earns the same USD 1,325 profit; pass-through costs (freight, insurance, duty) make the percentage shrink, and the tool says so.

## How the numbers work · 计算规则

- **Margin** = profit ÷ selling price. FOB price = (goods + origin costs) ÷ (1 − margin).
- **CIF** = CFR ÷ (1 − cover × rate), with cover 110% by default (Incoterms 2020 minimum). Premium = CIF × 110% × rate.
- **Duty** = rate × CIF (EU, UK, China, most countries) or × FOB (US, Canada, Australia).
- **Import VAT** = rate × (CIF + duty).
- **Container fit** tries every allowed carton orientation, applies a loading-efficiency allowance (default 90%), caps by payload, then searches the cheapest 20GP/40GP/40HQ mix using your lane's 40ft-to-20ft rate ratio (default 1.4).

## Limitations · 局限

- It does not fetch freight rates or HS-code duty rates. Those change weekly and vary by lane; ask your forwarder or customs broker and pass them in. The tool warns when they are missing.
- Container payloads are typical values. Road weight limits at origin or destination can be lower; use `max_payload_kg`.
- Exchange rates are ECB reference rates (about 30 currencies, updated each working day). Banks add a spread.
- Network access: only `api.frankfurter.dev` (for `convert_currency`). Everything else runs locally; no data leaves your machine.
- This is a calculator, not tax or legal advice.

## Development · 开发

```bash
uv run --extra dev pytest      # 29 tests: hand-checked golden numbers + MCP protocol tests
python ../../../tools/audit.py servers/foreign-trade/export-quote   # from repo root: Vic review standard
```

Review report: [`reports/export-quote-1.0.0.md`](../../../reports/export-quote-1.0.0.md)

---

Made by **Vic** · part of [vic-mcp-servers](https://github.com/voidgazer009/vic-mcp-servers)
