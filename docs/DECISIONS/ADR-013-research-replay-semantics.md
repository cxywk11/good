# ADR-013：Research Replay Semantics Core

- 日期：2026-10-01
- 状态：P4-4D1 主体已完成人工复核；P4-4D1.1 验收前正确性修复已实施，待本轮人工验收，尚未冻结。
- 版本：`RESEARCH_REPLAY_VERSION = "research-replay-v1"`。
- 范围：显式 immutable historical records → Research FeatureData → 原 Market / Goals → 原 Evaluation，全部在内存中运行。

## 两种时间语义

**LIVE_AS_OBSERVED** 表示本系统在当时实际已收集并确认可见的事实。继续由既有 `analysis_visibility`、live Feature 构建器及 `FeatureSnapshot` 承担，语义和实现均不变。供应商发布时间不是系统提交后可见的证明。今天导入 2024 年历史绝不能伪造 `visible_at=2024`，也不能补造过去的 live FeatureSnapshot。

**RESEARCH_REPLAY** 表示根据历史来源提供的时间证据，在明确且固定的研究规则下重建“如果当时拥有这些历史源数据，可以看到什么”。它不声称本系统当年真的看到这些数据。所有 Research Feature context 和研究运行报告均标注 `mode/evaluation_mode=RESEARCH_REPLAY`、`live_visibility_proven=false`。

`analysis/research_replay.py` 不导入 live 构建器、ORM、DB、Provider 或可见性模块，不查询 analysis_visibility，不访问时钟、文件或网络。它仅调用原有纯计算函数；不能 INSERT `feature_snapshots` 或 `market_model_snapshots`。现有 MarketModelSnapshot 绑定 live FeatureSnapshot，不能容纳研究结果。未来研究持久化必须单独设计；本阶段没有表或 Migration。

## Immutable contracts

使用 frozen dataclass；所有非空时间拒绝 naive datetime，并在构造时转换 UTC，绝不推断本机时区。标识只接受非空字符串，未知的可选 ID 为 None；不做球队名称匹配。

| 类型 | 字段与约束 |
| --- | --- |
| ResearchMatch | research_match_id、sporttery_match_id、competition_id、home_team_id、away_team_id、kickoff_at、source、source_record_id，以及可用性证据 |
| ResearchOddsQuote | record_id、research_match_id、provider、bookmaker、market_type、selection、line、decimal_odds，以及可用性证据；赔率和非空盘口仅接受有限 Decimal，赔率 > 1，拒绝 float 和字符串隐式转换 |
| ResearchResult | record_id、research_match_id、home_team_id、away_team_id、非负整数 home_score/away_score、finished_at、source、score_scope=REGULATION，以及可用性证据；表示调用方提供的最终常规时间赛果，含补时、不含加时或点球大战 |
| ResearchSource | source_name、source_type、retrieval_note；均为必填来源说明 |
| ResearchDataset | dataset_id、dataset_version、replay_version、matches、odds、results、source_manifest；集合复制为稳定排序的 tuple，元素必须是上述 immutable contract |
| ReplayCutoffSpec | kind=MINUTES_BEFORE_KICKOFF、正整数 minutes；拒绝其他策略、bool、float、零和负数 |

每类记录的 ID 在该类集合中唯一，不按数组顺序解决重复；Match 的 `(source, source_record_id)` 也必须唯一，不得指向两个不同 research_match_id。不同 source 可使用相同 source_record_id。Dataset 拒绝不支持的 replay_version、悬空 match 引用、未列入 manifest 的 source/provider，以及已知 Result team ID 与对应 Match canonical ID 的矛盾。未知 team ID 可以保留，但该历史记录不能用于 Goals，缺身份的目标 Match 或 Label 不能正式 Evaluation。Match 同一场仅有一个 canonical 定义；版本纠错须由调用方构造新的 dataset_version，V1 没有比赛版本解析器。

Dataset 对所有 Result（目标和历史、包括缺 availability 的记录）验证 `result.finished_at > match.kickoff_at`；等于或早于开球均拒绝整个 Dataset。非空 `replay_available_at` 必须满足 `replay_available_at >= finished_at`，等于终场允许，早于终场拒绝；不会静默过滤或自动取 max 修正。Label 只豁免赛前 cutoff，不豁免真实事件 chronology。

## replay_available_at 与证据

`replay_available_at` 是当前 Research Dataset 规则下，该记录最早可用于研究的时间。它不是 `analysis_visibility.visible_at`，不证明系统收集时刻。所有记录都必须显式传入它和 availability_basis。

允许的 basis 是有限枚举：

