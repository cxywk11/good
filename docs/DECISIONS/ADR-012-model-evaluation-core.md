# ADR-012: Model Evaluation Core

状态：已实施，待人工复核。范围：P4-4C；2026-10-01。

## 目的与边界

`analysis/evaluation.py` 是标准库纯函数模块，只消费调用者已经准备好的不可变 evaluation samples，统一评估已知赛果上的概率质量与校准误差。不查询数据库、OddsSnapshot、FeatureSnapshot、MarketSnapshot、Provider、网络或当前时间；不生成预测、不训练模型，也不做投注决策。没有新表、Migration、持久化评估记录、模型注册表、公开 API 或前端。

`EVALUATION_VERSION = "evaluation-v1"`。指标公式、clipping、数值精度、概率和容差、calibration bins、outcome mapping、样本验证/排除规则、排序及 aggregate 方式任何变化都须升级版本，保留旧版本实现及运行工件。

## 不可变样本与验证

`EvaluationSample(sample_id, match_id, prediction_source, probabilities, actual_result, *, match_time=None)` 是 frozen dataclass。前三项均为非空字符串，ID 由上游生成；sample_id 是不解析的身份标识，未来可包含 cutoff、match_id 与 model_version。概率复制为只读 MappingProxyType，转换为 Decimal 后保留原数值；修改原输入字典不会改变样本。不要求数据库对象存在。

- probabilities 的键必须恰好为 HOME、DRAW、AWAY；值仅接受有限 Decimal 或 Python Decimal 可解析的字符串。拒绝 float、int、bool、NaN、Infinity、负数和大于 1 的值。
- 概率和要求 `abs(HOME + DRAW + AWAY - 1) <= 1e-23`，固定 `PROBABILITY_SUM_TOLERANCE` 与 market-v1 的序列化容差一致，兼容其 24 位小数以及 score-math-v1 的 50 位输出。验证求和按输入小数位扩展临时精度，精确判断容差边界；不将错误概率重新归一化或修改末项残差。
- actual_result 只能是大写 HOME/DRAW/AWAY；模块不读取或解释比分文本。上游负责常规时间赛果口径、匹配及标签质量。
- 同一 `prediction_source + match_id` 重复直接 ValueError，即使 sample_id 不同也拒绝。V1 同一模型的一场比赛只能评估一次；不根据输入顺序选择 cutoff。同一比赛跨模型的 actual_result 矛盾也直接拒绝。
- `evaluate` 只接受单一 prediction_source，禁止混合模型得到一个看似单模型的 aggregate。无效输入导致整次调用失败，不静默丢弃或重复计数。

## 固定数学与输出

计算采用独立 Decimal Context：50 位有效数字、ROUND_HALF_EVEN、Emin=-999999、Emax=999999、capitals=1、clamp=0，固定 traps 与空 flags。异常数值运算显式失败，不返回伪造指标。外部 Decimal Context 不影响结果或被改变。样本按 match_id、prediction_source、sample_id 升序累加；模型键升序输出。整数计数保持整数，核心数值用 `str(Decimal)`，零规范为字符串 `0`，无 float；不量化展示精度。

### Log Loss

每场 `loss = -ln(max(p_actual, LOG_EPSILON))`，自然对数，`LOG_EPSILON = 1e-15`。最终 Log Loss 是各场 loss 的等权算术平均。仅为了数值有限性对实际赛果对应的评估概率设置下限，不设上限裁剪。

`clipping_count` 是原 p_actual **严格小于** epsilon 的场数，包括零；等于 epsilon 不计。原概率、Prediction/Feature/Market Snapshot 不变，Brier 和 Calibration 均使用原概率。非实际赛果上的零概率不计入 clipping_count。

### Multiclass Brier 与 Accuracy

`Brier_sample = Σ_{k∈HOME,DRAW,AWAY} (p_k - 1[actual=k])²`，固定 **sum across 3 classes**，不除以 3。最终再按样本平均。完美预测为 0，极端错误预测可达 2。

Accuracy 使用最大概率分类；完全并列时固定优先 HOME、其次 DRAW、最后 AWAY，即 probability DESC / HOME < DRAW < AWAY。Accuracy=正确分类场数/N，仅为辅助指标，不能替代 Log Loss、Brier 或 Calibration。

### One-vs-rest Calibration 与 ECE

每个 selection 分别固定 10 桶：`[0.0,0.1), [0.1,0.2), ... [0.8,0.9), [0.9,1.0]`。直接比较原概率与边界，0 在首桶，0.1 在第二桶，1 在末桶。

每桶保留 lower_bound、upper_bound、upper_inclusive、count、mean_predicted_probability、actual_frequency、calibration_error。后者是 `abs(mean_probability - actual_frequency)`；频率为该桶中实际发生此 selection 的样本比例。空桶 count=0，其余三个统计值为 null，边界仍保留。

`ECE_selection = Σ_bin (count_bin/N) × abs(mean_probability_bin - actual_frequency_bin)`。分别返回 HOME、DRAW、AWAY，`ece.macro` 是三项的算术平均，不加任意置信度评分。V1 先计算桶均值/频率/绝对差，再按桶序累加加权误差；各步在固定 Context 内进行。

`sample_size=0` 时 Log Loss、Brier、Accuracy、三项 ECE 与 macro 均为 null；clipping_count=0，30 个空桶完整保留，无除零。

## 多模型、配对与 Coverage

`evaluate(samples, *, eligible_samples=None)` 返回 evaluation_version、evaluation_mode、prediction_source、sample_size、eligible_samples、evaluated_samples、coverage、log_loss、brier_score、accuracy、clipping_count、calibration、ece。

