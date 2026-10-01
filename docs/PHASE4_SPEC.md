# Phase 4 — Prediction & Recommendation Engine

已交付并人工复核 P4-0～P4-3、P4-4A Score Probability Mathematics、P4-4B1 Goals Baseline Lambda Estimator 与 P4-4C Model Evaluation Core；P4-4D1 Research Replay Semantics Core 主体已完成人工复核，P4-4D1.1 验收前正确性修复已实施，待本轮人工验收后冻结 v1。当前研究规范见文末，前文保留各历史阶段的规范与验收记录。没有 CORE/WATCH/PASS、EV、串关、LLM、自动投注或最终预测模型；没有真实赛果/统计 Provider 线上验收声明。

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
- Phase 1 的真实数据、Docker/Redis 阻塞仍存在，Market Baseline 不关闭这些 Gate。

## P4-0～P4-2 实测结果（2026-10-01，北京时间）

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

## P4-0～P4-2 历史文件清单

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

以上为 P4-0～P4-2 的历史交付记录，未修改旧 odds.py、jobs.py 或 001～006 Migration；既有赔率及任务语义保留。

## P4-3 Market Probability Engine

仅回答“市场当前如何定价”，建立 `P_market` 基准，不实施 P4-4 或任何预测、推荐、Edge、EV、串关、LLM、新闻搜索、自动投注功能。

数据流为 `Raw/Odds → 原 P4-2 FeatureSnapshot @ analysis_cutoff → market-v1 → MarketModelSnapshot`。纯计算 `analysis/market.py:build_market_data` 只接收冻结 FeatureData；持久化 `analysis/market_snapshots.py:get_or_create_market_snapshot` 只按 ID 读取一个 FeatureSnapshot、查找或追加 MarketSnapshot。创建时间、随机 UUID 只用于行身份，不参与 market_data。没有回查当前赔率/比赛/Provider，没有更新旧 Feature。

### 固定算法与数值规则

`MARKET_MODEL_VERSION="market-v1"`，`NORMALIZATION_METHOD="proportional-v1"`；API 不接受任意版本，服务拒绝未实现版本，当前只支持 p4-features-v1 输入。

```text
q_i = 1 / decimal_odds_i
overround = Σq_i
vig = overround - 1
no_vig_i = q_i / overround
```

使用独立 Decimal Context（50 位精度，ROUND_HALF_EVEN），拒绝 float 核心输入。计算后的概率、overround、vig、gap、变化以 24 位小数字符串编码；原始赔率保持 Feature 中的字符串。内部概率和误差必须 ≤1e-45，序列化后允许 ≤1e-23。不强制将最后一项改写为残差。

negative vig 原样保存，并标注 `NEGATIVE_OVERROUND`；overround 严格大于 1.20 标注 `HIGH_OVERROUND`。阈值随 market-v1 固定，只作诊断、不删除数据或改变等权。均值、中位数、总体标准差使用支持 Decimal 的 Python statistics 标准库。任何实质规则变更须新增版本并保留旧版本工件。

### 支持范围及完整性

| market_type | 完整选项 | line 规则 |
| --- | --- | --- |
| 1X2 | HOME/DRAW/AWAY | NULL |
| SPORTTERY_HAD | HOME/DRAW/AWAY | NULL，仅 provider=sporttery |
| ASIAN_HANDICAP | HOME/AWAY | HOME=line，AWAY=-line，按 canonical_home_line 配对 |
| TOTALS | OVER/UNDER | 同一非负 line |
| SPORTTERY_HHAD | HOME/DRAW/AWAY | 同一体彩让球 line，不翻转 AWAY |
| SPORTTERY_TTG | 0/1/2/3/4/5/6/7+ | NULL，八项全部存在 |

每个 provider + bookmaker + market_type + canonical_line 独立分组，每项恰好一条。缺项保留 `MISSING_SELECTION:...`，重复、额外选项、混合映射绑定、非法 odds/line 同样不能形成完整市场。缺项不从别家公司或别的玩法补齐，也不归一剩余选项；overround/vig/no-vig 为 NULL，逐项合法 raw implied 仍保留。

亚洲盘明确验证 `away_line == -home_line`。例如 HOME -0.5 和 AWAY +0.5 归入 -0.5；HOME -0.5 和 AWAY -0.5 分属两个不完整分组，输出 `HANDICAP_LINE_MISMATCH`。同时存在多个合法 canonical line 时分别计算。TOTALS 不同 line 也分开。二项盘口仅是价格去水；涉及走盘、半赢半输时不是完整结算概率。

亚洲盘与 HHAD 三项不互转；TOTALS 与 TTG 八项不互转。`SPORTTERY_CRS`、`SPORTTERY_HAFU`、`CORRECT_SCORE` 及未知市场标记 `unsupported_for_v1=true` / `UNSUPPORTED_FOR_V1`，原始赔率保留，不崩溃、不去水。

### 外部共识、体彩和变化

外部共识只取 `provider != sporttery && market_type == 1X2 && complete`。每个完整 `(provider, bookmaker)` source 先去水，再等权算 HOME/DRAW/AWAY 的 arithmetic mean（`external_consensus.p_market`）。保留来源列表和 source_count，逐项输出 mean/median/min/max/population_stddev；不造冲突分。无来源时统计和 p_market 为 NULL。体彩即使标为 1X2 也被排除。

跨 Provider 同名 bookmaker 不去重；可能重复覆盖同一真实公司，V1 不声称已经实体消歧。没有 sharp 权重，也不因 vig 异常改变权重。

`sporttery.HAD/HHAD/TTG` 是各自来源市场数组，缺失为 []。只有同时存在外部共识和唯一完整 Sporttery HAD 来源时，输出 `sporttery_external_gap[selection] = external_consensus.mean - sporttery_HAD.no_vig`；否则 NULL。多个完整 HAD 来源额外给出 `AMBIGUOUS_SPORTTERY_HAD`，不任意选择。字段不叫 Edge。

movement 按 Feature 冻结的 odds_movement.items 与 quote ID 关联，输出：

- odds_delta = current_odds - previous_odds。
- odds_pct_delta = odds_delta / previous_odds × 100，单位 percent。
- raw_implied_probability_delta = 1/current_odds - 1/previous_odds。

缺 previous 时三个字段均为 NULL，不补 0。每个 selection 的 previous 独立，不能推断同刻历史市场，因此没有 previous_market_probability 或 no-vig 历史变化。

### 持久化与 API

