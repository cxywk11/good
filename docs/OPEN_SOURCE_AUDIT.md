# Open Source Reference & Reuse Audit

审计日期：2026-10-02（Asia/Shanghai）。本次只交付文档，不安装依赖、不复制第三方源码、不修改业务实现。

## Current Capability Inventory

先完成本节，再发现外部候选。基准为 `main` / `origin/main` / GitHub `refs/heads/main` 一致的 `52e9497a1c532270100bc32e5f63ccd8bbd07603`；开始时工作区干净。以下状态由代码而非 roadmap 判定。`IMPLEMENTED` 表示范围内有实际实现，不代表真实生产数据验收完成；`PARTIAL` 表示只有边界、部分路径或尚缺真实来源；`NOT_IMPLEMENTED` 表示未找到对应实现。

| 能力 | 状态 | 代码定位与实际边界 |
|---|---|---|
| Phase 0–3 数据底座 | IMPLEMENTED / 真实源验收 PARTIAL | `providers/`、`ingestion.py`、`entities.py`、`odds.py`、`models.py`；Mock 链路具备，真实源/Docker/Redis 验收不是已完成事实 |
| Provider Adapter | IMPLEMENTED | `providers/base.py:OddsProvider`、`registry.py:providers`；体彩为唯一主池；The Odds API 为补充；默认历史/赛果路径显式拒绝 |
| Raw-first ingestion | IMPLEMENTED | `providers/http.py:HttpTransport.fetch` 先 `record`，`ingestion.py` 独立 Raw 事务；Research importer 先 source/Raw 后成员 |
| Entity Resolution / 跨源球队映射 | IMPLEMENTED / 覆盖 PARTIAL | `entities.py:bind_team/resolve_mapping`；provider ID→UUID、审核及绑定版本已实现，缺 ID 不造假；不代表拥有通用跨站球队对照表 |
| Append-only Odds | IMPLEMENTED | `odds.py:store_quotes`、`models.py:OddsSnapshot`、数据库不可变迁移；报价 dedup 与观察记录分开 |
| Odds Observation / Snapshot | IMPLEMENTED | `OddsObservation`、`OddsKeySnapshot`、`finalize_keys`；FIRST_OBSERVED 不等同 PROVIDER_OPEN；不补造错过的阈值 |
| Historical cutoff | IMPLEMENTED | `odds.py:visible_at/mapping_visibility` 是展示历史边界；建模必须用更严格的 `analysis/features.py` 与 `visibility.py` |
| P4-2 FeatureSnapshot / analysis_cutoff / analysis_visibility | IMPLEMENTED | `features.py:get_or_create_snapshot`、`visibility.py:record_visibility/temporal/proven`；独立连接证明已提交可见，禁止倒填 |
| P4-3 Market Probability / proportional de-vig | IMPLEMENTED | `market.py:ProportionalNormalization/source_market/build_market_data`；50 位 Decimal、完整选项、逐源去水 |
| external consensus / market gap | IMPLEMENTED | `market.py:consensus`；完整外部 1X2 等权，体彩排除；gap 不是 Edge；bookmaker 跨 provider 去重尚缺 |
| P4-4A Poisson score matrix | IMPLEMENTED | `score_matrix.py:poisson_marginal/build_score_matrix`；显式 Decimal λ、动态尾界、cap=30，无法满足尾界时报错 |
| Dixon–Coles mathematical correction | IMPLEMENTED | `build_score_matrix` 四格 τ 校验与统一归一化；不拟合参数 |
| 1X2 / TTG / HHAD derivation | IMPLEMENTED | `three_way_handicap` 与 `build_score_matrix`；整数三项 HHAD、0–6/7+ TTG；不是亚洲盘结算 |
| P4-4B1 Goals-only λ baseline | IMPLEMENTED | `goals_baseline.py:estimate_goals_baseline`；每队最近20/至少5场、等权GF/GA、跨源冲突整场排除、ρ=0 |
| Team strength / 主客场攻防分解 / time decay / league priors | NOT_IMPLEMENTED | 上述基线是 `(本队GF+对手GA)/2`；`FeatureData.team_strength.rating=None`，无拟合攻防参数、主场项、衰减或 prior |
| Elo / Pi Rating / Dixon–Coles ρ estimation | NOT_IMPLEMENTED | 无训练/更新代码；ρ 是调用参数或固定零，不是估计结果 |
| xG / xGA | PARTIAL | `providers/contracts.py:NormalizedTeamStats`、`models.py:TeamMatchStats`、`results.py:store_post_match` 支持字段；无真实统计 Provider、xG训练/推理；Replay `past_stats=[]` |
| event data / xT / VAEP | NOT_IMPLEMENTED | 无事件 contract、SPADL 或事件模型 |
| P4-4C Log Loss / Brier / Calibration / ECE / Paired evaluation | IMPLEMENTED | `evaluation.py:evaluate/_losses/_calibration/evaluate_models`；三类Brier求和、固定10桶、共同match_id配对、coverage |
| probability calibration fitting / isotonic / Platt / Dirichlet | NOT_IMPLEMENTED | Calibration/ECE 是诊断，不是校准器拟合 |
| ML / LightGBM / XGBoost / CatBoost / Ensemble | NOT_IMPLEMENTED | 全局源码检索及依赖清单无实现 |
| Model registry / Prediction snapshot | NOT_IMPLEMENTED | ADR-005/007 为规划；`MarketModelSnapshot` 已有，但不能当成正式 Prediction/model registry |
| P4-4D1 Research Replay | IMPLEMENTED | `research_replay.py:ResearchDataset/build_research_feature/run_research_evaluation`；frozen contract、目标标签隔离、单一cutoff、`live_visibility_proven=false` |
| P4-4D2A Research Dataset Persistence / Raw provenance / SEALED | IMPLEMENTED | `research/contracts.py:validate_import/dataset_content_hash`、`importer.py:import_research_dataset`、`repository.py:seal_dataset/load_research_dataset/verified_sporttery_targets`；六张独立Core研究表 |
| P4-4D2B Historical source qualification | PARTIAL | `official_evidence.py:intake_official_evidence`、`probe_manifest.py:build_probe_manifest`、`vipc_evidence.py:inspect_vipc_history`、`research/providers/inspection.py`；检查工具存在，实际时间语义/授权/官方目标仍不等同 VERIFIED |
| walk-forward backtesting | PARTIAL | `evaluation.py:temporal_split` 和纯Replay存在；没有滚动训练/验证/测试窗口、调参和训练工件管理 |
| CLV / ROI / Yield / Max Drawdown / Bootstrap CI | NOT_IMPLEMENTED | 无投注账本、结算、置信区间或资金曲线实现 |
| Asian handicap settlement / quarter handicap / push / half-win / half-loss | PARTIAL（盘口）；NOT_IMPLEMENTED（结算） | `providers/parsing.py:parse_line` 与 `market.py:read_quote` 支持0.25线、符号规范化；未实现结算状态或收益 |
| complete TTG mapping | IMPLEMENTED | `SportteryProvider.selection_name` + `score_matrix.build_score_matrix`；八项完备，不需要再造 |
| complete CRS mapping | PARTIAL | `selection_name` 能解析比分及HOME/DRAW/AWAY_OTHER；概率层未聚合官方比分“其他”，`market-v1` 不支持CRS去水 |
| large-scale football data acquisition | PARTIAL | 有Adapter、Raw、重试限流基础；无已核验三赛季研究数据、规模化赛事历史或事件采集 |

代码路径在未注明前缀时相对 `apps/api/src/jc/`。检查了 README、ARCHITECTURE、DATA_MODEL、CONSTITUTION、BACKLOG、PHASE4_SPEC、ADR-001～014，以及 analysis/research/providers、odds/results/models 和关联测试。文档历史段落存在旧阶段“未实施”措辞，本表以当前代码及后续验收段为准。真实 Pilot 阻塞不因本次开源调研被解除。

## 审计结论与范围

**结论选 C：当前自主实现合理；下一阶段若自行重写成熟拟合器、校准器和事件标准化，会出现可避免的重复。** good 的主要资产是可信数据与时态契约，而不是通用统计库。现有 `score-math-v1`、`market-v1`、配对评估应保留；开源组件接在这些边界内。当前最大阻塞仍是真实官方 Pilot，增加模型不会解除阻塞。

本次发现 **135 个去重候选条目**（含搜索噪声），按相关性/范围初筛出 **23 个重点候选**；最终完成 **20 个完整深审档案**，另对 seed soccerapi 做排除性代码检查，旧 bpl 与 LanusStats 在元数据阶段排除。112 个未晋级候选没有做源码质量判定，不能将135称作已审计项目。机器证据账本包含候选名单、路径、SHA、版本、评分和能力状态。

检索覆盖 GitHub Repository Search、Code Search、足球分析 topic 条件，以及 football prediction / soccer data / Dixon Coles / Elo / odds scraper / implied / sports backtest / Bayesian 等查询。以仓库自身源码为主证据，GitHub metadata/commit/release/issues、PyPI metadata 和源方协议为辅；没有使用第三方榜单。只抽读与任务相关的实现、代表测试、CI与示例，不声称逐行审过全部文件。没有安装或运行第三方软件，没有现场测量预测精度、性能、CI成功率或网站可达性。

| 类别 | 最低要求 | 最终覆盖数 | 代表项目 |
|---|---:|---:|---|
| A 数据采集/事件适配 | 4 | 7 | soccerdata、ScraperFC、statsbombpy、kloppy、socceraction、penaltyblog、sports-betting |
| B 足球比分模型 | 4 | 5 | penaltyblog、goalmodel、bpl-next、footBayes、octopy |
| C 球队评级 | 2 | 3 | penaltyblog、elote、octopy |
| D 赔率/市场 | 3 | 6 | penaltyblog、soccerdata、shin、implied、sports-betting、octopy |
| E 评估/回测 | 3 | 13 | SciPy、sklearn、netcal、Dirichlet 等；通用组件不是完整足球回测器 |
| F 高级足球分析 | 2 | 4 | socceraction、soccer_xg、kloppy、statsbombpy（字段/数据，非自行训练xG） |

### Seeds 的实际去留

| Seed | 决定 | 证据 |
|---|---|---|
| penaltyblog | 入选，最高复用价值但先作reference | 有完整拟合/概率代码；公开DC helper缺陷、依赖许可与CI触发范围需限制 |
| soccerdata | 入选，架构参考 | 多源reader/season/cache真实存在；时态证据弱于good |
| socceraction | 入选，P3参考 | SPADL/xT/VAEP真实实现；当前缺事件数据且依赖旧 |
| octopy | 入选，低分研究参考 | 非纯Notebook，有JAX可微Elo；许可冲突/同名包风险，明确不生产采用 |
| soccerapi | **排除** | README明确说明大多数scraper已坏；核心与测试过旧，没有严格报价历史/观察时间 |

