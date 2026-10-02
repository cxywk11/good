# Open Source Gap Analysis

审计基准：2026-10-02，good main `52e9497a1c532270100bc32e5f63ccd8bbd07603`。本文件按能力而非仓库组织；证据位置、20库评分、许可与源码链接见 [主审计](OPEN_SOURCE_AUDIT.md)，横向状态见 [能力矩阵](OPEN_SOURCE_CAPABILITY_MATRIX.md)。文中的建议均未实施。

## 1. Data Acquisition / 大规模历史来源

**good current state：PARTIAL。** Provider Adapter、HttpTransport Raw-first、解析contract、入库事务、source/probe/evidence工具已有；`research/importer.py`、`repository.py`有不可变SEALED生命周期。真实官方Pilot没有SEALED，历史赔率/统计的时间和权利资格仍不足。不能用“工具存在”代替实际覆盖。

**best OSS reference：** soccerdata的BaseReader、LEAGUE_DICT、SeasonCode；sports-betting的source/RawPayload/schema；ScraperFC仅查provider字段；未来事件解析用kloppy。

**gap：** 稳定合格的实际源、联赛/赛季覆盖、来源ID与本地UUID绑定、quote历史时间证据、raw hash与可追溯版本。没有库能把不存在的历史观察补出来。sports-betting RawPayload有原始bytes，但不是good持久化/visibility机制。

**recommended action：** 先完成lottery.gov.cn真实官方Pilot及Gate A–F；来源层逐个qualified。借鉴league/season参数和列映射，不复制全套scraper。仅当原始响应可在解析前落盘/落库时才评估现成reader；否则保持现有HttpTransport，使用最少的解析适配。禁止为获取历史数据绕过访问限制。

## 2. Entity Resolution / 跨源身份

**current：IMPLEMENTED / 覆盖PARTIAL。** `entities.py`的provider ID→UUID、审核绑定版本和不确定状态已存在；不等于拥有覆盖各联赛的可信对照表。

**best reference：** soccerdata的provider league/season映射、kloppy的provider ID保留，sports-betting身份列。

**gap：** 同名/更名/青年队/女足/中立场、主客翻转、重复比赛与跨provider bookmaker身份。通用字符串替换或fuzzy match无法证明“此比赛属于官方竞彩目标”。

**action：** 保留good审核/绑定与原文证据；只让外部别名生成候选。对bookmaker建立足够明确的同源去重政策后再改善consensus。不要重写已存在的UUID服务，不引入独立实体框架。

## 3. Score Math / Poisson、DC、TTG、HHAD、CRS

**current：IMPLEMENTED；CRS其他概率PARTIAL。** `analysis/score_matrix.py`有50位Decimal、动态Poisson尾界、DC四格、1X2、TTG0–6/7+、整数三项HHAD。已有80位独立阶乘测试，不缺最基本的数学oracle。

**best reference：** SciPy Poisson PMF/SF、goalmodel dDCP、penaltyblog Cython/FootballProbabilityGrid。

**gap：** 外部实现的独立交叉验证；官方CRS HOME/DRAW/AWAY_OTHER聚合；亚洲盘结算另属下一节。TTG完备，不能重复列为待开发。

**action：** 保留score-math-v1，任何数学/截断/映射变更须新版本。设计非对称λ、非零ρ、tail、退化/非法输入golden；penaltyblog public helper交叉项有缺陷，非零ρ暂不作为oracle。不要把float算到“差不多”当作Decimal契约等价。

## 4. Team Strength / 拟合攻防、主场、衰减、ρ与prior

**current：NOT_IMPLEMENTED（训练）；baseline已实现。** `goals_baseline.py`按每队最近20场且至少5场，等权GF/GA平均，ρ固定0；冲突比赛整场排除。没有home/away attack-defense decomposition、优化器、league priors或time decay。

**best reference：** penaltyblog DixonColesGoalModel；goalmodel拟合和rho.ml作独立oracle；bpl-next/footBayes仅后续Bayesian参考。

**gap：** 训练成员选择、识别约束、加权似然、收敛/未知队伍/稀疏联赛处理、训练工件。库能提供优化与概率模型，不能替代时间筛选。

**action：** P1先比较一个带home项的Poisson/DC MLE，固定基线与相同paired sample；参数符号/中心化不同用λ与预测比较，不能直接比较attack系数。先证明数据与拟合有收益再升级priors/Bivariate。停止默认从零开发整套DC求解器；若现成包许可/缺陷/API无法满足准入，先找更窄合法实现或独立数学规格，不复制GPL实现。