迁移 `008_market_probability` 新增 market_model_snapshots：UUID id/match_id/feature_snapshot_id、analysis_cutoff、market_model_version、normalization_method、JSONB market_data、mock、created_at。唯一键 `(feature_snapshot_id, market_model_version)`；复用 immutability helper 在 PostgreSQL/SQLite 拒绝 UPDATE/DELETE。INSERT ON CONFLICT DO NOTHING 后读回胜者，重复及并发请求幂等。Schema 详见 DATA_MODEL。

`GET /api/v1/matches/{match_id}/market-model?analysis_cutoff=<带时区时间>`

沿用 success/data/request_id 信封，data 返回 market_snapshot_id、feature_snapshot_id、match_id、UTC analysis_cutoff、market_model_version、normalization_method、market_data、mock。cutoff 必填；无时区、未来、达到/超过当时开球时刻为 422；当时没有已证明可见比赛、ID 不存在或 Mock/live 不符为 404。

API 先调用原有 get_or_create_snapshot，再传 Feature ID 给 Market 服务。首次 GET 可物化两张快照；已存在 Feature 直接复用。服务无当前 Match 查询，无未来数据补齐。P4-2 的 analysis_visibility 和读取规则保持；原有 ORM commit 后扫描仍是已知技术债。

### P4-3 验证

`tests/test_market_model.py` 覆盖 Decimal 及环境精度隔离、完整性、去水/共识/统计、跨公司与跨 Provider 身份、体彩排除与 gap、盘口规范化、TTG 完整性、异常与不支持市场、逐项变化、冻结输入不变、SQL 读取边界、幂等并发、API/cutoff/模式隔离、数据库不可变性、唯一性和 008↔007 迁移往返。P4-2 tests/test_features.py、test_odds.py、test_results.py 纳入全量回归。

实测结果（2026-10-01，北京时间）：

| 项目 | 结果 |
| --- | --- |
| SQLite 全量 pytest | 179 passed，74.91 秒；原 118 项 + 新增 Market 61 项 |
| PostgreSQL 全量 pytest | 独立 PostgreSQL 17 实例（127.0.0.1:55433）空库 jc_market_test：179 passed，74.33 秒 |
| 迁移及 Alembic check | 两种数据库均通过 008 → 007 → head，以及全链 upgrade/head；PG 每个数据库用例结束 downgrade/base；迁移用例内 command.check 通过，无 Schema 差异 |
| PostgreSQL 生产类型 | market_data=JSONB；唯一约束、FK、不可变触发器均通过集成测试 |
| Ruff | apps/api/src、tests、008 migration、immutability helper：通过 |
| mypy | 34 个源文件通过 |
| 前端回归 | npm run test：1 passed；npm run build：通过 |
| 数据边界 | SQL 监听测试确认 Market 服务只按键读 Feature / Market Snapshot；后续报价、比赛改期、Provider 状态变化不影响旧 Feature 的派生结果 |
| 旧底座 | features.py、visibility.py、odds.py、001～007 migrations 和原 Feature/Odds/Results 测试未修改，全部纳入回归 |

两套 pytest 均保留现有一条 Starlette/httpx 弃用警告；前端构建仍有大 chunk 提示。没有新增依赖，没有压制告警或跳过失败项。日志位于本机 artifacts/market-sqlite-tests.txt 和 artifacts/market-postgres-tests.txt（Git 忽略）。

本机原 55432 演示实例进程存在但连接无响应；本轮未重启、未迁移演示库，也未宣称运行中的演示 API 已部署 008。为完成真实 PostgreSQL 测试，使用已有程序创建独立测试实例；完成后停止该实例，保留日志。上线/本机演示应用新接口前仍须在目标库执行 `alembic upgrade head` 并加载新 API 代码。

P4-3 文件清单（14 个）：修改 README.md、analysis/contracts.py、api.py、models.py、docs/ARCHITECTURE.md、BACKLOG.md、CONSTITUTION.md、DATA_MODEL.md、PHASE4_SPEC.md；新增 analysis/market.py、analysis/market_snapshots.py、migrations/versions/008_market_probability.py、tests/test_market_model.py、docs/DECISIONS/ADR-009-market-probability-baseline.md。Python 源码相对根均为 apps/api/src/jc。

真实 Provider、Docker/Redis 验收仍未完成。下一阶段只建议先评审本阶段和真实数据 Gate，再单独授权 P4-4；本轮没有实施 P4-4。

## P4-4A Score Probability Mathematics

P4-3 经人工复核后，本阶段实现 `analysis/score_matrix.py`，唯一目标是把显式、正确的进球参数稳定转换为同一概率空间中的比分和各玩法分布。**当前仍不能产生真实比赛预测**：lambda_home、lambda_away、rho 的真实估计来源均未建立；没有默认参数、球队强度模型、训练或上游数据读取。

引擎为纯函数，仅依赖标准库，不访问数据库、Feature/Odds/Market Snapshot、网络、当前时间、随机数或 LLM。没有新表、Migration、公开预测 API 或前端页面。现有 Raw-first、体彩主比赛池、append-only、FeatureSnapshot 边界、analysis_cutoff、analysis_visibility 与 Market 不回查当前 Odds 的规则保持。

### 调用和结果

```python
from decimal import Decimal
from jc.analysis.score_matrix import build_score_matrix, three_way_handicap, top_scores

# 仅为可人工核验的数学 Golden Case，不代表任何比赛或默认模型参数。
result = build_score_matrix(
    lambda_home=Decimal("2"),
    lambda_away=Decimal("1"),
    rho=Decimal("0"),
    lines=[-2, -1, 0, 1, 2],
)
assert three_way_handicap(result["matrix"], 0) == result["one_x_two"]
display_scores = top_scores(result, 3)
```

三项参数均为必填有限 Decimal，lambda≥0；不自动转换字符串、整数或 float。lines 可省略，仅接受 Python int（不含 bool）；先去重再数值升序，原对象不变。相同输入、任意关键词及 lines 顺序、外部 Decimal Context 下输出一致。

`ScoreMatrixResult` 的矩阵为 `matrix[home_goals][away_goals]` 二维数组，完整保留动态范围内的格子和零概率。输出包括 engine_version、三项参数、max_home_goals/max_away_goals、tail_upper_bound、pre_normalization_mass、normalization_factor、matrix、one_x_two、total_goals、sporttery_ttg、handicap。除进球范围整数外，参数、概率和数值元数据均为 Decimal 字符串，无 float；完整字段定义见 [ADR-010](DECISIONS/ADR-010-score-probability-math.md)。

