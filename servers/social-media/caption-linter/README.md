# Vic Caption Linter MCP · 多平台文案长度与规则检查 MCP

> Count and lint one social post the way each platform really counts it: X weighted count (CJK and emoji = 2, links = 23), Bluesky graphemes, Threads, Mastodon, Instagram, TikTok, YouTube bytes. Official MCP spec (revision 2026-07-28, Python SDK v2). Offline, no API key.
>
> 一稿多发之前，按各平台真实的计数规则检查长度、话题标签、链接、占位符，告诉你哪个平台超了多少。

**Direction 方向:** 全球自媒体 Global social media · **Version:** 1.0.0 · **License:** MIT · **Transport:** stdio, Streamable HTTP

---

## 解决什么痛点 · Pain points

目标用户：同一条内容发 X、Bluesky、Threads、Instagram、LinkedIn、YouTube 的出海自媒体和一人公司。

| 常见的坑 | 后果 | 这个 MCP 怎么解决 |
|---|---|---|
| 用 Word 或字数统计数中文推文 | X 中文和 emoji 每个算 2，280 实际只能写约 140 个汉字，发布被拒 | 按 X 官方加权规则计数，链接固定算 23 |
| Bluesky 带长链接（UTM 链接） | 链接按全长计入 300 字，正文被吃掉 | 警告长链接，按 grapheme 计数 |
| Threads 里 emoji | 按 UTF-8 字节算（常见 4），500 字不够用；超过 5 个不同链接直接创建失败 | 按规则计数并检查链接数 |
| Instagram 话题标签 | 帮助中心已写最多 5 个，API 文档仍写 30，旧攻略说 30 | 超过 5 给警告，超过 30 报错 |
| YouTube 描述 | 按字节算（中文 3 字节/字），标题和描述不能含 `<` `>` | 按字节计数并检查非法字符 |
| 模板占位符 `{{name}}`、标签粘连 `#a#b` | 发出去才发现 | lint 报错/警告 |

Compared with the registry's social MCP servers (publishing, analytics and scraping services that need accounts or API keys, and SRT/WebVTT subtitle checkers): this one is offline and free and only answers "will this text pass on each network?"; it publishes nothing.

## Tools · 工具

| Tool | 做什么 | 只读 |
|---|---|---|
| `count_post_text` | 按各平台规则计数，给出剩余字数 | ✅ |
| `lint_post_text` | 发布前完整检查（超限、标签、链接、非法字符、占位符、折叠位置） | ✅ |
| `find_fitting_platforms` | 一段文字在哪些平台放得下、其他平台要删多少 | ✅ |
| `list_platform_limits` | 所有限制、计数规则和官方来源 | ✅ |

**Resource:** `caption://limits`. **Prompt:** `adapt_post`.

Platform ids: `x`, `bluesky`, `threads`, `mastodon`, `linkedin`, `instagram`, `tiktok`, `youtube_title`, `youtube_description`, `pinterest_title`, `pinterest_description`, `facebook`.

## Install · 安装

Python 3.10+, with [uv](https://docs.astral.sh/uv/):

```bash
git clone https://github.com/voidgazer009/vic-mcp-servers.git
cd vic-mcp-servers/servers/social-media/caption-linter
uv run vic-caption-linter-mcp          # stdio
uv run vic-caption-linter-mcp --http   # Streamable HTTP on http://127.0.0.1:8000/mcp
```

### Claude Desktop / Claude Code

```json
{
  "mcpServers": {
    "vic-caption-linter": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/vic-mcp-servers/servers/social-media/caption-linter", "vic-caption-linter-mcp"]
    }
  }
}
```

Claude Code: `claude mcp add vic-caption-linter -- uv run --directory /path/to/caption-linter vic-caption-linter-mcp`

### Cursor (`.cursor/mcp.json`) · VS Code / Copilot (`.vscode/mcp.json`)

Same `command` and `args`. For VS Code use the key `"servers"` instead of `"mcpServers"`.

### Codex CLI (`~/.codex/config.toml`)

```toml
[mcp_servers.vic-caption-linter]
command = "uv"
args = ["run", "--directory", "/path/to/caption-linter", "vic-caption-linter-mcp"]
```

## Try it · 试试这样问

- 「帮我检查这条中文推文发 X 会不会超长：……（粘贴文案）」
- 「这段文案同时发 X、Bluesky、Threads、Instagram，各平台还剩多少字？」
- 「我的 Instagram 文案带了 8 个话题标签，会有问题吗？」
- 「YouTube 描述里有中文和 emoji，按字节算有没有超 5000？」
- 「这个 Mastodon 实例的上限是 800，帮我按这个数检查，带内容警告。」

## How it works · 规则说明

- **X:** weighted. Code points 0–4351 and a few punctuation ranges weigh 1, everything else (CJK) 2, emoji 2, every http(s)/www link 23. Limit 280 (25,000 with Premium).
- **Bluesky:** 300 graphemes and 3,000 UTF-8 bytes; links at full length.
- **Threads:** 500; emoji count their UTF-8 bytes; more than 5 unique links fails.
- **Mastodon:** server limit (default 500); links 23, mentions count the username only, content warning included.
- **Instagram:** 2,200 characters, 20 @ tags; hashtags: Help Center 5 (warning above 5), API 30 (error above 30). **TikTok:** 2,200 UTF-16 units (API). **LinkedIn:** 3,000. **YouTube:** title 100 characters, description 5,000 bytes, no `<` `>`. **Pinterest:** title 100, description 800 (API). **Facebook:** no documented limit, nothing enforced.
- "See more" fold positions (Instagram ~125, LinkedIn ~210) are measured by others, not published: shown as info only.
- Grapheme clustering is a stdlib approximation (ZWJ sequences, skin tones, flags, keycaps); exotic scripts may differ by one.
- Sources are listed per platform in `list_platform_limits` (checked 2026-11-23).

## Limitations · 局限

- The in-app composer can differ from API documentation; posts within a few characters of a limit should be re-checked there.
- Platforms change limits (Instagram's hashtag cap just did). Re-check the cited page when a result surprises you.
- No Chinese-platform rules (小红书, 抖音, 微博) yet: their limits were not verifiable from official pages.
- It does not post, schedule or shorten links.
- Network access: none. Everything runs locally; no data leaves your machine.

## Development · 开发

```bash
uv run --extra dev pytest
python tools/audit.py servers/social-media/caption-linter   # from repo root
```

Review report: [`reports/caption-linter-1.0.0.md`](../../../reports/caption-linter-1.0.0.md)