## 5. Team Rating / Elo、Pi、Colley

**current：NOT_IMPLEMENTED。** FeatureData的team_strength占位不是评级模型。

**best reference：** elote EloCompetitor与known-values；penaltyblog Elo/Pi作为第二实现；octopy可微Elo只作低优先级研究。

**gap：** 截止时点可见的逐场更新、赛季状态、初值、主场项、三项概率映射及calibration。Elo expected score=胜+半平，不等于单独主胜概率。

**action：** P1用一个普通Elo challenger即可；按结果可用时间更新、同批预测先于更新、保留draw/unseen coverage。不要重复实现十种rating，也不要照搬elote benchmark默认用test history调阈值。Pi变体、可微Elo等待基准显示明确不足。

## 6. xG / xGA

**current：PARTIAL（字段），NOT_IMPLEMENTED（模型与真实统计源）。** TeamMatchStats/NormalizedTeamStats存储xG/xGA；Replay当前past_stats为空。Goals baseline λ是预期进球参数，不是射门模型。

**best reference：** soccerdata Understat用于已有供应商统计；soccer_xg用于射门距离/角度/身体部位特征；StatsBomb/kloppy只提供事件与源字段。

**gap：** 源授权、历史xG统计的可获得时间、坐标和shot标签、供应商口径变更、稳定历史聚合。目标比赛赛后xG不能进入该场赛前特征。

**action：** P2在授权且有时态证据时优先试已有provider xG/xGA作为历史特征；仅在P3有事件需求才考虑自行训练。soccer_xg旧依赖不能直接装入Python3.12；不修复整包作为当前项目任务。

## 7. Odds / 去水、历史、盘口与结算

**current：IMPLEMENTED / PARTIAL。** Decimal赔率、Append-only Observation/Snapshot、market-v1完整选项比例去水、外部1X2等权共识和market gap已实现；cross-provider同bookmaker去重尚缺。AH quarter line解析存在，实际settlement没有。

**best reference：** shin纯函数、implied多方法oracle、penaltyblog概率市场；sports-betting历史API仅供数据层设计参考。

**gap：** 非比例去水对照、bookmaker规范身份、合格逐时赔率历史、完整CRS去水/概率。AH全赢/半赢/走水/半输/全输、void/延期/取消、佣金与结算时间都未实现。

**action：** 不替换比例基线；先P1比较Shin/power且记录方法、失败和相同样本。HHAD是整数三项，AH是二项；quarter半注概率不等于结算状态机。结算口径保留in-house，先真实赔率资格，再谈ROI/CLV。第三方网络只能在acquisition层，永不放model.fit/predict。

## 8. Calibration / 指标口径

**current：IMPLEMENTED（诊断），NOT_IMPLEMENTED（拟合）。** `evaluation.py`有自然对数LogLoss、三类Brier求和、10桶逐类OVR ECE、paired common-match及覆盖。isotonic/Platt/Dirichlet未实现。

**best reference：** sklearn作首选拟合/指标实现；netcal查ECE/temperature定义；dirichletcal仅P2高级对照。

**gap：** 独立时间calibration窗口、冻结工件、样本量/缺类处理、过拟合诊断与复现。ECE低并非预测更好；校准也可能恶化LogLoss。

**action：** P1样本足够时先sigmoid，再测试isotonic；P2才考虑Dirichlet。train→calibrate→test必须时间分离；同比赛快照不可跨边界。不要直接默认StratifiedKFold或copy随机train_test_split示例。PB log2需换算ln；goalmodel p=0为Inf；netcal top-label ECE不是good macro；sklearn dtype epsilon需对齐。保留现有对外指标版本。

## 9. Evaluation / Walk-forward / Bootstrap

**current：PARTIAL。** Replay纯函数、SEALED输入、temporal_split和配对评估已实现；完整窗口编排、每折训练工件/校准、超参选择、置信区间尚缺。

**best reference：** sports-betting要求TimeSeriesSplit与快照负向测试；elote period先预测后更新；SciPy paired/bootstrap统计；sklearn splitter仅作为索引工具。

**gap：** 外层时序测试、内层过去验证、分组/隔离、purge/embargo如存在重叠标签窗口、数据资格/coverage、paired block CI。没有一个候选库满足good全部available_at/visibility治理。

