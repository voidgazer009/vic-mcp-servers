# Vic UTM Builder MCP · UTM 链接生成与检查 MCP

> Build, lint and classify UTM campaign links for GA4: one lower-case naming convention, predicted GA4 channel, batch links for many platforms. Official MCP spec (revision 2026-07-28, Python SDK v2). Offline, no API key.
>
> 自媒体 / 增长 / 一人公司的追踪链接工具：统一命名、检查已有链接的错误、预测它在 GA4 里会归到哪个渠道、一次生成多平台链接。

**Direction 方向:** 全球自媒体 Global social media · **Version:** 1.0.0 · **License:** MIT · **Transport:** stdio, Streamable HTTP

---

## 解决什么痛点 · Pain points

目标用户：做多平台内容和投放的自媒体运营、独立站卖家、一人公司创始人。

| 常见的坑 | 后果 | 这个 MCP 怎么解决 |
|---|---|---|
| `Meta` 和 `meta`、`SpringSale` 和 `Spring_Sale` 混着写 | GA4 区分大小写，同一个渠道被拆成多行，报表对不上 | `build_utm_url` 默认统一成小写加下划线，并列出改了什么 |
| 漏填 `utm_campaign` 或写错参数名（`utm_campaing`） | 报表出现 `(not set)`，流量归因丢失 | `lint_utm_url` 找出缺失、拼写错误、重复参数 |
| `?utm_...` 写在 `#` 后面 | 浏览器不会把 # 后面的内容发给服务器，GA4 根本收不到 | lint 直接报错 |
| 自定义 medium（如 `xiaohongshu` + `cpc`）不在 GA4 规则里 | 流量掉进 `Unassigned` 或 `Paid Other`，渠道报表失真 | `predict_ga4_channel` 按 Google 文档的规则顺序预测渠道 |
| 多平台发同一个活动，每人各写各的命名 | 数据无法合并，月底手工清洗 | `build_campaign_links` 用统一预设一次生成全部链接 |
| 模板占位符 `{{campaign.name}}` 忘了替换 | 报表里出现字面量占位符 | lint 给出警告 |

Compared with the registry's UTM servers (a SaaS short-link and click-analytics service): this one is offline and free, focused on naming consistency, linting and GA4 channel prediction; it does not shorten links or track clicks.

## Tools · 工具

| Tool | 做什么 | 只读 |
|---|---|---|
| `build_utm_url` | 给一个链接加 UTM，清洗命名，预测 GA4 渠道 | ✅ |
| `lint_utm_url` | 检查已有链接的错误和风险 | ✅ |
| `predict_ga4_channel` | source + medium → GA4 默认渠道分组 | ✅ |
| `build_campaign_links` | 一个活动 × 多个平台，批量生成链接 | ✅ |

**Resource:** `utm://naming-convention`. **Prompt:** `plan_campaign_tracking`.

## Install · 安装

Python 3.10+, with [uv](https://docs.astral.sh/uv/):

```bash
git clone https://github.com/voidgazer009/vic-mcp-servers.git
cd vic-mcp-servers/servers/social-media/utm-builder
uv run vic-utm-builder-mcp          # stdio
uv run vic-utm-builder-mcp --http   # Streamable HTTP on http://127.0.0.1:8000/mcp
```

### Claude Desktop / Claude Code

```json
{
  "mcpServers": {
    "vic-utm-builder": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/vic-mcp-servers/servers/social-media/utm-builder", "vic-utm-builder-mcp"]
    }
  }
}
```

Claude Code: `claude mcp add vic-utm-builder -- uv run --directory /path/to/utm-builder vic-utm-builder-mcp`

### Cursor (`.cursor/mcp.json`) · VS Code / Copilot (`.vscode/mcp.json`)

Same `command` and `args`. For VS Code use the key `"servers"` instead of `"mcpServers"`.

### Codex CLI (`~/.codex/config.toml`)

```toml
[mcp_servers.vic-utm-builder]
command = "uv"
args = ["run", "--directory", "/path/to/utm-builder", "vic-utm-builder-mcp"]
```

## Try it · 试试这样问

- 「给 https://example.com/pricing 生成 LinkedIn 付费广告的追踪链接，活动叫 Spring Sale 2026。」
- 「检查这个链接有没有问题：https://example.com/?utm_source=Meta&utm_medium=cpc&utm_campaing=a」
- 「小红书投流用 source=xiaohongshu、medium=cpc，在 GA4 里会归到哪个渠道？」
- 「新品发布活动，帮我一次生成 YouTube、newsletter、微信、LinkedIn 四个渠道的链接，utm_id 用 launch01。」
- 「我的 UTM 写在 # 后面了，这样 GA4 能收到吗？」

## How it works · 规则说明

- **Naming:** values are lower-cased, spaces and punctuation become `_`, Chinese characters are kept (and percent-encoded). `normalize=false` keeps exact values but warns.
- **Parameters:** `utm_id`, `utm_source`, `utm_medium`, `utm_campaign`, `utm_term`, `utm_content`, `utm_source_platform`. Source, medium and campaign are required; `utm_id` is recommended. Existing query parameters and the `#fragment` are preserved; existing UTM tags are replaced with a warning.
- **Channel prediction:** follows the manual-traffic rules of GA4's default channel group in Google's order (Direct, Cross-network, Paid Shopping/Search/Social/Video, Display, Paid Other, Organic Shopping/Social/Video/Search, AI Assistant, Referral, Email, Affiliates, Audio, SMS, Mobile Push). Paid medium regex: `^(.*cp.*|ppc|retargeting|paid.*)$`.
- **Our own conventions (not Google limits):** values over 100 characters and URLs over 2000 characters get a warning.
- Sources: Google Analytics Help, "URL builders: Collect campaign data with custom URLs" and "Default channel group" (checked 2026-11-15).

## Limitations · 局限

- Google's source lists (which sites count as search, social, video, shopping) are longer than the ones built in; the prediction is approximate. Check Traffic acquisition in your own property.
- It does not shorten links, make QR codes or read click data.
- It cannot know your internal domains: never tag links between pages of your own site.
- Network access: none. Everything runs locally; no data leaves your machine.

## Development · 开发

```bash
uv run --extra dev pytest
python tools/audit.py servers/social-media/utm-builder   # from repo root
```

Review report: [`reports/utm-builder-1.0.0.md`](../../../reports/utm-builder-1.0.0.md)
