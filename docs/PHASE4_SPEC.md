# Phase 4 — Prediction & Recommendation Engine

本轮只交付 P4-0、P4-1、P4-2。没有 CORE/WATCH/PASS、EV、串关、LLM、自动投注或最终预测模型；没有真实赛果/统计 Provider 线上验收声明。

## 先行架构审查

Phase 0–3 保持原样：体彩开售主池、Adapter、独立 Raw 事务、UUID 实体解析、赔率及观察 append-only、UTC、PostgreSQL 基准均保留。

发现的边界：现有 Odds 查询约束报价四个时间，但未同时约束关联 Raw；比赛当前行可变；Provider/Team 当前状态也不代表过去；created_at 是 INSERT 时间，不是 COMMIT 时间。因此不能直接把现有展示 API 当作 Feature 输入。

采用独立 analysis 读取边界，不改旧赔率语义。新增 analysis_visibility：独立连接读取已提交的不可变输入后，记录系统确认其可见的时间。仅有 created_at 而没有这项证明的旧数据，不能用于早于证明时间的 Feature；绝不按旧 effective_at 回填证明。这是保守缺失，不是追补历史事实。

## 数据和采集契约

Migration `007_feature_foundation`，前置 `006_auth_rate_buckets`，新增四表：

| 表 | 内容 / 唯一性 |
| --- | --- |
| match_results | 比分、半场、首球；同比赛/来源/Raw/比赛版本/映射绑定版本的 dedup_key 唯一 |
| team_match_stats | 球队 UUID、xg/xga、射门/射正、控球百分比、角球/红牌；同比赛/球队/来源/Raw/比赛版本/映射绑定版本的 dedup_key 唯一 |
| feature_snapshots | cutoff、feature_version、JSONB/JSON 内容、质量分、mock、created_at；同比赛/cutoff/版本唯一 |
| analysis_visibility | 不可变输入表名/UUID 复合主键、visible_at；确认已提交输入可见的保守时间 |

四表均有 PostgreSQL 和 SQLite UPDATE/DELETE 拒绝触发器。新迁移通过固定的 migrations/immutability.py 复用 002 的 PostgreSQL reject_immutable_change 函数；不改历史迁移，不依赖 ORM 自动重建历史 Schema。

赛后两表还保存 finished_at、observed_at、created_at、published_at/effective_at（未知 NULL）、raw_payload_id、match_version_id、mapping_id/version、source、mock。整数必须非负；射正不超过射门；控球 0–100；小数拒绝 NaN/无穷；半场比分不超过全场；首球 NONE 仅表示来源明确无进球，未知必须 NULL。REGULATION 指常规时间（含补时，不含加时/点球大战）；首球分钟采用来源明确的整数分钟，不推测缺失补时。

Provider 扩展可选 fetch_results，默认 RESULTS_UNSUPPORTED。NormalizedBatch 增加 results/team_stats，Provider 只规范化；IngestionService 独立事务保存 Raw，再 normalize/validate/store，失败保留 Raw，整批业务回滚。FINAL/REGULATION、明确 finished_at 是 V1 必需条件，不推算终场时间。

外部比赛必须已有确认映射；未映射留在 Raw，不建主池。球队必须通过 provider ID → UUID 明确注册并属于该比赛版本；不靠名字猜。后续修正使用新的 Raw 追加，重复处理同一 Raw 幂等。

MockSportteryProvider 只在显式 results 操作读取 tests/fixtures/post_match.json，标识 mock=true，不注册自动赛后任务，不改变 seed_demo，不宣称体彩已提供 xG 或取得真实线上赛果。真实 Adapter 默认不支持赛后数据。生产拒绝 Mock，数据库和 API 模式隔离。

## Feature V1

代码位于 analysis/__init__.py、contracts.py、features.py、visibility.py。只保留实际使用模块。

```json
{
  "market": {"quotes": []},
  "odds_movement": {"items": []},
  "team_strength": {"rating": null, "past_results": [], "past_stats": []},
  "schedule": {"kickoff_at": "来自当时比赛版本", "seconds_to_kickoff": "按cutoff计算", "rest_days": null},
  "squad": {"available": false, "players": null},
  "context": {"mock": true, "match_version_id": "UUID", "raw_payload_id": "UUID", "match": {}, "evidence": null},
  "data_quality": {"algorithm": "availability-v1", "checks": {}, "score": 0}
}
```

以上是结构示意，不是实际数据。空数组表示没有可见记录，NULL 表示未知或未实现；不能用 0 冒充 xG/休息天数/强度。过去赛后记录按来源保留，不跨源平均、不自动选择“可信公司”；不是最终球队强度模型。