`evaluate_models({source: samples, ...}, *, baseline, eligible_samples=None)` 要求调用者显式指定已有的 baseline 名称，不自动决定优胜模型。模型键必须与每个样本的 prediction_source 一致；每个模型先计算自己完整样本集的指标，空模型也保留。eligible_samples 在此接口为按模型名提供的可选计数映射，缺少某模型分母则该模型 coverage=null，未知模型键拒绝。

每个非 baseline 模型均返回一项 paired comparison，只按 match_id 与 baseline 取交集、逐场计算 loss 差、再按共同场数平均。输出 baseline、candidate、common_sample_size、mean_log_loss_difference、mean_brier_difference，以及明确的 `direction="candidate - baseline"`、`negative_means="candidate loss is lower"`。无交集时两项差值为 null。不得将不同样本集的两个全量 aggregate 相减来冒充配对；重复与矛盾赛果在取交集前就拒绝。

每个模型单独报告 eligible_samples、evaluated_samples（等于 sample_size）、coverage。已知正分母时 `coverage=evaluated_samples/eligible_samples`；分母未知或为零时 null，已知正分母且评估数为零时为字符串 0。分母必须是非负 Python int，不能小于 evaluated_samples，拒绝 bool/float。上游须在过滤不可评估预测前确定 eligible 范围；评估器不猜分母，也不能证明各模型的 eligible 样本群相同。Coverage 与共同样本数必须一起看，避免将只预测少量容易比赛的模型与全覆盖模型直接比较。

没有 WINNER、best_model、排名或统计显著性结论；没有 ROI、Yield、CLV、EV、Edge、P_final、Recommendation。投注评估还需要实际投注赔率、Selection Timestamp 与明确策略，当前未建立。

## 纯 Adapter

`market_evaluation_sample(market_data, *, sample_id, match_id, actual_result, match_time=None)` 只读取已冻结 JSON 的 version 与 external_consensus.p_market。p_market=null 返回 None（not evaluable）；绝不从 Sporttery 自身价格补齐外部共识。结构缺失或非空错误概率直接拒绝，不当作可用输入。无需 MarketModelSnapshot 对象或查询。

`goals_evaluation_sample(result, ...)` 只在 status=OK 且 score 非 null 时读取 score.one_x_two，来源保留 result.version。INSUFFICIENT_DATA、OUT_OF_RANGE 或 OK 但无 score 返回 None；未知 status 拒绝。不重新估计 lambda、不调用比分引擎或查询 Feature。两种 adapter 生成的样本均经过统一验证并冻结概率，不修改输入。None 不能直接传入 evaluate，上游显式过滤并保留 eligible 分母；不额外制造预测。

## 时间划分与历史研究边界

`temporal_split(samples, cutoff_date)` 仅提供 past → future 的分组契约：上游明确给出每场比赛的 match_time（比赛时间，如开球时间），必须是带时区 datetime，复制为 UTC；cutoff_date 同样必须带时区。返回两个不可变 tuple，第一组严格 `< cutoff`，第二组 `>= cutoff`。各组按 UTC match_time、match_id、prediction_source、sample_id 升序排列。缺时间不猜，同一 match_id 跨来源时间矛盾拒绝；相同时间位于同一侧。没有随机 train_test_split、训练、拟合、purge window 或回测管道；比赛时间排序本身不能证明输入在当时可见。

当前所有评估固定 `evaluation_mode="FROZEN_SAMPLE_SET"`，不接受调用者改成其他模式。它仅表示评估给定冻结样本集，不保证样本来自真实线上、无泄漏的历史数据，也不能将合成 Golden Case 当作真实回测结果。

现有 `analysis_visibility` 表示“本系统当时实际已经看见的数据”。今天导入 2024 年历史数据，不能生成 2024 年 live-visible FeatureSnapshot；严禁使用 `visible_at = provider published_at` 或其他供应商时间伪造系统可见时间，不能修改旧快照或回填过去的 visibility 凭据。

未来 `LIVE_AS_OBSERVED` 必须有本系统当时的真实可见证据；三赛季历史研究必须另行定义 `RESEARCH_REPLAY` 或 historical_research_dataset，记录研究输入来源、可用性假设和重放规则，与 LIVE_AS_OBSERVED 严格区分。本轮仅记录接口边界和语义，没有实现后两种 evaluation_mode、历史回填或伪回放，也不因增加评估工具放宽 Feature 的 cutoff/visibility 规则。

## Golden Case 与验证

三场实际赛果分别 HOME/DRAW/AWAY，概率分别 `[.7,.2,.1]`、`[.2,.6,.2]`、`[.1,.2,.7]`。手算：Log Loss=`-ln(.294)/3`；每场 Brier 为 .14/.24/.14，均值 `.52/3`；Accuracy=1；HOME ECE=1/5、DRAW ECE=4/15、AWAY ECE=1/5、macro ECE=2/9。测试逐一核验全部桶，包括空桶与同桶多样本。

`tests/test_evaluation.py` 覆盖数学、输入/重复/赛果冲突、精确容差及分桶边界、适配真实纯函数输出、配对交集与方向、coverage、时间拆分、无 I/O、输入不变、顺序确定性、外部 Context 隔离及无 float JSON。SQLite、PostgreSQL 全量回归和静态检查结果见 PHASE4_SPEC 的 P4-4C 验证记录。

当前不能证明 Goals Baseline 优于 Market：这里只有评估数学工具，尚无真实、足量、严格时间语义的历史样本结果。xG、Elo、主客场增强、衰减、rho 拟合、ML、Ensemble、Research Replay、Recommendation 均未实施。
