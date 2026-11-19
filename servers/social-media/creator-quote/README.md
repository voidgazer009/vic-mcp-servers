# Vic Creator Quote MCP · 达人报价审核 MCP

> Is this creator's quote fair? Engagement rate from real posts, CPM and CPE with usage rights and exclusivity included, the highest fee that hits your target, a sales payback ceiling, and counter-offer drafts. Official MCP spec (revision 2026-07-28, Python SDK v2). Offline, no API key.
>
> 品牌方 / 跨境卖家审达人报价：按真实帖子算互动率，把授权费和排他费算进有效 CPM，给出能接受的最高报价和还价草稿。

**Direction 方向:** 全球自媒体 Global social media · **Version:** 1.0.0 · **License:** MIT · **Transport:** stdio, Streamable HTTP

---

## 解决什么痛点 · Pain points

目标用户：找海外 KOL / 达人投放的品牌方、跨境卖家、代理公司。

| 常见的坑 | 后果 | 这个 MCP 怎么解决 |
|---|---|---|
| 用粉丝数算 CPM，粉丝多但播放少 | 8 万粉的号播放只有 1.2 万，实际 CPM 是表面的 6 倍多 | `evaluate_creator_quote` 按预期播放算 CPM，并并列提示粉丝口径的误导 |
| 一条爆款拉高平均播放 | 按均值报价，后面的内容跑不到 | `calculate_engagement_rate` 取中位数并标出 3 倍中位数以上的爆款 |
| 授权期限、排他条款藏在报价外 | 基础价便宜，加上授权后翻倍 | 有效 CPM 把授权费（每月 %）和排他费一起计入 |
| 不知道还价还多少 | 凭感觉砍价，或被迫全价接受 | 给出达到目标 CPM 的最高基础价，并生成还价邮件草稿（不发送） |
| 带货投放不知道要卖多少才回本 | 花了钱才发现卖不回 | `calculate_payback_ceiling` 算回本单量和最高可付费用 |

Compared with registry servers: existing ones manage campaigns on one platform (e.g. 1stCollab) or sell contact data. This one is offline pricing maths that works with any creator and platform; you supply the benchmark, nothing is guessed.

## Tools · 工具

| Tool | 做什么 | 只读 |
|---|---|---|
| `calculate_engagement_rate` | 单帖/中位互动率、爆款异常值 | ✅ |
| `evaluate_creator_quote` | CPM、CPE、有效 CPM、对比目标、最高基础价 | ✅ |
| `calculate_payback_ceiling` | 回本单量、预期盈亏、最高基础价 | ✅ |
| `draft_counter_offer` | 中/英还价邮件草稿（不发送） | ✅ |

**Resource:** `creator://formulas`. **Prompt:** `review_creator_quote`.

## Install · 安装

Python 3.10+, with [uv](https://docs.astral.sh/uv/):

```bash
git clone https://github.com/voidgazer009/vic-mcp-servers.git
cd vic-mcp-servers/servers/social-media/creator-quote
uv run vic-creator-quote-mcp          # stdio
uv run vic-creator-quote-mcp --http   # Streamable HTTP on http://127.0.0.1:8000/mcp
```

### Claude Desktop / Claude Code

```json
{
  "mcpServers": {
    "vic-creator-quote": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/vic-mcp-servers/servers/social-media/creator-quote", "vic-creator-quote-mcp"]
    }
  }
}
```

Claude Code: `claude mcp add vic-creator-quote -- uv run --directory /path/to/creator-quote vic-creator-quote-mcp`

### Cursor (`.cursor/mcp.json`) · VS Code / Copilot (`.vscode/mcp.json`)

Same `command` and `args`. For VS Code use the key `"servers"` instead of `"mcpServers"`.

### Codex CLI (`~/.codex/config.toml`)

```toml
[mcp_servers.vic-creator-quote]
command = "uv"
args = ["run", "--directory", "/path/to/creator-quote", "vic-creator-quote-mcp"]
```

## Try it · 试试这样问

- 「达人 8 万粉，一条 Reel 报价 800 美元，平时播放约 1.2 万，我的目标 CPM 是 50，这个价合理吗？」
- 「再加 3 个月授权，每月收基础价的 10%，有效 CPM 变成多少？最高能接受的基础价是多少？」
- 「这是达人最近 10 条视频的播放、点赞、评论、分享、收藏，帮我算中位互动率，看有没有爆款拉高平均。」
- 「客单价 50 美元、毛利 40%，合同总成本 1040 美元，要卖多少单才回本？预期卖 30 单亏多少？」
- 「帮我写一封中文还价邮件，把 1000 美元降到 800 美元，语气友好。」

## How the numbers work · 计算规则

- **Engagements** = likes + comments + shares + saves. **ER by views** = engagements ÷ views × 100; **by followers** = engagements ÷ followers × 100.
- **CPM** = fee ÷ expected views × 1000. **Effective CPM** = (fee + usage fee + exclusivity fee) ÷ expected views × 1000. **Usage fee** = fee × usage % per month × months.
- **Max base fee** = (target CPM × views ÷ 1000 − exclusivity fee) ÷ (1 + usage % × months).
- **Break-even sales** = ceil(contract cost ÷ (net order value × margin %)).
- Viral outlier: views above 3× the median, needs at least 4 posts.
- No market benchmarks are hard-coded: CPM and CPE targets come from you.

## Limitations · 局限

- Expected views are the creator's typical past performance, not a guarantee; ask for native analytics.
- Does not detect fake followers or engagement pods; it only warns when numbers look implausible.
- Single currency per call; no FX. Payback ignores brand lift and repeat purchases.
- Drafts are never sent. Keep paid-partnership disclosure in the contract (e.g. FTC Endorsement Guides). Not legal advice.
- Network access: none. Everything runs locally; no data leaves your machine.

## Development · 开发

```bash
uv run --extra dev pytest
python tools/audit.py servers/social-media/creator-quote   # from repo root
```

Review report: [`reports/creator-quote-1.0.0.md`](../../../reports/creator-quote-1.0.0.md)
