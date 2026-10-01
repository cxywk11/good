# 待办与技术债

本文件不授权扩大本阶段范围。2026-10-01 P4-0～P4-3、P4-4A 比分概率数学层及 P4-4B1 Goals-only Football Baseline 已经人工复核；P4-4C Model Evaluation Core 已实施，待人工复核。后续模型与功能等待明确指令。

## 当前阶段验收阻塞

- 在具有 Docker Engine 的主机执行 Compose 四服务启动与重启验证，实测 Redis 锁、速率门、失败恢复和 readiness。
- 体彩公开数据接口本机返回 HTTP 567。取得可用访问环境/授权接口，保存真实脱敏 Raw，核对官方当日比赛数量、编号、销售日、销售状态、五玩法与单关字段。
- 提供一个海外数据源有效凭据及对应权限，核验真实 bookmaker / market 覆盖并贯通 PG/API/UI。The Odds API 适配器已有契约测试；它不保证 Bet365 或澳门覆盖，不能把合成 fixture 当专有接口样例。
- 对真实无队 ID 的事件执行人工映射，取得稳定实体 ID 源后再扩大自动确认；完成开球变更、停售、跨日和延迟回填的真实样本验收。

## 上线前工程工作

- 邮件验证和账号恢复；基础登录/注册/刷新限流已完成，生产仍需可信代理配置和外部流量压力测试。
- 引入可复现的跨平台 Python 依赖锁及漏洞扫描；npm lock 已存在。现有 Starlette TestClient 对 httpx 有弃用警告，需在确认新客户端兼容后升级，当前没有压制该警告。
- 实际 Redis 并发/网络中断演练、容器构建和 CI；当前调度边界和 Redis 故障路径有测试，不能等价于真实 Redis 验收。
- 大表压测、分页与最新值查询计划、按月分区及冷存储恢复方案；当前每序列变化查询仍有额外 SQL，可在真实负载下合并批量查询。
- 前端按路由进一步拆分和 Ant Design 体积优化；当前 ECharts 已懒加载，但构建仍有大 chunk 提示。自动化浏览器端到端回归和可访问性检查尚未建立。
- Token 只放浏览器内存，刷新后重新登录。若要求持久会话，设计 HttpOnly Cookie 与 CSRF 防护后再改。
- 增加完整身份维护工作台（已有逐场审核和可选稳定队 ID 绑定）、运行日志检索及外部告警。现有管理日志页提供变更审计。
- 已存在业务 matches 在后续官方列表中缺席时，不凭缺席推断停售；待真实接口完整性语义确认后定义可信撤销策略。

## 下一阶段开始前

先关闭全部数据验收 Gate，再建立真实数据的人工核验集和连续采集观察期。核验来源覆盖、延迟、缺失、映射准确率、时间泄漏与备份可恢复性，形成通过标准。Mock 仅可用于评估数学 Golden Case，不得将 Mock 或未确认映射的结果作为真实模型质量结论；当前实现 Feature、Market Baseline、比分数学转换、Goals-only Football Baseline 与纯 Evaluation Core，不实现 AI 分析。

## Phase 4 审查发现及后续债务

- 原 created_at 是插入时刻而非提交时刻；P4 已增加独立读取确认的 analysis_visibility。迁移前没有此证据的历史不能恢复精确系统可见性；不得以事后推测时间回填。旧赔率展示语义保留。
- 可见性收集扫描七张历史表的待确认行，Feature 读取可见比赛版本/映射审计并逐条校验赛后绑定版本；需数据规模基准后再优化批次、索引和窗口，不提前推翻底座。
- 真赛果/统计 Provider、比分冲突裁决、完整球队比赛历史（当前仅体彩池）、阵容/新闻证据尚未接入。100 分只表示 V1 的五项可用性检查通过。
- 模型版本注册、训练工件摘要、Feature 历史构建器归档、时间拆分回测留给后续授权阶段，ADR-007/008 仅确立规则。
- 自动提交凭据失败会留日志并保守拒绝相关输入；需生产监控、UTC 时钟同步、最小数据库权限和大批量恢复演练。

## P4-3 后续债务（不在本轮实施）

- 保留原 analysis_visibility 每次 ORM commit 的待证明历史扫描；本轮不改可见性基础设施，后续需专项设计和负载数据。Market 服务仅按 ID 读冻结 Feature 和快照，无新增历史扫描。
- Bookmaker Entity Resolution 尚未建立；相同真实公司可能跨 Provider 重复覆盖。V1 identity 为 provider + bookmaker，等权，不加 sharp/Pinnacle 等人工权重。未来权重需历史 Out-of-Sample 证据。
- Feature 的 latest/previous 是各报价序列的观察，不保证市场各项同刻。P4-3 只输出当前冻结报价去水与逐项变化；真正同步的 T_24H～T_5M 概率截面须另行设计，不能利用 previous 拼造。
- 亚洲盘/大小球含走盘或半赢半输时，二项去水只是价格归一，不是完整结算概率。P4-4A 已实现 Score Matrix 的 HHAD/TTG 派生；亚洲盘结算空间留给独立 Settlement Engine，不在数学层混入 EV。
- `HIGH_OVERROUND` 使用版本固定的 >1.20 诊断阈值，没有历史校准依据，不改变概率权重或剔除数据。真实来源覆盖、市场完整性和报价时效仍需验收。
- 旧 market-v1 的实现与 Python/Decimal 运行工件需随发布保留；规则、精度或来源选择变化须升级版本。全局模型注册和依赖锁仍待后续工作。
- P4-3、P4-4A 已经人工复核；P4-4B1 仅实现冻结赛果的透明 lambda baseline，其他模型仍未实施。

