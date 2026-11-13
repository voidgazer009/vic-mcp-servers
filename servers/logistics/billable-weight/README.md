# Vic Billable Weight MCP · 计费重 MCP

> Know the weight you will be billed before you ship, catch oversize surcharges before the carrier does, and fight unfair "weight adjustments" with numbers. UPS, FedEx, DHL, air cargo, sea LCL and road groupage. Built to the official Model Context Protocol spec (revision 2026-07-28, Python SDK v2). Runs fully offline.
>
> 发货前就算准计费重，订舱前先查出超长超重附加费，收到“重量/尺寸调整”账单时用数字判断该不该申诉，并告诉你纸箱要缩小多少才不再为空气付钱。

**Direction 方向:** 国际物流 International logistics · **Version:** 1.0.0 · **License:** MIT · **Transport:** stdio, Streamable HTTP

---

## 解决什么痛点 · Pain points

| 从业者真实的坑 | 后果 | 这个 MCP 怎么解决 |
|---|---|---|
| 不同渠道除数不一样（快递 5000、空运 6000、拼箱按 W/M），货代结账时偷换系数 | 同一箱货计费重差 20% 以上 | 8 种计费规则一键切换，`divisor_override` 按报价单的系数算，换系数会提示“写进报价” |
| 只知道“体积重 = 长×宽×高÷5000”，不知道每边先向上取整、每件按 0.5 kg 进位、UPS 超 20 kg 按整公斤 | 自己算 19.2 kg，账单 21 kg | 按 UPS / FedEx / DHL 2026 官方规则逐件取整、逐票进位，显示取整后的尺寸 |
| 收到 UPS/FedEx “Shipping Charge Correction”，复测尺寸每边多 2 到 3 cm、重量翻倍，补费比运费还高（Reddit、亚马逊卖家论坛大量投诉） | 不知道是正常进位还是乱收，申诉无从下手 | `audit_weight_adjustment` 逐票重算，区分“正常进位 / 可申诉 / 强烈申诉”，算出涉及金额，生成中英文申诉草稿和证据清单 |
| 箱子 123 cm，只比 UPS 附加操作线 122 cm 多 1 cm；L+围长 303 cm 触发大包裹最低 40 kg | 一箱多付几百元附加费 | `check_express_surcharges` 按三家 2026 国际附加费线逐箱检查，指出哪一边超了多少 |
| 轻泡货用大箱子，体积重是实重的 3 倍 | 长期为“空气”付运费 | `optimize_box_size` 算出体积上限、每边要缩多少、每缩 1 cm 省多少、围着产品的最紧箱型 |
| 货代“单件不足 12 kg 按 12 kg”、空运“六四分泡” | 报价和账单对不上 | `min_billable_per_piece`、`volume_split_customer_pct` 直接按约定算 |
| 快递、空运、海运拼箱报价单位不同（kg / RT），没法直接比 | 选错渠道，多花钱或多等一个月 | `compare_freight_options` 每个报价按各自规则算计费重，排出总价、每真实公斤成本、每快一天多花多少 |

## Tools · 工具

| Tool | 做什么 | 只读 |
|---|---|---|
| `calculate_chargeable_weight` | 计费重：UPS / FedEx / DHL 快递（逐件）、IATA 空运 1:6000（整票）、海运拼箱 W/M（RT）、欧洲公路 1:333、美国国内 139、自定义 | ✅ |
| `check_express_surcharges` | 逐箱检查 UPS / FedEx / DHL 2026 附加操作费、大包裹/超尺寸、超重件、不可传送件、超限拒收 | ✅ |
| `audit_weight_adjustment` | 承运商重量/尺寸调整核查：重算、判定、涉及金额、新增附加费、申诉草稿（只生成草稿，不发送） | ✅ |
| `optimize_box_size` | 纸箱缩多少才按实重计费，每缩 1 cm 省多少，最紧可行箱型，贴线附加费提醒 | ✅ |
| `compare_freight_options` | 多个真实报价按各自计费规则比总价、每公斤成本和时效 | ✅ |

**Resource:** `freight://billable-weight-rules`, every profile's divisor, rounding and source as JSON.
**Prompt:** `audit_freight_invoice`, walks through an invoice, re-rates every line and prepares disputes for you to send.

## Install · 安装