### 固定数学规则

| 规则 | score-math-v1 |
| --- | --- |
| 精度 | 矩阵/归一化/聚合 50 位有效数字，ROUND_HALF_EVEN，独立 Context；tau 符号验证保留输入乘积系数所需额外精度 |
| Poisson | p0=Decimal.exp(-lambda)，p(k+1)=p(k)×lambda/(k+1) |
| 动态范围 | 两侧独立扩展，至少保留 0、1 球；每侧保守尾部界≤1e-12；最大 30 球 |
| 尾部上界 | p(K+1)/(1-lambda/(K+2))+1e-45，要求 lambda<K+2；零 lambda 精确为 0；联合界为两侧界之和，至多 2e-12 |
| 超限 | cap 内无法满足容差抛 TailToleranceError，禁止静默截断；如 lambda=8 失败 |
| Dixon–Coles | tau00=1-h×a×rho，tau01=1+h×rho，tau10=1+a×rho，tau11=1-rho，其他为 1 |
| rho | 必须显式给出，rho=0 为独立 Poisson；任何负 tau 拒绝，tau=0 合法，不修改 rho |
| 归一化 | 记录 DC 后有限矩阵质量 M，每格统一乘 1/M；没有残差桶；和误差≤1e-45 |
| 编码 | 直接 str(Decimal)，保留全部计算精度，可含科学计数法，不强制小数位数 |
| 版本变化 | Poisson、DC、截断、归一化、精度/容差或映射变化必须升级 SCORE_ENGINE_VERSION |

至少保留整个 DC 四格块，使修正质量 -c/+c/+c/-c 相互抵消，避免很小 lambda 过早截断造成不一致。50 位 Context 外的极端数值范围失败显式暴露，不生成伪造分布。

1X2 复用 `three_way_handicap(matrix,0)`；HHAD 按 `home_goals+line` 与 away_goals 比较后求和，HHAD(0) 与 1X2 严格一致。total_goals 按 i+j 聚合到 0～max_home_goals+max_away_goals；TTG 0～6 按对应格求和，7+ 实际累加 i+j≥7 的所有矩阵格。各分布均源自归一化矩阵，总和在 Decimal 容差内为 1。top_scores 只排序展示，顺序为概率降序、主进球升序、客进球升序。

本阶段不处理亚洲盘结算（quarter line/push/half win/half loss）、竞彩比分 HOME_OTHER/DRAW_OTHER/AWAY_OTHER，不输出 P_model/P_final、confidence、推荐、Edge 或 EV，也不保存任意 lambda 为正式预测。真实参数来源、时间拆分验证方案与缺失处理待数学层复核后的 P4-4B，当前停止于 P4-4A。

### P4-4A 验证

新增 `tests/test_score_matrix.py`，覆盖 33 项要求及高精度 tau 边界：Poisson P0/递推/直接 factorial Golden Cases、尾部界、动态范围与 cap、非法输入、零/单侧零 lambda、独立 Poisson 和四格 DC、归一化元数据、对称性、1X2/TTG/HHAD 一致性、Top Score 排序、Context 隔离、输入不变、确定性和无 float JSON 输出。

Golden Cases 使用 lambda=(1,1)/(2,1)、rho=0，独立 80 位 Decimal + factorial 公式核验明确比分概率，并分别检查归一化因子与有限矩阵尾部误差。没有 Monte Carlo 或生产随机模拟。

最终实测结果（2026-10-01，北京时间）：

| 项目 | 结果 |
| --- | --- |
| 新增数学测试 | 84 项通过；原 179 项 + 新增 84 项 = 263 项 |
| SQLite 全量 pytest | 263 passed，71.13 秒 |
| PostgreSQL 全量 pytest | PostgreSQL 17.11，独立 127.0.0.1:55433 空库 jc_score_test：263 passed，75.44 秒 |
| 旧模块回归 | test_features.py / test_market_model.py / test_odds.py / test_results.py 全部纳入两套全量测试，原测试未修改 |
| 生产 Schema | 全量集成测试中的 upgrade/check/downgrade 通过；没有新增表或 Migration，未修改旧 001～008 |
| Ruff | 标准 apps/api/src、tests 范围通过；新文件 format --check 通过 |
| 扩展历史 lint | 额外对 migrations 检查发现 6 个既有问题，记录 BACKLOG；未改旧迁移或压制规则 |
| mypy | 35 个源文件通过 |
| 前端 | 源码/API 均未修改；本轮未重跑前端 test/build，没有接入预测展示 |

两套 pytest 均保留原有 1 条 Starlette/httpx 弃用警告，无失败、无跳过。日志在本机 `artifacts/score-sqlite-tests.txt`、`artifacts/score-postgres-tests.txt`（Git 忽略）。使用已有独立测试实例和新空测试库完成 PG 验证，完成后已正常停止该测试实例；没有修改或迁移演示业务库。真实数据源、Docker/Redis、依赖锁、可见性扫描性能等既有技术债不因此关闭。

本轮文件清单共 8 个：新增 `apps/api/src/jc/analysis/score_matrix.py`、`tests/test_score_matrix.py`、`docs/DECISIONS/ADR-010-score-probability-math.md`；修改 `docs/PHASE4_SPEC.md`、`docs/ARCHITECTURE.md`、`docs/BACKLOG.md`，并同步 `README.md`、`docs/CONSTITUTION.md` 的当前阶段声明。没有新建 score_contracts.py 或其他空模块。

P4-4B 建议先评审冻结 Feature 的真实历史覆盖、参数来源与缺失规则，再定义球队强度/λ/rho 的可复现估计和按时间拆分验证。当前没有实施 P4-4B，等待数学层人工复核。

## P4-4B1 Goals Baseline Lambda Estimator

P4-4A 经人工复核后，本阶段新增 `analysis/goals_baseline.py`。纯函数 `estimate_goals_baseline(feature: FeatureData)` 仅消费 Frozen FeatureSnapshot 内的 `context.match` 两队 ID 和 `team_strength.past_results`，不回查任何数据库、Provider、网络或当前时间，也不读取赔率、odds_movement、past_stats/xG。原 Feature 构建器继续承担截止时刻、可见性与目标赛果隔离，不改 p4-features-v1。

