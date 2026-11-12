# Vic MCP Servers

> 面向**外贸、国际物流、AI 一人公司、全球自媒体**从业者的开源 MCP Server 合集。每一个都从真实痛点出发，按 Model Context Protocol 官方规范（2026-07-28 修订版，Linux 基金会 Agentic AI Foundation 维护）开发，并通过 Vic 审核标准后才发布。
>
> Open-source MCP servers for foreign trade, international logistics, AI one-person companies and global social media. Each starts from a real pain point, follows the official MCP spec, and ships only after passing the Vic review standard.

**By Vic** · MIT License · Works with Claude, ChatGPT, Cursor, VS Code / Copilot, Codex and any MCP client.

## Servers · 目录

| 方向 | Server | 解决什么 | 工具 | 审核分 | 版本 |
|---|---|---|---|---|---|
| 外贸 | [export-quote](servers/foreign-trade/export-quote) | 一次算对 EXW/FOB/CFR/CIF/DDP 报价，装柜最省钱组合，汇率，贸易术语避坑 | 5 | 🏆 96 | 1.0.0 |

更多主题见 [ROADMAP.md](ROADMAP.md)，四个方向轮流更新，一个打磨完再做下一个。

## 审核标准 · Review standard

每个 Server 必须通过 9 道硬门槛（能启动、测试全过、无泄密、错误不崩溃、结果经人工核算等）和 100 分制质量评分（需求价值、协议合规、正确性、安全、体验、可维护），≥ 85 分才发布。

- 标准全文：[REVIEW_STANDARD.md](REVIEW_STANDARD.md)
- 自动审核脚本：[`tools/audit.py`](tools/audit.py)
- 每个版本的审核报告：[`reports/`](reports)

## Quick start · 快速使用

```bash
git clone https://github.com/voidgazer009/vic-mcp-servers.git
cd vic-mcp-servers/servers/foreign-trade/export-quote
uv run vic-export-quote-mcp
```

每个 Server 的 README 里都有 Claude Desktop / Claude Code / Cursor / VS Code / Codex 的配置示例。

## Repo layout · 结构

```
servers/
  foreign-trade/       外贸
  logistics/           国际物流
  one-person-company/  AI 一人公司
  social-media/        全球自媒体
tools/audit.py         自动审核
reports/               审核报告
REVIEW_STANDARD.md     审核标准
ROADMAP.md             选题池
```

## Contributing · 参与

欢迎提 Issue 告诉我你工作中的痛点，被选中的主题会做成新的 MCP Server。
