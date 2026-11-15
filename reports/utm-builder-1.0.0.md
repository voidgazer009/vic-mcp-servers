# Review report · vic-utm-builder 1.0.0 (2026-11-15)

Standard: REVIEW_STANDARD v1.2. Result: **hard gates pass, score 96 / 100**.

## 1. 选题理由
多平台投放和内容分发最常见的数据事故是 UTM 乱：大小写混用（GA4 区分大小写）、漏填 campaign、参数名拼错、`?utm_` 写在 `#` 后、自定义 medium 掉进 Unassigned。Google 官方文档明确了这些规则，可离线、可验证。

## 2. 竞品检查（官方 Registry）
搜索 utm：`co.utmkit/mcp`（SaaS 短链、二维码、点击分析，需账号）；其余结果无关（UTM 虚拟机监控等）。本 Server 差异：离线免费，专注命名统一、已有链接检查、GA4 渠道预测、多平台批量，不做短链和点击统计。

## 3. 自动审核
全部硬门槛通过，自动项 59 / 61（F4 报告项在本报告写好后补满为 61），pytest 31 通过。

## 4. 人工评分（39）
| 项 | 得分 | 备注 |
|---|---|---|
| A1 真实痛点 | 6/6 | GA4 官方文档本身强调大小写、命名一致 |
| A2 可量化收益 | 4/5 | 避免报表拆分和 (not set)，但难给出具体金额 |
| A3 不重复 | 3/4 | 与 utmkit 在生成 UTM 上有重叠，差异在 lint 与渠道预测 |
| A4 粒度 | 5/5 | 4 个工具 |
| C1 边界测试 | 5/6 | 12 组渠道参数化测试、坏 URL、中文、重复参数；缺超长 URL 专项测试 |
| C2 权威来源 | 4/5 | Google 官方两篇文档；来源站点清单是子集 |
| D1/D2/D4 | 8/8 | 无网络，无数据外传，无发送动作 |
| G1/G8 | 通过 | 手算 golden tests（构建、12 个渠道、lint 拼写） |
合计人工 35 + 自动 61 = **96**。

## 5. 实测发现并修复
- `utm-medium`（连字符）和 `UTM_Source`（大写）没被识别为 UTM 参数，lint 只报"缺失"；现在明确报「必须写成 utm_medium」，补测试。
- 其余刁钻输入（纯符号 source、中文活动名、已有 UTM 被覆盖、占位符、重复平台、# 后的 UTM）均正确报错或警告。

## 6. 标准迭代
audit.py C3 把 `urllib.parse` 也当成联网库，对离线 Server 误扣 4 分。现在只匹配真实联网用法（urllib.request、urlopen、http.client、aiohttp、websockets、socket 等），范围比原来更完整；旧 Server 复审全部不变。REVIEW_STANDARD → v1.2。

## 7. 局限
GA4 渠道的来源站点清单是 Google 表格的子集，预测是近似；不做短链、二维码、点击数据；不知道你的内部域名。