| 规则 | goals-baseline-v1 |
| --- | --- |
| 去重 | match_id 合并；相同比分计一场，记录不同 source 数量；冲突整场排除，保留 CONFLICTING_RESULT_SOURCES 和 excluded_match_ids |
| 无效记录 | 缺 ID/来源、负数或非整数比分、球队归属错误、无效时间拒绝；有 match_id 时保守排除整场，INVALID_RESULT_RECORD |
| 排序 | 一致来源取最早 finished_at（UTC），按时间降序、match_id 升序；不依赖数组/字典/source 顺序 |
| 窗口 | 去重/排除后每队分别最近 20 场，最少 5 场；相互交锋两队各计一次，无额外天数限制 |
| 权重 | 等权；按历史实际主/客身份计算 GF/GA，不做主客场修正、时间衰减、联赛 prior 或 shrinkage |
| 进失球率 | GF_rate=总进球/场数，GA_rate=总失球/场数 |
| lambda | home=(home GF+away GA)/2；away=(away GF+home GA)/2 |
| rho | 字符串 0，rho_source=fixed-zero-v1；独立 Poisson，没有拟合 rho |
| 数值 | 独立 50 位 Decimal Context、ROUND_HALF_EVEN；无 float、无默认 lambda |
| 样本不足 | 任一队不足 5 场、目标 ID 缺失或同队对同队：INSUFFICIENT_DATA，两个 lambda 与 score=NULL，不调用引擎 |
| 超出引擎范围 | TailToleranceError → OUT_OF_RANGE / SCORE_ENGINE_RANGE_EXCEEDED；保留原 lambda，score=NULL，不 clamp 或调整引擎 |
| 输出 | JSON-ready Result，含 version、score_engine_version、两队历史场数/率/入选 ID/来源数、lambda、rho、score、稳定排序诊断及排除 ID |

合格输入调用原 `build_score_matrix(lambda_home, lambda_away, Decimal("0"))`；1X2/总进球/TTG 完全源自返回矩阵。没有从赔率读取 HHAD lines，handicap 为空。所有规则及数值精度随 GOALS_BASELINE_VERSION 固定，变化需升级版本；详细契约见 [ADR-011](DECISIONS/ADR-011-goals-baseline-lambda.md)。

Golden Case 使用指定的两队 5 场进失球序列，历史主客场交错：Home 率 (2,1)、Away 率 (1,2)，lambda=(2,1)、rho=0，比分结果严格等于直接调用 score-math-v1(2,1,0)。输入字段访问守卫及冻结快照集成测试验证赔率/xG不被读取、目标结果隔离，以及数据库后续变化不会改变旧输入的结果。

**不能称为最终真实比赛预测。** 当前仅得到 Goals-only Football Baseline，用作后续模型必须击败的比较基准；没有真实全量球队历史与时间拆分回测验收。没有新增持久化、Migration、HTTP API 或前端，也没有实施下一阶段。

### P4-4B1 验证

最终实测结果（2026-10-01，北京时间）：

| 项目 | 结果 |
| --- | --- |
| 新增测试 | 61 项（参数化后），覆盖所列 33 类要求；原 263 项 + 新增 61 项 = 324 项 |
| SQLite 全量 pytest | 324 passed，46.01 秒 |
| PostgreSQL 全量 pytest | PostgreSQL 17.11，独立 127.0.0.1:55433 空库 jc_goals_baseline_test：324 passed，53.14 秒 |
| 旧模块回归 | test_features / test_results / test_market_model / test_score_matrix / test_odds 全部纳入两套全量，旧测试及模块均未修改 |
| Ruff | apps/api/src、tests 全部通过；两个新 Python 文件 format --check 通过 |
| mypy | 36 个源文件通过 |
| Schema / API | 无新表、Migration 或 HTTP API；001～008 未修改；原 upgrade/check/downgrade 集成测试通过 |
| Golden Case | 两队率 (2,1)/(1,2) → lambda=(2,1)、rho=0 → 与 score-math-v1 直接调用完全一致 |

两套测试均无失败、无跳过，保留原有 1 条 Starlette/httpx 弃用警告。PG 首轮发现新增测试的 I/O 守卫作用域覆盖了 fixture 清理，已限制为估计器调用期间；恢复本轮专用测试库至 base 后完成全量复验，没有修改业务代码或旧测试来绕过该问题。最终确认专用测试库仅剩空 alembic_version 表，没有业务表；本轮启动的独立测试实例已正常停止，没有修改或迁移演示业务库。

本机日志（Git 忽略）：`artifacts/goals-baseline-sqlite-tests.txt`、`artifacts/goals-baseline-postgres-tests.txt`；首轮排查日志另存 `artifacts/goals-baseline-postgres-first-run.txt`。没有新增依赖；前端无修改，本轮未重跑前端构建。

共 8 个文件：新增 `apps/api/src/jc/analysis/goals_baseline.py`、`tests/test_goals_baseline.py`、`docs/DECISIONS/ADR-011-goals-baseline-lambda.md`；修改 `docs/PHASE4_SPEC.md`、`docs/ARCHITECTURE.md`、`docs/BACKLOG.md`、`docs/CONSTITUTION.md`、`README.md`。完成后停止于 P4-4B1，等待人工复核，不继续下一阶段。

## P4-4C Model Evaluation Core

P4-4B1 经人工复核后，新增 `analysis/evaluation.py`，只消费上游已经准备好的不可变 `EvaluationSample`，不新增足球因素。模块运行时仅依赖标准库，不访问数据库、网络、Provider、当前时间或任何 Snapshot 查询。所有结果固定 `evaluation_mode=FROZEN_SAMPLE_SET`；不判断投注价值，也不输出 WINNER/best_model。

### Contract 与固定规则

样本字段为 sample_id、match_id、prediction_source、HOME/DRAW/AWAY 概率、actual_result，以及可选的带时区 match_time。概率只接受 Decimal 或 Decimal string，复制为不可变映射；赛果必须由上游明确映射，拒绝解析比分文本。单模型重复 `prediction_source + match_id`、跨模型矛盾赛果、非法输入均整次拒绝，不静默排除。