| availability_basis | 时间证据 |
| --- | --- |
| SOURCE_SNAPSHOT_AT | 历史源快照本身明确给出的时间，直接作为 replay_available_at |
| PROVIDER_PUBLISHED_AT | 必须存在 published_at，且 replay_available_at 必须等于它 |
| PROVIDER_EFFECTIVE_AT | 必须存在 effective_at，且 replay_available_at 必须等于它 |
| VERIFIED_ARCHIVE_TIMESTAMP | 调用方已验证的归档时间，直接作为 replay_available_at |

快照/归档时间的外部真实性由 Dataset 提供方负责，manifest 必须保留获取与验证说明；本纯函数不读取或验证网站/归档文件。通过 contract 校验不等于来源已获真实数据验收。published_at/effective_at 可以未知，但存在时仍须通过 cutoff 检查。

不一概强制 published_at/effective_at 晚于 finished_at，不推定不同来源的业务时间语义。仅当它被选为 PROVIDER_PUBLISHED_AT / PROVIDER_EFFECTIVE_AT 的证据时，由于必须等于 replay_available_at，自然受到不早于 finished_at 的约束。

没有可靠时间证据时显式传入 `replay_available_at=None, availability_basis=None`，状态为 `REPLAY_UNAVAILABLE`，保留记录但不进入可评估输入。只缺二者之一、GUESSED、UNKNOWN、其他非法 basis 均拒绝。不得按比赛日期推测、自动 `published_at + 5 minutes` 或 `kickoff - 24h`；固定延迟假设需要未来显式的新 policy/version。

## Cutoff 与输入选择

每场目标 `analysis_cutoff = kickoff_at - timedelta(minutes=minutes)`。一个 run 接收一个 ReplayCutoffSpec，所有目标共享同一策略；没有选择“最有利时点”的能力。T-30M、T-90M、T-360M 分别运行，不在一次研究中混用。

目标 Match 必须具有非空字符串 sporttery_match_id；缺失时 `build_research_feature` 抛出 `NotReplayable`，固定为 `NOT_REPLAYABLE + TARGET_NOT_IN_SPORTTERY_POOL`，优先于 cutoff 检查。空白或非字符串 ID 由 contract 拒绝。此门槛只施加于所请求的目标，不要求所有 ResearchMatch 都来自体彩池；可信非体彩比赛仍可作为球队历史上下文。Evaluation 只处理显式 research_match_ids，不自动扩充目标池。

通过目标池门槛后，目标 Match 必须有可靠 availability，并同时满足 replay_available_at ≤ cutoff、非空 published_at ≤ cutoff、非空 effective_at ≤ cutoff，否则 `build_research_feature` 抛出 `NotReplayable`（status=NOT_REPLAYABLE，diagnostic=MATCH_UNAVAILABLE_AT_CUTOFF），研究运行记录原因并保留在 eligible 分母中，不制造空的可用 Feature。

本轮 ID 非空只是必要条件，不能证明实际开售。P4-4D2 真实导入必须验证该 ID 来自**官方体彩历史开售比赛池**并保留来源证明，不能把外部源随意提供的 sporttery_match_id 字符串当作已证明开售；本轮不新增爬虫或导入。

Odds 使用同样的三时间门槛。只有目标 research_match_id 的报价进入候选。序列键为 `(provider, bookmaker, market_type, selection, canonical raw line)`；Decimal 精确数值相等的原始盘口属于同一序列，例如 -0.50 与 -0.5000，相反号和不同数值不合并。这里不把 AWAY 盘口反向；market-v1 仍自行执行它已有的市场盘口规范化。用 Decimal equality 分组，不调用受环境精度影响的 normalize。

每条序列按以下二元键降序排列：

```text
(effective_at if present else published_at if present else replay_available_at,
 record_id)
```

这是选取一个有效业务时间的 fallback，不是再将三个时间依次作为 tie-break。最大记录为 latest，次大记录为 previous；相同时间用 record_id 降序打破并列。先筛选可见性再排序，不按数组输入顺序。previous 不跨公司、来源、市场、选项或盘口；没有第二条可见记录时为 null。绝不以后续报价补造过去 movement。每序列的观测独立，不声称各选项构成同步市场快照。

Goals 历史要求：

1. 首先无条件排除目标 research_match_id 的所有 Result，无论其时间字段是什么。
2. 历史 Match 自身三时间门槛通过；canonical Match/Result 两队 ID 均存在，至少一队是目标 canonical team ID。
3. Dataset 已强制 `historical_match.kickoff_at < result.finished_at`；Feature 再要求 `result.finished_at < target cutoff`。不可能的 chronology 在 Dataset 阶段报错，不在 Feature 阶段静默过滤。
4. Result 有可靠证据、replay_available_at ≤ cutoff，非空 published_at/effective_at 也 ≤ cutoff。finished_at 是严格小于，available_at 边界允许相等。

