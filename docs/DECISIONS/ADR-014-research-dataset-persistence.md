# ADR-014：Research Dataset Persistence

- 日期：2026-10-01
- 范围：P4-4D2A；实现后等待人工复核，停止于 D2A
- 前置：P4-2、P4-3、P4-4A、P4-4B1、P4-4C、P4-4D1/D1.1 已通过人工复核
- 冻结：`research-replay-v1`。可用性、cutoff、chronology、target pool、identity、选择规则或 provenance 变化必须另立 v2

## 决定与物理边界

Migration `009_research_dataset_persistence` 只新增 research_datasets、research_sources、research_raw_artifacts、research_matches、research_odds_quotes、research_results。允许与 LIVE 共用 PostgreSQL 实例/schema，但六表使用独立 Core metadata，FK 全部指向 research_*；研究球队/赛事 ID 为 contract 字符串，不连接 LIVE teams/competitions。001～008 不变。

内部模块为 `jc.research.contracts/schema/repository/importer`，不创建微服务、公开 API、后台任务或前端入口。调用方传 Core Engine/Connection，明确拒绝 ORM Session：现有 Session 全局 after_commit 会扫描 LIVE 可见性，不应被 Research 提交触发。LIVE 模块、analysis_visibility、FeatureSnapshot、MarketModelSnapshot 均不修改。迁移环境仅将独立 Research metadata 纳入 Alembic check。

## Dataset identity 与生命周期

存储 UUID `research_datasets.id` 只用于 FK；冻结 contract 的 `dataset_id` 映射自然键 `dataset_key`，与 `dataset_version` 组成唯一键。版本字符串由调用方显式提供，版本一经使用不得复用成其他内容。

```text
新建 → BUILDING → SEALED
              └→ REJECTED
```

创建必须 BUILDING。成员只能在 BUILDING 增加，任何阶段均不能 UPDATE/DELETE。数据集本身不允许删除；只有上述两种状态转移可更新，除 status/sealed_at/content_hash/quality_summary 外字段不能随转移变化。SEALED、REJECTED 均是终态，不能恢复或继续追加。

错误修正使用新 record ID / 新 Raw hash；一个版本内 Match canonical ID 或来源记录 ID 已占用时，应建立新 dataset_version。保留 REJECTED 的取证记录，不物理删除失败版本。

高层 importer 先完整校验输入，再在一个事务中写入并提交 BUILDING；第二个事务执行 Seal。Seal 失败固定保留 BUILDING，不跳行、不自动 REJECTED。调用方可显式 `reject_dataset` 并创建新版本。输入预校验失败不创建数据集；成员写入事务失败整体回滚，避免半批次入库。已有 SEALED 同 key/version 且完整内容 hash 相同可返回 existing；不同内容或未完成/已拒绝版本返回 `DatasetConflict`，不使用 ON CONFLICT DO UPDATE。并发导入遇到仍在 BUILDING 的同版本也返回冲突，稍后可对完成的同内容版本重试。

## Raw first 与显式 Import Contract

输入为冻结 D1 `ResearchDataset` 加 `ResearchImport`，其中明确列出 ResearchSourceInput、ResearchRawArtifactInput、逐记录 ResearchRecordProvenance 和可选 SportteryVerificationInput。Importer 不接受任意 ORM 数据；先验证 Raw 的存在、来源、hash 与全部规范化记录的关联，再写 source → Raw → matches → odds → results。fixture 从本地 JSON 先构造 Raw，再解析 D1 contract。

Raw 保存 artifact_type、external_ref、retrieved_at、content_type、payload、metadata、content_hash、source/dataset FK 和 created_at。PostgreSQL payload/metadata 为 JSONB，SQLite 为 JSON；文本原件可作为 JSON 字符串保存（包含其完整文本），非 JSON Python 对象拒绝。未来冷存储可沿用 external_ref/hash，本轮无对象存储、S3、MinIO、Kafka。

