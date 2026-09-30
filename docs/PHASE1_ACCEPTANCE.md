# Phase 1 验收记录

本文件只记录实际检查，不以代码存在代替服务运行验收。

## 最终结论（2026-09-30）

**工程实现和 Mock→真实 PostgreSQL→API→前端演示已完成；全部 Definition of Done 尚未满足，不宣称第一阶段正式验收通过。** Task 8 的线上数据验收以及 Gate 1/2、Gate 3/4 的真实数据部分仍受外部条件阻塞。没有开发 AI 分析、推荐、下注、滚球或资金功能。

2026-09-30 后续：用户确认暂无真实源凭据，先推进本机可验证项。已补充认证限流、迁移 006、本地预检与 PostgreSQL 备份恢复演练，详见 [本机验收增量](LOCAL_VALIDATION.md)。外部阻塞 Gate 状态不变。

## 1. 当前架构

React 19 + TypeScript + Vite + Ant Design + TanStack Query + Router + ECharts；FastAPI + Pydantic 2 + SQLAlchemy 2 + Alembic；PostgreSQL、Redis 与 APScheduler。模块位于单 Python 包，Adapter/采集/实体/赔率/任务边界明确。完整结构见 [ARCHITECTURE](ARCHITECTURE.md)。

## 2. 数据库 ER

球队/联赛 UUID 通过 Provider 身份表关联；体彩 matches 是主池，外部 provider_matches 通过 match_mapping 绑定。Raw 关联比赛版本、报价和观察；固定标签引用报价；审计记录映射版本。认证表管理用户、刷新令牌和可撤销会话。详见含 Mermaid ER 图的 [DATA_MODEL](DATA_MODEL.md)。

## 3–4. Gate 状态

| Gate | 结果 | 实际证据或未满足项 |
| --- | --- | --- |
| 1 Docker 四服务 | 未完成 | Compose 与健康依赖已提供；本机没有 Docker Engine，Redis 实例也未运行 |
| 2 当日真实体彩池 | 未完成 | 公开接口返回 HTTP 567；演示 3 场不是实际开售比赛 |
| 3 五玩法 | Mock 验证通过；真实待验收 | 一场演示比赛五类均有数据；支持 available=false；真实响应尚未取得 |
| 4 海外完整链路 | Mock+PG 验证通过；真实待验收 | 四家 Mock→映射→赔率→实际 PostgreSQL→API→UI 已通；The Odds API 无密钥，未实调 |
| 5 四家 Mock | 通过 | Pinnacle、Bet365、Macau、WilliamHill Adapter 与 fixture 全链路 |
| 6 保留变化历史 | 通过 | 报价变更追加、同价幂等、观察留痕，PG UPDATE/DELETE 触发器拒绝修改 |
| 7 曲线 | 通过（演示数据） | ECharts 展示分市场、选项与盘口的历史，图例可控制公司显示 |
| 8 自动与审核 | 通过（fixture 集） | 显式身份映射后评分；低置信/歧义 REVIEW，无可靠身份 UNMATCHED；真实样本准确率未评估 |
| 9 状态可见 | 通过 | 质量中心显示 MATCHED 8、REVIEW 4、UNMATCHED 4；主池仍 3 场 |
| 10 测试 | 通过（现有自动测试） | 后续增至 56 项，分别在 SQLite / PostgreSQL 通过；前端 1 项通过；没有跳过失败用例 |

不以 Gate 10 的单元/集成测试通过替代尚未运行的 Docker、真实 Redis 和供应商线上验收。

## 5. 数据源实际情况

体彩 Adapter 依据可访问的官方 HTML/JS 编写，数据 API HTTP 567；未绕过验证，也未取得真实当日响应。The Odds API v4 Adapter 包含实时/历史契约测试，尚无账号凭据，真实公司覆盖和历史权限未知。四家 fixture 是明确 mock=true 的合成数据，不是四家专有接口返回。详细字段与官方来源链接见 [PROVIDERS](PROVIDERS.md)。

## 6. 发现并处理的问题

- 同价去重会丢失最后观察时间：引入不可变 observation，固定标签另存 observed_at。
- 晚到旧赔率可能覆盖“当前”：按有效时间选择最新，同时限制四个可见时间。
- 开球变更与错误重绑可能污染当前报价：映射失效进入 REVIEW，按不可变审计和映射版本过滤；历史 cutoff 仍可还原原状态。
- 任务重叠可能永久停在 QUEUED：冲突任务记录 SKIPPED/BUSY，异常和重启中断均可追踪。
- 源结构、异常价格、超时、500、空响应和 429：Raw 先保存，验证失败回滚业务，有限退避/冷却，不静默吞错。
- 官方列表缺席语义、真实字段稳定性和数据覆盖仍需真实样本核验，不根据猜测删除或补造赛事。

## 7. 技术债

