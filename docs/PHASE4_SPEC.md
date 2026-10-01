# Phase 4 — Prediction & Recommendation Engine

已交付 P4-0～P4-3 与 P4-4A Score Probability Mathematics；当前数学层规范见文末，前文保留各历史阶段的规范与验收记录。没有 CORE/WATCH/PASS、EV、串关、LLM、自动投注或最终预测模型；没有真实赛果/统计 Provider 线上验收声明。

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
