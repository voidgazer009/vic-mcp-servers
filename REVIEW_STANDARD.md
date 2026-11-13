# Vic MCP 审核标准 · Review Standard v1.1

每个 MCP Server 上架前必须通过这套审核。审核分两层：**一票否决的硬门槛**，加上 **100 分制质量评分**。硬门槛全部通过、且评分 ≥ 85 分才能发布；任何一项硬门槛不过，直接打回重做。

Every server in this repo must pass this review before release: all **hard gates** pass, and a **quality score ≥ 85 / 100**.

标准依据：Model Context Protocol 官方规范（当前修订版 2026-07-28，由 Linux 基金会 Agentic AI Foundation 维护）、官方 SDK 文档、官方 MCP Registry 的 `server.json` 规范，以及 Vic 自己对实用性的要求。

`tools/audit.py` 自动检查标 🤖 的项目；标 👤 的由审核人逐条人工确认，结论写进 `reports/<server>-<version>.md`。

---

## 一、硬门槛（任一不过即打回）· Hard gates

| # | 门槛 | 检查方式 |
|---|---|---|
| G1 | **真实痛点**：README 写明目标用户、具体痛点、不用它会有什么损失 | 👤 |
| G2 | **能启动**：stdio 方式能启动，能完成协议握手/发现 | 🤖 |
| G3 | **工具可列出**：`tools/list` 返回至少 1 个工具，名称为 snake_case | 🤖 |
| G4 | **测试全过**：`pytest` 0 失败，且至少包含 1 个通过真实 MCP Client 调用的协议级测试 | 🤖 |
| G5 | **不泄密**：仓库内无 API Key、Token、密码、私人数据；需要的密钥只从环境变量读取 | 🤖 + 👤 |
| G6 | **不越权**：无 `eval`/`exec`/`os.system`/`shell=True`；写操作或删除操作必须标注 `destructiveHint` 并在 README 里说明 | 🤖 |
| G7 | **错误不崩溃**：非法输入返回 `isError: true` 的工具结果，并给出可操作的提示，而不是让服务器崩溃 | 🤖 |
| G8 | **结果正确**：核心计算/逻辑至少有 3 个人工核算过的“标准答案”测试（golden tests），注释里写出推算过程 | 👤 |
| G9 | **可发布**：有 LICENSE（仓库级 MIT）、`pyproject.toml`（或 `package.json`）、通过官方 schema 校验的 `server.json` | 🤖 |

## 二、质量评分（100 分）· Quality score

### A. 需求价值 · Value（20 分）👤
| 项 | 分 |
|---|---|
| A1 痛点来自真实场景（外贸/物流/一人公司/自媒体从业者每天会遇到），不是为做而做 | 6 |
| A2 解决后能省时间、省钱或避免损失，并能说清楚是多少 | 5 |
| A3 与现有热门 MCP 不重复，或明显做得更好（说明差异） | 4 |
| A4 工具粒度合理：一个工具完成一件完整的事，3 到 8 个工具为宜 | 5 |

### B. 协议合规 · Spec compliance（25 分）🤖
| 项 | 分 |
|---|---|
| B1 使用官方 SDK 当前大版本（Python `mcp>=2` / TS SDK 对应 2026-07-28 修订版） | 3 |
| B2 Server 声明 `name`、`title`、`version`、`description`，并提供 `instructions` 告诉模型何时、如何使用 | 3 |
| B3 每个工具有清楚的 `description`（≥ 60 字符，说明做什么、何时用） | 4 |
| B4 每个输入参数（含 list[Model] 等嵌套模型的每个字段）都有 `description`，并用约束（范围、长度、枚举）防止乱填 | 5 |
| B5 每个工具声明 `outputSchema`，返回结构化结果（structuredContent） | 4 |
| B6 每个工具声明 annotations：`readOnlyHint`、`destructiveHint`、`idempotentHint`、`openWorldHint` | 4 |
| B7 支持 stdio，且可选 Streamable HTTP（无状态，可水平扩展） | 2 |

### C. 正确性与健壮性 · Correctness（20 分）👤 + 🤖
| 项 | 分 |
|---|---|
| C1 golden tests 覆盖核心公式，边界情况（0、负数、极大值、空输入）有测试 | 6 |
| C2 业务规则引用权威来源（如 Incoterms 2020、海关规则、平台官方政策），写在代码注释或 README | 5 |
| C3 联网调用有超时、有失败提示、说明数据来源和更新频率 | 4 |
| C4 输出里主动给出风险提示（warnings），让模型转告用户 | 5 |

### D. 安全 · Safety（10 分）🤖 + 👤
| 项 | 分 |
|---|---|
| D1 只访问 README 里声明的外部域名 | 3 |
| D2 不收集、不上传用户数据；日志里不打印敏感信息 | 3 |
| D3 依赖最少且固定大版本范围 | 2 |
| D4 涉及发送、付款、删除的工具默认只生成草稿，需人确认 | 2 |

### E. 使用体验 · Developer & user experience（15 分）🤖 + 👤
| 项 | 分 |
|---|---|
| E1 README 中英双语，含：痛点、工具表、安装、客户端配置、示例提问、计算规则、局限 | 6 |
| E2 至少覆盖 Claude Desktop/Code、Cursor、VS Code、Codex 四种客户端配置 | 3 |
| E3 5 条以上可直接复制的中文示例提问 | 3 |
| E4 提供 1 个 Prompt 或 Resource，帮模型把工具串成完整工作流 | 3 |

### F. 可维护与可发布 · Maintainability（10 分）🤖
| 项 | 分 |
|---|---|
| F1 语义化版本号，`pyproject.toml`、`server.json`、代码里的版本一致 | 3 |
| F2 有 CHANGELOG | 2 |
| F3 业务逻辑与协议层分离（纯函数可单测） | 3 |
| F4 审核报告已写入 `reports/` | 2 |

## 三、审核流程 · Process

1. **选题**：从 `ROADMAP.md` 里选当天方向价值最高、还没做的主题，先写清楚痛点。
2. **开发**：业务逻辑写成纯函数，再用官方 SDK 包成 MCP 工具。
3. **自动审核**：`python tools/audit.py servers/<方向>/<名字>`，硬门槛和 🤖 项必须全过。
4. **人工审核**：逐条核对 👤 项，至少用 3 个真实场景从 MCP Client 端实际调用一遍，记录发现的问题。
5. **修复复审**：发现的问题全部修复后，重跑 1 到 4。
6. **发布**：写审核报告、更新 CHANGELOG 和仓库 README 的目录，提交并打 tag `<名字>-v<版本>`。
7. **完善再继续**：上一个 Server 的已知问题清零、审核分 ≥ 85，才开始写下一个。

## 四、评分档位 · Grades

| 分数 | 结论 |
|---|---|
| ≥ 95 | 🏆 精品，可提交官方 MCP Registry |
| 85 to 94 | ✅ 通过，可发布 |
| 70 to 84 | 🔧 需修改，不发布 |
| < 70 或任一硬门槛未过 | ❌ 打回重做 |

## 五、标准变更记录 · Changelog

| 版本 | 日期 | 变更 |
|---|---|---|
| v1.0 | 2026-11-12 | 首版 |
| v1.1 | 2026-11-13 | 收紧 B4：`audit.py` 现在也检查嵌套输入模型（`$defs`）里每个字段的描述和约束，之前只看顶层参数（billable-weight 人工审核时发现的盲区） |