报价按供应商有效时间（缺失则采集时间）、采集、创建、UUID 依次降序，保留完整序列（含盘口及映射版本）的最新与前一条。变化由 Decimal 算出，缺少前价时变化为 NULL；不依赖现时、随机数或 LLM。最新观察用于新鲜度，但必须自身及关联 Raw 均可见。

过去赛后数据只取目标两队已结束的其他体彩池比赛，同比赛/来源/球队按观察、创建、UUID 选择最新修正；finished_at 必须早于 cutoff 和目标开球。绑定比赛版本也必须可见，球队和开球与当时最新版本一致；同事实的重复赛程版本不会抹掉赛后统计。目标自身结果永远不能进入其输入。

## 可见性与重建

所有 Raw、比赛版本、报价、观察、赛果、统计、映射审计均需不可变提交可见性凭据。业务的 collected_at/observed_at、created_at、已知 published_at/effective_at 及其 Raw 四时间须 <= cutoff；没有凭据则不可用。比赛信息不从 matches 的当前内容、Team 当前名称、ProviderState 当前健康状态读取。当前只从可见 AuditLog 恢复映射证据，不读取尚未建立的新闻或阵容证据。

analysis_visibility 在 ORM commit 后由独立连接读取已提交输入，再采样 UTC 时钟，使用唯一键追加；独立 Core 写入和旧数据在 Feature 构建前补做确认，但时间只能是现在。构建前同步确认还会等待并发凭据唯一键冲突完成，避免读到半完成的可见性记录。系统时钟必须同步；管理者不能伪造过去的可见性凭据。

因此后补的旧事件、延迟解析、晚提交事务、未来赔率/统计/Raw、未来映射审核和后续比赛改期都不能回流到过去 Feature。已保存快照也由数据库禁止更改；缓存外重建测试验证输入筛选本身。没有当时比赛版本/凭据时返回 404，不拿当前状态补造历史。

老数据库迁移后，在首次后续提交或 Feature 请求前没有可见性凭据。早于首次确认的历史 Feature 不可恢复；这是发现既有 COMMIT 时间缺口后的安全边界。已有 Phase 0–3 历史记录和展示 API 不变。

## API

`GET /api/v1/matches/{UUID}/features?analysis_cutoff=2026-10-01T00:00:00Z`

使用现有 success/data/request_id 信封，data 返回 feature_snapshot_id、match_id、UTC analysis_cutoff、feature_version、七组 feature_data、0–100 data_quality_score。cutoff 必填；无时区/未来/达到或超过当时开球时间返回 422；不存在、模式不符、当时无可见比赛返回 404。

GET 首次物化持久化快照；同一 UUID + UTC cutoff + p4-features-v1 重复/并发请求返回同一行，不 UPDATE。不接受客户端自定义 feature_version。Decimal 保持字符串；创建时间和 id 不参与特征计算。V1 规则变化必须升级版本，未来预测另行绑定 model_version，本轮没有模型版本占位值。

## Data Quality V1

固定 `score = 20 × 通过检查的数量`，五项等权，不使用臆造权重或 LLM；缺失/未知检查不得分。

| 检查 | 得 20 分的条件 |
| --- | --- |
| match_data_available | 可见比赛版本包含 kickoff、两队 UUID、competition UUID、sell_status |
| sporttery_odds_available | 至少一条通过全部时间约束的体彩报价 |
| external_odds_coverage | 至少一个外部 provider 有可见且确认绑定的报价；另外输出实际 provider 列表/数量，不虚构预期覆盖分母 |
| entity_mapping_quality | 两队 UUID 已知，且存在通过当时确认映射与版本检查的外部报价；其余 UNKNOWN。输出审计证据 id |
| source_freshness | 至少有报价，且比赛采集及每个最新报价的最后可见观察（无观察用报价采集）的年龄均在 0–3600 秒 |

年龄基于 cutoff 而非请求当前时间；观察新鲜不等于供应商有效时间新鲜，后者在报价字段中独立公开。source_age_seconds、阈值和检查结果随快照保存。该分数只衡量 V1 输入可用性；不能证明来源真伪、数据正确率、模型置信度、全部市场完整或推荐可用。即使 100 分，阵容/新闻/强度仍可缺失。

## 验证范围

tests/test_features.py 覆盖创建和并发幂等、直接重建确定性、赔率与 Raw 的各时间约束、回填/晚解析/跨 cutoff 提交、无凭据旧数据、改期与当前名称、映射确认/撤销/换版本、观察新鲜度、赛后修正和目标标签隔离、缺失/降分、API 时间/模式、四表 UPDATE/DELETE、upgrade/check/downgrade 不损坏旧历史。