| 规则 | evaluation-v1 |
| --- | --- |
| 版本 | EVALUATION_VERSION="evaluation-v1"；公式、clipping、精度、容差、桶、映射、样本及 aggregate 规则变化须升级 |
| 概率验证 | 全部有限且 0≤p≤1，abs(Σp−1)≤1e-23；精确验证输入和，兼容 market-v1 序列化；拒绝 float/NaN/Infinity，不重归一 |
| 数值计算 | 独立 50 位 Decimal Context / ROUND_HALF_EVEN，固定指数范围、traps/flags；核心结果为 Decimal string |
| Log Loss | mean(−ln(max(p_actual,1e-15)))；LOG_EPSILON=1e-15，clipping_count 统计 p_actual 严格低于 epsilon 的场数，原概率保留 |
| Brier | mean_samples(Σ_classes(p−y)²)，三类求和、不除以 3；完美 0，错误极值 2 |
| Accuracy | 正确 argmax/N；完全并列时 HOME → DRAW → AWAY，辅助指标 |
| Calibration | 三类各自 one-vs-rest，10 桶 [0,.1)…[.9,1]；count/mean_predicted_probability/actual_frequency/绝对 calibration_error，空桶统计为 null |
| ECE | 每类 Σ_bin(count_bin/N)×abs(mean_probability−actual_frequency)；macro 为 HOME/DRAW/AWAY ECE 的算术平均 |
| Aggregate | 样本等权，按 match_id/source/sample_id 稳定累加，模型键排序；0 样本核心统计 null、clipping_count=0，30 个空桶保留 |
| Coverage | evaluated_samples/eligible_samples；未知或零分母 null，显式正分母且无评估样本为 0；分母必须为 int 且≥已评估数 |
| Paired | 指定 baseline，与每个 candidate 按 match_id 交集逐场求差再平均；direction=candidate − baseline，负数表示 candidate loss 更低；无交集差值 null |
| 时间划分 | temporal_split 按上游 match_time 的 UTC 时间稳定排序，< cutoff 为 past，≥ cutoff 为 future；缺失/无时区/同场矛盾时间拒绝，无随机切分或训练 |

`evaluate(samples, eligible_samples=...)` 仅聚合单模型。`evaluate_models({source: samples}, baseline=..., eligible_samples={source: total})` 保留各模型自己完整集合的指标、coverage 和每个 candidate 对 baseline 的配对结果；baseline 必须显式传入，空模型也保留。不同模型全量 aggregate 之差不是配对结果。

纯 adapter `market_evaluation_sample(market_data, ...)` 仅使用冻结 external_consensus.p_market；null 返回 None，不用 Sporttery 补齐。`goals_evaluation_sample(result, ...)` 仅在 OK 且 score 非空时使用 score.one_x_two；INSUFFICIENT_DATA / OUT_OF_RANGE 返回 None。两者保留来源版本并统一验证、冻结概率。上游过滤 None 前先明确 eligible 范围，不能把只成功预测的场数当成总分母。

### 可复现的数学样例

```python
from jc.analysis.evaluation import EvaluationSample, evaluate

# 合成 Golden Case，仅验证数学；不代表真实回测。
samples = [
    EvaluationSample("s1", "m1", "example-v1", {"HOME": ".7", "DRAW": ".2", "AWAY": ".1"}, "HOME"),
    EvaluationSample("s2", "m2", "example-v1", {"HOME": ".2", "DRAW": ".6", "AWAY": ".2"}, "DRAW"),
    EvaluationSample("s3", "m3", "example-v1", {"HOME": ".1", "DRAW": ".2", "AWAY": ".7"}, "AWAY"),
]
metrics = evaluate(samples, eligible_samples=3)
assert metrics["accuracy"] == metrics["coverage"] == "1"
```

手算 Log Loss=−ln(.294)/3；Brier=(.14+.24+.14)/3=.52/3；Accuracy=1；ECE HOME=1/5、DRAW=4/15、AWAY=1/5，macro=2/9。测试逐桶核验 mean/frequency/error 和空桶，并验证 exact zero、0.1、1.0 边界、非等样本集的配对差值以及原概率不被 clipping 修改。

### Provenance 与历史研究

FROZEN_SAMPLE_SET 只表示输入固定，不认证真实线上来源或无时间泄漏。analysis_visibility 代表本系统当时实际已经看见的数据；今天导入 2024 年历史不能生成 2024 年 live-visible FeatureSnapshot，禁止 `visible_at = provider published_at` 等伪造。未来 LIVE_AS_OBSERVED 与 RESEARCH_REPLAY / historical_research_dataset 必须分开设计；当前两个模式均未实施，时间拆分也不构成历史回放。

当前不能证明 Goals Baseline 优于 Market，因为尚无真实、足量、严格时间语义的历史样本结果。没有 Research Replay、xG、Elo、主客场增强、时间衰减、rho 拟合、ML、Ensemble、P_final、ROI/EV、Recommendation、公开 Prediction API 或自动投注。完整语义见 [ADR-012](DECISIONS/ADR-012-model-evaluation-core.md)。

### P4-4C 验证

最终实测结果（2026-10-01，北京时间）：

| 项目 | 结果 |
| --- | --- |
| 新增评估测试 | 105 项（参数化后）；原 324 项 + 新增 105 项 = 429 项 |
| SQLite 全量 pytest | 429 passed，48.85 秒 |
| PostgreSQL 全量 pytest | PostgreSQL 17.11，独立 127.0.0.1:55433 测试库 jc_evaluation_test：429 passed，54.97 秒 |
| 必须回归的旧链路 | test_features / test_results / test_market_model / test_score_matrix / test_goals_baseline / test_odds 均包含于两套全量测试并通过 |
| Ruff | apps/api/src、tests 范围全部通过；本轮 3 个 Python 文件 format --check 通过 |
| mypy | 37 个源文件全部通过 |
| 独立运行 | python -S 禁用 site-packages，并以导入守卫拒绝第三方和其他 jc 业务模块，evaluation 导入及完美预测计算通过 |
| Migration / Schema | 无新增或修改的表、Migration；现有 upgrade/check/downgrade 测试在 SQLite/PG 通过，head 保持 008_market_probability |
| API / 前端 | 无新增或修改 API、预测端点或前端；没有新增依赖 |

首轮两套全量各有 1 个旧验收用例失败，均为 `test_kickoff_change_invalidates_and_old_raw_does_not_revert`：真实时钟可能在连续调用中给出相同时间，破坏用例预期的 older < newer 或 cutoff < invalidation，分别导致历史映射被视为已失效、或“旧” Raw 与新 Raw 同时而未被旧数据保护拦截。仅在该合成测试中替换 `jc.time.datetime` 为确定性递增时钟，使 ORM 捕获的 utcnow 默认值也遵循同一时间线；保留所有原断言，没有修改业务处理、历史可见性或旧 Migration。针对性复验后重跑两套完整测试，全部通过。该测试时钟不生成真实历史样本或回填生产 analysis_visibility。