**action：** P1从只读predictive walk-forward runner开始，不捆绑betting engine。固定一个cutoff策略/研究run，所有模型在相同目标池报告coverage和paired差值。Bootstrap按独立单位或预定义时间块；SciPy普通IID对相关快照无效。训练随机seed与库版本必须记录，但不承诺跨平台bitwise一致。

## 10. ROI / Yield / CLV / Drawdown / Bankroll

**current：NOT_IMPLEMENTED。** 不能从market gap直接得到策略Edge或收益。

**best reference：** PB Account、sports-betting收益实现可作反例/最小概念参考，没有完整可直接复用框架。

**gap：** 可成交报价证据、stake/turnover分母、commission、settlement state、open exposure、现金/权益曲线、同market/line/bookmaker closing、缺失率。PB bankroll min/max不是max drawdown，sports-betting按非零returns计数不覆盖所有下注资金。

**action：** P2在独立确认需收益研究后再设计in-house账本。Yield=净收益/实际投入额，bankroll return另命名；CLV不能跨line盲比odds，需固定closing policy。所有赔率/金额持久化Decimal。Kelly/自动投注/推荐逻辑不在本轮或自动后续范围。

## 11. ML / Ensemble

**current：NOT_IMPLEMENTED。** 当前依赖无numpy/scipy/sklearn，FastAPI/SQLAlchemy栈不需要为了“完整”立即扩大。

**best reference：** sklearn简单概率分类/校准，LightGBM单一boosting challenger。

**gap：** 合格三赛季数据、稳定特征、泄漏审计、模型记录和out-of-time基准；不是缺三个boosting adapter。

**action：** P2先一套简单模型和一个LightGBM对照。XGBoost/CatBoost不是本次Top20，不作其源码质量结论，也无需三选全装。Ensemble只有独立out-of-time预测显示互补增益才做；组合权重不能在final test学习。

## 12. Model Registry / Prediction Snapshot

**current：NOT_IMPLEMENTED（正式模型）；MarketModelSnapshot不是Prediction Snapshot。** ADR里的规划不能计为实现。

**best reference：** 外部库save/load/state export只提供工件序列化；没有候选能够代管good的审核/版本与可见性。

**gap：** 自有model_id/version、训练dataset/member hash、训练cutoff、参数/seed/env、模型工件hash、预测feature_snapshot与analysis_visibility关联、明确fail状态。

**action：** 在第一个拟合模型真正接入时实现最少记录字段和冻结预测契约；不先引入通用ML平台或只有一个实现的抽象工厂。参数概率可跨库，外部类实例不能成为API/数据库公共类型。

## 13. Advanced Analytics / SPADL、xT、VAEP、Bayesian

**current：event/SPADL/xT/VAEP NOT_IMPLEMENTED。** Bayesian/prior训练也没有；这些不是当前Pilot先决条件。

**best reference：** kloppy本地多源解析，socceraction SPADL/xT/VAEP；bpl-next与footBayes统计结构。

**gap：** 事件数据许可/采样范围、坐标与身份、完整比赛时序、目标用途，以及NumPy1.x与2.x依赖隔离。高级模型的事件标签与输入有不同时间边界。

**action：** Bayesian仅P2在MLE不足时评估；事件链P3先一种来源+SPADL+xT，再VAEP。不并行建设全部高级模型，不让事件依赖阻塞当前主API。

## 14. Keep In-house / 不能委托的核心边界

必须由good掌握：官方Sporttery目标池及映射、来源资格、Raw-first与append-only、Decimal odds、cutoff与独立提交可见性证明、LIVE_AS_OBSERVED≠RESEARCH_REPLAY、SEALED/manifest hash、冻结FeatureSnapshot、标签隔离、market gap≠Edge、Prediction≠Recommendation、Recommendation Gate、审计/版本/数据授权与规则结算。

这些能力在候选中最多局部存在；保留并完善它们不叫重复造轮子。第三方应适应good的契约；唯一必要的适配是把已审冻结数据变为数值输入，再把概率与诊断变成本地输出。

## 优先级结论

最紧急的gap是**可信真实数据**；随后是**可复现拟合与独立时间评估**；最后才是ML/事件。现有数值基线保持稳定作为benchmark。Phase4建议做顺序和复用策略调整，OLD→NEW及验收条件见 [Reuse Plan](OPEN_SOURCE_REUSE_PLAN.md)，原roadmap和业务代码本轮不改。
