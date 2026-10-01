# ADR-011: 冻结赛果的 Goals Baseline Lambda Estimator

状态：已实施，待人工复核。范围：P4-4B1；2026-10-01。

## 目的与输入边界

`analysis/goals_baseline.py` 提供纯函数 `estimate_goals_baseline(feature: FeatureData) -> GoalsBaselineResult`。这是第一个透明、可复现的 Goals-only Football Baseline，供后续模型比较；**不能称为最终真实比赛预测**，也没有完成真实历史数据的回测验收。

调用者传入已冻结 FeatureSnapshot 的 `feature_data`，估计器只读取 `context.match.home_team_id/away_team_id` 和 `team_strength.past_results`。不访问 MatchResult、TeamMatchStats、Match、OddsSnapshot、MarketSnapshot、Provider、数据库、网络或时钟；不读取 market、odds_movement、past_stats 或 xG。不按名称猜球队，不使用市场盘口修正 lambda。

Feature 构建器继续负责 analysis_cutoff、analysis_visibility、赛果常规时间语义及目标比赛隔离。现有 p4-features-v1 的 FeatureData 内不含目标 match_id / analysis_cutoff（它们在快照外层），因此估计器不重新查询或重建这些信息。不能把任意拼装的历史列表当作经过可见性验证的 FeatureSnapshot。集成测试从真实构建器冻结快照，验证目标赛果不会进入输入，且后续数据库变化不影响同一冻结输入。

## 固定版本规则

`GOALS_BASELINE_VERSION = "goals-baseline-v1"`。样本选择、去重、加权、最少样本、数值精度、lambda 公式或 rho 策略变化均须升级版本，保留旧版本代码与运行工件。此版本绑定 score-math-v1，引擎版本变化也需升级估计器版本。相同 feature_snapshot_id 的固定内容与 estimator_version 应得到完全相同结果。

1. 目标两队必须具有非空字符串实体 ID，且不能相同。缺失输出 MISSING_HOME_TEAM_ID / MISSING_AWAY_TEAM_ID；相同输出 INVALID_TARGET_TEAMS，状态均为 INSUFFICIENT_DATA。
2. 历史比赛按 match_id 合并。每条必须包含非空 match_id、home_team_id、away_team_id、source；双方不能相同，至少一方属于目标两队。比分必须是非负 Python int，拒绝 bool、float、字符串或缺失比分。finished_at 必须为带时区的 ISO 时间，统一转为 UTC。
3. 无效记录输出 INVALID_RESULT_RECORD；存在可识别 match_id 时保守排除整个比赛，包括该 ID 的其他来源，避免坏记录被丢弃后隐式裁决来源。缺失 match_id 的记录只能记录诊断。多来源球队归属不一致也按无效比赛排除。
4. 同一 match_id 的有效来源比分完全一致，只算一场；保留该场不同 source 的数量 evidence_source_count，重复同一来源不会增加计数或权重。比分不一致则排除整个比赛，输出 CONFLICTING_RESULT_SOURCES 和 excluded_match_ids；不投票、不平均、不按来源优先级、观测新旧或输入顺序选比分。
5. 一致比分的来源若 finished_at 不同，使用最早 UTC finished_at 作为保守的排序时间，不改变比分。按 finished_at DESC、match_id ASC 排序（同一时刻由 ID 打破平局）。来源排列与字典键序不影响结果。
6. 去重与排除完成后，两队分别筛选自己参与的比赛，最多取最近 `MAX_MATCHES_PER_TEAM = 20` 场；没有额外 365 天条件。相互交锋在两队各计一次，不能全局分配给一方。
7. 每队至少 `MIN_MATCHES_PER_TEAM = 5` 场。不足分别输出 INSUFFICIENT_HOME_HISTORY / INSUFFICIENT_AWAY_HISTORY，整体 INSUFFICIENT_DATA，两项 lambda 与 score 均为 NULL，不调用引擎。已有样本仍输出实际场数及进失球率，零样本率为 NULL；目标身份不完整或错误时不建立任何球队历史。