两套最终测试均无失败、无跳过，保留原有 1 条 Starlette/httpx 弃用警告。日志在本机 Git 忽略的 `artifacts/evaluation-sqlite-tests.txt`、`artifacts/evaluation-postgres-tests.txt`；首轮日志分别保留为 `evaluation-sqlite-first-run.txt`、`evaluation-postgres-first-run.txt`。专用 PG 测试库最终仅剩空 alembic_version 表，本轮启动的独立测试实例已停止；没有修改或迁移演示业务库。

文件共 9 个：新增 `apps/api/src/jc/analysis/evaluation.py`、`tests/test_evaluation.py`、`docs/DECISIONS/ADR-012-model-evaluation-core.md`；修改 `docs/PHASE4_SPEC.md`、`docs/ARCHITECTURE.md`、`docs/BACKLOG.md`、`docs/CONSTITUTION.md`、`README.md`、`tests/test_acceptance.py`。前端未改，未重跑其 test/build；真实 Provider、Docker/Redis、研究数据集与发布工件归档等既有 Gate 不因此关闭。

本轮停止于 P4-4C，等待人工复核，不继续 Research Replay 或后续模型/推荐阶段。

## P4-4D1 Research Replay Semantics Core

P4-4C 人工复核后，授权独立的 research-replay-v1。只新增 `analysis/research_replay.py`，消费 frozen ResearchMatch、ResearchOddsQuote、ResearchResult、ResearchSource / ResearchDataset 与 ReplayCutoffSpec；没有修改 live Feature、Market、Goals、Evaluation 核心及可见性语义。

LIVE_AS_OBSERVED 代表系统当时实际看到的数据；RESEARCH_REPLAY 代表有明确来源时间证据和研究规则的假设回放，两者不能混淆。Research context/报告明确 evaluation_mode=RESEARCH_REPLAY、live_visibility_proven=false。禁止回填过去的 analysis_visibility；Research Feature 和模型结果只在内存中，不能写 FeatureSnapshot 或 MarketModelSnapshot。

### 固定规则

| 项目 | research-replay-v1 |
| --- | --- |
| 可用性 | 显式 replay_available_at + availability_basis；SOURCE_SNAPSHOT_AT、PROVIDER_PUBLISHED_AT、PROVIDER_EFFECTIVE_AT、VERIFIED_ARCHIVE_TIMESTAMP 四种；provider basis 要求等于对应证据时间，无 magic lag |
| 缺证据 | 显式 None/None 标记 REPLAY_UNAVAILABLE 并排除；GUESSED/UNKNOWN/非法枚举拒绝；所有非空时间 aware → UTC |
| Dataset 时间完整性 | 所有 Result 强制 finished_at > 对应 Match kickoff_at；非空 replay_available_at ≥ finished_at；违反则拒绝 Dataset，不静默过滤/修正 |
| Target 池/身份 | 目标缺 sporttery_match_id 则 NOT_REPLAYABLE + TARGET_NOT_IN_SPORTTERY_POOL；目标缺任一 canonical team ID 则 NOT_EVALUABLE；非体彩历史上下文仍允许 |
| Cutoff | 只接受正整数 MINUTES_BEFORE_KICKOFF；一个 run 一个策略；T-30M 与 T-360M 分开运行 |
| 目标/赔率 | available_at 及非空 published/effective 均 ≤ cutoff；目标不通过则 NOT_REPLAYABLE |
| Latest/previous | provider/bookmaker/market/selection/精确 Decimal raw line 分组；coalesce(effective,published,available) + record_id 降序；仅从已筛过的可见记录中取前两条 |
| 历史赛果 | 目标 Result 先硬排除；历史 Match 与 Result 三时间门槛、kickoff < finished < cutoff；两者 canonical team ID 完整，且涉及目标至少一队；多来源冲突交给原 Goals |
| Label | 目标赛果不受赛前 cutoff 限制，但必须通过 chronology；两队 ID 完整且严格等于目标，缺失 NOT_EVALUABLE、矛盾拒绝 Dataset；只进 actual_result，比分冲突 NOT_EVALUABLE + CONFLICTING_TARGET_RESULT |
| Feature | 兼容原 FeatureData；past_stats=[]，mapping_id/version=null 并注明 Dataset canonical identity；独立 research_data_quality，无总分 |
| Provenance | Match 的 (source, source_record_id) 唯一；input_match_ids 保存 canonical research_match_id；input_record_ids.odds/results/match_source_records 只保存对应记录 ID，包含 previous 与已用历史证据；label_record_ids 独立 |
| Evaluation | 使用原 adapter/evaluate_models；prediction_source 带 @research-T{minutes}M；外层研究模式，内层仍 FROZEN_SAMPLE_SET；显式目标总数作两模型共同 eligible 分母 |

入口 `build_research_feature` 可直接供原 Market/Goals 纯函数消费；未知目标返回稳定 `ValueError("Unknown research target")`。`build_research_evaluation_samples` 返回 immutable 样本和 JSON-safe 报告；`run_research_evaluation` 运行原评估数学并保留报告。所有代码无 DB、网络、Provider、文件读取、当前时间或 analysis_visibility 依赖；无正式 Prediction、Schema、Migration、公开 API 或前端。

published_at/effective_at 不一概要求晚于 finished_at；仅被选为 provider availability basis 时，由于必须等于 replay_available_at，受不早于终场的约束。目标 Label 只豁免赛前 cutoff，不豁免 chronology、canonical identity 或证据完整性。

本轮 sporttery_match_id 非空不构成“实际开售”证明。P4-4D2 Historical Research Dataset Persistence 真实导入时，必须验证 ID 来自官方体彩历史开售比赛池并保留证据，外部源随意提供的字符串不算证明；本轮不实施 D2。

完整 contract、边界、诊断计数口径及版本升级规则见 [ADR-013](DECISIONS/ADR-013-research-replay-semantics.md)。测试 fixture 为 12 场历史、1 场目标、多公司多次外部报价，两队各 6 场历史，两个模型均得到合法 EvaluationResult；不断言谁胜过谁。

**仍不能进行真实三赛季模型优劣结论。** 当前只有语义和纯函数 fixture；真实来源获取、时间证据验证、覆盖率检查及持久化导入尚未开始。本轮完成后停止，不继续爬虫、Research Dataset DB、xG、Elo、Ensemble 或 Recommendation。

### P4-4D1 验证

最终实测结果（2026-10-01，北京时间）：