tests/test_results.py 覆盖 Raw-first、幂等重放/追加纠错、无部分落库、无效值、终场时间、球队身份、未映射不扩池、真实 Adapter 不支持、生产拒绝 Mock。相同测试套件在 SQLite 和独立 PostgreSQL `_test` 库运行，结果见本文件末尾。

## 已知限制

- 首次确认以前的旧数据无法证明提交可见时间，不能恢复对应历史 Feature；不回填虚假时间。
- 可见性收集 V1 按七张不可变表执行反连接检查，每次 ORM 提交触发；尚未做大数据量/高并发基准。后续可在保持独立提交确认和幂等语义下用待确认 ID 批次优化。
- V1 读取可见比赛版本和映射审计，过去统计还逐条校验版本；尚未提供有界赛季窗口/大表性能优化。生产扩容前需 EXPLAIN/压测。
- 真实赛果/统计来源、新闻/阵容来源、模型、模型注册/回测产品均未实现或验收。比分冲突按来源分别保留，未做跨源裁决。
- 时间同步、受限数据库角色、依赖锁及工件归档属于上线要求；超级用户绕过触发器不属于应用保证范围。
- Phase 1 的真实数据、Docker/Redis 阻塞仍存在。P4-3 未实施。

## 实测结果（2026-10-01，北京时间）

| 项目 | 结果 |
| --- | --- |
| SQLite 全量 pytest | 118 passed，42.80 秒；原 56 项 + 新增 62 项 |
| PostgreSQL 全量 pytest | 独立空库 jc_phase4_test：118 passed，49.15 秒；每个数据库用例 upgrade/head、结束 downgrade/base |
| 迁移往返 | 两种数据库均验证 007 → 006 → head，旧比赛/不可变保护保留 |
| Ruff | apps/api/src、tests、新迁移及触发器 helper 均通过 |
| mypy | 32 个源文件通过 |
| Alembic check | SQLite / PostgreSQL 测试内及本机演示 PostgreSQL 均通过，No new upgrade operations detected |
| 本机数据库升级 | jc_demo_pg 已到 007_feature_foundation；不可变触发器由 6 增至 10 |
| 原数据保留 | 对 Raw、match_versions、odds_snapshots、odds_observations、odds_key_snapshots、audit_logs、matches 做迁移前后行数及 SHA-256 核对，全部一致；保留 3 场及 206 条赔率 |
| 实际 HTTP | 重启原本机 API 后 Feature GET 200；同 cutoff 重复返回完全一致；无旧时可见性凭据返回 404；明确 mock=true |

两套 pytest 都保留现有一条 Starlette/httpx 弃用警告，没有跳过失败用例、没有关闭警告。未改前端，未执行新的前端构建；没有把 Mock/本机检查当作真实 Provider 或 Docker/Redis 验收。

本机明细输出（artifacts 被 Git 忽略）：phase4-postgres-tests.txt、phase4-local-migration.json、phase4-api-smoke.json。实际 API 演示快照质量分 40；未把缺失的海外映射/陈旧来源提升到满分。

## 本轮文件清单

修改 15 个已有文件：

- README.md
- docs/ARCHITECTURE.md
- docs/DATA_MODEL.md
- docs/PROVIDERS.md
- docs/CONSTITUTION.md
- docs/BACKLOG.md
- apps/api/src/jc/api.py
- apps/api/src/jc/db.py
- apps/api/src/jc/ingestion.py
- apps/api/src/jc/main.py
- apps/api/src/jc/models.py
- apps/api/src/jc/providers/base.py
- apps/api/src/jc/providers/contracts.py
- apps/api/src/jc/providers/mock.py
- tests/test_health.py

新增 15 个文件：

- docs/PHASE4_SPEC.md
- docs/DECISIONS/ADR-005-prediction-snapshot.md
- docs/DECISIONS/ADR-006-feature-cutoff.md
- docs/DECISIONS/ADR-007-model-versioning.md
- docs/DECISIONS/ADR-008-recommendation-gate.md
- apps/api/src/jc/analysis/__init__.py
- apps/api/src/jc/analysis/contracts.py
- apps/api/src/jc/analysis/features.py
- apps/api/src/jc/analysis/visibility.py
- apps/api/src/jc/results.py
- migrations/immutability.py
- migrations/versions/007_feature_foundation.py
- tests/fixtures/post_match.json
- tests/test_features.py
- tests/test_results.py

未修改旧 odds.py、jobs.py 或 001～006 Migration；既有赔率及任务语义保留。P4-3 及之后的工作未实施。