诊断码去重后按字符串升序输出，excluded_match_ids 同样稳定升序；它记录无效/冲突排除，不含因为最近 20 场上限而自然落在窗口外的比赛。冲突存在但两队剩余有效样本仍各达 5 场时，可以继续计算并保留诊断。

## 进失球率、lambda 与 rho

所有入选比赛等权。目标球队在历史主场时 GF=home_score、GA=away_score；在历史客场时反过来。当前目标的 HOME/AWAY 身份不改变历史方向。

```text
GF_rate = Σ goals_for / matches_used
GA_rate = Σ goals_against / matches_used
lambda_home = (home_team_GF_rate + away_team_GA_rate) / 2
lambda_away = (away_team_GF_rate + home_team_GA_rate) / 2
rho = 0
rho_source = "fixed-zero-v1"
```

不拆主客场历史、不加主场优势、不做时间衰减、联赛权重、league/Bayesian prior 或 shrinkage；不硬编码平均进球数，不用默认 1.5/1.2 补缺失，不混用部分 xG 和部分进球。整数求和精确，率与 lambda 使用独立 Decimal Context：50 位有效数字、ROUND_HALF_EVEN、Emin=-999999、Emax=999999、capitals=1、clamp=0，固定 traps 和空 flags。率先按此精度计算，再代入 lambda 公式；无额外量化，输出 `str(Decimal)`，没有 float。外部 Context 的精度、舍入、指数范围、traps/flags 既不影响结果，也不会被修改。

rho 固定零，含义为 Independent Poisson Football Baseline；没有估计或校准 Dixon–Coles rho。

## 引擎及结果

只有两队样本均合格、状态 OK 时，调用既有 `build_score_matrix(lambda_home, lambda_away, Decimal("0"))`。不从盘口提取 handicap lines，因此 score.handicap 为空；1X2、总进球、TTG 均保留引擎原样返回的同矩阵结果。

若引擎抛 TailToleranceError，返回 OUT_OF_RANGE 与 SCORE_ENGINE_RANGE_EXCEEDED，score=NULL，保留实际估出的 lambda 和球队历史。禁止 clamp、改成 6、改尾部容差、扩大 cap 或默认回退；score-math-v1 保持不变。

结果为 JSON-ready TypedDict：version、status、两队 ID、home_history/away_history、lambda_home/lambda_away、rho、rho_source、score_engine_version、score、diagnostics、excluded_match_ids。每队历史包含 matches_used、按选样顺序排列的 match_ids、逐场 evidence_source_count、gf_rate、ga_rate。version 保存 goals-baseline-v1，score_engine_version 保存 score-math-v1。结果没有 P_final、Edge、EV、信心等级或推荐语义。

## Golden Case 与验证

手算样例：Home 的 GF=[2,1,3,0,4]、GA=[1,1,2,1,0]，率为 (2,1)；Away 的 GF=[1,1,2,1,0]、GA=[2,2,1,1,4]，率为 (1,2)。历史主客场交错，最终 lambda=(2,1)，rho=0，score 与 `build_score_matrix(Decimal("2"), Decimal("1"), Decimal("0"))` 完全相同。另有攻防率不相同的案例检验双方进攻与对手防守确实各占一半。

`tests/test_goals_baseline.py` 覆盖样本筛选、去重/冲突、无效数据、最近 20 场与最少 5 场、目标隔离、两队共用交锋、Decimal 隔离、矩阵派生、字段访问限制、无 I/O、输入不变和稳定诊断。SQLite / PostgreSQL 全量回归与 Ruff / mypy 结果记入 PHASE4_SPEC。

本阶段不增加表、Migration、Model Snapshot、HTTP 预测 API 或前端。不实现 xG、Elo、ML、自动 rho 拟合、Ensemble、Calibration 或投注功能。后续真实历史覆盖、来源裁决、时间拆分回测和正式模型快照需另行评审授权；当前仅建立比较基准。