| 项目 | 结果 |
| --- | --- |
| 新增测试 | 122 项（参数化后）；原 429 项 + 新增 122 项 = 551 项 |
| SQLite 全量 pytest | 551 passed，72.65 秒 |
| PostgreSQL 全量 pytest | PostgreSQL 17.11，独立 127.0.0.1:55433 专用空库 jc_research_replay_test：551 passed，77.19 秒 |
| 指定旧模块回归 | test_features / test_results / test_market_model / test_score_matrix / test_goals_baseline / test_evaluation / test_odds 均包含在两套全量中并通过；原测试和业务代码未改 |
| Ruff | `ruff check apps/api/src tests` 全部通过；两个新 Python 文件 format --check 通过 |
| mypy | apps/api/src 38 个源文件全部通过 |
| 隔离验证 | AST 依赖/调用守卫、独立进程禁止导入 live/ORM 模块、运行时拒绝 SQL/文件/网络/时钟访问均通过 |
| Migration / Schema | 无新增或修改；原 upgrade/check/downgrade 测试两种数据库通过，head 保持 008_market_probability |
| API / 前端 / 依赖 | 均无新增或修改 |

两套无失败、无跳过，保留原有一条 Starlette/httpx 弃用警告。日志保存在本机 Git 忽略的 `artifacts/research-replay-sqlite-tests.txt`、`artifacts/research-replay-postgres-tests.txt`。数据库测试只使用专用空库；研究模块自身不访问 DB。结束时确认专用库仅剩空 alembic_version、无业务表，本轮启动的独立 PostgreSQL 测试实例已停止，没有迁移或修改演示业务库。

共 7 个文件：新增 `apps/api/src/jc/analysis/research_replay.py`、`tests/test_research_replay.py`、`docs/DECISIONS/ADR-013-research-replay-semantics.md`；修改本规范、`docs/ARCHITECTURE.md`、`docs/BACKLOG.md`、`docs/CONSTITUTION.md`。停止于 P4-4D1，等待人工复核。

### P4-4D1.1 Pre-acceptance correction

本次属于正式验收前正确性修复：补足 Dataset chronology、目标 canonical identity/体彩池、来源记录复合唯一性与 provenance 拆分；保留 `RESEARCH_REPLAY_VERSION="research-replay-v1"`。本轮通过人工验收后 v1 正式冻结，之后任何研究规则变化必须升级 v2。原实现阶段验证记录保留在上方，本轮结果另列于下方。

历史非法 chronology 测试改为断言 Dataset 拒绝；合法赛后 Label 的新增、删除、分数及可用性变化仍不影响 Feature。完整 12 场历史 + 1 场目标 fixture、非体彩球队历史、Market/Goals/Evaluation 内存链路和 LIVE 隔离均继续验证。

本轮实测结果（2026-10-01，北京时间）：

| 项目 | 结果 |
| --- | --- |
| 测试增量 | Research Replay 参数化后净增 38 项，122 → 160；全量 551 → 589 项 |
| SQLite 全量 pytest | 589 passed，43.97 秒 |
| PostgreSQL 全量 pytest | PostgreSQL 17.11，127.0.0.1:55433 专用空库 jc_research_replay_correction_test：589 passed，52.12 秒 |
| 指定回归 | test_features / test_market_model / test_score_matrix / test_goals_baseline / test_evaluation / test_research_replay / test_results / test_odds 均通过 |
| 隔离及完整链路 | 原 fixture 集成、AST/独立导入/运行时 I/O 守卫、LIVE/analysis_visibility 隔离均通过；live 模块和原模型计算未改 |
| Ruff | `ruff check apps/api/src tests` 与两个变更 Python 文件的 format --check 均通过 |
| mypy | apps/api/src 38 个源文件全部通过 |
| Migration / Schema | 无新增或修改；现有 upgrade/check/downgrade 两种数据库均通过，head 仍为 008_market_probability |
| API / 前端 / 依赖 | 无新增或修改；前端 `npm test` 1 项通过 |

两套后端全量均无失败、无跳过，保留原有 1 条 Starlette/httpx 弃用警告。日志为本机 Git 忽略的 `artifacts/research-replay-correction-sqlite-tests.txt`、`artifacts/research-replay-correction-postgres-tests.txt`。PG 结束后确认仅剩空 alembic_version 表，明细在 `artifacts/research-replay-correction-postgres-postflight.json`；本轮启动的专用测试实例已正常停止，未迁移或修改演示业务库。

本轮仅修改 7 个已有文件：research_replay.py、test_research_replay.py、ADR-013、本规范、BACKLOG、CONSTITUTION 和 README。未进入 P4-4D2，没有历史采集、Research DB、Migration、API、Live Feature 或 analysis_visibility 改动；没有 xG、Elo、Ensemble、Recommendation、EV/ROI 或 LLM。通过这些检查只说明语义层可提交人工验收冻结，真实历史三赛季结论仍不能开始。

## P4-4D2A Research Dataset Persistence

D1/D1.1 现已通过人工复核，research-replay-v1 正式冻结。本节授权并实现独立持久化，不追溯修改上方各阶段的实现/验收记录，也不改变冻结 contract、cutoff、target pool、时间、identity、选择和 provenance 规则。

Migration 009 新增 research_datasets、research_sources、research_raw_artifacts、research_matches、research_odds_quotes、research_results；001～008 不变。独立 research/schema metadata + Core importer/repository，全部 FK 为研究内部引用，不使用 LIVE ORM Session，也不触发其 after_commit 可见性扫描。

