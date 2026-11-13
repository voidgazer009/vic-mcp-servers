# Roadmap · 选题池

每天轮换一个方向：外贸 → 国际物流 → AI 一人公司 → 全球自媒体 → 外贸 …
每个方向从下面挑价值最高、还没做的主题。✅ = 已发布。选题标准：真实痛点、能确定性解决、优先免 API Key。

## 外贸 Foreign trade (`servers/foreign-trade/`)
- ✅ export-quote · 多术语报价、装柜、汇率、贸易术语
- buyer-vetting · 买家背调：域名年龄、公司注册、邮箱真伪、诈骗特征
- proforma-invoice · 生成形式发票 / 报价单 PDF
- lc-checker · 信用证条款审单，找软条款和不符点
- payment-terms-risk · T/T、L/C、D/P、O/A 风险评估与建议
- sample-policy · 样品费、运费、抵扣规则计算
- inquiry-triage · 询盘打分：真买家 vs 同行/骗子/学生
- hs-code-helper · HS 编码初判与各国税率查询入口
- trade-show-planner · 展会 ROI 与跟进节奏

## 国际物流 International logistics (`servers/logistics/`)
- ✅ billable-weight · 计费重（UPS/FedEx/DHL/空运/拼箱/公路）、附加费预检、重量调整申诉、纸箱优化、报价比价（合并原 freight-calculator 与 dim-weight-optimizer）
- shipment-tracker · 集装箱号/提单号/空运单号格式校验与追踪入口
- customs-docs · 报关单据清单：按国家和品类列出需要的文件
- demurrage-detention · 滞港费/滞箱费计算与免费期提醒
- dangerous-goods · 危险品（锂电池等）运输规则初判
- port-lookup · 港口代码 UN/LOCODE 查询
- transit-time · 主要航线时效与转运风险

## AI 一人公司 One-person company (`servers/one-person-company/`)
- invoice-tracker · 开票、收款、逾期提醒
- pricing-calculator · 服务/产品定价：成本、时薪、目标收入倒推
- cashflow-forecast · 13 周现金流预测
- client-crm-lite · 轻量客户管理（本地 SQLite）
- tax-calendar · 各国个体户/小公司报税日历
- contract-checker · 合同风险条款提示
- time-tracker · 工时与项目利润
- automation-roi · 自动化投入回报计算

## 全球自媒体 Global social media (`servers/social-media/`)
- post-scheduler-planner · 多平台最佳发布时间（按目标时区）
- hashtag-research · 话题标签分组与长度/数量规则校验
- content-repurpose · 一稿多平台改写规则（字数、格式、标签）
- caption-linter · 各平台文案限制检查（字数、链接、敏感词）
- creator-rate-card · 达人报价计算（粉丝、互动率、平台系数）
- utm-builder · UTM 链接生成与归因命名规范
- video-spec-checker · 各平台视频尺寸、时长、码率要求
- analytics-digest · 多平台数据周报