同场多个来源的历史 Result 全部保留，Replay 不做比分裁决、不选“最新结果”，交给原 goals-baseline-v1 的 match_id 去重及冲突整场排除。双方交锋可以进入双方历史。Baseline 原有最近 20 场、最少 5 场、等权、rho=0 规则不变。

## FeatureData 与 provenance

`build_research_feature(dataset, research_match_id, cutoff_spec)` 返回新的、兼容原 contract 的 FeatureData，绝不修改或复用 live Snapshot。未知目标统一抛出 `ValueError("Unknown research target")`，不暴露内部 KeyError：

- market.quotes：latest 引用的 research record ID 使用兼容字段 odds_snapshot_id；保留 provider、bookmaker、market_type、selection、line、decimal_odds、可用性证据。mapping_id/version 均为 null，context 显式说明 canonical_identity_basis=RESEARCH_DATASET。这些 ID 不是 DB snapshot 外键。
- odds_movement.items：current_odds、previous_odds、previous_snapshot_id；额外保留 previous_quote 的完整来源和时间证据，供追溯。变化数值由原 market-v1 计算。
- team_strength：past_results 含 match_id、两队 ID、比分、finished_at、source、record_id 与时间证据；past_stats=[]、rating=null，不补 xG=0。
- schedule：显式 kickoff_at 与整数 seconds_to_kickoff；squad 缺失保持不可用。
- context.research：mode、evaluation_mode、replay_version、dataset_id/version、cutoff_kind/minutes、analysis_cutoff、research_match_id、live_visibility_proven=false、canonical_identity_basis、完整 source_manifest。
- input_match_ids：按顺序保存目标与真正使用的历史比赛的 canonical research_match_id。
- input_record_ids：odds 保存 latest/previous 的 record_id；results 保存真正使用的历史 Result record_id；match_source_records 保存真正的 source_record_id，均稳定排序。移除旧的 matches 键，不与 canonical match ID 混用。match_records 保留 research_match_id、source、source_record_id、kickoff 和全部时间证据，因此即使不同 source 的源 ID 同名，也能通过 source + source_record_id 追溯。目标标签独立保存在 label_record_ids，绝不作为 Feature 输入。
- data_quality.research_data_quality：match_available、market_source_count、historical_result_count_home/away、records_without_verified_availability。没有 availability-v1 或 0–100 总分。

market_source_count 是选中报价的不同 `(provider, bookmaker)` 数量，不代表完整 1X2 源数；完整性仍由 Market 判断。两队历史计数是传给 Goals 的来源记录数，未经去重/冲突排除，不等于 Goals 的 matches_used。无可靠证据计数是 Dataset 全体记录的诊断，排除当前目标的全部 Result，防止标签可用性通过质量计数进入 Feature；它不参与任何模型计算。新增、删除、修改目标标签不会改变 Feature。

输出是全新的字典结构，消费者修改输出不影响 immutable Dataset 或下次构建。Decimal 在内存 contract 中保持 Decimal，Feature/报告 JSON 中编码为字符串；时间为 UTC ISO 字符串，整数秒不经过 float。

## Evaluation 标签的独立边界

`build_research_evaluation_samples(dataset, research_match_ids, cutoff_spec)` 接收显式目标群，返回 `(samples_by_prediction_source, research_report)`。样本为原 immutable EvaluationSample 的 tuple。重复或未知目标直接拒绝；不自动把全部历史比赛变为研究目标。

目标 ResearchResult **只作为 actual_result label**，允许赛后产生和发布，不受 pre-match cutoff 门槛限制，不能用于 Feature，但必须通过上述 Dataset chronology 校验。目标 Match 的 home_team_id / away_team_id 必须均非空，否则 `NOT_EVALUABLE + TARGET_CANONICAL_IDENTITY_MISSING`；即使已有 Market 预测也不得评估，不猜球队。

每一条目标 Result 的两队 ID 也必须均非空并严格等于目标 Match；已知 ID 矛盾由 Dataset 直接拒绝，缺失则 `NOT_EVALUABLE + TARGET_RESULT_CANONICAL_IDENTITY_MISSING`。同比分多来源中任何一条缺身份也不可绕过，不仅根据分数生成标签。全部身份与标签校验通过后，常规时间比分 home>away / 相等 / home<away 才映射 HOME / DRAW / AWAY。