| 项目 | D2A 规则 |
| --- | --- |
| Dataset identity | (dataset_key, dataset_version) 唯一；contract.dataset_id 是自然 key，另设存储 UUID |
| 生命周期 | BUILDING→SEALED 或 REJECTED；两个终态不可恢复/追加；成员任何阶段禁止 UPDATE/DELETE |
| Raw first | 本地原件先构造 Raw，再 parse/normalize；source/Raw 入库早于成员；每条成员必须同 dataset/source Raw |
| 输入 | 原 ResearchDataset + ResearchImport 中的显式 source、Raw、provenance、verification contracts；不接受 ORM 任意数据 |
| Raw 幂等 | 同 dataset/source/payload hash 且 metadata 一致返回 existing；修正 payload 追加；同 hash 改 metadata 冲突 |
| Dataset hash | SHA-256、research-content-v1 canonical JSON；来源完整定义/manifest、所有成员与 Raw/关联/验证声明均纳入；排除 UUID、created/sealed 时钟、版本标签和 DB 行顺序 |
| Seal | 锁定 BUILDING、从 DB 重建并完整验证 contract、FK、chronology、manifest、Raw/体彩证据与 hash；生成质量计数、sealed_at、SEALED |
| 失败策略 | 导入预校验失败不写；成员事务原子提交 BUILDING；Seal 独立事务失败保留 BUILDING，显式拒绝或新版本，不跳坏行 |
| 同版本重导 | SEALED 且 hash 相同才幂等返回；不同内容、BUILDING 或 REJECTED 均 CONFLICT |
| DB 保护 | 复用 immutability helper；双库成员 INSERT/UPDATE/DELETE 与状态 trigger；PG 防 TRUNCATE；复合 FK 与时间/来源证据保护 |
| 并发 | PG READ COMMITTED 父行锁、SQLite BEGIN IMMEDIATE 写锁，避免 hash 与终态之间追加成员 |
| Source 核验 | 显式状态/时间/说明，不自动 VERIFIED；SYNTHETIC_FIXTURE 固定 UNVERIFIED；拒绝常见凭据字段/文本/URL |
| 体彩核验 | 默认 UNVERIFIED；VERIFIED 须关联官方历史 Raw、已验证 source、当前比赛 ID/两队/kickoff 证据；未来真实目标从 verified_sporttery_targets 取得 |
| Availability | 四枚举原值保存；缺失保持 NULL；provider basis 等值检查；绝不自动生成 replay_available_at |
| Chronology | 沿用 v1 finished_at > kickoff_at，available_at NULL 或 ≥ finished_at；REGULATION，已知球队身份一致 |
| Numeric | PG 无固定 scale NUMERIC；SQLite 精确十进制 TEXT；不经 float/double，完整 Decimal 往返 |
| Materialization | load_research_dataset 仅接收 SEALED；复核完整 hash/quality；恢复原 ResearchDataset 再交给原 replay 纯函数 |

quality_summary 包含 match_count、sporttery_target_verified_count、odds_count、result_count、sources_count、records_with/without_verified_availability、matches/results_missing_team_identity、date_min/max（开球范围），没有 quality_score。时间证据计数不等于真实来源已被核验。

完整本地 `tests/fixtures/research_history.json` 链路有 12 历史比赛 + 1 体彩形状 Target、两个外部 bookmaker、各选项多时间赔率和 Target final result。所有 synthetic 来源与 Target 维持 UNVERIFIED，真实目标准入名单为空；为验证冻结算法，测试显式向原 replay 传入 synthetic target。加载前后 contract 完全相等、Evaluation 报告相等，Market 与 Goals 都生成样本，不评判模型优劣。

完整决定、内部调用/锁/精度限制、官方验证声明口径见 [ADR-014](DECISIONS/ADR-014-research-dataset-persistence.md)。本轮无互联网访问、Crawler、公开 API、LIVE 表内容或 analysis_visibility 改动，也无 xG/Elo/ML/Ensemble/Recommendation/EV/ROI。

**当前没有真实三个完整赛季 + 当前赛季数据。** 本轮仅为将来安全导入建立结构；完成后停止，不进入 D2B。

### P4-4D2A 验证

实测日期：2026-10-01（北京时间）。

| 检查 | 结果 |
| --- | --- |
| 新增测试 | tests/test_research_persistence.py 参数化后 145 项；589 + 145 = 734 项 |
| SQLite 全量 | 734 passed，140.40 秒 |
| PostgreSQL 全量 | PostgreSQL 17.11；专用 jc_research_persistence_test，127.0.0.1:55433；734 passed，136.31 秒 |
| SQLite / PG Migration | 009 upgrade/head、Alembic check、009→008 及 downgrade/base→head 均通过；旧 Feature/Market 迁移回归亦通过 |
| 完整链路 | 13 场比赛、12 条多时间赔率、13 条赛果；contract round-trip 相等，加载前后 Evaluation 报告相等，Market/Goals 各 1 个样本 |
| 并发 / 精度 | 双库 Seal/追加串行保护通过；PG NUMERIC / SQLite 精确文本保留超 30 位 Decimal；低全局精度不改变 hash/数值；JSONB 指数数值 hash 往返一致 |
| LIVE 隔离 | 留有未证明 LIVE Raw 的情况下，Research 全链 SQL 无任何 LIVE 表访问；全部 LIVE 表行数保持不变，无可见性凭据或 Feature/Market Snapshot 新增 |
| 冻结代码 | research_replay.py、Market/Goals/Evaluation、LIVE 模块、Migration 001～008 均无改动 |
| Ruff | apps/api/src、tests、migrations/env.py 和新 009 全部通过；7 个新/新增测试 Python 文件及 env.py 格式检查通过 |
| mypy | apps/api/src，43 个源文件通过 |
| 真实数据 / API / 依赖 | 无真实历史数据、无互联网访问/爬虫、无公开 API/前端/依赖变更 |

两套全量均无失败、无跳过，只有原有一条 Starlette/httpx 弃用警告。日志在 Git 忽略的 `artifacts/research-persistence-sqlite-tests.txt`、`artifacts/research-persistence-postgres-tests.txt`；postflight JSON 确认专用 PG 测试库仅余空 alembic_version。专用测试实例完成后停止，未迁移或修改演示业务库。

本轮只交付 D2A，等待人工复核；没有获取过去三完整赛季或当前赛季真实历史，也不据合成 Evaluation 样本判断模型优劣。D2B、xG、Elo、ML、Ensemble、Recommendation、EV/ROI 均未实施。

## P4-4D2B Source Discovery 与 Pilot 阻塞验收

2026-10-01 用户确认 D2A 已人工复核，授权先做 1～3 个历史销售日 / 50～100 场 Pilot。
实际探测候选窗口 2026-09-26～28：官方历史开售/赛果 API HTTP 567，The Odds API 缺凭据且匿名请求 401。
保存 26 个 probe、25 个 HTTP response Raw；没有实际 Target、VERIFIED、SEALED 或 Research Replay。
T-30M/T-90M/T-360M 分别为 BLOCKED_NOT_RUN；Gate A～F 均 BLOCKED，不适合扩展三赛季。
新增独立研究探测模块、日期范围限制、Raw-first/secret 防护和报告；未对未验证来源提前写业务 Adapter。
测试 754 passed、1 网络项 skipped；Ruff/Mypy 通过；本机 PostgreSQL 未运行，alembic check 连接超时。
Migration 仍为 009，冻结 v1 和 LIVE 均无改动。完整证据、限制与 28 项汇报见
[RESEARCH_SOURCES](RESEARCH_SOURCES.md) 和 [PILOT_DATASET_REPORT](PILOT_DATASET_REPORT.md)。
