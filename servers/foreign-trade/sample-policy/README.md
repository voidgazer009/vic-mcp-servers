# Vic Sample Policy MCP · 外贸样品政策 MCP

> Decide who gets a free sample, what to charge, how to credit it on the first order, and whether it is worth it. Built to the official Model Context Protocol spec (revision 2026-07-28, Python SDK v2). Fully offline.
>
> 客户说 “send me a sample”：免费寄还是收费？运费谁出？样品费抵首单怎么写、怎么算？这个 MCP 帮外贸人把这些算清楚、写清楚。

**Direction 方向:** 外贸 Foreign trade · **Version:** 1.0.0 · **License:** MIT · **Transport:** stdio, Streamable HTTP (stateless)

---

## 解决什么痛点 · Pain points

目标用户：外贸业务员、工厂老板、小型出口团队。

| 外贸人常见的坑 | 后果 | 这个 MCP 怎么解决 |
|---|---|---|
| 客户一要样就免费寄，寄出去石沉大海 | 样品和快递费白烧，老板有意见 | `triage_sample_request` 按客户信号打分，推荐免费到付、收费抵扣或不寄 |
| 到付被拒收，或国际快递找发件人要双程运费 | 货丢了还倒贴运费 | 到付档要求有效快递账号；账号缺失自动降档 |
| “样品费首单可抵”只说了一句 | 首单请款时对不上：运费抵不抵、过期没、哪张单 | `first_order_credit` 按范围、最低订单额、有效期、上限算出抵扣和应付；`draft_sample_terms` 把条款写进 PI |
| 不知道一个样值不值得寄 | 凭感觉烧预算 | `sample_roi` 给出期望利润和盈亏平衡转化率 |
| 样品费只按出厂价收，漏了开模/印版/人工 | 打样越多亏越多 | `quote_sample_package` 四档并排比较，含一次性费用和手续费 |
| 连环要样、仿冒域名、住宅地址 | 被套样品 | 风险信号写进 `red_flags`，命中硬红旗最多只给全额收费档 |

## Tools · 工具

| Tool | 做什么 | 只读 |
|---|---|---|
| `triage_sample_request` | 给样品请求打分（0–100），推荐五档之一并列出红旗和寄前清单 | ✅ |
| `quote_sample_package` | 同一个样品包在四档下：买方付多少、你花多少、不下单的损失、首单抵扣额 | ✅ |
| `sample_roi` | 下单/不下单的利润、期望利润、盈亏平衡转化率 | ✅ |
| `first_order_credit` | 按约定算首单抵扣与应付金额，说明被削减的原因 | ✅ |
| `draft_sample_terms` | 生成中英文条款草稿（只生成，不发送） | ✅ |

五档：`FREE_COLLECT` 免费到付 · `FREE_FREIGHT_CREDIT` 免费、垫运费、首单抵运费 · `FEE_CREDIT` 收样品费、首单抵 · `FULL_PAID` 全收不退 · `NO_SAMPLE` 不寄。

**Resource:** `sample-policy://tiers`. **Prompt:** `sample_request_reply`（回复客户要样邮件，只生成草稿）。

## Install · 安装

Requires Python 3.10+ and [uv](https://docs.astral.sh/uv/):

```bash
git clone https://github.com/voidgazer009/vic-mcp-servers.git
cd vic-mcp-servers/servers/foreign-trade/sample-policy
uv run vic-sample-policy-mcp          # stdio
uv run vic-sample-policy-mcp --http   # Streamable HTTP on http://127.0.0.1:8000/mcp
```

### Claude Desktop / Claude Code

```json
{
  "mcpServers": {
    "vic-sample-policy": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/vic-mcp-servers/servers/foreign-trade/sample-policy", "vic-sample-policy-mcp"]
    }
  }
}
```

Claude Code: `claude mcp add vic-sample-policy -- uv run --directory /path/to/sample-policy vic-sample-policy-mcp`

### Cursor (`.cursor/mcp.json`) · VS Code / Copilot (`.vscode/mcp.json`)

Same `command` and `args` as above. For VS Code use the key `"servers"` instead of `"mcpServers"`.

### Codex CLI (`~/.codex/config.toml`)

```toml
[mcp_servers.vic-sample-policy]
command = "uv"
args = ["run", "--directory", "/path/to/sample-policy", "vic-sample-policy-mcp"]
```

## Try it · 试试这样问

- 「客户用 Gmail 发邮件，只说 please send free sample，什么都不说，我该怎么回？」
- 「样品 2 个，单个成本 10 美元，另有 20 美元印版费，快递 60 美元，四种政策分别怎么收、亏多少？」
- 「免费样加垫付运费 135 美元，首单预计 5000 美元、毛利 20%，转化率 10%，值不值得？」
- 「客户 1 月 1 日付了 75 美元样品费，8 月 1 日下 5000 美元的单，约定 180 天内抵扣，能抵吗？」
- 「帮我写一段 PI 里的样品条款：收 75 美元，首单满 2000 美元抵扣，180 天有效。」

## How it works · 计算与规则

- **四档对比**：样品费 = 件数×单件成本×(1+加价%) + 一次性费用 + 手续费；运费单列。`FEE_CREDIT` 只抵样品费，不抵运费。
- **首单利润**：下单时利润 = 订单金额×毛利率 + 买方已付 − 抵扣 − 你的支出；不下单时 = 买方已付 − 你的支出。盈亏平衡转化率 = 亏损 ÷ (两种利润之差)。
- **抵扣**：取 `min(范围内已付金额, 订单额×上限%)`；订单低于最低额或超过有效期则为 0；日期按 YYYY-MM-DD 计算。
- **打分**：基础 50 分，企业邮箱 +10、公司已核实 +15、给规格 +10、给数量/目标价 +10、问测试标准 +5、当面见过 +10；免费邮箱 −10、仿冒域名 −25、公司核不到 −10、拒付运费 −20、要全系列无项目 −10、住宅地址 −10、此前样品无反馈每次 −10（最多 −30）、催着先寄 −10。阈值：<25 不寄，<45 全收，<60 收费抵扣，<75 免费抵运费，≥75 免费到付。定制或货值达到门槛至少收费抵扣；仿冒域名或 2 次以上无反馈最多全收。
- 依据：外贸行业公开的寄样 SOP 与实务做法（免费到付、先收后抵、写进 PI），属于经验规则，不是法律。

## Limitations · 局限

- 打分是启发式：只看你输入的信号，不核实公司；请配合买家背调。
- 单一币种，不做汇率换算；运费、成本由你提供，不联网查询。
- 条款草稿不构成法律意见；转化率是你的估计，请用自己 CRM 的历史数据。
- Network access: none. 完全离线，数据不离开你的机器。

## Development · 开发

```bash
uv run --extra dev pytest
python tools/audit.py servers/foreign-trade/sample-policy   # from repo root
```

Review report: [`reports/sample-policy-1.0.0.md`](../../../reports/sample-policy-1.0.0.md)