标签处理：通过目标 Match 身份门槛后，先检查所有目标 Result 的完整比分一致性；任何比分冲突均 `NOT_EVALUABLE + CONFLICTING_TARGET_RESULT`，即使双方都判 HOME 也不能合并。不能投票、优先体彩、取最新或随机选择。相同比分且身份完整的多来源记录形成一个 label，保留所有 label_record_ids。没有赛果为 MISSING_TARGET_RESULT；通过标签身份检查后，任何标签记录缺可靠时间证据则 TARGET_RESULT_REPLAY_UNAVAILABLE。后者是 V1 的保守政策：赛后可用的例外只豁免 cutoff，并不豁免可靠来源时间。它不会把未验证的冲突来源悄悄丢掉。

调用原 build_market_data / estimate_goals_baseline，再调用原 market_evaluation_sample / goals_evaluation_sample；缺预测不补默认概率。研究 prediction_source 分别为 `market-v1@research-T30M`、`goals-baseline-v1@research-T30M` 等，原版本包含在名称中。evaluation-v1 的 `prediction_source + match_id` 唯一限制保持原样。不同 cutoff 必须分开运行，不能把它们混成同一实验。

`run_research_evaluation` 将原 evaluate_models 包在研究报告内：外层 evaluation_mode=RESEARCH_REPLAY，内层 Evaluation-v1 仍是 FROZEN_SAMPLE_SET，仅表达评估数学输入已固定，不提升为 live 证明。两个模型共享调用方显式目标总数作为 eligible 分母，包含不可回放、冲突/缺失标签及缺预测的目标；各模型有效样本数和 coverage 分别保留。baseline 显式为 Market，配对仍用原共同 match_id 规则，没有优胜结论。

报告保留 dataset/version、唯一 cutoff、matches_total/replayable、market/goals_evaluable、每场 cutoff/input_match_ids/input_record_ids/label_record_ids、质量诊断和排除原因。不可回放目标也保留一致的空 provenance 字段；它仍计入调用方显式目标总数和 coverage 分母。结果仅在内存中，不生成正式 Prediction、Model Snapshot 或公开 API。

## Pre-acceptance correction（P4-4D1.1）

2026-10-01：主体人工复核后、正式验收冻结前，补充 Dataset chronology（finished > kickoff、available ≥ finished）、Target/Label canonical identity、体彩目标池必要条件、Match 来源记录复合唯一性、拆分 canonical/input record provenance 和稳定 unknown target 业务错误。合法赛后 Label 仍完全隔离于 Feature 及其质量计数，LIVE/analysis_visibility 不变。

本轮属于 pre-acceptance correctness fix，继续保留 `RESEARCH_REPLAY_VERSION = "research-replay-v1"`，不表示已验收。**本轮通过人工验收以后 v1 正式冻结，之后任何上述研究规则变化必须升级 v2。** P4-4D2 Historical Research Dataset Persistence 仍未实施；官方体彩历史开售池证明、真实历史数据采集/导入、来源验证与覆盖率均保留为后续工作。

## 版本、验证与剩余边界

本轮人工验收冻结以后，available_at 语义、chronology、目标池/identity、provenance、record 筛选、odds 排序、历史 Result 选择、cutoff、conflict、Feature 构造任一规则变化都必须升级 RESEARCH_REPLAY_VERSION 至 v2；不能在 research-replay-v1 下静默修改。Dataset 内容变化则需独立 dataset_version，不能把研究版本与模型版本混为一谈。

测试覆盖所有时间门槛和严格/含等号边界、naive 拒绝、Decimal 与 no-float JSON、不可变输入、乱序一致、来源追溯、目标硬排除、历史冲突下放、目标 label 冲突、缺失证据、固定 cutoff、coverage 分母，以及 12 场历史 + 1 场目标 + 多源多次报价的完整内存链路。AST import/name 检查、独立进程导入守卫和运行时 DB/文件/网络/时钟守卫保证架构隔离；不需为纯计算构造 Live Snapshot 数据库测试。

本轮只使用 synthetic fixture，没有访问任何互联网历史源，没有历史爬虫、真实数据导入、Research Dataset DB、TeamStats/xG、Elo、Ensemble、Recommendation、ROI/EV、Model Snapshot、公开 API 或前端。

**目前仍不能开展真实三赛季模型优劣结论。** 真实数据获取、时间证据验证、覆盖率检查、canonical identity 审核、持久化导入均未开始；通过 fixture 和回归只证明语义与计算集成，不证明历史源质量或模型效果。
