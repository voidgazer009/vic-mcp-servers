# Roadmap · 选题池

每天轮换一个方向：外贸 → 国际物流 → AI 一人公司 → 全球自媒体 → 外贸 …
每个方向从下面挑价值最高、还没做的主题。✅ = 已发布。选题标准：真实痛点、能确定性解决、优先免 API Key。

## 外贸 Foreign trade (`servers/foreign-trade/`)
- ✅ export-quote · 多术语报价、装柜、汇率、贸易术语
- buyer-vetting · 买家背调：域名年龄、公司注册、邮箱真伪、诈骗特征
- proforma-invoice · 生成形式发票 / 报价单 PDF
- lc-checker · 信用证条款审单，找软条款和不符点
- ✅ payment-terms · 收款方式比较、推荐、条款/信用证软条款筛查（原 payment-terms-risk + lc-checker 的文本审查部分）
- ✅ sample-policy · 样品请求分级、四档报价、首单抵扣、ROI、条款草稿
- inquiry-triage · 询盘打分：真买家 vs 同行/骗子/学生
- hs-code-helper · HS 编码初判与各国税率查询入口
- trade-show-planner · 展会 ROI 与跟进节奏

## 国际物流 International logistics (`servers/logistics/`)
- ✅ billable-weight · 计费重（UPS/FedEx/DHL/空运/拼箱/公路）、附加费预检、重量调整申诉、纸箱优化、报价比价（合并原 freight-calculator 与 dim-weight-optimizer）
- ✅ transport-ids · 集装箱号/空运单号校验、箱型解码（shipment-tracker 的离线部分；真实追踪与提单号待做）
- customs-docs · 报关单据清单：按国家和品类列出需要的文件
- demurrage-detention · 滞港费/滞箱费计算与免费期提醒
- dangerous-goods · 危险品（锂电池等）运输规则初判
- port-lookup · 港口代码 UN/LOCODE 查询
- transit-time · 主要航线时效与转运风险

## AI 一人公司 One-person company (`servers/one-person-company/`)
- ✅ invoice-aging · 到期日、应收账龄、逾期利息、催款草稿（无状态版 invoice-tracker；存储版留待后续）
- ✅ solo-pricing · 时薪倒推、固定价报价、手续费倒推、打折影响、真实时薪（原 pricing-calculator）
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
- ✅ creator-quote · 达人报价审核（CPM/CPE、授权费、回本；取代 creator-rate-card）
- ✅ utm-builder · UTM 链接生成、检查、GA4 渠道预测、多平台批量
- video-spec-checker · 各平台视频尺寸、时长、码率要求
- analytics-digest · 多平台数据周报
