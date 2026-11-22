# Vic MCP Servers

> 面向**外贸、国际物流、AI 一人公司、全球自媒体**从业者的开源 MCP Server 合集。每一个都从真实痛点出发，按 Model Context Protocol 官方规范（2026-07-28 修订版，Linux 基金会 Agentic AI Foundation 维护）开发，并通过 Vic 审核标准后才发布。
>
> Open-source MCP servers for foreign trade, international logistics, AI one-person companies and global social media. Each starts from a real pain point, follows the official MCP spec, and ships only after passing the Vic review standard.

**By Vic** · MIT License · Works with Claude, ChatGPT, Cursor, VS Code / Copilot, Codex and any MCP client.

## Servers · 目录

| 方向 | Server | 解决什么 | 工具 | 审核分 | 版本 |
|---|---|---|---|---|---|
| 外贸 | [export-quote](servers/foreign-trade/export-quote) | 一次算对 EXW/FOB/CFR/CIF/DDP 报价，装柜最省钱组合，汇率，贸易术语避坑 | 5 | 🏆 96 | 1.0.0 |
| 外贸 | [payment-terms](servers/foreign-trade/payment-terms) | 收款方式比较（T/T、L/C、D/P、D/A、O/A）、推荐、合同和信用证软条款筛查 | 4 | 🏆 95 | 1.0.0 |
| 外贸 | [sample-policy](servers/foreign-trade/sample-policy) | 样品请求分级、四档报价、首单抵扣、ROI、条款草稿 | 5 | 🏆 94 | 1.0.0 |
| 国际物流 | [billable-weight](servers/logistics/billable-weight) | 算准 UPS/FedEx/DHL/空运/拼箱计费重，订舱前查附加费，核查承运商重量调整并写申诉，纸箱缩多少最省 | 5 | 🏆 95 | 1.0.0 |
| 国际物流 | [transport-ids](servers/logistics/transport-ids) | 集装箱号（ISO 6346）与空运单号校验、箱型代码解码、文本提取 | 4 | 🏆 95 | 1.0.0 |
| 国际物流 | [demurrage-detention](servers/logistics/demurrage-detention) | 滞港费/滞箱费：最后免费日、阶梯计费、提柜日期比较、账单核对 | 4 | 🏆 95 | 1.0.0 |
| AI 一人公司 | [cashflow-forecast](servers/one-person-company/cashflow-forecast) | 按周现金流预测、还能撑几个月、大客户晚付款压力测试 | 3 | ✅ 94 | 1.0.0 |
| AI 一人公司 | [solo-pricing](servers/one-person-company/solo-pricing) | 从想拿的收入倒推最低时薪，固定价报价含缓冲和改稿，手续费倒推，打折要多卖多少，单子真实时薪 | 5 | 🏆 96 | 1.0.0 |
| AI 一人公司 | [invoice-aging](servers/one-person-company/invoice-aging) | 到期日、应收账龄、欧盟/英国逾期利息和固定追款费、分级催款邮件草稿 | 4 | 🏆 95 | 1.0.0 |
| 全球自媒体 | [utm-builder](servers/social-media/utm-builder) | UTM 链接生成、已有链接检查、GA4 渠道预测、多平台批量生成 | 4 | 🏆 96 | 1.0.0 |
| 全球自媒体 | [creator-quote](servers/social-media/creator-quote) | 达人报价审核：互动率中位数、有效 CPM/CPE（含授权/排他）、最高可接受报价、回本单量、还价草稿 | 4 | 🏆 94 | 1.0.0 |

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