Raw 身份为 `(dataset_id, source_id, SHA256(canonical payload bytes))`。同源相同 payload 和相同工件元数据幂等返回原 UUID；同 hash 但元数据不同显式冲突，不能覆盖旧工件。修订 payload 产生新 hash/新行。跨来源的相同 payload 仍是独立来源工件。每条 Match/Odds/Result 都有非空 raw_artifact_id，以复合 FK 保证与其 dataset/source 同属；不存在只存 normalized 数据的路径。

Source 声明必须完整匹配创建时 manifest_json 中的 source_manifest 快照。保存 provider、license/retrieval note、可空 URL、verification_status/verified_at/verification_note。VERIFIED 必须显式提供时间与非空说明；代码成功导入不会自动认证。SYNTHETIC_FIXTURE 强制 UNVERIFIED。Raw、metadata、manifest、来源、文本/URL 等输入递归拒绝常见 API key、Authorization、cookies、password、token/secret 字段及凭据形式，不读取 LIVE .env，也不回显被拒绝的秘密值。此检查不冒充任意自由文本秘密的通用识别器，调用方仍需提供无凭据原件。

## Canonical hash

Raw hash 与 Dataset hash 各自独立计算 SHA-256。

Dataset 的 `research-content-v1` canonical 内容包括 replay_version、description、manifest、冻结 source_manifest、完整 source definitions（包含来源验证/授权/检索说明）、Match/Odds/Result、Raw 的业务身份/hash/内容/元数据/检索时间、逐记录 Raw 关联和体彩验证关联。

- UTF-8、JSON key 排序、紧凑分隔符、UTC ISO 时间；拒绝 NaN/Infinity。
- Decimal 使用无指数、无多余尾零的精确字符串，不调用受全局精度影响的 normalize。JSON 整数型浮点按其十进制表示统一为整数，避免 PostgreSQL JSONB 展开指数导致 hash 漂移。
- sources、raw_artifacts、provenance、sporttery_verifications 按业务身份排序，D1 自身按 record ID 排序 matches/odds/results/source_manifest。输入排列和 DB 行顺序不影响 hash；Raw/manifest 内部 JSON 数组有顺序语义，数组内容顺序改变属于原件内容改变。
- 不纳入存储 UUID、created_at、sealed_at、状态或质量统计，也不纳入作为内容标签的 dataset_key/version。相同内容可用不同版本标签产生相同 hash，但同标签绝不覆盖不同内容。
- Raw 链接在 hash 中以 source_name + raw_content_hash 表示，不使用 UUID。输入与从 DB 重建的 hash 必须一致。

## Seal、数据库保护与并发

Seal 锁定 BUILDING dataset，读取全部 source/raw/member，重建并重新验证原始 D1 contracts，再验证所有 Raw hash、全部 FK/来源归属、source_manifest、体彩证据、availability/chronology 和无 secret 条件。全部通过后写 hash、事实统计、sealed_at、SEALED。Materialization 再次验证 hash 与统计，防止直接 SQL 伪造封存元数据被当成有效数据集使用。

成员 UPDATE/DELETE 复用 `migrations/immutability.py`；成员 INSERT 触发器要求父 dataset 为 BUILDING，dataset 触发器限制状态转移与其他字段不可变。PostgreSQL 额外禁止研究表 TRUNCATE。复合 FK 防跨数据集/来源引用，trigger 校验 Result finished_at 严格晚于 Match kickoff_at、已知球队身份一致、Odds provider 与 source_name 一致，以及 VERIFIED 体彩工件的官方来源和比赛证据。两种 DB 均保护终态成员 INSERT/UPDATE/DELETE。

PostgreSQL 成员追加触发器和 Seal 使用相同 dataset 行锁；服务写事务限定 READ COMMITTED，以保证等待行锁后读取新快照。SQLite Seal/追加在默认 sqlite3 尚未启动实际事务时执行 BEGIN IMMEDIATE，获取写锁后再读取。并发测试覆盖：Seal 先行时追加被拒绝；追加先行时 Seal hash 包含新工件。Core 调用者仍负责提交/回滚事务，不接受 AUTOCOMMIT 写入。