## P4-4A 后续债务（不在本轮实施）

- P4-4B1 已建立冻结赛果到 lambda 的最简基准，rho 仍固定零而非估计。真实完整历史覆盖、模型准确率与时间拆分验证仍未完成，不能用默认 lambda 补缺失。
- score-math-v1 每侧最多 30 球；如 lambda=8，尾部容差不能满足就显式失败。P4-4B1 转为 OUT_OF_RANGE 并保留原 lambda；更大范围必须评估后升级算法版本，不能静默截断。
- 归一化矩阵只保留有界支持，联合遗漏质量上界至多 2e-12；该数值误差控制不是足球模型准确率。版本代码、Python/Decimal 运行工件与依赖锁仍需纳入发布归档。
- 亚洲盘结算、竞彩比分“其他”选项映射、正式 Prediction Snapshot/API 与推荐仍未实施，需分别明确范围和授权。
- 扩展 Ruff 到整个 migrations 目录发现 6 个既有问题（env.py、005、观察迁移及初始迁移的 import 排序/未使用/重复导入）。标准 `ruff check apps/api/src tests` 通过；本轮遵循不修改旧迁移的约束，未修这些历史 lint。

## P4-4B1 后续债务（不在本轮实施）

- goals-baseline-v1 已实现最近 20 场 / 最少 5 场 / 等权 / 无 prior 的赛果基准，已人工复核。当前只有体彩池历史，不保证球队完整赛程；有效样本不足必须保持 INSUFFICIENT_DATA。
- 多来源同比分仅计一次，冲突整场排除；无效同 ID 证据也保守排除整场。一致比分的来源采用最早 finished_at 排序。正式 Result Resolution、历史覆盖校验、来源终场时间一致性仍待独立设计，不能静默改变 v1。
- P4-4C 已补充概率质量指标、Calibration/ECE 和纯时间划分契约；真实历史的按时间拆分回测与发布工件归档尚未实施。没有证明此基准能胜过 Market；不能称为最终真实比赛预测。
- xG、Elo、自动 rho 拟合、ML、概率校准拟合、Ensemble、Model Snapshot、预测 API 与推荐保持未实施；后续任何样本/权重/公式/精度/rho 变化须升级版本并另行授权。

## P4-4C 后续债务（不在本轮实施）

- evaluation-v1 只验证评估数学，FROZEN_SAMPLE_SET 不认证真实数据来源或历史无泄漏。需真实、足量、赛果明确且严格时间语义的样本才能判断 Goals Baseline 与 Market 的表现，不能输出优胜结论。
- eligible 样本群及分母由上游明确提供；真实缺预测原因、各模型相同样本群的 coverage 与来源质量仍需数据管道设计。本轮只有纯 adapter，未建 evaluation_runs/model_registry/prediction_snapshots 表或公开 API。
- 未来三赛季研究须单独设计 RESEARCH_REPLAY / historical_research_dataset，与 LIVE_AS_OBSERVED 严格区分；不得用 provider published_at 回填 analysis_visibility，不得让今天导入的旧历史冒充当时 live-visible Feature。
- 时间拆分只按显式 UTC 比赛时间分组，没有训练、历史回放、置信区间、显著性检验或校准器拟合。固定 10 桶的 ECE 依赖样本量，不能包装成 confidence score。
- Research Replay、xG、Elo、主客场增强、时间衰减、rho 拟合、ML、Ensemble、Recommendation 与 ROI/EV 等等待另行授权；本轮完成后停止。

## 已关闭的本机待办（2026-09-30 后续）

- 数据库原子认证限流：账号与客户端来源双维度，注册/登录/刷新独立预算，跨进程共享；并发配额和过期恢复通过 SQLite/PG 测试。
- PostgreSQL 演示数据备份恢复：同一导出快照核对 21 表、60 约束、6 触发器，Raw 内容哈希复核通过；12 次不可变表 UPDATE/DELETE 均被拒绝。
- 本地只读预检脚本：明确返回 PASS / BLOCKED / UNVERIFIED，缺少 Docker/Redis 和真实源时不输出全部 Gate 已通过。

备份演练仅覆盖本机小数据集和数据库对象，不代表生产异机灾备、持续归档、角色/权限恢复和大数据量 RTO/RPO 已验收。