排除项目 [S1M0N38/soccerapi](https://github.com/S1M0N38/soccerapi)：179 stars / 36 forks，MIT；HEAD `88c6733cf65f55145d7d07910756241f7710786f`（2022-02-16 README），最近核到的核心修改 `2421191e78f615c2d261b6a31600a4795d0e07f1`（2021-02-24），无 GitHub release。实际检查 README、LICENSE、pyproject.toml、基础Api与bookmaker实现、网络测试/旧3.7–3.9 CI。其 odds 合并依赖列表位置/名称，日期是赛事时间，未构成历史quote证明。复用决定 **DO_NOT_USE**，三个风险均HIGH。旧 anguswilliams91/bpl（GPL-3、旧实现）由 bpl-next 替代；LanusStats仅元数据筛查，license UNKNOWN，不做源码质量评价。

## Top 20（Exactly 20）

按下面固定加权得分降序排列。排名是对 **good 的复用价值**，不等同库的绝对质量或生产准入；许可证/数据资格仍是独立硬门槛。Top5立即利用指阅读、设计交叉验证与规划，本轮没有安装/接入。

| Rank | Repository | Category | Stars | License | Reuse Score | Reuse Type | Main Value | Integration Cost | Risk（数据/维护/泄漏） |
|---|---|---|---:|---|---:|---|---|---|---|
| 1 | [martineastwood/penaltyblog](https://github.com/martineastwood/penaltyblog) | A/B/C/D/E | 228 | MIT | 86 | REFERENCE_IMPLEMENTATION | 足球比分拟合、概率市场、评级、去水、采集与回测的综合工具包。 | 中：只做离线 oracle；整包接入高 | MEDIUM/MEDIUM/HIGH |
| 2 | [scipy/scipy](https://github.com/scipy/scipy) | E | 15068 | BSD-3-Clause | 85 | DEPENDENCY_CANDIDATE | 数值分布、优化和统计重采样基础库，不是足球预测产品。 | 低至中：通用数值 API，二进制栈较大 | LOW/LOW/MEDIUM |
| 3 | [scikit-learn/scikit-learn](https://github.com/scikit-learn/scikit-learn) | E | 67444 | BSD-3-Clause | 84 | DEPENDENCY_CANDIDATE | 分类、指标、预处理与校准的通用标准实现。 | 中：统一分类/校准 API，但时间切分必须自控 | LOW/LOW/HIGH |
| 4 | [probberechts/soccerdata](https://github.com/probberechts/soccerdata) | A/D | 2096 | Apache-2.0 + retained MIT notice | 81 | ARCHITECTURE_REFERENCE | 多来源足球采集，覆盖 FBref、Understat、WhoScored、football-data 等。 | 中至高：浏览器/TLS栈与来源资格审查 | HIGH/HIGH/HIGH |
| 5 | [wdm0006/elote](https://github.com/wdm0006/elote) | C/E | 33 | MIT | 78 | DEPENDENCY_CANDIDATE | Elo、Colley 等成对竞技评级与顺序评估工具。 | 中：评级易用；三项概率与时间状态要包装 | LOW/MEDIUM/HIGH |
| 6 | [mberk/shin](https://github.com/mberk/shin) | D | 105 | MIT | 77 | DEPENDENCY_CANDIDATE | 实现 Shin bookmaker margin removal 的专门库。 | 低：小型数值 API；需匹配 Rust wheel | LOW/MEDIUM/LOW |
| 7 | [PySport/kloppy](https://github.com/PySport/kloppy) | A/F | 557 | BSD-3-Clause | 76 | DEPENDENCY_CANDIDATE | 多供应商事件/追踪格式解析、坐标转换和统一领域对象。 | 中至高：事件领域模型和后续数据成本 | HIGH/MEDIUM/HIGH |
| 8 | [lightgbm-org/LightGBM](https://github.com/lightgbm-org/LightGBM) | E | 18826 | MIT | 75 | DEPENDENCY_CANDIDATE | 梯度提升决策树；未来表格特征模型候选，不是开箱足球预测。 | 中：C++/OpenMP 与训练验证流程 | LOW/MEDIUM/HIGH |
| 9 | [georgedouzas/sports-betting](https://github.com/georgedouzas/sports-betting) | A/D/E | 804 | MIT | 74 | ARCHITECTURE_REFERENCE | 数据加载、赔率历史、模型回测和投注执行框架；本审计仅评价数据/评估部分。 | 高：框架包含数据/策略/执行，边界不同 | MEDIUM/MEDIUM/HIGH |
| 10 | [ML-KULeuven/socceraction](https://github.com/ML-KULeuven/socceraction) | A/E/F | 817 | MIT | 73 | REFERENCE_IMPLEMENTATION | 事件数据转 SPADL、网格 xT 和动作价值 VAEP。 | 高：旧科学栈与事件数据 | HIGH/HIGH/HIGH |
| 11 | [opisthokonta/goalmodel](https://github.com/opisthokonta/goalmodel) | B/E | 116 | GPL-3.0 (DESCRIPTION) | 71 | REFERENCE_IMPLEMENTATION | R 足球进球模型：攻防/主场项、DC校正及多种进球分布。 | 中：R环境，仅独立参考 | LOW/HIGH/MEDIUM |
| 12 | [opisthokonta/implied](https://github.com/opisthokonta/implied) | D | 9 | GPL-3.0 (DESCRIPTION) | 70 | REFERENCE_IMPLEMENTATION | 多种赔率去水与逆变换，包含 Shin/power/additive/odds-ratio/JS 等。 | 低至中：离线R结果参考 | LOW/MEDIUM/LOW |
| 13 | [anguswilliams91/bpl-next](https://github.com/anguswilliams91/bpl-next) | B | 5 | MIT | 69 | REFERENCE_IMPLEMENTATION | 基于NumPyro/JAX的Bayesian足球比分模型，旧bpl的后续项目。 | 高：JAX/NumPyro与版本生态 | LOW/HIGH/HIGH |
| 14 | [EFS-OpenSource/calibration-framework](https://github.com/EFS-OpenSource/calibration-framework) | E | 379 | Apache-2.0 | 68 | REFERENCE_IMPLEMENTATION | netcal校准方法与ECE/ACE/MCE等置信度诊断。 | 高：Torch/Pyro/GPyTorch依赖 | LOW/MEDIUM/HIGH |
| 15 | [LeoEgidi/footBayes](https://github.com/LeoEgidi/footBayes) | B/E | 59 | GPL-2.0 (DESCRIPTION) | 67 | REFERENCE_IMPLEMENTATION | R/Stan足球概率模型，支持DC与动态层次模型、不同prior与推断方法。 | 高：R+CmdStan编译/采样 | LOW/HIGH/HIGH |
| 16 | [dirichletcal/dirichlet_python](https://github.com/dirichletcal/dirichlet_python) | E | 33 | MIT | 63 | REFERENCE_IMPLEMENTATION | 多类Dirichlet校准：log概率上线性映射再softmax。 | 中至高：JAX依赖/小项目/源码包 | LOW/HIGH/HIGH |
| 17 | [oseymour/ScraperFC](https://github.com/oseymour/ScraperFC) | A | 412 | GPL-3.0 | 60 | ARCHITECTURE_REFERENCE | Sofascore、Understat、FBref、ClubElo等足球数据采集。 | 高：浏览器爬取栈/GPL/来源维护 | HIGH/HIGH/HIGH |
| 18 | [ML-KULeuven/soccer_xg](https://github.com/ML-KULeuven/soccer_xg) | E/F | 260 | Apache-2.0 | 52 | REFERENCE_IMPLEMENTATION | 射门级xG训练与特征pipeline，区分运动战/任意球/点球。 | 高：2020科学栈与Py312不兼容 | HIGH/HIGH/HIGH |
| 19 | [hudl/statsbombpy](https://github.com/hudl/statsbombpy) | A/F | 745 | UNKNOWN code / Custom data | 51 | DO_NOT_USE | StatsBomb官方Python数据访问客户端，公开/订阅API与事件DataFrame。 | 高：代码许可未明确，数据用途受限 | HIGH/HIGH/HIGH |
| 20 | [octosport/octopy](https://github.com/octosport/octopy) | B/C/D/E | 76 | MIT file / Apache-2.0 manifest conflict | 38 | REFERENCE_IMPLEMENTATION | 研究型足球Poisson、去水和可微Elo实验。 | 高：旧JAX、许可冲突、包名碰撞 | MEDIUM/HIGH/HIGH |

### 评分明细与风险口径

满分依次为：Current project relevance **25**；Code quality **15**；Architecture compatibility **15**；Maturity/tests **10**；Maintenance **10**；License friendliness **10**；Integration cost **10**（高分=成本低）；Unique capability **5**。主观工程评分，不是性能实验；同一包的pure math路径与联网路径风险不同，本表按文中拟议使用范围及容易误用的默认行为评分。

DATA_LEGAL_RISK：LOW=无内置数据采集或已受控输入，MEDIUM=需逐源确认，HIGH=限制明显或来源使用权未满足。TECHNICAL_MAINTENANCE_RISK：结合依赖、API、测试和更新。LEAKAGE_RISK：LOW=纯确定性数值函数，MEDIUM=调用方需配置采样/时间，HIGH=默认切分/网络当前态/历史时间缺失会直接误导。LOW不是数据许可证明；HIGH也不等于发现恶意。

| Repo | 相关25 | 质量15 | 架构15 | 测试10 | 维护10 | 许可10 | 成本10↑ | 独特5 | 合计 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| PB | 25 | 11 | 13 | 8 | 9 | 9 | 6 | 5 | 86 |
| SP | 18 | 15 | 14 | 10 | 10 | 10 | 5 | 3 | 85 |
| SK | 21 | 14 | 12 | 10 | 10 | 10 | 4 | 3 | 84 |
| SD | 24 | 12 | 10 | 8 | 8 | 10 | 5 | 4 | 81 |
| EL | 20 | 12 | 11 | 8 | 9 | 10 | 5 | 3 | 78 |
| SH | 19 | 12 | 13 | 8 | 6 | 10 | 6 | 3 | 77 |
| KL | 17 | 14 | 12 | 9 | 9 | 10 | 2 | 3 | 76 |
| LG | 16 | 14 | 10 | 10 | 9 | 10 | 4 | 2 | 75 |
| SB | 23 | 11 | 8 | 8 | 9 | 10 | 2 | 3 | 74 |
| SA | 19 | 13 | 10 | 8 | 4 | 10 | 4 | 5 | 73 |
| GM | 23 | 12 | 10 | 7 | 3 | 4 | 7 | 5 | 71 |
| IM | 21 | 11 | 10 | 7 | 7 | 4 | 6 | 4 | 70 |
| BP | 22 | 10 | 9 | 5 | 8 | 10 | 1 | 4 | 69 |
| NC | 19 | 11 | 8 | 4 | 7 | 10 | 5 | 4 | 68 |
| FB | 19 | 12 | 8 | 7 | 8 | 4 | 4 | 5 | 67 |
| DC | 17 | 11 | 9 | 6 | 3 | 10 | 3 | 4 | 63 |
| SF | 21 | 10 | 7 | 6 | 6 | 4 | 3 | 3 | 60 |
| XG | 15 | 9 | 7 | 4 | 1 | 10 | 1 | 5 | 52 |
| ST | 19 | 9 | 7 | 4 | 8 | 0 | 1 | 3 | 51 |
| OC | 16 | 6 | 5 | 3 | 1 | 2 | 1 | 4 | 38 |

## 逐仓库深审

以下源码链接固定到所读SHA；星数/分叉数为2026-10-02查询快照。Last meaningful commit排除纯README/CI机器人更新时间，列最近核实到的功能或兼容性修改；不是`pushed_at`。Active/Maintenance/Dormant为审计判断；20个仓库的GitHub archived字段均false。CI“存在”不代表本轮运行通过。GH release与PyPI最新版本分别列出，不将main的源码行为未经检查套到发行版。

### 1. martineastwood/penaltyblog · PB · 86/100

| 基础信息 | 核实结果 |
|---|---|
| Repository / main language | [martineastwood/penaltyblog](https://github.com/martineastwood/penaltyblog) / Python |
| CODE_LICENSE / stars / forks | MIT / 228 / 32 |
| Source SHA | [72de6519e0c9a357b8b1aa2a6441a454b18ff54e](https://github.com/martineastwood/penaltyblog/tree/72de6519e0c9a357b8b1aa2a6441a454b18ff54e) |
| Last meaningful commit | [2026-09-29 · feat: add Football Charts scraper with league mappings and data retrieval](https://github.com/martineastwood/penaltyblog/commit/60916c4c6f0773eb2fd6854fb84238df79e9ff13) |
| Last GitHub release | [v1.13.0](https://github.com/martineastwood/penaltyblog/releases/tag/v1.13.0) · 2026-10-01 |
| Status / package / Python | Active；[PyPI penaltyblog 1.13.0](https://pypi.org/project/penaltyblog/1.13.0/)，Requires-Python：>=3.10 |
| Test suite / CI | 有拟合、概率网格与指标测试；test.yml 覆盖三系统/Python 3.10–3.13，但当前只启用 workflow_dispatch，不能称每次提交自动通过。部分拟合测试标记 local。 |
| Documentation | README、模型示例 notebook、Sphinx API；未见独立性能基准目录。 |
| Reuse / risks | **REFERENCE_IMPLEMENTATION**；DATA_LEGAL_RISK=MEDIUM；TECHNICAL_MAINTENANCE_RISK=MEDIUM；LEAKAGE_RISK=HIGH |

1. **What it does**：足球比分拟合、概率市场、评级、去水、采集与回测的综合工具包。
2. **Core modules**：models/dixon_coles.py:DixonColesGoalModel；poisson.py:PoissonGoalsModel；bivariate_poisson.py；football_probability_grid.py:FootballProbabilityGrid/create_dixon_coles_grid；ratings/elo.py、pi.py；implied/implied.py。
3. **Code inspected**：[penaltyblog/models/base_model.py](https://github.com/martineastwood/penaltyblog/blob/72de6519e0c9a357b8b1aa2a6441a454b18ff54e/penaltyblog/models/base_model.py)；[penaltyblog/backtest/backtest.py](https://github.com/martineastwood/penaltyblog/blob/72de6519e0c9a357b8b1aa2a6441a454b18ff54e/penaltyblog/backtest/backtest.py)；[penaltyblog/backtest/account.py](https://github.com/martineastwood/penaltyblog/blob/72de6519e0c9a357b8b1aa2a6441a454b18ff54e/penaltyblog/backtest/account.py)；[penaltyblog/ratings/elo.py](https://github.com/martineastwood/penaltyblog/blob/72de6519e0c9a357b8b1aa2a6441a454b18ff54e/penaltyblog/ratings/elo.py)；[penaltyblog/ratings/pi.py](https://github.com/martineastwood/penaltyblog/blob/72de6519e0c9a357b8b1aa2a6441a454b18ff54e/penaltyblog/ratings/pi.py)；[penaltyblog/implied/implied.py](https://github.com/martineastwood/penaltyblog/blob/72de6519e0c9a357b8b1aa2a6441a454b18ff54e/penaltyblog/implied/implied.py)；[penaltyblog/models/bayesian_goal_model.py](https://github.com/martineastwood/penaltyblog/blob/72de6519e0c9a357b8b1aa2a6441a454b18ff54e/penaltyblog/models/bayesian_goal_model.py)；[test/test_football_probability_grid.py](https://github.com/martineastwood/penaltyblog/blob/72de6519e0c9a357b8b1aa2a6441a454b18ff54e/test/test_football_probability_grid.py)；[penaltyblog/scrapers/footballdata.py](https://github.com/martineastwood/penaltyblog/blob/72de6519e0c9a357b8b1aa2a6441a454b18ff54e/penaltyblog/scrapers/footballdata.py)；[penaltyblog/models/bivariate_poisson.py](https://github.com/martineastwood/penaltyblog/blob/72de6519e0c9a357b8b1aa2a6441a454b18ff54e/penaltyblog/models/bivariate_poisson.py)；[test/test_model_dixon_coles.py](https://github.com/martineastwood/penaltyblog/blob/72de6519e0c9a357b8b1aa2a6441a454b18ff54e/test/test_model_dixon_coles.py)；[penaltyblog/metrics/metrics.pyx](https://github.com/martineastwood/penaltyblog/blob/72de6519e0c9a357b8b1aa2a6441a454b18ff54e/penaltyblog/metrics/metrics.pyx)；[penaltyblog/scrapers/base_scrapers.py](https://github.com/martineastwood/penaltyblog/blob/72de6519e0c9a357b8b1aa2a6441a454b18ff54e/penaltyblog/scrapers/base_scrapers.py)；[penaltyblog/models/hierarchical_bayesian_goal_model.py](https://github.com/martineastwood/penaltyblog/blob/72de6519e0c9a357b8b1aa2a6441a454b18ff54e/penaltyblog/models/hierarchical_bayesian_goal_model.py)；[penaltyblog/models/poisson.py](https://github.com/martineastwood/penaltyblog/blob/72de6519e0c9a357b8b1aa2a6441a454b18ff54e/penaltyblog/models/poisson.py)；[penaltyblog/models/football_probability_grid.py](https://github.com/martineastwood/penaltyblog/blob/72de6519e0c9a357b8b1aa2a6441a454b18ff54e/penaltyblog/models/football_probability_grid.py)；[penaltyblog/models/probabilities.pyx](https://github.com/martineastwood/penaltyblog/blob/72de6519e0c9a357b8b1aa2a6441a454b18ff54e/penaltyblog/models/probabilities.pyx)；[README.md](https://github.com/martineastwood/penaltyblog/blob/72de6519e0c9a357b8b1aa2a6441a454b18ff54e/README.md)；[LICENCE](https://github.com/martineastwood/penaltyblog/blob/72de6519e0c9a357b8b1aa2a6441a454b18ff54e/LICENCE)；[pyproject.toml](https://github.com/martineastwood/penaltyblog/blob/72de6519e0c9a357b8b1aa2a6441a454b18ff54e/pyproject.toml)；[setup.py](https://github.com/martineastwood/penaltyblog/blob/72de6519e0c9a357b8b1aa2a6441a454b18ff54e/setup.py)；[.github/workflows/test.yml](https://github.com/martineastwood/penaltyblog/blob/72de6519e0c9a357b8b1aa2a6441a454b18ff54e/.github/workflows/test.yml)；[penaltyblog/models/dixon_coles.py](https://github.com/martineastwood/penaltyblog/blob/72de6519e0c9a357b8b1aa2a6441a454b18ff54e/penaltyblog/models/dixon_coles.py)；[penaltyblog/models/utils.py](https://github.com/martineastwood/penaltyblog/blob/72de6519e0c9a357b8b1aa2a6441a454b18ff54e/penaltyblog/models/utils.py)；[docs/models/example.ipynb](https://github.com/martineastwood/penaltyblog/blob/72de6519e0c9a357b8b1aa2a6441a454b18ff54e/docs/models/example.ipynb)；[penaltyblog/betting/kelly.py](https://github.com/martineastwood/penaltyblog/blob/72de6519e0c9a357b8b1aa2a6441a454b18ff54e/penaltyblog/betting/kelly.py)。
4. **Strengths**：已有加权攻防、主场项与ρ联合极大似然拟合；Cython 概率计算；多市场与评级 API，可显著减少统计模型探索。
5. **Weaknesses**：公开 DC helper 的两个交叉项与底层 Cython/数学公式不一致；float64、固定截断不等同 good 的 Decimal/动态尾界；整包依赖多，含许可证未确认的 statsbombpy。 DC拟合loss把τ裁到epsilon后取log，且参数bounds未逐场强制τ非负；因此成功收敛仍须独立检查所有预测格子的合法性。
6. **What overlaps good**：score_matrix.py 的 Poisson/DC 四格数学、1X2/总进球，以及 market.py 的比例去水、evaluation.py 的 Brier；这些 good 已经实现。
7. **What good lacks**：good 尚缺可估计攻防/主场项/ρ、time decay、Bivariate/Bayesian、Elo/Pi 和 RPS；这些是该库的主要增量。
8. **What should be reused**：先读拟合目标、约束、权重和指标；用独立公式+SciPy+经确认的 Cython 路径交叉核验，公开 helper 暂不作为非零ρ金标准。
9. **What should NOT be reused**：不搬 scraper 缓存、binary Account 结算、推荐/staking；不把期望进球 λ 标成 shot-level xG；不改 good 现有数学引擎。
10. **Integration approach**：P0 仅设计 oracle；P1 在 SEALED 数据上离线评估拟合，锁定版本/截止时间/队伍顺序/截断/收敛诊断，经自有 Prediction Contract 输出；整包生产依赖暂缓。
11. **License**：MIT 允许依赖和复制修改并保留版权/许可；本轮不复制。传递依赖 statsbombpy 的代码许可 UNKNOWN，使整包生产准入未过。 [实际许可证据](https://github.com/martineastwood/penaltyblog/blob/72de6519e0c9a357b8b1aa2a6441a454b18ff54e/LICENCE)。
12. **Data-source risk**：纯数学无数据授权问题；scrapers 所访问站点及 StatsBomb 数据单独审查，不随 MIT 放行。
13. **Estimated engineering saving**：HIGH · 10–18 人日：避免重写拟合器、多市场数值和研发对照；已扣接入与交叉验证，不能与其他比分库叠加。

维护信号：[Hi Martin](https://github.com/martineastwood/penaltyblog/issues/49)（open，2026-09-30）。只把issue/PR标题与状态当线索，未当作已复现缺陷。

### 2. scipy/scipy · SP · 85/100

| 基础信息 | 核实结果 |
|---|---|
| Repository / main language | [scipy/scipy](https://github.com/scipy/scipy) / Python |
| CODE_LICENSE / stars / forks | BSD-3-Clause / 15068 / 5981 |
| Source SHA | [3d18c8f1316850a21ee462bdd7268965c2509d90](https://github.com/scipy/scipy/tree/3d18c8f1316850a21ee462bdd7268965c2509d90) |
| Last meaningful commit | [2026-10-01 · ENH: special: make `poisson_binom_cdf` gufunc public and add delegation for gufuncs (#26093)](https://github.com/scipy/scipy/commit/2ceccbf06f27ccabb4458d0cc725500ed6464bb3) |
| Last GitHub release | [v1.18.1](https://github.com/scipy/scipy/releases/tag/v1.18.1) · 2026-08-21 |
| Status / package / Python | Active；[PyPI scipy 1.18.1](https://pypi.org/project/scipy/1.18.1/)，Requires-Python：>=3.12 |
| Test suite / CI | 分布与 resampling 有大规模测试；Windows CI 与 stats benchmarks 存在且抽读。本轮未执行。 |
| Documentation | README、函数文档、stats benchmark；源码 main 为开发版，不能与 PyPI 发行版混同。 |
| Reuse / risks | **DEPENDENCY_CANDIDATE**；DATA_LEGAL_RISK=LOW；TECHNICAL_MAINTENANCE_RISK=LOW；LEAKAGE_RISK=MEDIUM |

1. **What it does**：数值分布、优化和统计重采样基础库，不是足球预测产品。
2. **Core modules**：scipy/stats/_discrete_distns.py:poisson_gen._logpmf/_pmf/_sf；scipy/stats/_resampling.py:bootstrap；tests/test_resampling.py、benchmarks/benchmarks/stats.py。
3. **Code inspected**：[README.rst](https://github.com/scipy/scipy/blob/3d18c8f1316850a21ee462bdd7268965c2509d90/README.rst)；[.github/workflows/windows.yml](https://github.com/scipy/scipy/blob/3d18c8f1316850a21ee462bdd7268965c2509d90/.github/workflows/windows.yml)；[LICENSE.txt](https://github.com/scipy/scipy/blob/3d18c8f1316850a21ee462bdd7268965c2509d90/LICENSE.txt)；[pyproject.toml](https://github.com/scipy/scipy/blob/3d18c8f1316850a21ee462bdd7268965c2509d90/pyproject.toml)；[scipy/stats/_resampling.py](https://github.com/scipy/scipy/blob/3d18c8f1316850a21ee462bdd7268965c2509d90/scipy/stats/_resampling.py)；[scipy/stats/_discrete_distns.py](https://github.com/scipy/scipy/blob/3d18c8f1316850a21ee462bdd7268965c2509d90/scipy/stats/_discrete_distns.py)；[scipy/stats/tests/test_discrete_distns.py](https://github.com/scipy/scipy/blob/3d18c8f1316850a21ee462bdd7268965c2509d90/scipy/stats/tests/test_discrete_distns.py)；[benchmarks/benchmarks/stats.py](https://github.com/scipy/scipy/blob/3d18c8f1316850a21ee462bdd7268965c2509d90/benchmarks/benchmarks/stats.py)；[scipy/stats/tests/test_resampling.py](https://github.com/scipy/scipy/blob/3d18c8f1316850a21ee462bdd7268965c2509d90/scipy/stats/tests/test_resampling.py)。
4. **Strengths**：稳定 log-PMF 与尾概率、成对重采样与显式 RNG；成熟测试和 Windows wheel，比自造浮点统计工具可靠。
5. **Weaknesses**：不是 Decimal 算法；bootstrap 默认 IID 样本重采样，不知道赛季/比赛/时间相关性，paired=True 也不等于 block bootstrap。
6. **What overlaps good**：good 已有 Decimal Poisson 递推和独立阶乘 golden test；无需替换。
7. **What good lacks**：good 缺 bootstrap CI 和复杂分布/拟合工具；可用 Poisson PMF/SF 做第二种实现的数值参考。
8. **What should be reused**：P0 设计 Poisson/tail oracle；P1/P2 用统计 API，bootstrap 前由 good 明确定义独立单位或块。
9. **What should NOT be reused**：不以 float 取代持久化赔率，不将普通 bootstrap 宣称为时间序列置信区间，不自造 scipy 替代层。
10. **Integration approach**：薄函数调用；冻结数组、版本/RNG、分组索引，记录置信区间方法。升级 NumPy 2.x 与足球旧库需隔离。
11. **License**：BSD-3 可依赖/修改/分发，保留许可与声明；wheel 内第三方许可证仍要随发行清单保留。 [实际许可证据](https://github.com/scipy/scipy/blob/3d18c8f1316850a21ee462bdd7268965c2509d90/LICENSE.txt)。
12. **Data-source risk**：不获取数据；输入数据权利仍由 good 负责。
13. **Estimated engineering saving**：MEDIUM · 4–7 人日：数值交叉检查、重采样与边界处理；不计已有 Poisson 的重写成本。

维护信号：[ENH: add wrap functionality for find_peaks() helper signal._peak_finding_utils._local_maxima_1d](https://github.com/scipy/scipy/pull/26329)（open，2026-10-01）；[MAINT: linalg: unify C++ LAPACK wrappers](https://github.com/scipy/scipy/pull/26328)（open，2026-10-01）。只把issue/PR标题与状态当线索，未当作已复现缺陷。

### 3. scikit-learn/scikit-learn · SK · 84/100

| 基础信息 | 核实结果 |
|---|---|
| Repository / main language | [scikit-learn/scikit-learn](https://github.com/scikit-learn/scikit-learn) / Python |
| CODE_LICENSE / stars / forks | BSD-3-Clause / 67444 / 27470 |
| Source SHA | [6ad9bb9ed68bb562bc74f3c49231d95c86b1055c](https://github.com/scikit-learn/scikit-learn/tree/6ad9bb9ed68bb562bc74f3c49231d95c86b1055c) |
| Last meaningful commit | [2026-10-01 · PERF Speed up kdtree when distance metric's p is 1 or 2 (#35045)](https://github.com/scikit-learn/scikit-learn/commit/6ad9bb9ed68bb562bc74f3c49231d95c86b1055c) |
| Last GitHub release | [1.9.1](https://github.com/scikit-learn/scikit-learn/releases/tag/1.9.1) · 2026-09-11 |
| Status / package / Python | Active；[PyPI scikit-learn 1.9.1](https://pypi.org/project/scikit-learn/1.9.1/)，Requires-Python：>=3.11 |
| Test suite / CI | test_calibration.py 覆盖概率/缺类等；unit-tests CI、多系统；bench_isotonic.py 性能用例。 |
| Documentation | README、API docstrings 和完整官方文档；本次抽读核心及测试，未做完整测试运行。 |
| Reuse / risks | **DEPENDENCY_CANDIDATE**；DATA_LEGAL_RISK=LOW；TECHNICAL_MAINTENANCE_RISK=LOW；LEAKAGE_RISK=HIGH |

1. **What it does**：分类、指标、预处理与校准的通用标准实现。
2. **Core modules**：sklearn/calibration.py:CalibratedClassifierCV/_SigmoidCalibration；sklearn/model_selection/_split.py:TimeSeriesSplit；sklearn/metrics/_classification.py:log_loss/brier_score_loss。
3. **Code inspected**：[README.rst](https://github.com/scikit-learn/scikit-learn/blob/6ad9bb9ed68bb562bc74f3c49231d95c86b1055c/README.rst)；[COPYING](https://github.com/scikit-learn/scikit-learn/blob/6ad9bb9ed68bb562bc74f3c49231d95c86b1055c/COPYING)；[pyproject.toml](https://github.com/scikit-learn/scikit-learn/blob/6ad9bb9ed68bb562bc74f3c49231d95c86b1055c/pyproject.toml)；[sklearn/tests/test_calibration.py](https://github.com/scikit-learn/scikit-learn/blob/6ad9bb9ed68bb562bc74f3c49231d95c86b1055c/sklearn/tests/test_calibration.py)；[sklearn/metrics/_classification.py](https://github.com/scikit-learn/scikit-learn/blob/6ad9bb9ed68bb562bc74f3c49231d95c86b1055c/sklearn/metrics/_classification.py)；[sklearn/calibration.py](https://github.com/scikit-learn/scikit-learn/blob/6ad9bb9ed68bb562bc74f3c49231d95c86b1055c/sklearn/calibration.py)；[sklearn/model_selection/_split.py](https://github.com/scikit-learn/scikit-learn/blob/6ad9bb9ed68bb562bc74f3c49231d95c86b1055c/sklearn/model_selection/_split.py)；[.github/workflows/unit-tests.yml](https://github.com/scikit-learn/scikit-learn/blob/6ad9bb9ed68bb562bc74f3c49231d95c86b1055c/.github/workflows/unit-tests.yml)；[benchmarks/bench_isotonic.py](https://github.com/scikit-learn/scikit-learn/blob/6ad9bb9ed68bb562bc74f3c49231d95c86b1055c/benchmarks/bench_isotonic.py)。
4. **Strengths**：成熟 isotonic/sigmoid、概率标签处理和基线分类器；校准 API 可避免手写优化与边界逻辑。
5. **Weaknesses**：分类默认 CV 非时间顺序；TimeSeriesSplit 的 gap 是行数，不能保证同比赛快照不跨折。ensemble=False 使用 cross_val_predict，对普通滚动折不能直接套用。
6. **What overlaps good**：good 已有明确类别顺序、自然对数 Log Loss、三类 Brier、ECE 与配对覆盖；保留其口径。
7. **What good lacks**：good 缺校准器拟合和 ML 基线；应复用通用实现而自管训练/校准/测试边界。
8. **What should be reused**：P0 指标 oracle；P1 数据量合格后 sigmoid/isotonic 基准；P2 简单分类基线与预处理 Pipeline。
9. **What should NOT be reused**：不沿用默认随机/分层 CV；不在预测标签或同一训练样本上校准；不直接反序列化外来 pickle。
10. **Integration approach**：自有时间切分生成独立校准集；FrozenEstimator/显式预拟合路线需核对所锁版本；显式 classes、epsilon/Brier scaling；对外返回本地契约。
11. **License**：BSD-3 允许依赖/修改并保留声明；无需接受其对象为业务数据库模型。 [实际许可证据](https://github.com/scikit-learn/scikit-learn/blob/6ad9bb9ed68bb562bc74f3c49231d95c86b1055c/COPYING)。
12. **Data-source risk**：不抓取足球源；示例 datasets 不构成 good 数据许可。
13. **Estimated engineering saving**：HIGH · 8–12 人日：校准、指标边界、基础分类与预处理；与 netcal/Dirichlet 的估算重叠。

维护信号：[FIX Dont assume available CPU core count never changes](https://github.com/scikit-learn/scikit-learn/pull/35062)（open，2026-10-01）；[MNT Require higher minimum threadpoolctl](https://github.com/scikit-learn/scikit-learn/pull/35061)（open，2026-10-01）。只把issue/PR标题与状态当线索，未当作已复现缺陷。

### 4. probberechts/soccerdata · SD · 81/100

| 基础信息 | 核实结果 |
|---|---|
| Repository / main language | [probberechts/soccerdata](https://github.com/probberechts/soccerdata) / Python |
| CODE_LICENSE / stars / forks | Apache-2.0 + retained MIT notice / 2096 / 329 |
| Source SHA | [e120471e424a173e83e8aeeaaf4d954ab9d38ee4](https://github.com/probberechts/soccerdata/tree/e120471e424a173e83e8aeeaaf4d954ab9d38ee4) |
| Last meaningful commit | [2026-07-24 · fix(whoscored): add 'event_id' column to read_events(output_fmt == "events") (#960)](https://github.com/probberechts/soccerdata/commit/eda847099d4d13dc914dbb95350cc7c8c5b0b6ea) |
| Last GitHub release | [v1.9.1](https://github.com/probberechts/soccerdata/releases/tag/v1.9.1) · 2026-07-24 |
| Status / package / Python | Active；[PyPI soccerdata 1.9.1](https://pypi.org/project/soccerdata/1.9.1/)，Requires-Python：<3.15,>=3.10 |
| Test suite / CI | test_common.py mock 缓存/标准化；Ubuntu CI Python 3.10–3.14；未见 Windows 矩阵。 |
| Documentation | README.rst、readthedocs、MatchHistory/Home advantage notebook；实例不证明历史时间可用性。 |
| Reuse / risks | **ARCHITECTURE_REFERENCE**；DATA_LEGAL_RISK=HIGH；TECHNICAL_MAINTENANCE_RISK=HIGH；LEAKAGE_RISK=HIGH |

1. **What it does**：多来源足球采集，覆盖 FBref、Understat、WhoScored、football-data 等。
2. **Core modules**：soccerdata/_common.py:BaseReader/BaseRequestsReader/BaseSeleniumReader；_config.py:LEAGUE_DICT/SeasonCode；match_history.py:MatchHistory.read_games；fbref.py:FBref；understat.py:Understat。
3. **Code inspected**：[LICENSE.rst](https://github.com/probberechts/soccerdata/blob/e120471e424a173e83e8aeeaaf4d954ab9d38ee4/LICENSE.rst)；[README.rst](https://github.com/probberechts/soccerdata/blob/e120471e424a173e83e8aeeaaf4d954ab9d38ee4/README.rst)；[pyproject.toml](https://github.com/probberechts/soccerdata/blob/e120471e424a173e83e8aeeaaf4d954ab9d38ee4/pyproject.toml)；[.github/workflows/ci.yml](https://github.com/probberechts/soccerdata/blob/e120471e424a173e83e8aeeaaf4d954ab9d38ee4/.github/workflows/ci.yml)；[tests/test_common.py](https://github.com/probberechts/soccerdata/blob/e120471e424a173e83e8aeeaaf4d954ab9d38ee4/tests/test_common.py)；[soccerdata/_common.py](https://github.com/probberechts/soccerdata/blob/e120471e424a173e83e8aeeaaf4d954ab9d38ee4/soccerdata/_common.py)；[soccerdata/fbref.py](https://github.com/probberechts/soccerdata/blob/e120471e424a173e83e8aeeaaf4d954ab9d38ee4/soccerdata/fbref.py)；[soccerdata/understat.py](https://github.com/probberechts/soccerdata/blob/e120471e424a173e83e8aeeaaf4d954ab9d38ee4/soccerdata/understat.py)；[soccerdata/match_history.py](https://github.com/probberechts/soccerdata/blob/e120471e424a173e83e8aeeaaf4d954ab9d38ee4/soccerdata/match_history.py)；[soccerdata/_config.py](https://github.com/probberechts/soccerdata/blob/e120471e424a173e83e8aeeaaf4d954ab9d38ee4/soccerdata/_config.py)；[docs/examples/MatchHistory - Home advantage.ipynb](https://github.com/probberechts/soccerdata/blob/e120471e424a173e83e8aeeaaf4d954ab9d38ee4/docs/examples/MatchHistory%20-%20Home%20advantage.ipynb)。
4. **Strengths**：可复用的 league/season 映射、provider ID、分层 reader、缓存和 DataFrame 命名；节省站点差异识别。
5. **Weaknesses**：缓存按路径/mtime 覆盖，不是 append-only provenance；read_games 缺 Time 时填 12:00，不能视作真实 kickoff/quote time；站点风控和结构变化持续维护。
6. **What overlaps good**：good 有 Provider Adapter、重试限流、Raw、UUID 映射与时间证明；其数据治理强于普通抓取库。
7. **What good lacks**：good 缺大规模联赛/赛季覆盖及真实历史统计来源；可参考来源参数与 schema。
8. **What should be reused**：优先复用 league/season 设计及解析字段知识；必要时独立 acquisition worker 使用审过的单个 provider。
9. **What should NOT be reused**：不让模型直接调用 read_games；不以 cache mtime/CSV日期证明 T-30 可见；球队字符串替换不得自动认定体彩身份。
10. **Integration approach**：Research acquisition→原始响应留存→good 验证/映射→SEALED；若封装库内部网络无法先 Raw，不能接入现有主链路。
11. **License**：实际 LICENSE 为 Apache-2.0，并保留 football-data 部分 MIT 声明；GitHub NOASSERTION 不等于无许可。允许依赖/改写，分发保留 LICENSE/适用NOTICE与修改说明。 [实际许可证据](https://github.com/probberechts/soccerdata/blob/e120471e424a173e83e8aeeaaf4d954ab9d38ee4/LICENSE.rst)。
12. **Data-source risk**：数据源授权、反自动化限制、再分发权限独立；ClubElo 问题单中的 502/auth 是维护信号，不据此断言全部源失效。
13. **Estimated engineering saving**：HIGH · 7–12 人日：来源/赛季/schema 适配知识；不含解决授权、WAF或补造缺失历史。

维护信号：[fix(fbref): escape unsafe team names in match-log cache paths](https://github.com/probberechts/soccerdata/pull/978)（open，2026-09-29）；[(ClubElo) api.clubelo.com returns 502: the CSV API has moved behind authentication](https://github.com/probberechts/soccerdata/issues/977)（open，2026-09-23）。只把issue/PR标题与状态当线索，未当作已复现缺陷。

### 5. wdm0006/elote · EL · 78/100

| 基础信息 | 核实结果 |
|---|---|
| Repository / main language | [wdm0006/elote](https://github.com/wdm0006/elote) / Python |
| CODE_LICENSE / stars / forks | MIT / 33 / 5 |
| Source SHA | [15741e6fff3336656a3743d9410c4538d2958ddc](https://github.com/wdm0006/elote/tree/15741e6fff3336656a3743d9410c4538d2958ddc) |
| Last meaningful commit | [2026-09-20 · fix(arenas): dispatch arena losses through the loser's lost_to (#204)](https://github.com/wdm0006/elote/commit/15741e6fff3336656a3743d9410c4538d2958ddc) |
| Last GitHub release | [v1.5.0](https://github.com/wdm0006/elote/releases/tag/v1.5.0) · 2026-09-08 |
| Status / package / Python | Active；[PyPI elote 1.5.0](https://pypi.org/project/elote/1.5.0/)，Requires-Python：>=3.10 |
| Test suite / CI | Elo known-values、benchmark/tests；Ubuntu Python 3.10–3.14 CI。HEAD 的 arena 修复晚于 PyPI 1.5.0。 |
| Documentation | README、评级对照文档、examples、benchmark.py 已读代表路径。 |
| Reuse / risks | **DEPENDENCY_CANDIDATE**；DATA_LEGAL_RISK=LOW；TECHNICAL_MAINTENANCE_RISK=MEDIUM；LEAKAGE_RISK=HIGH |

1. **What it does**：Elo、Colley 等成对竞技评级与顺序评估工具。
2. **Core modules**：elote/competitors/elo.py:EloCompetitor.expected_score/beat/tied；competitors/colley.py:ColleyMatrixCompetitor；evaluation.py:walk_forward；benchmark.py:evaluate_competitor。
3. **Code inspected**：[LICENSE.md](https://github.com/wdm0006/elote/blob/15741e6fff3336656a3743d9410c4538d2958ddc/LICENSE.md)；[pyproject.toml](https://github.com/wdm0006/elote/blob/15741e6fff3336656a3743d9410c4538d2958ddc/pyproject.toml)；[.github/workflows/test-suite.yml](https://github.com/wdm0006/elote/blob/15741e6fff3336656a3743d9410c4538d2958ddc/.github/workflows/test-suite.yml)；[tests/test_EloCompetitor_known_values.py](https://github.com/wdm0006/elote/blob/15741e6fff3336656a3743d9410c4538d2958ddc/tests/test_EloCompetitor_known_values.py)；[elote/competitors/elo.py](https://github.com/wdm0006/elote/blob/15741e6fff3336656a3743d9410c4538d2958ddc/elote/competitors/elo.py)；[elote/evaluation.py](https://github.com/wdm0006/elote/blob/15741e6fff3336656a3743d9410c4538d2958ddc/elote/evaluation.py)；[elote/competitors/colley.py](https://github.com/wdm0006/elote/blob/15741e6fff3336656a3743d9410c4538d2958ddc/elote/competitors/colley.py)；[README.md](https://github.com/wdm0006/elote/blob/15741e6fff3336656a3743d9410c4538d2958ddc/README.md)；[elote/benchmark.py](https://github.com/wdm0006/elote/blob/15741e6fff3336656a3743d9410c4538d2958ddc/elote/benchmark.py)。
4. **Strengths**：评级更新和状态导出已有实现；walk_forward 按 period 先全部预测再更新，值得参考。
5. **Weaknesses**：expected_score 是胜+半平的期望得分，不是 1X2 主胜率；walk_forward 评估跳过平局/未见队；benchmark 默认在 test history 优化阈值，若把结果报成最终测试成绩会泄漏。
6. **What overlaps good**：good 有历史结果与 cutoff 边界，但没有评级；数据准备/冻结仍沿用 good。
7. **What good lacks**：Elo/Colley 的确定性更新、赛季初值与状态管理尚缺；足球主场和三项概率仍需验证。
8. **What should be reused**：参考/调用 Elo 更新和 known-values；关闭测试集阈值优化，用独立验证集调参，保留 draw/unseen coverage。
9. **What should NOT be reused**：不把 binary metrics 当完整足球三类评估；不把含未来比赛的最终 rating 回填历史；不照搬 benchmark 最优阈值。
10. **Integration approach**：P1 SEALED 数据上按 finished_at/available_at 顺序更新；存独立 model state 与训练成员；并发隔离类参数修改。
11. **License**：MIT 可依赖或修改，保留声明；小型维护团队，API/状态格式需锁版本。 [实际许可证据](https://github.com/wdm0006/elote/blob/15741e6fff3336656a3743d9410c4538d2958ddc/LICENSE.md)。
12. **Data-source risk**：核心纯算法风险低；不自动使用其 datasets extras 下载的数据。
13. **Estimated engineering saving**：MEDIUM · 3–5 人日：评级更新/状态与已知值测试，足球 1X2 校准不计入节省。

维护信号：[Whole-History Rating does not align with whr under closest exposed configuration](https://github.com/wdm0006/elote/issues/173)（open，2026-08-29）；[(autopilot) Add the Keener score-based rating system](https://github.com/wdm0006/elote/issues/123)（open，2026-08-30）。只把issue/PR标题与状态当线索，未当作已复现缺陷。

### 6. mberk/shin · SH · 77/100

| 基础信息 | 核实结果 |
|---|---|
| Repository / main language | [mberk/shin](https://github.com/mberk/shin) / Python |
| CODE_LICENSE / stars / forks | MIT / 105 / 13 |
| Source SHA | [ae460853fabeca7d512bbf7de8aaa55dc17f3485](https://github.com/mberk/shin/tree/ae460853fabeca7d512bbf7de8aaa55dc17f3485) |
| Last meaningful commit | [2025-10-23 · python 3.13 support](https://github.com/mberk/shin/commit/ae460853fabeca7d512bbf7de8aaa55dc17f3485) |
| Last GitHub release | [v0.2.2](https://github.com/mberk/shin/releases/tag/v0.2.2) · 2025-10-23 |
| Status / package / Python | Maintenance；[PyPI shin 0.2.2](https://pypi.org/project/shin/0.2.2/)，Requires-Python：>=3.9 |
| Test suite / CI | fixed odds 和 Python/Rust 路径参数化测试；CI 构建多平台 wheel，已见 CP312 Windows wheel。 |
| Documentation | README 包含模型定义、API/诊断与示例；未见独立 benchmark。 |
| Reuse / risks | **DEPENDENCY_CANDIDATE**；DATA_LEGAL_RISK=LOW；TECHNICAL_MAINTENANCE_RISK=MEDIUM；LEAKAGE_RISK=LOW |

1. **What it does**：实现 Shin bookmaker margin removal 的专门库。
2. **Core modules**：python/shin/__init__.py:calculate_implied_probabilities/_optimise；src/lib.rs:optimise；tests/test_shin.py。
3. **Code inspected**：[README.md](https://github.com/mberk/shin/blob/ae460853fabeca7d512bbf7de8aaa55dc17f3485/README.md)；[pyproject.toml](https://github.com/mberk/shin/blob/ae460853fabeca7d512bbf7de8aaa55dc17f3485/pyproject.toml)；[LICENSE](https://github.com/mberk/shin/blob/ae460853fabeca7d512bbf7de8aaa55dc17f3485/LICENSE)；[python/shin/__init__.py](https://github.com/mberk/shin/blob/ae460853fabeca7d512bbf7de8aaa55dc17f3485/python/shin/__init__.py)；[src/lib.rs](https://github.com/mberk/shin/blob/ae460853fabeca7d512bbf7de8aaa55dc17f3485/src/lib.rs)；[.github/workflows/CI.yml](https://github.com/mberk/shin/blob/ae460853fabeca7d512bbf7de8aaa55dc17f3485/.github/workflows/CI.yml)；[tests/test_shin.py](https://github.com/mberk/shin/blob/ae460853fabeca7d512bbf7de8aaa55dc17f3485/tests/test_shin.py)。
4. **Strengths**：小 API 支持 odds map 保持 selection keys，迭代诊断和两选项解析路径；比引入综合足球包更可控。
5. **Weaknesses**：float 算法；最大迭代达到并非保证抛错；虽然有 force_python，顶层仍导入 native 扩展。odds>=1 检查不替代 good 的有限且>1约束。
6. **What overlaps good**：good 的比例去水已完成，不需要 Shin 替换默认市场基线。
7. **What good lacks**：非比例去水的敏感性比较尚缺；Shin 可做挑战模型，不代表一定更准。
8. **What should be reused**：P0 golden/reference 数值；P1 有足够样本时比较 proportional vs Shin 的校准和覆盖。
9. **What should NOT be reused**：不把 Shin 的内部参数解释成已证实内幕交易；不自动对不完整/跨时间市场去水；不重写 Rust。
10. **Integration approach**：market 完整性验证后暂转 float，检查 delta/iterations/finite/nonnegative/sum；结果转 Decimal 文本并标方法/版本，不改变原始赔率。
11. **License**：MIT 允许依赖/修改并保留声明；主要实现及 Rust 构建均应核许可。 [实际许可证据](https://github.com/mberk/shin/blob/ae460853fabeca7d512bbf7de8aaa55dc17f3485/LICENSE)。
12. **Data-source risk**：无网络和数据采集，LOW。
13. **Estimated engineering saving**：LOW · 1–3 人日：去水求解器和边界校验；不含数据治理。

维护信号：[Bump black from 24.3.0 to 26.3.1](https://github.com/mberk/shin/pull/23)（open，2026-08-04）；[Bump pyo3 from 0.24.2 to 0.29.0](https://github.com/mberk/shin/pull/22)（open，2026-06-12）。只把issue/PR标题与状态当线索，未当作已复现缺陷。

### 7. PySport/kloppy · KL · 76/100

| 基础信息 | 核实结果 |
|---|---|
| Repository / main language | [PySport/kloppy](https://github.com/PySport/kloppy) / Python |
| CODE_LICENSE / stars / forks | BSD-3-Clause / 557 / 105 |
| Source SHA | [0997cc777d03ac9472c79615f9225ea4b264cf44](https://github.com/PySport/kloppy/tree/0997cc777d03ac9472c79615f9225ea4b264cf44) |
| Last meaningful commit | [2026-10-01 · fix(statsbomb): handle passes with a null end location and no recipient (#618)](https://github.com/PySport/kloppy/commit/3fbc20caaf8322cb417b5986ab4c1689f5025c92) |
| Last GitHub release | [v3.19.0](https://github.com/PySport/kloppy/releases/tag/v3.19.0) · 2026-06-07 |
| Status / package / Python | Active；[PyPI kloppy 3.19.0](https://pypi.org/project/kloppy/3.19.0/)，Requires-Python：>=3.9 |
| Test suite / CI | StatsBomb fixtures 覆盖事件/坐标/异常；test.yml 多 OS、Python 3.9–3.13；近期 null pass 修复。 |
| Documentation | README、模型文档、event/coordinate examples；已读 StatsBomb 示例。 |
| Reuse / risks | **DEPENDENCY_CANDIDATE**；DATA_LEGAL_RISK=HIGH；TECHNICAL_MAINTENANCE_RISK=MEDIUM；LEAKAGE_RISK=HIGH |

1. **What it does**：多供应商事件/追踪格式解析、坐标转换和统一领域对象。
2. **Core modules**：kloppy/_providers/statsbomb.py:load/load_open_data；infra/serializers/event/statsbomb/deserializer.py:StatsBombDeserializer；tests/test_statsbomb.py。
3. **Code inspected**：[LICENSE](https://github.com/PySport/kloppy/blob/0997cc777d03ac9472c79615f9225ea4b264cf44/LICENSE)；[pyproject.toml](https://github.com/PySport/kloppy/blob/0997cc777d03ac9472c79615f9225ea4b264cf44/pyproject.toml)；[README.md](https://github.com/PySport/kloppy/blob/0997cc777d03ac9472c79615f9225ea4b264cf44/README.md)；[.github/workflows/test.yml](https://github.com/PySport/kloppy/blob/0997cc777d03ac9472c79615f9225ea4b264cf44/.github/workflows/test.yml)；[kloppy/_providers/statsbomb.py](https://github.com/PySport/kloppy/blob/0997cc777d03ac9472c79615f9225ea4b264cf44/kloppy/_providers/statsbomb.py)；[kloppy/infra/serializers/event/statsbomb/deserializer.py](https://github.com/PySport/kloppy/blob/0997cc777d03ac9472c79615f9225ea4b264cf44/kloppy/infra/serializers/event/statsbomb/deserializer.py)；[kloppy/tests/test_statsbomb.py](https://github.com/PySport/kloppy/blob/0997cc777d03ac9472c79615f9225ea4b264cf44/kloppy/tests/test_statsbomb.py)；[examples/datasets/statsbomb.py](https://github.com/PySport/kloppy/blob/0997cc777d03ac9472c79615f9225ea4b264cf44/examples/datasets/statsbomb.py)。
4. **Strengths**：能从本地 raw 文件解析、保持 provider IDs 与坐标语义；适合把格式标准化从自有时态治理中剥离。
5. **Weaknesses**：事件时间是比赛内时钟，不是可获得时间；open-data loader 取 mutable master；wheel 约30 MB，自带领域模型但不是体彩映射。
6. **What overlaps good**：good 有 source identity/Raw contract，无事件；其 provider objects 不能替代本地 UUID 与版本。
7. **What good lacks**：事件格式、坐标、球员/球队事件关系在 good 缺失。
8. **What should be reused**：P3 本地流解析与坐标转换；在库外记录源文件hash、license和解析版本。
9. **What should NOT be reused**：不直接在模型内 load_open_data；不以 match clock 声明赛前可见，不引入 tracking 直到实际需要。
10. **Integration approach**：只读已保存 raw，输出自己的 event/features；先挑一种授权事件源，避免双份跨全系统领域对象。
11. **License**：BSD-3 对代码友好；许可不扩展到 StatsBomb/Wyscout 等数据。 [实际许可证据](https://github.com/PySport/kloppy/blob/0997cc777d03ac9472c79615f9225ea4b264cf44/LICENSE)。
12. **Data-source risk**：开源事件数据仍有源协议；StatsBomb 非商业/再分发限制使计划数据路径为 HIGH。
13. **Estimated engineering saving**：HIGH · 8–15 人日（P3）：多格式/坐标解析；与 socceraction 转换范围重叠。

维护信号：[feat(tracking): add visible_area to Frame model](https://github.com/PySport/kloppy/pull/620)（open，2026-09-30）；[SportsCode load drops repeated group values written by save](https://github.com/PySport/kloppy/issues/616)（open，2026-09-21）。只把issue/PR标题与状态当线索，未当作已复现缺陷。

### 8. lightgbm-org/LightGBM · LG · 75/100

| 基础信息 | 核实结果 |
|---|---|
| Repository / main language | [lightgbm-org/LightGBM](https://github.com/lightgbm-org/LightGBM) / C++ |
| CODE_LICENSE / stars / forks | MIT / 18826 / 4081 |
| Source SHA | [750c4fb49ac60b1b15b9d06439b185655f202c21](https://github.com/lightgbm-org/LightGBM/tree/750c4fb49ac60b1b15b9d06439b185655f202c21) |
| Last meaningful commit | [2026-09-25 · [swig] fix memory leak on error path in SaveModelToString/DumpModel helpers (#7450)](https://github.com/lightgbm-org/LightGBM/commit/f4777388bd0c580719feb03469e80f767dc9b09f) |
| Last GitHub release | [v4.7.0](https://github.com/lightgbm-org/LightGBM/releases/tag/v4.7.0) · 2026-07-18 |
| Status / package / Python | Active；[PyPI lightgbm 4.7.0](https://pypi.org/project/lightgbm/4.7.0/)，Requires-Python：>=3.10 |
| Test suite / CI | test_engine.py multiclass/evaluation 等，Python package 多平台 CI；simple_example.py 使用验证集 early stopping。 |
| Documentation | README、官方指南、Python examples；本次没有跑性能 benchmark。 |
| Reuse / risks | **DEPENDENCY_CANDIDATE**；DATA_LEGAL_RISK=LOW；TECHNICAL_MAINTENANCE_RISK=MEDIUM；LEAKAGE_RISK=HIGH |

1. **What it does**：梯度提升决策树；未来表格特征模型候选，不是开箱足球预测。
2. **Core modules**：python-package/lightgbm/sklearn.py:LGBMClassifier.predict_proba；engine.py:train/cv；src/objective/multiclass_objective.hpp:MulticlassSoftmax。
3. **Code inspected**：[python-package/pyproject.toml](https://github.com/lightgbm-org/LightGBM/blob/750c4fb49ac60b1b15b9d06439b185655f202c21/python-package/pyproject.toml)；[README.md](https://github.com/lightgbm-org/LightGBM/blob/750c4fb49ac60b1b15b9d06439b185655f202c21/README.md)；[LICENSE](https://github.com/lightgbm-org/LightGBM/blob/750c4fb49ac60b1b15b9d06439b185655f202c21/LICENSE)；[python-package/lightgbm/sklearn.py](https://github.com/lightgbm-org/LightGBM/blob/750c4fb49ac60b1b15b9d06439b185655f202c21/python-package/lightgbm/sklearn.py)；[src/objective/multiclass_objective.hpp](https://github.com/lightgbm-org/LightGBM/blob/750c4fb49ac60b1b15b9d06439b185655f202c21/src/objective/multiclass_objective.hpp)；[python-package/lightgbm/engine.py](https://github.com/lightgbm-org/LightGBM/blob/750c4fb49ac60b1b15b9d06439b185655f202c21/python-package/lightgbm/engine.py)；[.github/workflows/python_package.yml](https://github.com/lightgbm-org/LightGBM/blob/750c4fb49ac60b1b15b9d06439b185655f202c21/.github/workflows/python_package.yml)；[tests/python_package_test/test_engine.py](https://github.com/lightgbm-org/LightGBM/blob/750c4fb49ac60b1b15b9d06439b185655f202c21/tests/python_package_test/test_engine.py)；[examples/python-guide/simple_example.py](https://github.com/lightgbm-org/LightGBM/blob/750c4fb49ac60b1b15b9d06439b185655f202c21/examples/python-guide/simple_example.py)。
4. **Strengths**：成熟三类概率训练、early stopping 和 Python API；无需同时造 XGBoost/CatBoost/LightGBM 三套 adapter。
5. **Weaknesses**：cv 默认 stratified/shuffle；示例名为 test 的数据用于 early stopping，不能再当未接触最终测试；只固定seed不保证跨平台/线程位级一致。
6. **What overlaps good**：good 现有模型是冻结输入的基线；特征/标签边界可以继续使用。
7. **What good lacks**：good 缺 ML 基线、训练工件与调参记录；没有数据之前不应追求复杂提升树。
8. **What should be reused**：P2 三赛季合格数据后，只选一个 boosting challenger，对比 goals/market/Elo 与简单分类基线。
9. **What should NOT be reused**：不照抄随机CV，不把实时抓取放fit，不将feature importance当因果，不先建GPU/分布式训练。
10. **Integration approach**：CPU 优先、锁发行版，明确类别顺序与训练/验证/test成员，调参只用过去窗口；native工件hash经自有registry记录。
11. **License**：MIT 允许依赖/修改并保留声明；native 二进制及传递库许可证需随部署清单记录。 [实际许可证据](https://github.com/lightgbm-org/LightGBM/blob/750c4fb49ac60b1b15b9d06439b185655f202c21/LICENSE)。
12. **Data-source risk**：核心算法无数据源；授权责任在特征数据。
13. **Estimated engineering saving**：HIGH · 8–12 人日（P2）：成熟训练器/API/early stopping，非相对手写整个GBDT的夸大估计。

维护信号：[(ci): Bump the ci-dependencies group with 5 updates](https://github.com/lightgbm-org/LightGBM/pull/7480)（open，2026-10-01）；[regression_l1 and quantile loss are ~6-8x slower with sample weights (mape always)](https://github.com/lightgbm-org/LightGBM/issues/7479)（open，2026-10-01）。只把issue/PR标题与状态当线索，未当作已复现缺陷。

### 9. georgedouzas/sports-betting · SB · 74/100

| 基础信息 | 核实结果 |
|---|---|
| Repository / main language | [georgedouzas/sports-betting](https://github.com/georgedouzas/sports-betting) / Python |
| CODE_LICENSE / stars / forks | MIT / 804 / 150 |
| Source SHA | [eb4cedf376663fac68f508e50b83fd832e74dfd4](https://github.com/georgedouzas/sports-betting/tree/eb4cedf376663fac68f508e50b83fd832e74dfd4) |
| Last meaningful commit | [2026-07-27 · fix: make `execution status` work on a single bet's identity](https://github.com/georgedouzas/sports-betting/commit/98f7cef5c92439991fb9d3038ee763668d4dc2f0) |
| Last GitHub release | [0.15.1](https://github.com/georgedouzas/sports-betting/releases/tag/0.15.1) · 2026-07-28 |
| Status / package / Python | Active；[PyPI sports-betting 0.15.1](https://pypi.org/project/sports-betting/0.15.1/)，Requires-Python：<3.14,>=3.11 |
| Test suite / CI | test_leakage.py 真正测试 preplay/inplay 与同刻快照；ci.yml 覆盖 Windows/Linux/macOS、3.11–3.13。 |
| Documentation | README、源码文档与 modelling/plot_classifier_bettor.py；未执行交易或网络示例。 |
| Reuse / risks | **ARCHITECTURE_REFERENCE**；DATA_LEGAL_RISK=MEDIUM；TECHNICAL_MAINTENANCE_RISK=MEDIUM；LEAKAGE_RISK=HIGH |

1. **What it does**：数据加载、赔率历史、模型回测和投注执行框架；本审计仅评价数据/评估部分。
2. **Core modules**：sources/_odds/_odds_api.py；dataloaders/_base.py:BaseDataLoader；evaluation/_model_selection.py:backtest；evaluation/_base.py:BaseBettor。
3. **Code inspected**：[pyproject.toml](https://github.com/georgedouzas/sports-betting/blob/eb4cedf376663fac68f508e50b83fd832e74dfd4/pyproject.toml)；[README.md](https://github.com/georgedouzas/sports-betting/blob/eb4cedf376663fac68f508e50b83fd832e74dfd4/README.md)；[LICENSE](https://github.com/georgedouzas/sports-betting/blob/eb4cedf376663fac68f508e50b83fd832e74dfd4/LICENSE)；[tests/dataloaders/test_leakage.py](https://github.com/georgedouzas/sports-betting/blob/eb4cedf376663fac68f508e50b83fd832e74dfd4/tests/dataloaders/test_leakage.py)；[src/sportsbet/sources/_odds/_odds_api.py](https://github.com/georgedouzas/sports-betting/blob/eb4cedf376663fac68f508e50b83fd832e74dfd4/src/sportsbet/sources/_odds/_odds_api.py)；[src/sportsbet/evaluation/_model_selection.py](https://github.com/georgedouzas/sports-betting/blob/eb4cedf376663fac68f508e50b83fd832e74dfd4/src/sportsbet/evaluation/_model_selection.py)；[src/sportsbet/evaluation/_base.py](https://github.com/georgedouzas/sports-betting/blob/eb4cedf376663fac68f508e50b83fd832e74dfd4/src/sportsbet/evaluation/_base.py)；[.github/workflows/ci.yml](https://github.com/georgedouzas/sports-betting/blob/eb4cedf376663fac68f508e50b83fd832e74dfd4/.github/workflows/ci.yml)；[src/sportsbet/sources/_base.py](https://github.com/georgedouzas/sports-betting/blob/eb4cedf376663fac68f508e50b83fd832e74dfd4/src/sportsbet/sources/_base.py)；[src/sportsbet/dataloaders/_extraction.py](https://github.com/georgedouzas/sports-betting/blob/eb4cedf376663fac68f508e50b83fd832e74dfd4/src/sportsbet/dataloaders/_extraction.py)；[docs/examples/modelling/plot_classifier_bettor.py](https://github.com/georgedouzas/sports-betting/blob/eb4cedf376663fac68f508e50b83fd832e74dfd4/docs/examples/modelling/plot_classifier_bettor.py)；[src/sportsbet/dataloaders/_base.py](https://github.com/georgedouzas/sports-betting/blob/eb4cedf376663fac68f508e50b83fd832e74dfd4/src/sportsbet/dataloaders/_base.py)。
4. **Strengths**：The Odds API 历史快照、provider/market schema、信息状态过滤与 TimeSeriesSplit 回测值得借鉴；不是只有 betting bot 的项目。
5. **Weaknesses**：按行时间切分仍可切开同场快照；closing offset/tolerance 不能冒充 T-30；简单收益公式不支持完整AH/void/commission。returns!=0统计下注数会漏掉零收益投入。
6. **What overlaps good**：good 更强的 Raw/visibility/SEALED，已有 market normalization；不要为其 DataFrame 框架重构。
7. **What good lacks**：good 缺历史数据规模化和滚动评估编排，收益账本则必须另按本地规则定义。
8. **What should be reused**：借鉴显式快照状态、负向泄漏测试、滚动fit/predict分离和coverage；保留good的cutoff与原始时间证据。
9. **What should NOT be reused**：禁止连接 BaseBettor/执行/MCP/自动下注到 Recommendation；不直接用 market_maximum 作可成交赔率。
10. **Integration approach**：仅架构参考，设计自有只读 walk-forward runner；外部API留在 acquisition，历史回应先Raw，再校验成研究成员。
11. **License**：MIT 可依赖/改写并保留声明；此处不推荐全框架作为生产依赖。 [实际许可证据](https://github.com/georgedouzas/sports-betting/blob/eb4cedf376663fac68f508e50b83fd832e74dfd4/LICENSE)。
12. **Data-source risk**：The Odds API 有条件许可商业分析与存储，禁止以原始数据转售为主；历史权限/订阅和字段时间仍需核验。
13. **Estimated engineering saving**：MEDIUM · 4–7 人日：数据/评估边界和负向测试设计，不计自动投注功能。

维护信号：[feat(sources): add LumifyOdds live odds source](https://github.com/georgedouzas/sports-betting/pull/141)（open，2026-08-07）；[Proposal: tennis data source (stats + odds) — Live Tennis API](https://github.com/georgedouzas/sports-betting/issues/140)（open，2026-08-26）。只把issue/PR标题与状态当线索，未当作已复现缺陷。

### 10. ML-KULeuven/socceraction · SA · 73/100

| 基础信息 | 核实结果 |
|---|---|
| Repository / main language | [ML-KULeuven/socceraction](https://github.com/ML-KULeuven/socceraction) / Python |
| CODE_LICENSE / stars / forks | MIT / 817 / 160 |
| Source SHA | [93a1242d46c104889205753accaabadb00c45c6d](https://github.com/ML-KULeuven/socceraction/tree/93a1242d46c104889205753accaabadb00c45c6d) |
| Last meaningful commit | [2024-11-22 · Differentiate between keeper and fieldplayer save event in opta-spadl transformation](https://github.com/ML-KULeuven/socceraction/commit/84f78de8b2c073f6f689603da14f0af3ed959049) |
| Last GitHub release | [v1.5.3](https://github.com/ML-KULeuven/socceraction/releases/tag/v1.5.3) · 2024-08-15 |
| Status / package / Python | Maintenance；[PyPI socceraction 1.5.3](https://pypi.org/project/socceraction/1.5.3/)，Requires-Python：<3.13,>=3.9 |
| Test suite / CI | SPADL/xT fixtures、fit/io 测试；ci.yml 三OS/Python3.12；未证明最新依赖下全绿。 |
| Documentation | README、readthedocs、SPADL/xT/VAEP API 文档；代码更新明显慢于通用ML栈。 |
| Reuse / risks | **REFERENCE_IMPLEMENTATION**；DATA_LEGAL_RISK=HIGH；TECHNICAL_MAINTENANCE_RISK=HIGH；LEAKAGE_RISK=HIGH |

1. **What it does**：事件数据转 SPADL、网格 xT 和动作价值 VAEP。
2. **Core modules**：data/statsbomb/loader.py:StatsBombLoader；spadl/statsbomb.py:convert_to_actions；xthreat.py:ExpectedThreat；vaep/base.py:VAEP；vaep/labels.py。
3. **Code inspected**：[pyproject.toml](https://github.com/ML-KULeuven/socceraction/blob/93a1242d46c104889205753accaabadb00c45c6d/pyproject.toml)；[README.md](https://github.com/ML-KULeuven/socceraction/blob/93a1242d46c104889205753accaabadb00c45c6d/README.md)；[LICENSE.rst](https://github.com/ML-KULeuven/socceraction/blob/93a1242d46c104889205753accaabadb00c45c6d/LICENSE.rst)；[socceraction/xthreat.py](https://github.com/ML-KULeuven/socceraction/blob/93a1242d46c104889205753accaabadb00c45c6d/socceraction/xthreat.py)；[socceraction/vaep/labels.py](https://github.com/ML-KULeuven/socceraction/blob/93a1242d46c104889205753accaabadb00c45c6d/socceraction/vaep/labels.py)；[socceraction/data/statsbomb/loader.py](https://github.com/ML-KULeuven/socceraction/blob/93a1242d46c104889205753accaabadb00c45c6d/socceraction/data/statsbomb/loader.py)；[socceraction/spadl/statsbomb.py](https://github.com/ML-KULeuven/socceraction/blob/93a1242d46c104889205753accaabadb00c45c6d/socceraction/spadl/statsbomb.py)；[socceraction/vaep/base.py](https://github.com/ML-KULeuven/socceraction/blob/93a1242d46c104889205753accaabadb00c45c6d/socceraction/vaep/base.py)；[.github/workflows/ci.yml](https://github.com/ML-KULeuven/socceraction/blob/93a1242d46c104889205753accaabadb00c45c6d/.github/workflows/ci.yml)；[tests/test_xthreat.py](https://github.com/ML-KULeuven/socceraction/blob/93a1242d46c104889205753accaabadb00c45c6d/tests/test_xthreat.py)。
4. **Strengths**：坐标/动作转换与状态转移已有领域实现；16×12 xT、动作价值目标和测试可避免从零做事件估值。
5. **Weaknesses**：VAEP 内部 validation 默认随机打乱事件，足球时间评估有泄漏风险；SciPy interp2d 旧接口与 NumPy<2 约束需要兼容性处理。
6. **What overlaps good**：good 仅有球队统计xG字段，无事件模型；无理由现在替换已完成的比分数学。
7. **What good lacks**：SPADL/xT/VAEP整条链路缺失，但不阻塞当前真实Pilot。
8. **What should be reused**：P3 首先参考 SPADL/xT；验证完整比赛/时间分组后才试 VAEP，未来依赖准入另评。
9. **What should NOT be reused**：不把未来十动作得分标签放特征，不随机拆同场事件；不同时引入多事件源与所有估值模型。
10. **Integration approach**：授权事件→Raw→kloppy或对应loader→自有冻结事件特征；旧NumPy依赖放独立研究环境，不污染主API依赖。
11. **License**：MIT 代码允许复用；optional statsbombpy/data 的许可另审。 [实际许可证据](https://github.com/ML-KULeuven/socceraction/blob/93a1242d46c104889205753accaabadb00c45c6d/LICENSE.rst)。
12. **Data-source risk**：StatsBomb/Wyscout/Opta 数据权利与订阅各异；只加载本地文件也不消除许可限制。
13. **Estimated engineering saving**：VERY_HIGH · 12–20 人日（P3）：SPADL和xT/VAEP参考；与kloppy重叠，不纳入近期总节省。

维护信号：[Match Analysis: Arsenal vs Man City (1-1, 21 Sep 2025) — Pressing Patterns & Transitional Play through the VAEP/xT Lens](https://github.com/ML-KULeuven/socceraction/issues/951)（open，2026-07-22）；[`actiontype` feature should be adapted for atomic](https://github.com/ML-KULeuven/socceraction/issues/950)（open，2025-09-12）。只把issue/PR标题与状态当线索，未当作已复现缺陷。

### 11. opisthokonta/goalmodel · GM · 71/100

| 基础信息 | 核实结果 |
|---|---|
| Repository / main language | [opisthokonta/goalmodel](https://github.com/opisthokonta/goalmodel) / R |
| CODE_LICENSE / stars / forks | GPL-3.0 (DESCRIPTION) / 116 / 23 |
| Source SHA | [84ecd6c2bbad3ccb967abf88ef49e5bcd074e545](https://github.com/opisthokonta/goalmodel/tree/84ecd6c2bbad3ccb967abf88ef49e5bcd074e545) |
| Last meaningful commit | [2024-03-30 · new function rho.ml](https://github.com/opisthokonta/goalmodel/commit/0877b18dd3d4ed6d2d5057489a7ecf3f668167f7) |
| Last GitHub release | NONE（查询未返回Release；不等于没有源码版本或其他渠道发行） |
| Status / package / Python | Dormant；R包；Python不适用。安装来源和版本见README/DESCRIPTION；本次未核验最新CRAN二进制。 |
| Test suite / CI | tests/testthat/test_1.R 有拟合/ρ/错误输入；仓库树未见 GitHub CI 配置；未运行R。 |
| Documentation | README含模型与权重示例；R函数注释；DESCRIPTION 版本0.6.4，无GitHub Release。 |
| Reuse / risks | **REFERENCE_IMPLEMENTATION**；DATA_LEGAL_RISK=LOW；TECHNICAL_MAINTENANCE_RISK=HIGH；LEAKAGE_RISK=MEDIUM |

1. **What it does**：R 足球进球模型：攻防/主场项、DC校正及多种进球分布。
2. **Core modules**：R/dixoncoles.R:dDCP/rho.ml；R/goalmodel_fit.R:lambda_pred 与拟合目标；R/goalmodel_misc.R:weights_dc。 R/goalmodel_misc.R:score_predictions。
3. **Code inspected**：[DESCRIPTION](https://github.com/opisthokonta/goalmodel/blob/84ecd6c2bbad3ccb967abf88ef49e5bcd074e545/DESCRIPTION)；[README.md](https://github.com/opisthokonta/goalmodel/blob/84ecd6c2bbad3ccb967abf88ef49e5bcd074e545/README.md)；[R/dixoncoles.R](https://github.com/opisthokonta/goalmodel/blob/84ecd6c2bbad3ccb967abf88ef49e5bcd074e545/R/dixoncoles.R)；[R/goalmodel_misc.R](https://github.com/opisthokonta/goalmodel/blob/84ecd6c2bbad3ccb967abf88ef49e5bcd074e545/R/goalmodel_misc.R)；[tests/testthat/test_1.R](https://github.com/opisthokonta/goalmodel/blob/84ecd6c2bbad3ccb967abf88ef49e5bcd074e545/tests/testthat/test_1.R)；[R/goalmodel_fit.R](https://github.com/opisthokonta/goalmodel/blob/84ecd6c2bbad3ccb967abf88ef49e5bcd074e545/R/goalmodel_fit.R)；[R/goalmodel_predict.R](https://github.com/opisthokonta/goalmodel/blob/84ecd6c2bbad3ccb967abf88ef49e5bcd074e545/R/goalmodel_predict.R)。
4. **Strengths**：DC四格与 good 一致；ρ独立估计、加权似然和识别约束提供另一实现对照，与 penaltyblog 不共用代码路径。
5. **Weaknesses**：多年无功能更新；R/Rcpp生态非当前部署栈；ρ默认搜索区间并不自动保证每对λ都合法。 LogScore对p=0返回Inf，与good的epsilon裁剪口径不同。
6. **What overlaps good**：good已实现DC数学；目标不是替换score-math-v1，而是检验ρ/λ拟合的数值结果。
7. **What good lacks**：攻防参数、主场项、衰减和ρ估计尚缺；其似然/识别约束提供可核验定义。
8. **What should be reused**：离线 oracle，保存输入、版本与输出摘要；验证negativeτ拒绝、优化收敛及权重。
9. **What should NOT be reused**：不将GPL R代码翻译粘入Python；不把R对象/依赖塞进FastAPI；不宣称GPL禁止商业使用。
10. **Integration approach**：P0先写数值比较规格，P1才运行独立R基准；业务实现用许可合格的库API或独立数学实现，禁止无必要重写。
11. **License**：DESCRIPTION声明GPL-3；可按GPL条件使用/修改，但分发衍生/组合程序需评估copyleft与相应源码义务；内部运行不等于自动公开代码。 [实际许可证据](https://github.com/opisthokonta/goalmodel/blob/84ecd6c2bbad3ccb967abf88ef49e5bcd074e545/DESCRIPTION)。
12. **Data-source risk**：算法本身LOW，示例engsoccerdata数据不自动获得再分发权。
13. **Estimated engineering saving**：MEDIUM · 3–5 人日：独立DC拟合/ρ诊断参考；与penaltyblog高度重叠。

维护信号：[Fix Readme typo](https://github.com/opisthokonta/goalmodel/pull/2)（open，2019-12-28）。只把issue/PR标题与状态当线索，未当作已复现缺陷。

### 12. opisthokonta/implied · IM · 70/100

| 基础信息 | 核实结果 |
|---|---|
| Repository / main language | [opisthokonta/implied](https://github.com/opisthokonta/implied) / R |
| CODE_LICENSE / stars / forks | GPL-3.0 (DESCRIPTION) / 9 / 0 |
| Source SHA | [1d1c5cd548dd71bc1b9addd733db5c2db8566b71](https://github.com/opisthokonta/implied/tree/1d1c5cd548dd71bc1b9addd733db5c2db8566b71) |
| Last meaningful commit | [2026-05-23 · Renamed method = 'goto' to 'ooepc'](https://github.com/opisthokonta/implied/commit/1d1c5cd548dd71bc1b9addd733db5c2db8566b71) |
| Last GitHub release | NONE（查询未返回Release；不等于没有源码版本或其他渠道发行） |
| Status / package / Python | Maintenance；R包；Python不适用。安装来源和版本见README/DESCRIPTION；本次未核验最新CRAN二进制。 |
| Test suite / CI | testthat 覆盖方法、边界和概率↔赔率 roundtrip；仓库树未见GitHub CI。 |
| Documentation | README、R函数帮助与CRAN链接；DESCRIPTION0.6.1；CRAN最新发行时间UNKNOWN，无GH release。 |
| Reuse / risks | **REFERENCE_IMPLEMENTATION**；DATA_LEGAL_RISK=LOW；TECHNICAL_MAINTENANCE_RISK=MEDIUM；LEAKAGE_RISK=LOW |

1. **What it does**：多种赔率去水与逆变换，包含 Shin/power/additive/odds-ratio/JS 等。
2. **Core modules**：R/implied_probabilities.R:implied_probabilities、各方法root函数；R/implied_odds.R:implied_odds；tests/testthat/test_1.R。
3. **Code inspected**：[README.md](https://github.com/opisthokonta/implied/blob/1d1c5cd548dd71bc1b9addd733db5c2db8566b71/README.md)；[R/implied_probabilities.R](https://github.com/opisthokonta/implied/blob/1d1c5cd548dd71bc1b9addd733db5c2db8566b71/R/implied_probabilities.R)；[DESCRIPTION](https://github.com/opisthokonta/implied/blob/1d1c5cd548dd71bc1b9addd733db5c2db8566b71/DESCRIPTION)；[tests/testthat/test_1.R](https://github.com/opisthokonta/implied/blob/1d1c5cd548dd71bc1b9addd733db5c2db8566b71/tests/testthat/test_1.R)；[R/implied_odds.R](https://github.com/opisthokonta/implied/blob/1d1c5cd548dd71bc1b9addd733db5c2db8566b71/R/implied_odds.R)。
4. **Strengths**：比单方法实现更完整地暴露参数、normalization、求根失败标记，适合去水敏感性分析。
5. **Weaknesses**：R double 与good Decimal不同；输入overround假设、求根界与失败状态必须明确；并非每种方法都值得生产实现。
6. **What overlaps good**：good比例去水完备，IM basic可做对照；无需为方法数量扩张market-v1。
7. **What good lacks**：good尚无Shin/power等对照试验或失败诊断，且未证明非比例法有净收益。
8. **What should be reused**：用R参考值与shin/penaltyblog三角验证；最多先比较proportional、Shin、power。
9. **What should NOT be reused**：不移植GPL求根代码，不默认负概率截断后当可靠结果，不盲目实现所有方法。
10. **Integration approach**：离线输入同一完整市场、固定选项顺序和decimal赔率；记录method/version/parameters与problematic状态。
11. **License**：GPL-3需按分发方式评估copyleft；仅参考数学/独立运行输出不等于复制实现，也不自动豁免数据权利。 [实际许可证据](https://github.com/opisthokonta/implied/blob/1d1c5cd548dd71bc1b9addd733db5c2db8566b71/DESCRIPTION)。
12. **Data-source risk**：无数据抓取，LOW。
13. **Estimated engineering saving**：LOW · 2–4 人日：去水公式与边界测试设计；与shin节省不可相加。

维护信号：本次issue查询未返回条目，不能推断没有缺陷。只把issue/PR标题与状态当线索，未当作已复现缺陷。

### 13. anguswilliams91/bpl-next · BP · 69/100

| 基础信息 | 核实结果 |
|---|---|
| Repository / main language | [anguswilliams91/bpl-next](https://github.com/anguswilliams91/bpl-next) / Python |
| CODE_LICENSE / stars / forks | MIT / 5 / 2 |
| Source SHA | [a79b63f00ca57e07d9730789181892bfab74be52](https://github.com/anguswilliams91/bpl-next/tree/a79b63f00ca57e07d9730789181892bfab74be52) |
| Last meaningful commit | [2026-08-13 · fix packagenotfounderror downstream due to project name change](https://github.com/anguswilliams91/bpl-next/commit/9db75688e5a5ecc6b08b27b3c6a9ad147c56ca8b) |
| Last GitHub release | NONE（查询未返回Release；不等于没有源码版本或其他渠道发行） |
| Status / package / Python | Active；[PyPI bpl-next 0.5.2](https://pypi.org/project/bpl-next/0.5.2/)，Requires-Python：<4,>=3.10 |
| Test suite / CI | DC测试主要确认fit结果非空；tests.yml Ubuntu3.10/3.13，未见Windows验证；小团队/5stars不能代替算法质量判断。 |
| Documentation | README使用示例；包API；无GitHub Release，PyPI0.5.2与HEAD pyproject0.5.0有差异。 |
| Reuse / risks | **REFERENCE_IMPLEMENTATION**；DATA_LEGAL_RISK=LOW；TECHNICAL_MAINTENANCE_RISK=HIGH；LEAKAGE_RISK=HIGH |

1. **What it does**：基于NumPyro/JAX的Bayesian足球比分模型，旧bpl的后续项目。
2. **Core modules**：bpl/dixon_coles.py:DixonColesMatchPredictor.fit；bpl/base.py:BaseMatchPredictor.predict_score_grid_proba/predict_outcome_proba。
3. **Code inspected**：[LICENSE](https://github.com/anguswilliams91/bpl-next/blob/a79b63f00ca57e07d9730789181892bfab74be52/LICENSE)；[README.md](https://github.com/anguswilliams91/bpl-next/blob/a79b63f00ca57e07d9730789181892bfab74be52/README.md)；[.github/workflows/tests.yml](https://github.com/anguswilliams91/bpl-next/blob/a79b63f00ca57e07d9730789181892bfab74be52/.github/workflows/tests.yml)；[bpl/dixon_coles.py](https://github.com/anguswilliams91/bpl-next/blob/a79b63f00ca57e07d9730789181892bfab74be52/bpl/dixon_coles.py)；[tests/test_dixon_coles.py](https://github.com/anguswilliams91/bpl-next/blob/a79b63f00ca57e07d9730789181892bfab74be52/tests/test_dixon_coles.py)；[pyproject.toml](https://github.com/anguswilliams91/bpl-next/blob/a79b63f00ca57e07d9730789181892bfab74be52/pyproject.toml)；[bpl/base.py](https://github.com/anguswilliams91/bpl-next/blob/a79b63f00ca57e07d9730789181892bfab74be52/bpl/base.py)。
4. **Strengths**：分层攻防prior、主场项、ρ参数变换和NUTS后验；fit暴露random_state，输入数组可从冻结dataset生成。
5. **Weaknesses**：无时间过滤，测试强度有限；JAX/native与NumPy>=2要求，运行依赖竟包含pip>=26.2.1；预测截断与后验收敛需单独验证。
6. **What overlaps good**：与good比分数学重叠，训练/不确定性尚无。
7. **What good lacks**：层次prior、后验不确定性、稀疏队伍收缩；不是当前Pilot缺口。
8. **What should be reused**：P2 Bayesian challenger的模型结构和离线结果；比较DC MLE后才决定是否值得额外采样成本。
9. **What should NOT be reused**：不自动装入主API；不把random_state等同跨硬件位级可复现；不沿用默认时钟seed的模拟入口。
10. **Integration approach**：独立research环境；冻结训练成员、seed、warmup/samples/chain诊断；只导出本地概率契约与工件摘要。
11. **License**：MIT友好；PyPI与GitHub版本不一致需按选定发行物复查，不凭HEAD许可推定整条依赖已审核。 [实际许可证据](https://github.com/anguswilliams91/bpl-next/blob/a79b63f00ca57e07d9730789181892bfab74be52/LICENSE)。
12. **Data-source risk**：核心模型无采集，LOW；示例数据另审。
13. **Estimated engineering saving**：HIGH · 6–10 人日（P2）：Bayesian模型结构/采样参考；不与footBayes相加。

维护信号：[Add tests, docs for adding team from covariates](https://github.com/anguswilliams91/bpl-next/issues/11)（open，2022-07-18）；[dixon_coles_correlation_term can return nan values](https://github.com/anguswilliams91/bpl-next/issues/6)（open，2021-08-06）。只把issue/PR标题与状态当线索，未当作已复现缺陷。

### 14. EFS-OpenSource/calibration-framework · NC · 68/100

| 基础信息 | 核实结果 |
|---|---|
| Repository / main language | [EFS-OpenSource/calibration-framework](https://github.com/EFS-OpenSource/calibration-framework) / Python |
| CODE_LICENSE / stars / forks | Apache-2.0 / 379 / 48 |
| Source SHA | [34b677f42b83803aa35503c5b6fefb1387ea9167](https://github.com/EFS-OpenSource/calibration-framework/tree/34b677f42b83803aa35503c5b6fefb1387ea9167) |
| Last meaningful commit | [2026-01-14 · - fixes #62](https://github.com/EFS-OpenSource/calibration-framework/commit/ced7a95530fa5a876c1dde74db7826cd6e0b8e2c) |
| Last GitHub release | [r1.3.6](https://github.com/EFS-OpenSource/calibration-framework/releases/tag/r1.3.6) · 2024-08-08 |
| Status / package / Python | Maintenance；[PyPI netcal 1.4.0](https://pypi.org/project/netcal/1.4.0/)，Requires-Python：>=3.10 |
| Test suite / CI | 递归树未找到常规tests目录/测试CI；classification/Evaluation.py是示例而非独立测试证明。 |
| Documentation | README、官方文档和分类示例；GH release r1.3.6停在2024，但PyPI1.4.0于2026发布。 |
| Reuse / risks | **REFERENCE_IMPLEMENTATION**；DATA_LEGAL_RISK=LOW；TECHNICAL_MAINTENANCE_RISK=MEDIUM；LEAKAGE_RISK=HIGH |

1. **What it does**：netcal校准方法与ECE/ACE/MCE等置信度诊断。
2. **Core modules**：netcal/scaling/LogisticCalibration.py:LogisticCalibration；binning/IsotonicRegression.py；metrics/confidence/ECE.py；metrics/Miscalibration.py。
3. **Code inspected**：[netcal/metrics/confidence/ECE.py](https://github.com/EFS-OpenSource/calibration-framework/blob/34b677f42b83803aa35503c5b6fefb1387ea9167/netcal/metrics/confidence/ECE.py)；[netcal/binning/IsotonicRegression.py](https://github.com/EFS-OpenSource/calibration-framework/blob/34b677f42b83803aa35503c5b6fefb1387ea9167/netcal/binning/IsotonicRegression.py)；[setup.py](https://github.com/EFS-OpenSource/calibration-framework/blob/34b677f42b83803aa35503c5b6fefb1387ea9167/setup.py)；[LICENSE.txt](https://github.com/EFS-OpenSource/calibration-framework/blob/34b677f42b83803aa35503c5b6fefb1387ea9167/LICENSE.txt)；[netcal/scaling/LogisticCalibration.py](https://github.com/EFS-OpenSource/calibration-framework/blob/34b677f42b83803aa35503c5b6fefb1387ea9167/netcal/scaling/LogisticCalibration.py)；[README.md](https://github.com/EFS-OpenSource/calibration-framework/blob/34b677f42b83803aa35503c5b6fefb1387ea9167/README.md)；[pyproject.toml](https://github.com/EFS-OpenSource/calibration-framework/blob/34b677f42b83803aa35503c5b6fefb1387ea9167/pyproject.toml)；[examples/classification/Evaluation.py](https://github.com/EFS-OpenSource/calibration-framework/blob/34b677f42b83803aa35503c5b6fefb1387ea9167/examples/classification/Evaluation.py)；[requirements.txt](https://github.com/EFS-OpenSource/calibration-framework/blob/34b677f42b83803aa35503c5b6fefb1387ea9167/requirements.txt)；[netcal/metrics/Miscalibration.py](https://github.com/EFS-OpenSource/calibration-framework/blob/34b677f42b83803aa35503c5b6fefb1387ea9167/netcal/metrics/Miscalibration.py)。
4. **Strengths**：温度/向量校准、二类logit与多类逆softmax路径、binning细节可作为校准研究参考。
5. **Weaknesses**：默认多类ECE采用argmax与最大置信度，和good的逐类OVR macro口径不同；为isotonic安装完整Torch栈不划算。
6. **What overlaps good**：good已有ECE与可靠性分桶；相同名字不代表相同指标。
7. **What good lacks**：校准拟合尚缺，但标准isotonic/sigmoid优先用sklearn即可。
8. **What should be reused**：查清top-label/OVR、equal-width/equal-mass、空桶等定义；在受控数据上作为第二实现。
9. **What should NOT be reused**：不替换good ECE字段含义，不因指标数多而引入整包，不在同一数据拟合并汇报校准收益。
10. **Integration approach**：dev/reference独立环境；输出带完整metric configuration；生产校准首选已选择的sklearn。
11. **License**：Apache-2.0允许依赖/修改，保留许可/适用NOTICE及变更说明；传递native/Torch依赖另核。 [实际许可证据](https://github.com/EFS-OpenSource/calibration-framework/blob/34b677f42b83803aa35503c5b6fefb1387ea9167/LICENSE.txt)。
12. **Data-source risk**：库本身LOW；examples下载CIFAR等不在本轮范围。
13. **Estimated engineering saving**：LOW · 2–4 人日：校准定义和方法对照；与sklearn节省重叠。

维护信号：[ACE counts bins masked by sample_threshold in its denominator (ECE and UCE keep their samples in the normalizer)](https://github.com/EFS-OpenSource/calibration-framework/issues/67)（open，2026-09-26）；[ENIR .fit returns an error when AUC equals 1.](https://github.com/EFS-OpenSource/calibration-framework/issues/64)（open，2026-04-20）。只把issue/PR标题与状态当线索，未当作已复现缺陷。

### 15. LeoEgidi/footBayes · FB · 67/100

| 基础信息 | 核实结果 |
|---|---|
| Repository / main language | [LeoEgidi/footBayes](https://github.com/LeoEgidi/footBayes) / R |
| CODE_LICENSE / stars / forks | GPL-2.0 (DESCRIPTION) / 59 / 11 |
| Source SHA | [00540f5ae12b9dd6a4d97c5be228fb72c4be4b0d](https://github.com/LeoEgidi/footBayes/tree/00540f5ae12b9dd6a4d97c5be228fb72c4be4b0d) |
| Last meaningful commit | [2026-09-09 · Add dynamic model specs and vignette updates](https://github.com/LeoEgidi/footBayes/commit/00540f5ae12b9dd6a4d97c5be228fb72c4be4b0d) |
| Last GitHub release | NONE（查询未返回Release；不等于没有源码版本或其他渠道发行） |
| Status / package / Python | Active；R包；Python不适用。安装来源和版本见README/DESCRIPTION；本次未核验最新CRAN二进制。 |
| Test suite / CI | test_stan_foot.R有参数/模型测试，但CRAN或缺CmdStan时跳过；R-CMD-check有三系统，不能据此声称所有Stan路径执行。 |
| Documentation | README、vignettes、R帮助；DESCRIPTION2.1.0；CRAN链接存在，最新CRAN发行时间UNKNOWN，无GH release。 |
| Reuse / risks | **REFERENCE_IMPLEMENTATION**；DATA_LEGAL_RISK=LOW；TECHNICAL_MAINTENANCE_RISK=HIGH；LEAKAGE_RISK=HIGH |

1. **What it does**：R/Stan足球概率模型，支持DC与动态层次模型、不同prior与推断方法。
2. **Core modules**：src/stan/dixon_coles.stan:dc_inflation/dixon_coles_lpmf；R/stan_foot.R:stan_foot；tests/testthat/test_stan_foot.R。
3. **Code inspected**：[DESCRIPTION](https://github.com/LeoEgidi/footBayes/blob/00540f5ae12b9dd6a4d97c5be228fb72c4be4b0d/DESCRIPTION)；[src/stan/dixon_coles.stan](https://github.com/LeoEgidi/footBayes/blob/00540f5ae12b9dd6a4d97c5be228fb72c4be4b0d/src/stan/dixon_coles.stan)；[R/stan_foot.R](https://github.com/LeoEgidi/footBayes/blob/00540f5ae12b9dd6a4d97c5be228fb72c4be4b0d/R/stan_foot.R)；[.github/workflows/R-CMD-check.yaml](https://github.com/LeoEgidi/footBayes/blob/00540f5ae12b9dd6a4d97c5be228fb72c4be4b0d/.github/workflows/R-CMD-check.yaml)；[README.md](https://github.com/LeoEgidi/footBayes/blob/00540f5ae12b9dd6a4d97c5be228fb72c4be4b0d/README.md)；[tests/testthat/test_stan_foot.R](https://github.com/LeoEgidi/footBayes/blob/00540f5ae12b9dd6a4d97c5be228fb72c4be4b0d/tests/testthat/test_stan_foot.R)；[R/compare_foot.R](https://github.com/LeoEgidi/footBayes/blob/00540f5ae12b9dd6a4d97c5be228fb72c4be4b0d/R/compare_foot.R)。
4. **Strengths**：独立Stan DC四格、centered attack/defense、home effect、prior与负τ拒绝；可观察Bayesian假设而不黑盒调用。
5. **Weaknesses**：MCMC计算和Windows工具链成本；seed默认随机生成但可显式传入；ρ[-.2,.2]界仍需逐λ合法性判断。
6. **What overlaps good**：与score-math-v1的四格变换一致；good没有prior/动态强度/后验模型。
7. **What good lacks**：高级统计建模与不确定性；应排在MLE/数据质量验证之后。
8. **What should be reused**：P2/P3作为独立Bayesian/DC数值与结构参考，锁定seed与采样诊断。
9. **What should NOT be reused**：不移植GPL Stan/R代码到主仓库；不让API请求实时跑MCMC；不把动态模型视为必胜升级。
10. **Integration approach**：离线统计研究，输入冻结成员，返回后验预测与诊断；拒绝不收敛模型，不只看LogLoss。
11. **License**：GPL-2声明需按分发与组合方式审查；可内部研究，不建议当前生产嵌入R/Stan。 [实际许可证据](https://github.com/LeoEgidi/footBayes/blob/00540f5ae12b9dd6a4d97c5be228fb72c4be4b0d/DESCRIPTION)。
12. **Data-source risk**：算法LOW；包内/示例比赛数据需单独确定使用与分发权。
13. **Estimated engineering saving**：HIGH · 6–10 人日（P2/P3）：prior/模型诊断参考；与bpl-next重叠。

维护信号：[Future Predictions & xG as input](https://github.com/LeoEgidi/footBayes/issues/5)（open，2024-04-19）；[Add variables](https://github.com/LeoEgidi/footBayes/issues/4)（open，2023-12-19）。只把issue/PR标题与状态当线索，未当作已复现缺陷。

### 16. dirichletcal/dirichlet_python · DC · 63/100

| 基础信息 | 核实结果 |
|---|---|
| Repository / main language | [dirichletcal/dirichlet_python](https://github.com/dirichletcal/dirichlet_python) / Python |
| CODE_LICENSE / stars / forks | MIT / 33 / 10 |
| Source SHA | [b03f65fc6582cad89497b977b3b33a3c4fe48e39](https://github.com/dirichletcal/dirichlet_python/tree/b03f65fc6582cad89497b977b3b33a3c4fe48e39) |
| Last meaningful commit | [2024-08-05 · Fixed issues for Python 3.12](https://github.com/dirichletcal/dirichlet_python/commit/c46c83d6de93b08ae6f40f1ea90ebcdff1c49b42) |
| Last GitHub release | [0.3.dev4](https://github.com/dirichletcal/dirichlet_python/releases/tag/0.3.dev4) · 2021-09-21 |
| Status / package / Python | Maintenance；[PyPI dirichletcal 0.5.3](https://pypi.org/project/dirichletcal/0.5.3/)，Requires-Python：>=3.12 |
| Test suite / CI | synthetic ternary/extreme值测试、Ubuntu3.12 CI；示例不是足球时间评估。 |
| Documentation | README/论文入口和calibration_example.py；README badge文字不一致，实际LICENSE为MIT。 |
| Reuse / risks | **REFERENCE_IMPLEMENTATION**；DATA_LEGAL_RISK=LOW；TECHNICAL_MAINTENANCE_RISK=HIGH；LEAKAGE_RISK=HIGH |

1. **What it does**：多类Dirichlet校准：log概率上线性映射再softmax。
2. **Core modules**：dirichletcal/calib/fulldirichlet.py:FullDirichletCalibrator.fit/predict_proba；tests/calib/test_fulldirichlet.py；examples/calibration_example.py。
3. **Code inspected**：[setup.py](https://github.com/dirichletcal/dirichlet_python/blob/b03f65fc6582cad89497b977b3b33a3c4fe48e39/setup.py)；[LICENSE.txt](https://github.com/dirichletcal/dirichlet_python/blob/b03f65fc6582cad89497b977b3b33a3c4fe48e39/LICENSE.txt)；[README.md](https://github.com/dirichletcal/dirichlet_python/blob/b03f65fc6582cad89497b977b3b33a3c4fe48e39/README.md)；[examples/calibration_example.py](https://github.com/dirichletcal/dirichlet_python/blob/b03f65fc6582cad89497b977b3b33a3c4fe48e39/examples/calibration_example.py)；[dirichletcal/calib/fulldirichlet.py](https://github.com/dirichletcal/dirichlet_python/blob/b03f65fc6582cad89497b977b3b33a3c4fe48e39/dirichletcal/calib/fulldirichlet.py)；[.github/workflows/ci.yml](https://github.com/dirichletcal/dirichlet_python/blob/b03f65fc6582cad89497b977b3b33a3c4fe48e39/.github/workflows/ci.yml)；[dirichletcal/tests/calib/test_fulldirichlet.py](https://github.com/dirichletcal/dirichlet_python/blob/b03f65fc6582cad89497b977b3b33a3c4fe48e39/dirichletcal/tests/calib/test_fulldirichlet.py)。
4. **Strengths**：独立多类校准、正则化与优化器结构；可作为三类概率校准的高级对照。
5. **Weaknesses**：示例random train_test_split、shuffled StratifiedKFold，且分类器对训练集原位预测再拟合校准；对时序足球有乐观偏差。PyPI只见sdist。
6. **What overlaps good**：good只有诊断，未拟合校准器；不需要一开始就在Platt之外再增加高自由度方法。
7. **What good lacks**：多类联合校准缺失，但有效样本量/独立校准集比方法本身更紧迫。
8. **What should be reused**：P2与简单sigmoid/isotonic对比，在独立时间校准集上训练，验证正则化与稀有类别。
9. **What should NOT be reused**：不复制随机划分/训练内预测示例，不将fit data上的final_loss当泛化评估。
10. **Integration approach**：dev/reference独立JAX环境；导出概率与工件参数，预测契约显式类别顺序；生产资格另审。
11. **License**：LICENSE.txt为MIT，允许依赖/修改并保留声明；以实际文件为准而非README badge。 [实际许可证据](https://github.com/dirichletcal/dirichlet_python/blob/b03f65fc6582cad89497b977b3b33a3c4fe48e39/LICENSE.txt)。
12. **Data-source risk**：无足球数据采集LOW。
13. **Estimated engineering saving**：LOW · 2–4 人日（P2）：高级校准参考，不能与sklearn/netcal相加。

维护信号：[Fix sklearn scoring compatibility by using ClassifierMixin in calibrators](https://github.com/dirichletcal/dirichlet_python/pull/20)（open，2026-03-30）；[Error running the example code](https://github.com/dirichletcal/dirichlet_python/issues/19)（open，2026-03-30）。只把issue/PR标题与状态当线索，未当作已复现缺陷。

### 17. oseymour/ScraperFC · SF · 60/100

| 基础信息 | 核实结果 |
|---|---|
| Repository / main language | [oseymour/ScraperFC](https://github.com/oseymour/ScraperFC) / Python |
| CODE_LICENSE / stars / forks | GPL-3.0 / 412 / 103 |
| Source SHA | [50f5df9fae4141f91174debdb14cf87fb8ed810a](https://github.com/oseymour/ScraperFC/tree/50f5df9fae4141f91174debdb14cf87fb8ed810a) |
| Last meaningful commit | [2026-04-08 · [sofascore, transfermarkt] add France 3rd tier (#82)](https://github.com/oseymour/ScraperFC/commit/7cc47347fa8d6d1373e6a45d59f25eaa8f8a48c2) |
| Last GitHub release | [v4.5.0](https://github.com/oseymour/ScraperFC/releases/tag/v4.5.0) · 2026-04-08 |
| Status / package / Python | Maintenance；[PyPI ScraperFC 4.5.0](https://pypi.org/project/ScraperFC/4.5.0/)，Requires-Python：>=3.10 |
| Test suite / CI | test_sofascore.py含真实网络测试；CI Ubuntu Python3.12，未见Windows矩阵；不能把网络测试存在等同稳定可复现。 |
| Documentation | README、readthedocs、example.ipynb多来源示例；未见独立benchmark。 |
| Reuse / risks | **ARCHITECTURE_REFERENCE**；DATA_LEGAL_RISK=HIGH；TECHNICAL_MAINTENANCE_RISK=HIGH；LEAKAGE_RISK=HIGH |

1. **What it does**：Sofascore、Understat、FBref、ClubElo等足球数据采集。
2. **Core modules**：src/ScraperFC/sofascore.py:Sofascore；understat.py:Understat.scrape_match/scrape_league；utils/botasaurus_getters.py。
3. **Code inspected**：[README.md](https://github.com/oseymour/ScraperFC/blob/50f5df9fae4141f91174debdb14cf87fb8ed810a/README.md)；[pyproject.toml](https://github.com/oseymour/ScraperFC/blob/50f5df9fae4141f91174debdb14cf87fb8ed810a/pyproject.toml)；[LICENSE](https://github.com/oseymour/ScraperFC/blob/50f5df9fae4141f91174debdb14cf87fb8ed810a/LICENSE)；[src/ScraperFC/utils/botasaurus_getters.py](https://github.com/oseymour/ScraperFC/blob/50f5df9fae4141f91174debdb14cf87fb8ed810a/src/ScraperFC/utils/botasaurus_getters.py)；[.github/workflows/test.yml](https://github.com/oseymour/ScraperFC/blob/50f5df9fae4141f91174debdb14cf87fb8ed810a/.github/workflows/test.yml)；[test/test_sofascore.py](https://github.com/oseymour/ScraperFC/blob/50f5df9fae4141f91174debdb14cf87fb8ed810a/test/test_sofascore.py)；[src/ScraperFC/sofascore.py](https://github.com/oseymour/ScraperFC/blob/50f5df9fae4141f91174debdb14cf87fb8ed810a/src/ScraperFC/sofascore.py)；[src/ScraperFC/understat.py](https://github.com/oseymour/ScraperFC/blob/50f5df9fae4141f91174debdb14cf87fb8ed810a/src/ScraperFC/understat.py)；[docs/source/code_examples.rst](https://github.com/oseymour/ScraperFC/blob/50f5df9fae4141f91174debdb14cf87fb8ed810a/docs/source/code_examples.rst)；[docs/source/example.ipynb](https://github.com/oseymour/ScraperFC/blob/50f5df9fae4141f91174debdb14cf87fb8ed810a/docs/source/example.ipynb)。
4. **Strengths**：来源覆盖和provider ID/比赛字段提取参考，Understat shot数据可帮助定义未来事件contract。
5. **Weaknesses**：botasaurus/cloudscraper/selenium/marimo等依赖较重；浏览器/站点结构脆弱，源事件时间不等于抓取时已知。
6. **What overlaps good**：good有Provider/Raw基础；与soccerdata来源覆盖重叠，没理由并装两套综合scraper。
7. **What good lacks**：规模化来源和字段映射知识不足，但权利/历史时间仍未解决。
8. **What should be reused**：参考来源schema与provider ID，不复制实现；只有数据授权明确且其他方案不足时再评估单一provider。
9. **What should NOT be reused**：不拷GPL scraper；不绕过访问限制；不把ClubElo抓取列成自行训练Elo能力。
10. **Integration approach**：仅acquisition设计参考，原始网络与浏览器始终在研究采集层；无资格就不seal。
11. **License**：GPL-3对分发衍生/组合程序有条件；不是商业禁令，但与当前许可清单和部署形态需审查，不建议直接生产依赖。 [实际许可证据](https://github.com/oseymour/ScraperFC/blob/50f5df9fae4141f91174debdb14cf87fb8ed810a/LICENSE)。
12. **Data-source risk**：网站条款、抓取限制、历史时间和再分发权独立，HIGH；本轮未触发目标网站批量抓取。
13. **Estimated engineering saving**：MEDIUM · 3–5 人日：schema/站点差异调研；与soccerdata重叠。

维护信号：[(capology, fbref, sofascore, transfermarkt) add Greek 1st Tier](https://github.com/oseymour/ScraperFC/pull/98)（open，2026-09-20）；[Capology fails with: ScraperFC Driver Warning: 'NoneType' object has no attribute 'find_all'](https://github.com/oseymour/ScraperFC/issues/97)（open，2026-08-29）。只把issue/PR标题与状态当线索，未当作已复现缺陷。

### 18. ML-KULeuven/soccer_xg · XG · 52/100

| 基础信息 | 核实结果 |
|---|---|
| Repository / main language | [ML-KULeuven/soccer_xg](https://github.com/ML-KULeuven/soccer_xg) / Jupyter Notebook |
| CODE_LICENSE / stars / forks | Apache-2.0 / 260 / 31 |
| Source SHA | [b9489d929e0fa34771267d429256366d0fda27ad](https://github.com/ML-KULeuven/soccer_xg/tree/b9489d929e0fa34771267d429256366d0fda27ad) |
| Last meaningful commit | [2020-07-09 · first commit](https://github.com/ML-KULeuven/soccer_xg/commit/1ac174131cb62c4e9ffafe88237593b298b0ad58) |
| Last GitHub release | NONE（查询未返回Release；不等于没有源码版本或其他渠道发行） |
| Status / package / Python | Dormant；[PyPI soccer-xg 0.0.1](https://pypi.org/project/soccer-xg/0.0.1/)，Requires-Python：>=3.6.1,<4.0.0 |
| Test suite / CI | tests/test_xg.py存在，但同一WC2018训练/验证是smoke而非泛化证明；Travis Python3.6老配置。 |
| Documentation | README、notebooks；自定义pipeline示例有时间sample设计，也有data_val误用X_train赋值及测试集选校准方法的风险。 |
| Reuse / risks | **REFERENCE_IMPLEMENTATION**；DATA_LEGAL_RISK=HIGH；TECHNICAL_MAINTENANCE_RISK=HIGH；LEAKAGE_RISK=HIGH |

1. **What it does**：射门级xG训练与特征pipeline，区分运动战/任意球/点球。
2. **Core modules**：soccer_xg/xg.py:XGModel/OpenplayXGModel；features.py:goalangle/speed；notebooks/4-creating-custom-xg-pipelines.ipynb。
3. **Code inspected**：[README.md](https://github.com/ML-KULeuven/soccer_xg/blob/b9489d929e0fa34771267d429256366d0fda27ad/README.md)；[LICENSE](https://github.com/ML-KULeuven/soccer_xg/blob/b9489d929e0fa34771267d429256366d0fda27ad/LICENSE)；[tests/test_xg.py](https://github.com/ML-KULeuven/soccer_xg/blob/b9489d929e0fa34771267d429256366d0fda27ad/tests/test_xg.py)；[setup.cfg](https://github.com/ML-KULeuven/soccer_xg/blob/b9489d929e0fa34771267d429256366d0fda27ad/setup.cfg)；[soccer_xg/xg.py](https://github.com/ML-KULeuven/soccer_xg/blob/b9489d929e0fa34771267d429256366d0fda27ad/soccer_xg/xg.py)；[soccer_xg/features.py](https://github.com/ML-KULeuven/soccer_xg/blob/b9489d929e0fa34771267d429256366d0fda27ad/soccer_xg/features.py)；[.travis.yml](https://github.com/ML-KULeuven/soccer_xg/blob/b9489d929e0fa34771267d429256366d0fda27ad/.travis.yml)；[pyproject.toml](https://github.com/ML-KULeuven/soccer_xg/blob/b9489d929e0fa34771267d429256366d0fda27ad/pyproject.toml)；[notebooks/4-creating-custom-xg-pipelines.ipynb](https://github.com/ML-KULeuven/soccer_xg/blob/b9489d929e0fa34771267d429256366d0fda27ad/notebooks/4-creating-custom-xg-pipelines.ipynb)。
4. **Strengths**：射门距离角度、身体部位与上下文特征的领域定义；说明xG需要事件及坐标，不能只存一个字段。
5. **Weaknesses**：sklearn<0.23、socceraction0.2.x等旧依赖；声明Python>=3.6不代表支持3.12；示例和测试不能作为无泄漏基准。
6. **What overlaps good**：good只有xG/xGA字段与post-match存储，没有shot model，λ baseline也不等于xG。
7. **What good lacks**：事件来源、shot features、标签、模型校准；目前不是数据Pilot解阻路径。
8. **What should be reused**：P3复核特征定义和分场景建模，用现代已选工具重建最小实验；不搬完整pipeline。
9. **What should NOT be reused**：不安装旧整包，不采用不明训练数据/时间的预训练pickle，不用目标比赛shot特征作赛前输入。
10. **Integration approach**：授权事件先冻结为历史特征；整场与日期分组，校准/选择方法只看验证集；P3评估后决定是否真的自训xG。
11. **License**：Apache-2.0允许依法复用并保留声明/变更说明；依赖许可另审，本轮仅参考。 [实际许可证据](https://github.com/ML-KULeuven/soccer_xg/blob/b9489d929e0fa34771267d429256366d0fda27ad/LICENSE)。
12. **Data-source risk**：StatsBomb/Wyscout事件和数据衍生模型权利需明确；不能仅按仓库Apache放行。
13. **Estimated engineering saving**：MEDIUM · 4–7 人日（P3）：特征与实验设计，不含修复旧包。

维护信号：[Your soccer_xg models are live — anyone with match data can run xG estimates here](https://github.com/ML-KULeuven/soccer_xg/issues/4)（open，2026-06-22）；[How to calculate xG for a single shot in a local match](https://github.com/ML-KULeuven/soccer_xg/issues/2)（open，2023-11-08）。只把issue/PR标题与状态当线索，未当作已复现缺陷。

### 19. hudl/statsbombpy · ST · 51/100

| 基础信息 | 核实结果 |
|---|---|
| Repository / main language | [hudl/statsbombpy](https://github.com/hudl/statsbombpy) / Python |
| CODE_LICENSE / stars / forks | UNKNOWN code / Custom data / 745 / 104 |
| Source SHA | [a90d179b9e60e6e3ac6844da1c1e3d418f77f502](https://github.com/hudl/statsbombpy/tree/a90d179b9e60e6e3ac6844da1c1e3d418f77f502) |
| Last meaningful commit | [2026-07-29 · get API endpoint versions from endpoint-versions](https://github.com/hudl/statsbombpy/commit/890888fc513ab9b99dddab43e6111b658574ab0f) |
| Last GitHub release | [v1.22.0](https://github.com/hudl/statsbombpy/releases/tag/v1.22.0) · 2026-07-30 |
| Status / package / Python | Active；[PyPI statsbombpy 1.22.0](https://pypi.org/project/statsbombpy/1.22.0/)，Requires-Python：UNKNOWN |
| Test suite / CI | tests/test_sb.py混合mock与在线API；所见GitHub workflow仅标签校验，未发现测试CI。 |
| Documentation | README完整API示例；标准代码license未找到；doc/LICENSE.pdf为数据用户协议而非明确的开源代码授权。 |
| Reuse / risks | **DO_NOT_USE**；DATA_LEGAL_RISK=HIGH；TECHNICAL_MAINTENANCE_RISK=HIGH；LEAKAGE_RISK=HIGH |

1. **What it does**：StatsBomb官方Python数据访问客户端，公开/订阅API与事件DataFrame。
2. **Core modules**：statsbombpy/api_client.py:get_resource/api_versions；public.py:get_response；tests/statsbombpy_test/test_sb.py。
3. **Code inspected**：[README.md](https://github.com/hudl/statsbombpy/blob/a90d179b9e60e6e3ac6844da1c1e3d418f77f502/README.md)；[setup.py](https://github.com/hudl/statsbombpy/blob/a90d179b9e60e6e3ac6844da1c1e3d418f77f502/setup.py)；[statsbombpy/public.py](https://github.com/hudl/statsbombpy/blob/a90d179b9e60e6e3ac6844da1c1e3d418f77f502/statsbombpy/public.py)；[statsbombpy/api_client.py](https://github.com/hudl/statsbombpy/blob/a90d179b9e60e6e3ac6844da1c1e3d418f77f502/statsbombpy/api_client.py)；[tests/statsbombpy_test/test_sb.py](https://github.com/hudl/statsbombpy/blob/a90d179b9e60e6e3ac6844da1c1e3d418f77f502/tests/statsbombpy_test/test_sb.py)；[.github/workflows/required-labels.yaml](https://github.com/hudl/statsbombpy/blob/a90d179b9e60e6e3ac6844da1c1e3d418f77f502/.github/workflows/required-labels.yaml)；[doc/LICENSE.pdf（数据协议，PDF文本提取）](https://github.com/hudl/statsbombpy/blob/a90d179b9e60e6e3ac6844da1c1e3d418f77f502/doc/LICENSE.pdf)。
4. **Strengths**：供应商字段和端点版本知识权威；有球队/球员/事件IDs与供应商xG字段。
5. **Weaknesses**：代码许可证UNKNOWN；导入时全局requests-cache安装到临时sqlite，改变请求行为；非200打印后返回空列表，可能混淆空数据与失败。
6. **What overlaps good**：good已有可审计HttpTransport/Raw和错误语义，不应换成该库默认网络层。
7. **What good lacks**：事件数据接入尚缺；客户端只提供供应商字段，不是xG训练器。
8. **What should be reused**：仅阅读官方schema与接口作为信息来源；当前不采用依赖/代码。许可及数据合同另获明确证据后再重新评级。
9. **What should NOT be reused**：不因为是官方客户端就默认MIT；不直接安装其依赖链或复制；不让global cache影响good网络与Raw顺序。
10. **Integration approach**：当前DO_NOT_USE；若未来有明确权利，优先Raw后由kloppy本地解析，且另审StatsBomb协议是否允许目标用途。
11. **License**：GitHub/PyPI和源码未核到标准代码license，UNKNOWN阻断依赖/复制。PDF是Custom数据条款，不能替代代码授权。 [实际许可证据](https://github.com/hudl/statsbombpy/blob/a90d179b9e60e6e3ac6844da1c1e3d418f77f502/doc/LICENSE.pdf)。
12. **Data-source risk**：仓库2018数据协议及现行open-data 2023-09-08协议限制商业使用/数据外部分发并要求署名logo；当前商业产品用途不能凭公开下载放行。
13. **Estimated engineering saving**：LOW · 0–2 人日：只读schema可节省调研；不计接入收益。

维护信号：[Fix flattening of 50/50 event outcomes](https://github.com/hudl/statsbombpy/pull/87)（open，2026-09-21）；[install_cache() at import time monkeypatches the global requests session — unexpected side effect on the whole process](https://github.com/hudl/statsbombpy/issues/85)（open，2026-09-04）。只把issue/PR标题与状态当线索，未当作已复现缺陷。

### 20. octosport/octopy · OC · 38/100

| 基础信息 | 核实结果 |
|---|---|
| Repository / main language | [octosport/octopy](https://github.com/octosport/octopy) / Jupyter Notebook |
| CODE_LICENSE / stars / forks | MIT file / Apache-2.0 manifest conflict / 76 / 27 |
| Source SHA | [3f978fdfe92a232e30147122e6180aa2aa44b77a](https://github.com/octosport/octopy/tree/3f978fdfe92a232e30147122e6180aa2aa44b77a) |
| Last meaningful commit | [2022-04-06 · [BFX] depreciated jax index_add](https://github.com/octosport/octopy/commit/50433a233617f89a306d22404e652482eb4b86d3) |
| Last GitHub release | NONE（查询未返回Release；不等于没有源码版本或其他渠道发行） |
| Status / package / Python | Dormant；仓库setup版本1.0.0；无可确认的本仓库PyPI包。PyPI octopy 0.0.2 指向 monzita/octopy，**不同项目**；旧CI3.7–3.9不证明3.12。 |
| Test suite / CI | test_goals.py有固定值但旧import路径；CI Python3.7–3.9，2022后无核心维护证据。 |
| Documentation | README与研究notebooks；不是纯notebook，实际有Python模块；无GitHub Release。 |
| Reuse / risks | **REFERENCE_IMPLEMENTATION**；DATA_LEGAL_RISK=MEDIUM；TECHNICAL_MAINTENANCE_RISK=HIGH；LEAKAGE_RISK=HIGH |

1. **What it does**：研究型足球Poisson、去水和可微Elo实验。
2. **Core modules**：octopy/goals.py:PoissonDistribution；elo/elo.py:EloRatingNet；implied.py；metrics.py:compute_1x2_log_loss。
3. **Code inspected**：[setup.py](https://github.com/octosport/octopy/blob/3f978fdfe92a232e30147122e6180aa2aa44b77a/setup.py)；[octopy/goals.py](https://github.com/octosport/octopy/blob/3f978fdfe92a232e30147122e6180aa2aa44b77a/octopy/goals.py)；[LICENSE](https://github.com/octosport/octopy/blob/3f978fdfe92a232e30147122e6180aa2aa44b77a/LICENSE)；[README.md](https://github.com/octosport/octopy/blob/3f978fdfe92a232e30147122e6180aa2aa44b77a/README.md)；[.github/workflows/python-package.yml](https://github.com/octosport/octopy/blob/3f978fdfe92a232e30147122e6180aa2aa44b77a/.github/workflows/python-package.yml)；[octopy/metrics.py](https://github.com/octosport/octopy/blob/3f978fdfe92a232e30147122e6180aa2aa44b77a/octopy/metrics.py)；[octopy/implied.py](https://github.com/octosport/octopy/blob/3f978fdfe92a232e30147122e6180aa2aa44b77a/octopy/implied.py)；[octopy/elo/elo.py](https://github.com/octosport/octopy/blob/3f978fdfe92a232e30147122e6180aa2aa44b77a/octopy/elo/elo.py)；[tests/test_goals.py](https://github.com/octosport/octopy/blob/3f978fdfe92a232e30147122e6180aa2aa44b77a/tests/test_goals.py)。
4. **Strengths**：JAX lax.scan顺序评级、可微参数优化有独特研究价值；因此保留为少量研究参考，而非因用户seed自动纳入。
5. **Weaknesses**：LICENSE写MIT但setup写Apache-2.0；PyPI同名octopy属于monzita/octopy，不能pip install同名冒充本仓库；旧np.alltrue/JAX接口风险。log_loss实际返回mean(log p)，符号与惯例相反。
6. **What overlaps good**：Poisson与去水good已经更严格；只有评级参数学习是额外研究点。
7. **What good lacks**：good没有Elo/可微Elo；后者不是当前必须能力，普通Elo优先elote。
8. **What should be reused**：仅P2/P3阅读顺序scan/参数化思想，检查训练split与测试监控造成的选择偏差。
9. **What should NOT be reused**：不安装PyPI同名包，不复制许可冲突代码，不沿用负号相反的指标，不为旧JAX重构环境。
10. **Integration approach**：保留为文献式参考；若简单Elo足够则不落地任何octopy代码。
11. **License**：实际MIT文件与打包声明冲突，按UNKNOWN/需澄清处理，暂不放行依赖或代码复制。 [实际许可证据](https://github.com/octosport/octopy/blob/3f978fdfe92a232e30147122e6180aa2aa44b77a/LICENSE)。
12. **Data-source risk**：示例数据与网站来源权利并未随代码澄清，MEDIUM；算法独立使用可降风险但当前不集成。
13. **Estimated engineering saving**：LOW · 1–2 人日：避免从零探索可微评级设计；近期可为0，不计近期总节省。

维护信号：[Analytics Proposal: Quantifying Pressing Vulnerability and Transition Danger in (Arsenal 1-1 Man City)](https://github.com/octosport/octopy/issues/5)（open，2026-07-20）；[Feature Request: Pressing Pattern & Transitional Play Analysis Module](https://github.com/octosport/octopy/issues/4)（open，2026-07-20）。只把issue/PR标题与状态当线索，未当作已复现缺陷。

## penaltyblog 专项：应复用拟合能力，不替换当前数学契约

### 数学相同点与重要差异

[good score_matrix.py](https://github.com/cxywk11/good/blob/52e9497a1c532270100bc32e5f63ccd8bbd07603/apps/api/src/jc/analysis/score_matrix.py) 接收显式λ_home、λ_away、ρ，生成比分矩阵；[penaltyblog Cython probabilities](https://github.com/martineastwood/penaltyblog/blob/72de6519e0c9a357b8b1aa2a6441a454b18ff54e/penaltyblog/models/probabilities.pyx) 的DC预测采用同一独立Poisson基底和四格修正。以行=主队、列=客队：

| 格子 | 正确τ（good与PB Cython） | PB公开 create_dixon_coles_grid 当前τ |
|---|---|---|
| 0–0 | 1 − λ_home × λ_away × ρ | 相同 |
| 0–1 | 1 + λ_home × ρ | **1 + λ_away × ρ** |
| 1–0 | 1 + λ_away × ρ | **1 + λ_home × ρ** |
| 1–1 | 1 − ρ | 相同 |

差异定位：[football_probability_grid.py L536–550](https://github.com/martineastwood/penaltyblog/blob/72de6519e0c9a357b8b1aa2a6441a454b18ff54e/penaltyblog/models/football_probability_grid.py#L536)，其中L542/543的交叉项和 [Cython L127–139](https://github.com/martineastwood/penaltyblog/blob/72de6519e0c9a357b8b1aa2a6441a454b18ff54e/penaltyblog/models/probabilities.pyx#L127) 不一致；[goalmodel dDCP](https://github.com/opisthokonta/goalmodel/blob/84ecd6c2bbad3ccb967abf88ef49e5bcd074e545/R/dixoncoles.R) 与 [footBayes dc_inflation](https://github.com/LeoEgidi/footBayes/blob/00540f5ae12b9dd6a4d97c5be228fb72c4be4b0d/src/stan/dixon_coles.stan) 也支持good/Cython形式。

独立代数核算（本轮执行的是数学算式，**没有执行第三方包**）：λ_home=2、λ_away=1、ρ=−0.1 时，正确τ按00/01/10/11顺序为1.2/0.8/0.9/1.1；公开helper为1.2/0.9/0.8/1.1。相对独立Poisson的总质量修正，正确四格相互抵消为0；错误helper为 −0.1×exp(−3)=**−0.0049787068367863965**。随后归一化不会恢复正确的单元格与1X2概率。λ相同或ρ=0会掩盖问题；现有test_rho_adjustment仅检验变化，未核对非对称λ交叉项。此结论基于所固定HEAD的源码与代数，未声称在所有发行版本中复现。

| 方面 | good | penaltyblog | 复用判断 |
|---|---|---|---|
| 数值类型 | Decimal precision=50，严格有限输入 | NumPy/Cython float64 | 输入赔率保持Decimal；浮点只在隔离模型边界 |
| λ=0 | 允许退化分布 | public helper要求λ>0 | 零λ用独立解析基准，不强行对齐输入域 |
| 截断 | 每边tail<=1e−12，cap30不足则fail | 模型max_goals默认15，范围0…14；helper为0…15 | 比较前统一支持集与归一化；不能只比较默认值 |
| ρ合法性 | 四个τ非负，非法显式拒绝 | 路径间校验/参数界不同 | 逐输入域验证，不把全局ρ界当充分条件 |
| 1X2/TTG/HHAD | 已有1X2、TTG0–6/7+、整数三项HHAD | 网格聚合、totals、AH quarter split | 不用亚洲盘概率冒充竞彩三项让球 |
| 正确比分 | 有格子，官方OTHER概率未聚合 | exact_score格子查询 | 官方HOME/DRAW/AWAY_OTHER仍由good实现 |
| 训练 | 简单GF/GA λ baseline，ρ=0 | 攻防/主场项/ρ加权MLE | 这是值得复用的主要缺口 |

### Reference Oracle与Golden规格（仅设计，未写测试）

**可作为有条件的参考，不能作为唯一真值。** 正λ且ρ=0可比较公开helper；非零ρ暂不用有缺陷的helper。拟合模型的Cython路径可做拟合/概率一致性对照，但不为golden测试依赖非公开参数注入。优先独立Decimal解析式 + SciPy Poisson + goalmodel DC三方对照；上游helper修复并通过所锁发行版验证后再纳入。

拟议用例包括(1,1,0)、(2,1,0)、(2,1,−0.1)、(1,2,−0.1)、近边界合法ρ、非法τ、λ=0退化、较大λ触发截断失败。先比较未归一化指定格子，再统一支持集比较矩阵、1X2、总进球、TTG7+，防止normalize掩盖公式错误。浮点对照初始容差建议1e−10，加明确尾误差上界；需实际运行后校准，不把此值作为已验收门槛。good内部1e−45的求和契约继续有效，不能要求float oracle满足它。

已有 [test_score_matrix.py](https://github.com/cxywk11/good/blob/52e9497a1c532270100bc32e5f63ccd8bbd07603/tests/test_score_matrix.py) 用80位Decimal和独立阶乘公式校验。外部oracle是额外验证来源，并不是发现good缺少golden tests。

### 拟合、权重、Bayesian与评级

[DixonColesGoalModel.fit](https://github.com/martineastwood/penaltyblog/blob/72de6519e0c9a357b8b1aa2a6441a454b18ff54e/penaltyblog/models/dixon_coles.py) 使用带权约束优化，可联合估计attack/defense、home advantage和ρ。其指数参数采用attack+defense方向，约束sum(attack)=球队数；[goalmodel](https://github.com/opisthokonta/goalmodel/blob/84ecd6c2bbad3ccb967abf88ef49e5bcd074e545/R/goalmodel_fit.R) / [bpl-next](https://github.com/anguswilliams91/bpl-next/blob/a79b63f00ca57e07d9730789181892bfab74be52/bpl/dixon_coles.py) 的防守符号/中心化不同，参数本身不能直接横向相减，应比较λ、似然和预测。优化失败/未知球队/负τ/样本不足都需显式状态，不能降级成一个正常概率结果。 所读 [loss.pyx L133–145](https://github.com/martineastwood/penaltyblog/blob/72de6519e0c9a357b8b1aa2a6441a454b18ff54e/penaltyblog/models/loss.pyx#L133) 将τ截到epsilon再取log；fit只有参数box bounds和攻防识别约束，没有逐场τ非负约束。因此优化器报告成功不构成所有预测概率合法的证明，adapter必须另外检查。

[dixon_coles_weights](https://github.com/martineastwood/penaltyblog/blob/72de6519e0c9a357b8b1aa2a6441a454b18ff54e/penaltyblog/models/utils.py) 计算指数日期衰减；基准日期取传入日期最大值，权重不是未来样本过滤器。good必须先按训练cutoff、finished_at与available_at筛出训练集，再按训练时点计算权重；不能把未来行交给库再指望小权重消除泄漏。

[BayesianGoalModel](https://github.com/martineastwood/penaltyblog/blob/72de6519e0c9a357b8b1aa2a6441a454b18ff54e/penaltyblog/models/bayesian_goal_model.py) 的起点用全局NumPy随机数，fit没有清晰独立seed参数；不能宣称默认deterministic。Bivariate Poisson共享潜变量拟合、层次Bayesian都可作为P2研究参考，现阶段不引入其完整运行栈。

[Elo](https://github.com/martineastwood/penaltyblog/blob/72de6519e0c9a357b8b1aa2a6441a454b18ff54e/penaltyblog/ratings/elo.py) 的期望得分不等于完整1X2；draw概率是启发式。其 [PiRatingSystem](https://github.com/martineastwood/penaltyblog/blob/72de6519e0c9a357b8b1aa2a6441a454b18ff54e/penaltyblog/ratings/pi.py) 使用home/away rating、damped error和正态CDF构造概率，须标明具体变体与参数，不能只写“标准Pi”而未核论文一致性。建议先普通Elo，再证明Pi有独立价值。

### 指标与策略边界

[metrics.pyx](https://github.com/martineastwood/penaltyblog/blob/72de6519e0c9a357b8b1aa2a6441a454b18ff54e/penaltyblog/metrics/metrics.pyx) 的多类Brier求和口径与good一致；ignorance使用log2，good用ln，因此换算需乘ln(2)。RPS依赖有序类别，固定HOME/DRAW/AWAY并说明其隐含距离含义；它只能作为辅助，不替换LogLoss/Brier。octopy的“log loss”反号、netcal默认top-label ECE也必须单独标注，禁止把同名列直接平均。

[kelly.py](https://github.com/martineastwood/penaltyblog/blob/72de6519e0c9a357b8b1aa2a6441a454b18ff54e/penaltyblog/betting/kelly.py) 单项为edge/(odds−1)后fraction与clip，多项采用预算约束优化；风险计算假设互斥结果，不能随意用于不同比赛的相关组合。其max_loss/VaR不等于历史Max Drawdown，risk_of_ruin不是经长期路径验证的破产概率。本轮只分析，任何Kelly/staking/value-bet均不接入good。

## soccerdata 专项：来源适配可学，时态证明不可外包

`BaseReader`管理league/season、path cache与no_cache/no_store；`BaseRequestsReader`有最多5次尝试以及rate_limit/jitter，`BaseSeleniumReader`处理浏览器路径；FBref配置约7秒请求间隔。这说明它比“requests+BeautifulSoup”脚本成熟，但不意味着抓取获得法律授权或历史快照资格。[reader源码](https://github.com/probberechts/soccerdata/blob/e120471e424a173e83e8aeeaaf4d954ab9d38ee4/soccerdata/_common.py)、[FBref](https://github.com/probberechts/soccerdata/blob/e120471e424a173e83e8aeeaaf4d954ab9d38ee4/soccerdata/fbref.py)。

good可参考 `LEAGUE_DICT` 和 `SeasonCode` 对跨年赛季/来源联赛ID的表达；统一名称只用于候选匹配，必须保留provider ID与原文，由good的人工确认/绑定版本建立UUID关系。标准DataFrame不是跨站身份真实性证明。[config](https://github.com/probberechts/soccerdata/blob/e120471e424a173e83e8aeeaaf4d954ab9d38ee4/soccerdata/_config.py)。

`MatchHistory.read_games`抓取football-data赛季CSV，当前赛季刷新、坏行警告和缺时间补12:00均会影响时态可信度。CSV中closing odds可用于对应口径研究，不能还原不存在的T−30/T−90/T−360报价。缓存命中时间、文件mtime、比赛日期、当前抓取时间都不能自动成为历史published_at。[MatchHistory](https://github.com/probberechts/soccerdata/blob/e120471e424a173e83e8aeeaaf4d954ab9d38ee4/soccerdata/match_history.py)。

先重用来源覆盖知识；只有能够在解析前保存原始响应、遵守源协议、证明所需时间语义时，才评估独立研究worker调用库。为解决一个CSV来源安装全套Selenium/TLS栈不是默认方案。

## socceraction 专项：P3，而非当前Phase 4解阻项

`StatsBombLoader`支持本地JSON和远程statsbombpy；本地加载适合已冻结Raw，但不能免除数据许可。SPADL转换实际处理动作、球队/球员与坐标（StatsBomb120×80到105×68）等领域差异；xT以网格射门、得分、移动概率与转移矩阵迭代估值，成功移动价值为终点−起点。[loader](https://github.com/ML-KULeuven/socceraction/blob/93a1242d46c104889205753accaabadb00c45c6d/socceraction/data/statsbomb/loader.py)、[SPADL](https://github.com/ML-KULeuven/socceraction/blob/93a1242d46c104889205753accaabadb00c45c6d/socceraction/spadl/statsbomb.py)、[xT](https://github.com/ML-KULeuven/socceraction/blob/93a1242d46c104889205753accaabadb00c45c6d/socceraction/xthreat.py)。

VAEP未来动作目标是合法的训练label，不是允许未来特征进入模型。其内部 `np.random.permutation` 验证切分会混合同场事件，不能照用；需要完整比赛、时间顺序的外部训练/验证/测试设计。[VAEP](https://github.com/ML-KULeuven/socceraction/blob/93a1242d46c104889205753accaabadb00c45c6d/socceraction/vaep/base.py)、[labels](https://github.com/ML-KULeuven/socceraction/blob/93a1242d46c104889205753accaabadb00c45c6d/socceraction/vaep/labels.py)。

P3优先验证一种事件源与最小SPADL/xT链路，之后才考虑VAEP；先确认NumPy<2、旧pandera/SciPy插值API兼容。没有事件授权与目标比赛赛前可用的聚合方式，就不进入主API环境。

## 赔率源审计：抓到数字并不等于可回放

以下均基于上面逐库“Code inspected”链接中的provider实现。🟡表示存在部分字段/机制，但不满足good完整契约。

| 项目/路径 | Bookmaker/market/line | Timestamp / history / change | Decimal / dedup | retry / rate / cache | 对good的结论 |
|---|---|---|---|---|---|
| good odds.py + providers | provider与bookmaker字段；market/selection/quarter line规范 | 四类时间与独立visibility、Observation/Snapshot；禁止补造阈值 | Decimal、append-only去重；跨provider同bookmaker尚需统一身份 | 自有HttpTransport/Raw先存、限流重试 | 保留；不因引库降低语义 |
| PB FootballData/BaseScraper | CSV bookmaker列/标准名字；有限市场解析 | 历史CSV，不是逐次as-observed变动；无T−N证明 | pandas/float；无观察记录体系 | 所读requests.get路径未见显式timeout/retry；文件缓存 | 只能做来源/解析参考 |
| soccerdata MatchHistory | provider列名与球队别名；不是统一bookmaker registry | CSV历史，日期/补12:00非报价时间；cache覆盖 | DataFrame数值；名称级规范化非UUID/dedup历史 | reader有尝试/rate+jitter、mtime cache | 缺少时间证据不能SEALED |
| sports-betting OddsApi | bookmaker key、h2h与total2.5，source/schema分层 | 历史API约5分钟快照与5分钟tolerance；closing以开赛前1分钟为目标；lastupdate_max不是全市场同时发布证明 | pandas浮点；pivot first/身份列去重，非good observation | aiohttp连接数上限；所读fetch路径无显式retry/逐源节流；RawPayload只有item/content | 有用设计；追加good取得时间/hash/许可与逐项有效时间 |
| soccerapi（排除） | bookmaker parser；合并依赖位置与名字 | 赛事日期不是quote观察时间；无严格历史日志 | 浮点/字典；未核到可审计去重 | 旧网络脚本/部分Docker示例 | 禁止作为历史源补丁 |
| shin / implied | 接收完整odds array/map，非数据源 | 无联网/时间/history | 浮点求根；选择顺序/完整性由调用方负责 | 不适用 | 放在已验证市场之后，不承担来源身份 |

跨provider的同一bookmaker、不同market period、line符号、赔率格式和观测时刻要先统一，再做consensus；否则一家公司可被重复计权。third-party float只用于纯函数计算，原始赔率字符串、Decimal、source_record_id和时间证据必须保留。比赛开球时间、event clock、源方最后修改时间、抓取时间、数据库可见时间互不替代。

## 回测/泄漏与结算专项

| 核查项 | penaltyblog | sports-betting | elote / 通用库 | good所需约束 |
|---|---|---|---|---|
| 时间切分 | 按date日训练，train<day；日内精度丢失 | DatetimeIndex排序+TimeSeriesSplit | elote period先预测后更新；sklearn默认CV非时序 | 按真实cutoff/available_at、整场分组，训练/校准/测试分离 |
| 标签隔离 | predictor callback收到整行，可能包含赛果 | schema防preplay使用inplay，但仍是框架时间 | VAEP随机事件验证、Dirichlet随机示例高风险 | frozen feature内无target，标签只在评估侧 |
| closing odds | 不提供可审计closing政策 | historical closing目标/tolerance有实现 | 无统一closing | T−30特征不能使用closing；CLV单独事后评价 |
| settlement | Account的二值outcome、stake×(odds×outcome−1) | bool bets与Y/O简单收益 | 评级/校准不是结算系统 | 全赢/半赢/走水/半输/全输/void分别定义 |
| quarter / push | 概率helper拆半注；Account不等于完整结算 | 所读路径未见完整亚洲盘结算 | 不适用 | HHAD三项与AH二项不能共用结算 |
| commission | 未见通用佣金账本 | 未见完整佣金模型 | 不适用 | 是否交易所、净赢佣金等须按venue记录 |
| ROI / Yield | ROI=profit/initial bankroll | ROI/initial_cash；fixed-stake Yield，零收益下注计数风险 | binary评级指标不能代替收益 | 明确ROI分母与turnover，不混用bankroll return/yield |
| Drawdown | bankroll min/max不是峰谷回撤 | 所读回测未见完整资金曲线maxDD | 无统一实现 | 自有settled cash与open exposure，逐时刻equity峰谷 |
| bankroll | 简单float Account | init_cash与固定stake回测 | 无完整资金账本 | Decimal、占用资金、同时赛事与结算顺序 |
| Kelly | 单项/多项函数，假设条件见专项 | 模型/下注政策耦合，未纳入复用 | 不适用 | 不接入；Prediction ≠ Recommendation |
| CLV | 未见 | closing数据不等于已实现CLV | 未见 | 同bookmaker/market/line对齐，closing定义和缺失率显式 |
| Bootstrap CI | 未见端到端时间CI | 未见 | SciPy有IID/paired bootstrap | 成对模型差值按比赛/时间块，不能把相关快照当独立样本 |
| 调参/模型选择 | 用户callback自负边界 | splitter之外仍需验证集 | elote benchmark测试集优化阈值；LGB默认shuffle | 参数/阈值只看过去验证窗口，final test不得回流 |
| coverage | 需外部记录 | NaN/零收益等需核分母 | elote跳过draw/unseen队 | good已有paired/coverage；所有剔除原因审计 |

**没有一个入选库可直接替代good的完整、可审计、支持竞彩规则的回测系统。** 可以复用数值函数/训练器与测试思想；回测编排、结算口径与资金账本需要掌握在本项目内。此处是能力边界分析，不实施任何投注策略。

## License与数据权利

本仓库根目录本次未找到LICENSE/LICENCE文件，因此good未来的对外分发许可政策也尚未由代码明确。生产依赖候选不等于在任何分发场景均无义务。

| 代码许可类别 | 依赖 | 复制/修改 | 署名/通知 | copyleft / 本项目风险 |
|---|---|---|---|---|
| MIT | 按条款可 | 按条款可 | 保留版权与许可文本 | 低；数据许可独立 |
| BSD-3-Clause | 按条款可 | 按条款可 | 保留版权/许可/免责声明，不借作者背书 | 低 |
| Apache-2.0 | 按条款可 | 按条款可 | 保留LICENSE、适用NOTICE、标明修改 | 低至中；保留专利/通知条件 |
| GPL-2 / GPL-3 | 使用本身并非禁止；生产需结合部署/分发形态 | 受GPL条件约束 | 保留许可与相应源码等义务依场景落实 | 分发组合/衍生程序copyleft需审；内部运行不自动要求公开；独立进程不是万能豁免 |
| AGPL | 本次最终20没有 | 本轮无此类复制建议 | 未做该类候选准入 | 后续单独审查 |
| Unknown / 冲突 | 当前不放行 | 当前不放行 | 不能靠“公开仓库”补足授权 | statsbombpy代码、octopy冲突 |
| Custom数据条款 | 不能当开源代码许可 | 仅按具体数据条款 | 来源规定的署名/用途/分发约束 | StatsBomb需明确目标用途授权 |

逐项目可执行判定：

| Repo | Can use dependency? | Can copy/modify code? | Attribution? | Copyleft risk? | Production risk |
|---|---|---|---|---|---|
| PB | YES（许可证层面） | YES（保留许可） | YES，版权/许可 | LOW | 代码许可友好≠推荐生产采用 |
| SP | YES（许可证层面） | YES（保留许可） | YES，版权/许可 | LOW | 依赖准入表所列技术/数据门槛 |
| SK | YES（许可证层面） | YES（保留许可） | YES，版权/许可 | LOW | 依赖准入表所列技术/数据门槛 |
| SD | YES（许可证层面） | YES（保留许可） | YES，LICENSE/适用NOTICE与变更说明 | LOW | 代码许可友好≠推荐生产采用 |
| EL | YES（许可证层面） | YES（保留许可） | YES，版权/许可 | LOW | 依赖准入表所列技术/数据门槛 |
| SH | YES（许可证层面） | YES（保留许可） | YES，版权/许可 | LOW | 依赖准入表所列技术/数据门槛 |
| KL | YES（许可证层面） | YES（保留许可） | YES，版权/许可 | LOW | 依赖准入表所列技术/数据门槛 |
| LG | YES（许可证层面） | YES（保留许可） | YES，版权/许可 | LOW | 依赖准入表所列技术/数据门槛 |
| SB | YES（许可证层面） | YES（保留许可） | YES，版权/许可 | LOW | 代码许可友好≠推荐生产采用 |
| SA | YES（许可证层面） | YES（保留许可） | YES，版权/许可 | LOW | 代码许可友好≠推荐生产采用 |
| GM | CONDITIONAL（分发审查） | CONDITIONAL（遵守GPL） | YES，版权/许可 | HIGH（衍生/组合分发） | MEDIUM/HIGH，故仅reference |
| IM | CONDITIONAL（分发审查） | CONDITIONAL（遵守GPL） | YES，版权/许可 | HIGH（衍生/组合分发） | MEDIUM/HIGH，故仅reference |
| BP | YES（许可证层面） | YES（保留许可） | YES，版权/许可 | LOW | 代码许可友好≠推荐生产采用 |
| NC | YES（许可证层面） | YES（保留许可） | YES，LICENSE/适用NOTICE与变更说明 | LOW | 代码许可友好≠推荐生产采用 |
| FB | CONDITIONAL（分发审查） | CONDITIONAL（遵守GPL） | YES，版权/许可 | HIGH（衍生/组合分发） | MEDIUM/HIGH，故仅reference |
| DC | YES（许可证层面） | YES（保留许可） | YES，版权/许可 | LOW | 代码许可友好≠推荐生产采用 |
| SF | CONDITIONAL（分发审查） | CONDITIONAL（遵守GPL） | YES，版权/许可 | HIGH（衍生/组合分发） | MEDIUM/HIGH，故仅reference |
| XG | YES（许可证层面） | YES（保留许可） | YES，LICENSE/适用NOTICE与变更说明 | LOW | 代码许可友好≠推荐生产采用 |
| ST | NO（待许可澄清） | NO | UNKNOWN / 另有数据署名 | UNKNOWN | HIGH |
| OC | NO（待许可澄清） | NO | UNKNOWN / 另有数据署名 | UNKNOWN | HIGH |

上述YES只是许可层面，**本轮复制数量=0、安装数量=0**。每项实际许可证据见逐库固定SHA链接；GPL判断直接对照所读ScraperFC GPL-3全文的§0/§2/§5/§6，不根据“GPL不能商业化”误解作结论。

| 数据源 | 本次已核证据 | 可接受用途与未解问题 |
|---|---|---|
| The Odds API | [官方Terms，2026-08-31版](https://the-odds-api.com/terms-and-conditions.html) | 允许长期存储及商业应用/研究/衍生模型等；禁止将原始数据作为主要产品转售或重打包数据feed。历史访问权限、合同、订阅范围仍须确认，不能仅凭开源client推定 |
| StatsBomb open-data | [当前open-data LICENSE.pdf](https://github.com/statsbomb/open-data/blob/master/LICENSE.pdf)（文本日期2023-09-08）及 [statsbombpy附带2018协议](https://github.com/hudl/statsbombpy/blob/a90d179b9e60e6e3ac6844da1c1e3d418f77f502/doc/LICENSE.pdf) | 非商业/外部分发限制、署名logo等；公开可下载不等于可用于当前商业产品及衍生分析。生产用途需取得与目的相符的权利 |
| football-data.co.uk | [Data说明](https://www.football-data.co.uk/data.php) | 免费历史CSV/研究资源不是明确开放再分发许可证；包含多来源赔率，需核使用/分发权和列语义，不保证准确性与任意历史时点可用性 |
| FBref / Understat / WhoScored / Sofascore / ClubElo | 仓库provider实现与最新问题单 | 本次未获得覆盖全部站点的商业/批量/再分发授权证据，UNKNOWN；反自动化限制不是需要绕过的bug |
| lottery.gov.cn / sporttery / VIPC | [good RESEARCH_SOURCES](https://github.com/cxywk11/good/blob/52e9497a1c532270100bc32e5f63ccd8bbd07603/docs/RESEARCH_SOURCES.md)、[PILOT_DATASET_REPORT](https://github.com/cxywk11/good/blob/52e9497a1c532270100bc32e5f63ccd8bbd07603/docs/PILOT_DATASET_REPORT.md) | 官方主池身份、原始历史可得时刻、授权与可回放资格仍需逐项完成；当前无真实SEALED Pilot。本轮不探测或绕过567 |

## 工程决策摘要

最值得立即利用的Top5：**penaltyblog、SciPy、scikit-learn、soccerdata、elote**。前两者用于互相独立的数值/拟合边界，sklearn避免未来自造校准器，soccerdata减少来源适配调研，elote减少评级重复。立即利用均以本次只读审计为界。

Top5 Reference Oracle：**SciPy（Poisson/tails）、goalmodel（独立DC/ρ/RPS）、penaltyblog（受限路径，先排helper缺陷）、scikit-learn（指标/校准）、shin（去水）**。这些不是完全可互换的五个“真值”，均需明确输入域、口径和数值误差。

没有选择 CODE_PORT_CANDIDATE：虽然MIT等允许，当前没有必须复制代码才能解决的缺口。优先已知数学规格、稳定库API和独立测试；不要为了凑五种类型而建议vendor源码。

未来近期模块估计**净省30–45开发人日，约25%–28%**，仅相对于复用计划中明确的120–160人日工程篮子；不是全项目总工期，更不是预测收益/ROI。逐库范围重叠，禁止累加；P3事件分析与授权等待不纳入近期节省。详见 [复用计划](OPEN_SOURCE_REUSE_PLAN.md)。

配套文件：[能力矩阵](OPEN_SOURCE_CAPABILITY_MATRIX.md)、[按能力Gap分析](OPEN_SOURCE_GAP_ANALYSIS.md)、[分阶段复用与依赖风险](OPEN_SOURCE_REUSE_PLAN.md)、[机器证据账本](open-source-audit-data.json)。本轮未改原Phase4 roadmap，仅在新文档提出OLD→NEW供人工复核。