Requires Python 3.10+. With [uv](https://docs.astral.sh/uv/):

```bash
git clone https://github.com/voidgazer009/vic-mcp-servers.git
cd vic-mcp-servers/servers/logistics/billable-weight
uv run vic-billable-weight-mcp          # stdio
uv run vic-billable-weight-mcp --http   # stateless Streamable HTTP on http://127.0.0.1:8000/mcp
```

### Claude Desktop / Claude Code

```json
{
  "mcpServers": {
    "vic-billable-weight": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/vic-mcp-servers/servers/logistics/billable-weight", "vic-billable-weight-mcp"]
    }
  }
}
```

Claude Code: `claude mcp add vic-billable-weight -- uv run --directory /path/to/billable-weight vic-billable-weight-mcp`

### Cursor (`.cursor/mcp.json`) · VS Code / Copilot (`.vscode/mcp.json`)

Same `command` and `args` as above. For VS Code use the key `"servers"` instead of `"mcpServers"`.

### Codex CLI (`~/.codex/config.toml`)

```toml
[mcp_servers.vic-billable-weight]
command = "uv"
args = ["run", "--directory", "/path/to/billable-weight", "vic-billable-weight-mcp"]
```

## Try it · 试试这样问

- 「纸箱 60×40×40 cm，每箱 7 kg，走 UPS 和 DHL 各按多少公斤计费？」
- 「UPS 给我发了重量调整：我报 46×18×7 英寸、16 磅，他们说 48×21×9、26 磅，每磅大概 2 美元，该不该申诉？帮我写申诉邮件。」
- 「这箱 123×50×40 cm、30 kg 的货，走 FedEx 会不会被收附加费？UPS 呢？」
- 「我的产品 50×30×20 cm，现在用 60×40×40 的箱子，毛重 7 kg，换多大的箱子最省？」
- 「3 箱 60×40×40、每箱 10 kg：DHL 40 元/kg 燃油 20%，空运 25 元/kg 加 500 杂费，海运拼箱 300 元/方加 1200，哪个最划算？」
- 「货代说空运六四分泡，体积按 6000 算，10 箱 60×50×40、每箱 12 kg，计费重是多少？」

## How it works · 计算规则

| Profile | Divisor | Rounding | Basis | Source |
|---|---|---|---|---|
| `ups_express` | 5000 cm³/kg | each side up to next cm; actual and dim weight up to 0.5 kg per package; shipment ≤20 kg in 0.5 kg, above in whole kg | per package | UPS 2026 Rate and Service Guide, China |
| `fedex_international` | 5000 | each side up to next cm; 0.5 kg steps to 20.5 kg, whole kg from 21 kg | per package | fedex.com.cn FAQ; FedEx China 2026 rate-sheet weight bands |
| `dhl_express` | 5000 | piece up to 0.5 kg; shipment ≤30 kg in 0.5 kg, above in whole kg | per package | DHL Express Service & Rate Guide 2026 |
| `air_cargo_iata` | 6000 | sides to nearest cm; shipment up to 0.5 kg | whole shipment | IATA 1:6000 (167 kg/cbm) |
| `sea_lcl` | 1 cbm = 1,000 kg | 0.01 RT, minimum 1 RT | whole shipment | W/M revenue-ton convention |
| `road_ltl_eu` | 1 cbm = 333 kg | whole kg | whole shipment | common European groupage ratio |
| `us_domestic_daily` | 139 in³/lb | sides to nearest inch; whole lb | per package | ups.com Shipping Dimensions and Weight |
| `custom` | yours | yours | per package | your quote |

- **Billable** = greater of actual and dimensional weight, after the carrier's rounding. Per-package carriers add up each package's billable weight; air cargo, sea and road compare totals.
- **分泡 / volume split**: billable = volumetric − (volumetric − actual) × your share.
- **Surcharge lines (international, 2026)**: UPS Additional Handling > 122 cm longest / > 76 cm second / > 25 kg; Large Package L+girth > 300 cm (min 40 kg); max 70 kg, 274 cm, 400 cm. FedEx AHS-Dimension > 121 / > 76 / L+girth > 266 cm / > 169,901 cm³ (min 18 kg); AHS-Weight > 25 kg; Oversize > 243 cm / > 330 cm / > 283,168 cm³ / > 50 kg; Unauthorized > 274 cm / > 419 cm / > 68 kg; only the highest applies. DHL Overweight piece > 70 kg actual or volumetric; Oversize piece > 100 cm longest or > 80 cm second; Non-Conveyable 25 to 70 kg or non-corrugated packaging.
- **Adjustment verdicts**: every side within 1 cm (0.5 in) → normal rounding; a side more than 5% and 2 cm larger, or weight 1.5× and 2 kg heavier → worth disputing; weight jump with the same box, or an invoice above the carrier's own audit → strong dispute.

## Limitations · 局限

- Rules are the published 2026 international rules (China-origin guides where they differ). Contracts, peak-season rules and other origin countries can differ; `divisor_override` and `rounding_step` let you match your quote.
- Surcharge amounts shown are 2026 China list prices before discount (UPS, FedEx); DHL amounts vary by origin and are not shown. Fuel, remote-area and peak surcharges are not included.
- It does not fetch live rates or track packages: you bring the quotes, it does the arithmetic.
- The adjustment verdict is a numerical judgement, not a guarantee; carriers decide disputes based on evidence.
- Network access: **none**. All calculations run locally; no data leaves your machine.

## Development · 开发

```bash
uv run --extra dev pytest      # hand-checked golden numbers + MCP protocol tests
python ../../../tools/audit.py servers/logistics/billable-weight   # from repo root: Vic review standard
```

Review report: [`reports/billable-weight-1.0.0.md`](../../../reports/billable-weight-1.0.0.md)

---

Made by **Vic** · part of [vic-mcp-servers](https://github.com/voidgazer009/vic-mcp-servers)