缺少真实 Redis/Compose 演练、Python 跨平台依赖锁、邮件验证/找回、千万行压测、完整浏览器自动回归和生产异机灾备演练。前端构建有大 chunk 提示，Starlette TestClient 有一条 httpx 弃用警告；均保留记录，没有用关闭告警掩盖。基础认证限流与本机备份恢复已补齐。完整列表见 [BACKLOG](BACKLOG.md)。

## 8. 下一阶段前建议

先补齐 Docker/Redis 和有效数据源凭据，完成真实当日池与至少一家海外数据贯通，再做连续采集与人工核验、时间泄漏检查、故障恢复和容量基准。全部数据 Gate 关闭后再讨论后续分析；当前等待下一阶段明确指令。

## 可复验记录

- Windows / Python 3.12.10 / Node 24.18 / 便携 PostgreSQL 17.11。
- `pytest -q`：50 passed；同一套测试在独立 PostgreSQL 测试库：50 passed，迁移逐次 upgrade / downgrade。
- Ruff 通过；mypy 26 源文件通过；Alembic upgrade/check 通过，无模型差异。
- Vitest 1 passed；TypeScript + Vite production build 通过；npm production audit 为 0 条漏洞（不代表整体安全审计）。
- 实际演示 PG：3 matches、16 mappings、206 odds_snapshots。四家海外各有前后两组价格；阿森纳演示详情载入 109 条历史。
- 浏览器验收：首页、比赛详情、五玩法标签、公司报价、ECharts；控制台未见 error/warn。当前默认窄视口采用可滚动表格，未声明全尺寸或全浏览器覆盖。
- `/health` 200；`/ready` 503，明确 `postgres=true, redis=false`；没有把它改成虚假健康。
- 本地预览 http://127.0.0.1:5173；管理凭据仅在未跟踪的 `.env`。未发布公网，未创建 PR。

## 逐任务实施记录

环境：Windows / Python 3.12.10 / Node 24.18；初始未安装 Docker。
Task 0：pytest 1 通过、mypy 通过、前端 production build 通过。该任务尚无 Schema，Migration 检查不适用。
完整 Gate 清单见上方 Task 14 最终结果。

Task 1：Migration upgrade + check 通过；pytest 2 通过；mypy / TypeScript 通过。
已添加数据库级 append-only 保护（PostgreSQL 和 SQLite），生产运行检查仍独立验收。

Task 2：11 项测试通过；mypy / TypeScript / Alembic check 通过。真实接口 HTTP 567，未取得有效响应。
Task 3：建立今日比赛分页 API 与首页、来源状态、Mock 环境提示、明确空态与错误态。
检查：12 项测试通过、mypy、前端构建和 Alembic check 通过。

Task 4：实现 UUID 实体、身份注册、别名、评分、歧义处理、映射失效审计。
检查：14 项测试、mypy、TypeScript、Alembic check 通过。

Task 5：人工审核 UI/API、角色鉴权、注册登录、轮换刷新令牌、退出撤销会话。
检查：15 项测试通过，前端构建 / 类型检查 / Alembic check 通过。登录令牌只保存在浏览器内存，刷新页面需重新登录。

Task 6：统一 OddsProvider ABC、数据契约、Decimal 赔率与四分之一盘口解析、时区校验。
检查：28 项测试、mypy、TypeScript、Alembic check 通过。

Task 7：四家 Mock Adapter、体彩演示源、显式 ID fixture、三种映射结果与可重复 bootstrap。
检查：29 项测试、mypy、TypeScript、Alembic check 通过。

Task 8：The Odds API v4 Adapter 和文档契约测试已实现；真实密钥缺失，线上贯通待验收。继续其余可独立验证任务。
检查：31 项测试、mypy、TypeScript、Alembic check 通过。

Task 9：只追加赔率与观察记录、幂等批量写入、latest 查询、可见时刻 cutoff、固定快照标签、历史 API。
检查：33 项测试通过；Migration upgrade / check、mypy、TypeScript 通过。

Task 10：动态采样、跨进程 Redis 限流和任务锁、有限重试、429 冷却、APScheduler 生命周期。
检查：43 项测试通过；mypy、TypeScript、Alembic check 通过。Redis 实际服务验证在 Task 14 单列。

Task 11：详情页、体彩五玩法、公司报价、初始/当前/历史、ECharts 分市场/选项/盘口曲线、公司图例切换。
检查：43 项后端测试、1 项前端测试、生产构建、mypy 与 Alembic check 通过。

Task 12：数据质量、Provider 管理、同步任务及 Raw 查看、用户权限、审计日志 UI/API。
检查：完整后台 API 集成测试、前端构建、类型和迁移检查通过。

Task 13：补齐失败重试、回填 cutoff、映射失效、并发冲突、固定标签观察时间测试，维护全部要求文档、ER、四项 ADR、运维和技术债。

Task 14：SQLite 与 PostgreSQL 各 50 项、前端 1 项、Ruff/mypy/build、Alembic check 和浏览器演示复验通过；阻塞 Gate 明确保留未完成。