DB 管理员仍能禁用 trigger/改 schema；本轮不建立数据库用户/角色体系。合法直接 SQL 状态转移并不能代替服务的完整 Seal 验证；load 对完整内容再校验。

## 时间、Numeric 与冻结 v1

四种 availability_basis 原值持久化，时间和 basis 必须同时有值或同时 NULL；provider basis 要求 available_at 等于对应 published/effective。Importer 不推断时间，不从 retrieved_at/created_at 或 published_at 自动补值。

所有 Result 必须 `finished_at > match.kickoff_at`，且 available_at 为 NULL 或 ≥ finished_at；不对所有 published/effective 附加未冻结的终场约束。仅 REGULATION。赔率与 line 在 PG 为无固定 scale 的 NUMERIC，SQLite 使用精确文本防浮点精度损失；D1 Decimal 校验在写入和 Seal/load 时重跑，非法或非有限赔率不能封存。SQLite 文本 CHECK 只是初步防线，完整数值域校验由冻结 contract 完成。

`load_research_dataset(connection, dataset_key, dataset_version)` 仅加载 SEALED，完整恢复 D1 ResearchDataset，包括所有缺失时间/身份、来源记录和高精度 Decimal。round-trip 的 contract 业务内容相等。UUID 和创建时钟不进入 contract。

`research_replay.py`、Market、Goals、Evaluation 代码不变，依然只接受内存 contract。没有给 build_research_feature 传 Session，没有改变 v1 的 target pool、选择或 provenance 语义。

## 体彩验证与真实研究目标

sporttery_verification_status 默认 UNVERIFIED。VERIFIED 必须有 sporttery_match_id、同数据集 sporttery_verification_artifact_id，且该工件 artifact_type=SPORTTERY_POOL，其来源 provider_name=sporttery、source_type=OFFICIAL_SPORTTERY_HISTORY、verification_status=VERIFIED。工件 metadata.sporttery_pool_evidence 保存显式核验的 sporttery_match_id、canonical home/away IDs、UTC kickoff_at，必须完整对应当前比赛。裸字符串 ID 不构成开售证明。

该 metadata 是核验者对保留原件的结构化声明，并不表示代码联网认证了来源真实性。D2A 只实现验证声明的强制结构、关联与不可变保存。未来真实数据必须经过实际官方证据核验，之后用 `verified_sporttery_targets` 取得唯一允许的真实研究目标名单；不能绕过这个入池步骤直接把所有非空 sporttery_match_id 当真实目标。历史上下文允许保留非体彩记录。

合成链路为测试显式传入 synthetic target 运行原 v1，其来源与比赛仍 UNVERIFIED，正式目标名单为空。单独的官方验证正向单元测试只模拟显式核验声明，不代表获取或验证了任何真实官方数据。

## Quality 与验收

quality_summary 为事实：match_count、sporttery_target_verified_count、odds_count、result_count、sources_count、records_with/without_verified_availability、matches/results_missing_team_identity、date_min/max（Match kickoff_at 范围，空集为 NULL）。availability 计数指 D1 时间/basis 配对有效，不代表来源真实性已获认证。没有 quality_score。

验证范围包括双数据库 upgrade/head、check、downgrade/base、记录及来源唯一性、SQL 绕过保护、秘密拒绝、精确 Numeric、hash 顺序稳定/版本冲突、并发、往返和 LIVE SQL 隔离。完整 fixture 为 12 历史比赛 + 1 体彩形状 target、2 外部 bookmaker、多时间赔率、target final result；Market/Goals 都有 Evaluation Sample，不评判谁更强。最终运行计数在 PHASE4_SPEC。

本轮无互联网访问、Crawler、真实历史导入或三赛季结论。没有 xG、Elo、ML、Ensemble、Recommendation、EV/ROI。当前没有真实三完整赛季 + 当前赛季的数据，D2B 留待另行授权。
