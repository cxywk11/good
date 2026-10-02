# Open Source Reuse Plan

日期2026-10-02；基准good main `52e9497a1c532270100bc32e5f63ccd8bbd07603`。**本轮只交付方案；新增生产/开发依赖均为0，下面实施项等待人工复核后的另一次授权。** 不自动开始集成。源码与风险证据见 [Audit](OPEN_SOURCE_AUDIT.md)，按能力缺口见 [Gap Analysis](OPEN_SOURCE_GAP_ANALYSIS.md)。

## P0 — Now：先确定基准、边界与准入

当前已完成：本次20库源码审计、能力清单/矩阵、许可与数据风险、官方Pilot仍阻塞的确认、非零ρ helper差异的独立代数核查。没有运行外部库、创建新测试或修改roadmap。

人工复核后最有价值的下一轮工作：

| 项 | 使用参考 | 最小工作 | 完成证据 |
|---|---|---|---|
| 数学oracle规格 | SciPy、goalmodel、penaltyblog | 为现有score-math-v1设计跨实现测试；保留现有Decimal独立公式；屏蔽PB非零ρ有缺陷入口 | 非对称λ/ρ、tail、退化输入、非法τ、统一截断及单位/类别顺序清楚 |
| 指标口径核对 | sklearn、PB、netcal | ln/log2、Brier scale、ECE top-label/OVR、RPS排序的独立小fixture规格 | 同一输入明确何时相等、何时须换算；不重写已有evaluation |
| 非比例去水参考 | shin、implied | 保留比例基线，只定义Shin/power对照输入和失败状态 | 完整市场、同时间、相同选项和收敛诊断 |
| 依赖准入决定 | 本文件风险表 | 仅选真正需要的dev oracle，锁发行物、许可、Windows3.12 smoke清单 | 不把20库一次性装入环境；发布版与HEAD分开 |
| 来源适配评审 | soccerdata、sports-betting | 借鉴league/season/schema；核对是否支持先Raw后解析 | 无法证明时态/权限即不入合格dataset，不因可抓取降低Gate |

P0推荐“利用”是参考与可批准的dev验证；当前主项目没有需要立即替换的生产模块。不得为执行这些建议自行修改本轮范围。

## P1 — After Official Pilot：有真实SEALED之后

**硬门槛：lottery.gov.cn真实官方Pilot SEALED**，且官方Sporttery目标身份/赛果、raw来源、时区与报价可获得时间、合法用途和原项目Gate A–F通过。仅本地mock SEALED、手造dataset或第三方赔率表不满足此门槛。不同T−30/T−90/T−360 cutoff独立run；不足覆盖不能补造。小Pilot通过也不自动意味着足以拟合所有模型。

| 顺序 | 工作 | 第三方边界 | 验收/停止条件 |
|---|---|---|---|
| 1 | 只读walk-forward预测评估 | 参考sports-betting/elote；用good冻结dataset/visibility | 同比赛不跨折，训练/校准/测试时间隔离，每折成员hash、coverage、paired LogLoss/Brier |
| 2 | 一个攻防Poisson/DC拟合challenger | penaltyblog先离线reference；license/依赖/公开API/数值缺陷解决后另评生产准入 | λ/ρ合法、收敛与未知队伍显式；与现有goals baseline同样本，不能仅看训练似然 |
| 3 | 普通Elo基线 | elote candidate；不为单个简单rating孤立引入全科学栈 | 逐场/period正确更新、draw/unseen coverage；Elo expected score→1X2映射另验证 |
| 4 | 最小校准实验 | sklearn sigmoid优先，样本支持时isotonic | 独立calibration窗口；训练与最终test不回流；若LogLoss恶化或样本不足保持未校准 |
| 5 | 去水敏感性 | shin窄API；implied仅oracle | 不替换market-v1默认算法；报告失败、覆盖、方法参数与paired差值 |
| 6 | 最小训练/预测工件记录 | good自行掌握 | dataset/hash/cutoff/feature引用、版本、类别顺序、失败状态；不引入ML平台 |

若当前许可合格的库不能在不破坏good时态/数值边界下工作，应停在reference，而不是重构整个项目迁就它。

## P2 — After 3-season Dataset：再做规模模型

**门槛：至少三赛季、来源权利与历史时间语义合格、真实目标身份可追溯、SEALED可复现。** 三赛季数量本身不代表无偏：同时报告联赛/赛季/市场/盘口/目标池覆盖与缺失模式。

1. 在相同外层时间窗口比较market、goals、拟合DC、Elo、简单sklearn分类基线；只选择一个LightGBM challenger，不并装三个boosting框架。
2. 若稀疏队伍/联赛差异表明有需要，再参考bpl-next/footBayes的层次prior/Bayesian模型；记录seed、chains、warmup、收敛、运行环境，不承诺跨硬件位级一致。
3. 对授权且具备可得时间证据的历史供应商xG/xGA做特征实验；模型λ不能改名成shot xG。
4. 校准数据足够时才试Dirichlet；Ensemble须有独立out-of-time互补证据和只用过去验证集学习的权重。
5. Bootstrap使用paired模型差值与预先规定的比赛/时间块；不对同场多快照作IID。SciPy提供数值方法，抽样单位由good定义。
6. 只有收益研究另获需求后才做settlement/ROI/Yield/CLV/Max Drawdown；历史quote资格、可成交性、佣金、void、quarter/push、stake与资金占用必须先定义。禁止自动接投注执行/Kelly。

## P3 — Advanced：事件分析

**门槛：真实业务需要+事件数据权利+完整事件时间/身份/坐标质量。** 一种源先行：本地Raw→kloppy或对应reader→SPADL→最小xT。避免重复用kloppy和socceraction做两套完整事实模型。VAEP在按完整比赛和日期切分后再试。

socceraction旧NumPy1.x栈不能直接与当前SciPy NumPy2.x栈合并。soccer_xg只借鉴特征，不修整个旧包；如已有合法供应商xG足够，就不自训。octopy可微Elo没有必要触发独立实现。没有授权就不因“open-data”名称推进商业接入。

## Recommended Production Dependencies（未来候选，当前不新增）

这里的候选指通过后续具体准入测试后可使用稳定API；不是要求逐个安装。

| 包 | 阶段/用途 | 采用前门槛 | 不采用条件 |
|---|---|---|---|
| scipy | P1/P2统计工具；P0可仅dev oracle | 选定版本/Windows3.12 wheel，分组bootstrap与数值口径 | 仅现有Decimal Poisson无需增加生产依赖 |
| scikit-learn | P1 calibration、P2简单分类基线 | 明确时序/分组训练与独立calibration，版本冻结 | 无足够校准样本时保持当前诊断 |
| elote | P1普通Elo | 科学栈已因其他实际用途获准；状态/三类映射/版本测试 | 为几行评级更新引入整套非必要栈，或所需修复只在未发行HEAD |
| shin | P1非比例去水challenger | Windows wheel、收敛与输入域验证、实验价值明确 | 比例去水已满足目标或样本无差异，不新增 |
| lightgbm | P2单一boosting | 三赛季合格、简单baseline、独立out-of-time评估 | 尚未完成数据/评估；不自动扩大到XGBoost/CatBoost |
| kloppy | P3本地事件解析 | 源许可与事件契约、固定raw/hash/坐标验证 | 没有事件需求、无权利、只需球队统计 |

**penaltyblog暂不列生产推荐**：有高复用价值，但public helper缺陷、整包依赖和statsbombpy代码许可尚未通过准入。soccerdata优先架构参考；只有具体provider可以满足Raw与权利门槛时另评独立acquisition worker。DO_NOT_USE statsbombpy、octopy不因依赖其他包而被间接放行。

## Recommended Dev/Test Reference Dependencies（与生产分表）

| 层级 | 项目 | 用途 | 约束 |
|---|---|---|---|
| 首选oracle | SciPy | Poisson PMF/SF、统计对照 | 统一截断与数值误差，不替换Decimal契约 |
| 首选oracle | goalmodel | 独立DC/ρ/Log/Brier/RPS | 独立R研究环境；GPL源码不复制；zero-prob log口径明确 |
| 受限oracle | penaltyblog | 拟合目标、Cython路径与市场聚合 | 非零ρhelper暂排除；安装前连同statsbombpy许可审核，未通过时只读源码 |
| 首选oracle | sklearn | LogLoss/Brier与校准对照 | epsilon/scaling/类别顺序固定；禁止默认随机时序评估 |
| 首选oracle | shin | 独立Shin数值与收敛 | 同一完整市场、输出诊断；无网络 |
| 次选 | implied | 去水方法/逆变换 | R/GPL，离线结果对照，非production |
| 次选 | elote | Elo known values、period顺序设计 | draw/unseen与测试阈值选择风险 |
| 后期 | netcal、dirichletcal | ECE定义/高级校准 | 单独重依赖环境；不得混指标口径 |
| 后期 | bpl-next、footBayes | Bayesian结构/后验预测 | 不同JAX/Stan环境；采样诊断与数据边界 |
| P3参考 | socceraction、soccer_xg | SPADL/xT/VAEP与shot特征 | 授权事件、完整比赛切分；旧依赖隔离 |

本轮没有创建这些环境；“reference dependency”不表示可以跳过代码许可证或数据协议。

## Dependency Risk：Windows / Python 3.12+ / FastAPI栈

当前root pyproject只含Web/数据库/任务/鉴权依赖，没有NumPy/SciPy/sklearn。以下来自2026-10-02的PyPI JSON与固定HEAD manifest。wheel大小是**单个压缩发行文件**，不是安装大小或依赖闭包。全量安装体积、完整传递闭包、在本项目实际可运行性均为 **UNKNOWN（未安装/未解析环境）**。pure-Python wheel不意味着依赖无native代码。

| 包/发行版 | Python metadata | 选定发行物压缩大小 | compiled / Windows3.12证据 | 直接及主要传递依赖风险 | 代码许可 / API稳定性 |
|---|---|---:|---|---|---|
| [penaltyblog 1.13.0](https://pypi.org/project/penaltyblog/1.13.0/#files) | >=3.10 | 2,249,958 bytes（wheel） | Cython/C/C++构建；cp312 Windows wheel已见 | 22个直接依赖；numpy/scipy/pandas/native lxml及statsbombpy等。后者代码许可UNKNOWN；安装闭包未解析。 | MIT；中；公开helper与底层不一致、发展快，锁函数路径。 |
| [scipy 1.18.1](https://pypi.org/project/scipy/1.18.1/#files) | >=3.12 | 36,658,278 bytes（wheel） | C/C++/Fortran/BLAS；cp312 Windows wheel已见 | numpy>=2.0,<2.8；二进制与第三方许可证体积明显。 | BSD-3-Clause；高成熟；main开发版与发行1.18.1分开。 |
| [scikit-learn 1.9.1](https://pypi.org/project/scikit-learn/1.9.1/#files) | >=3.11 | 8,262,238 bytes（wheel） | Cython/C/C++/OpenMP；cp312 Windows wheel已见 | NumPy/SciPy/joblib/narwhals/threadpoolctl；版本下限不代表所有组合已验证。 | BSD-3-Clause；高成熟；FrozenEstimator/CV/scaling语义依版本核对。 |
| [soccerdata 1.9.1](https://pypi.org/project/soccerdata/1.9.1/#files) | <3.15,>=3.10 | 52,631 bytes（wheel） | 包本身pure Python；lxml/浏览器/TLS native组件 | seleniumbase、wrapper-tls-requests、pandas、lxml等；浏览器下载体积不在wheel内。 | Apache-2.0 + retained MIT notice；源站脆弱；Ubuntu CI无Windows成功证据。 |
| [elote 1.5.0](https://pypi.org/project/elote/1.5.0/#files) | >=3.10 | 150,669 bytes（wheel） | pure Python包；NumPy/SciPy native传递栈 | 基础numpy/scipy/tqdm/setuptools；不装datasets extras；不应为了简单Elo新装全部数据依赖。 | MIT；小项目；HEAD arena修复不在1.5.0发行中。 |
| [shin 0.2.2](https://pypi.org/project/shin/0.2.2/#files) | >=3.9 | 102,660 bytes（wheel） | Rust/PyO3/maturin；cp312 Windows wheel已见 | Requires-Dist为空；native扩展是硬导入，force_python不免除它。 | MIT；窄API；0.2.x，必须验证收敛/字段。 |
| [kloppy 3.19.0](https://pypi.org/project/kloppy/3.19.0/#files) | >=3.9 | 30,121,375 bytes（wheel） | 包pure Python；lxml native，fsspec[http] | dateutil/pytz/sortedcontainers；fsspec HTTP extra带aiohttp依赖；wheel含较多fixtures。 | BSD-3-Clause；活跃，source parser仍随上游格式变。 |
| [lightgbm 4.7.0](https://pypi.org/project/lightgbm/4.7.0/#files) | >=3.10 | 1,360,833 bytes（wheel） | C++/OpenMP native DLL；Windows wheel已见 | numpy/scipy/narwhals；sklearn wrapper需scikit-learn；不引入GPU或源码编译。 | MIT；成熟但版本间训练结果不保证位级相同。 |
| [sports-betting 0.15.1](https://pypi.org/project/sports-betting/0.15.1/#files) | <3.14,>=3.11 | 154,143 bytes（wheel） | pure Python包；pyarrow/numpy/scipy native传递 | pandas/pandera/pyarrow/scikit-learn/aiohttp等；execution extras另有浏览器。 | MIT；0.15.x，framework与good边界不同。 |
| [socceraction 1.5.3](https://pypi.org/project/socceraction/1.5.3/#files) | <3.13,>=3.9 | 93,103 bytes（wheel） | pure Python包；lxml/numpy/scipy native传递 | numpy>=1.26,<2；pandera<.18、lxml<5、sklearn；与SciPy1.18.1的numpy>=2不相容。 | MIT；核心更新慢；interp2d等旧API需兼容验证。 |
| [bpl-next 0.5.2](https://pypi.org/project/bpl-next/0.5.2/#files) | <4,>=3.10 | 30,505 bytes（wheel） | pure Python包；JAX/jaxlib/NumPyro native传递 | numpy>=2.2.6、numpyro>=.19、scipy>=1.15.3、pip>=26.2.1；Windows无本次验证。 | MIT；小型0.x；HEAD0.5.0与PyPI0.5.2差异需复查。 |
| [netcal 1.4.0](https://pypi.org/project/netcal/1.4.0/#files) | >=3.10 | 235,951 bytes（wheel） | pure Python包；torch/GPyTorch/Pyro等较重传递 | numpy>=2、scipy、sklearn、matplotlib、torch、pyro-ppl、tensorboard、gpytorch。 | Apache-2.0；GH release与PyPI不同步；只参考不生产引入。 |
| [dirichletcal 0.5.3](https://pypi.org/project/dirichletcal/0.5.3/#files) | >=3.12 | 12,694 bytes（sdist） | 只见sdist；JAX/jaxlib是native传递 | numpy/scipy/sklearn/jax/jaxlib；Python>=3.12；Windows运行UNKNOWN。 | MIT；小型研究包，0.5.3；锁优化器和正则化。 |
| [ScraperFC 4.5.0](https://pypi.org/project/ScraperFC/4.5.0/#files) | >=3.10 | 60,156 bytes（wheel） | pure Python包；浏览器/native栈 | botasaurus/cloudscraper/selenium/marimo/pandas/numpy/lxml等；GPL。 | GPL-3.0；源站脆弱；无Windows CI证据。 |
| [soccer-xg 0.0.1](https://pypi.org/project/soccer-xg/0.0.1/#files) | >=3.6.1,<4.0.0 | 156,287 bytes（wheel） | pure Python wheel不代表依赖能安装 | sklearn<.23、socceraction.2.x、pandas<2、numpy<2、tables/xgboost/python-Levenshtein；Python3.12不具备可接受兼容性。 | Apache-2.0；Dormant；不可作为现代部署依赖。 |
| [statsbombpy 1.22.0](https://pypi.org/project/statsbombpy/1.22.0/#files) | UNKNOWN | 18,130 bytes（wheel） | pure Python wheel；Python requires未声明 | pandas/requests/requests-cache/inflect/joblib；代码license UNKNOWN。 | UNKNOWN code / Custom data；官方API更新但global cache和失败语义需审；暂不准入。 |
| goalmodel / DESCRIPTION0.6.4 | R，不适用Python | UNKNOWN | R/Rcpp；Windows本次未测试 | Rcpp/MASS/示例数据包等；不放主API | GPL-3；Dormant，只做oracle |
| implied / DESCRIPTION0.6.1 | R，不适用Python | UNKNOWN | R运行时；Windows未测试 | R求根/测试生态；最新CRAN版本UNKNOWN | GPL-3；仅oracle |
| footBayes / DESCRIPTION2.1.0 | R，不适用Python | UNKNOWN | CmdStan/C++编译；R多OS CI不代表所有采样路径完成 | cmdstanr/instantiate等，工具链/采样成本高 | GPL-2；研究参考 |
| octosport/octopy / setup1.0.0 | 旧CI3.7–3.9；3.12 UNKNOWN | UNKNOWN | 旧JAX及NumPy兼容性未通过 | **不使用PyPI同名octopy**，其主页为其他仓库 | MIT/Apache冲突；Dormant |

发行元数据逐包可由 [机器账本](open-source-audit-data.json) 中 `pypi.package/version/files/requires` 重查。仅核验wheel标签存在，未声称已经安装/导入成功。示例：socceraction要求numpy<2，SciPy1.18.1要求numpy>=2，已构成明确解析冲突；bpl-next运行Requires-Dist含pip>=26.2.1也须先审。不应把所有reference塞进一个“dev extras”。

API优先公开稳定入口，不依赖private类属性来满足lambda golden；模型保存必须可信本地产出，不能加载网上不明pickle。依赖升级会改变epsilon/分类次序/默认split，必须复核版本化contract。

## Adapter 思想（只设计，不创建抽象层）

概念边界可以叫 `FootballProbabilityModel`，但没有第二个实际模型接入前不创建多余框架、factory、registry service或空目录。所需只是薄适配：

`SEALED dataset / frozen FeatureSnapshot → 时间筛选后的训练数据或纯特征 → library.fit/predict → 本地 Probability/Prediction Contract`

模型不得接收provider client、当前数据库session、网络凭据或目标赛果。采集一律位于Provider/Research acquisition；模型I/O仅本地已批准工件。当前正式Prediction Contract/registry尚未实现，下面是接入第一个拟合模型时的候选字段，不是声称good已有。

| 边界 | 最少约束 |
|---|---|
| 输入身份 | feature_snapshot_id/hash、target match UUID、analysis_cutoff、mode；RESEARCH_REPLAY保留live_visibility_proven=false |
| 训练审计 | dataset_id/version/content_hash、成员集合/训练截止、source资格、模型代码/包版本、hyperparameters/seed/运行环境 |
| 数值输入 | 赔率存Decimal/原始文本；只有数值计算临时转float，明确转换与误差；团队顺序/主客方向固定 |
| 输出 | model_id/version、训练工件hash、outcome顺序HOME/DRAW/AWAY、finite概率、sum容差、市场/line/尾界及诊断 |
| 失败 | UNKNOWN_TEAM / INSUFFICIENT_DATA / NONCONVERGED / INVALID_PROBABILITY / UNSUPPORTED_MARKET等显式状态；不伪造正常结果 |
| 持久化 | 本地不可变Prediction snapshot与原FeatureSnapshot关联；外部Python对象不进入公共API或数据库契约 |
| 业务隔离 | Prediction ≠ Recommendation；概率输出不能自动触发staking/Kelly/Recommendation Gate放行 |

DC模型若能直接输出λ/ρ，应优先通过经版本确认的本地比分数学派生竞彩市场；若只提供比分矩阵/概率，明确其float和截断误差，不能假称来自score-math-v1。任何回落baseline都必须单独标记模型和原因。

## STOP REIMPLEMENTING

| 不要默认从零开发 | 首选复用 | 允许自研的具体例外 |
|---|---|---|
| 完整DC/攻防MLE求解器 | penaltyblog拟合参考与合法公开API；goalmodel独立oracle | 库许可/公开API/收敛/必要约束无法满足且确有模型需求；按数学规格最小实现并独立验证 |
| 重写已完成的Poisson/DC数学 | 保留good score-math-v1；SciPy/PB/goalmodel作对照 | 发现已复现数学错误或新的版本化市场要求 |
| 十种Elo/Pi/Colley评级框架 | elote普通Elo、PB对照 | 现有依赖开销明显不值或目标公式库不支持；只写必要最小更新式 |
| 通用Shin/power求根器合集 | shin；implied oracle | 所需Decimal精度/输入域稳定API无法满足，并有实验证据需要 |
| Platt/isotonic校准优化器 | sklearn | 必要约束无公开API、可证明不同数值契约；不要因为想统一风格重写 |
| LogLoss/Brier/ECE另一套默认定义 | 保留good版本化评估；外部oracle核对 | 新指标明确版本/语义；不是改名后改变分母或log底 |
| 梯度提升树/多个并行boosting接入 | P2选一个LightGBM | 有独立时间评估证明另一个库解决现实短板 |
| 每个事件格式的完整解析器/坐标变换 | P3 kloppy/SPADL | 已授权实际源不受支持且只有少量差异 |
| 自写xT/VAEP整套研究框架 | P3 socceraction参考 | 研究问题确实超出现有方法且数据已具备 |
| 通用bootstrap/数值分布工具 | SciPy | 重采样单位/依赖结构由good自定义；不重复基础数值实现 |

STOP不等于替换已有可靠代码，更不等于本轮开始安装；未具备需求的模块直接不做。

## KEEP IN-HOUSE

- Sporttery官方唯一目标池、赛事/球队/provider ID的验证映射和版本；跨源bookmaker身份。
- Raw-first、append-only odds/observation、源资格、时区/时间语义及来源权限证据。
- analysis_cutoff、analysis_visibility独立提交证明、FeatureSnapshot、标签隔离。
- LIVE_AS_OBSERVED与RESEARCH_REPLAY区分、SEALED状态机、manifest/hash和不可变研究运行。
- Decimal赔率/金额、本地市场/竞彩selection映射、完整TTG/CRS/HHAD语义、规则结算。
- model/prediction版本审计、paired evaluation/coverage、Recommendation Gate和Prediction ≠ Recommendation。

## 工程节省：按模块去重，非20库求和

单位为熟悉Python与现有good架构的一名工程师开发人日。区间包括适配、版本固定、基本回归与文档；不含数据采购/授权等待、绕过访问限制、长时间训练算力、事件P3。不是已测工时，不承诺预测效果。独立模块端点构成两个一致情景，不能随意用最小投入减最大收益。

| 未来P1/P2工程篮子 | 全自建/多头重复基准 | 克制复用后 | 净省 | 依据 |
|---|---:|---:|---:|---|
| 来源适配与schema整理 | 24–32 | 18–24 | 6–8 | soccerdata/sports-betting减少来源结构调研；Raw/权利工作保留 |
| 攻防/DC拟合与诊断 | 20–28 | 12–16 | 8–12 | 成熟求解/参数设计与独立oracle；适配与样本治理保留 |
| 评级基线 | 10–14 | 7–9 | 3–5 | elote known-values/API；三类映射与时态状态自管 |
| 校准与指标验证 | 18–24 | 12–16 | 6–8 | sklearn和外部口径参考，避免重复优化器 |
| 回测统计/置信区间 | 25–32 | 21–26 | 4–6 | 只复用统计基础和切分思想，账本/时态成本不虚减 |
| 一种ML challenger | 23–30 | 20–24 | 3–6 | 一个训练API，避免多个boosting框架接入 |
| **合计** | **120–160** | **90–115** | **30–45** | 120→90省25%；160→115省28.125% |

保守结论：该特定未来工程篮子约省 **25%–28%**。如果数据门槛长期未过，相关工作本就不该开始，实际兑现节省也可能为0。各库逐项人日用于比较替代方案，互相重叠；不能把penaltyblog+goalmodel+bpl+footBayes、sklearn+netcal+Dirichlet、soccerdata+ScraperFC的数字累加。P3的事件复用可能另省较多，但本次近期总数不纳入。

## Phase 4 Roadmap：OLD → NEW（建议，未改现有roadmap）

“OLD”指当前缺口在从零实现路径下的工作内容，不虚构roadmap承诺已排定具体依赖；以代码库存量为起点。

| OLD / 当前状态或潜在实现方式 | NEW / 建议顺序 | 原因 |
|---|---|---|
| P4-4A已实现，可考虑换综合库 | 保留score-math-v1，追加独立oracle计划 | Decimal/tail契约已有价值，PB还存在路径差异 |
| P4-4B1后自行扩展整套拟合器 | 官方Pilot后，先现成拟合reference benchmark，再决策窄adapter | 避免重复优化/识别约束，保持当前baseline |
| P4-4C有评估，继续叠加自研校准 | 数据量足够后复用sklearn；先独立时间calibration | ECE诊断与拟合不同，默认随机CV不适用 |
| P4-4D2B仍在来源资格/证据阶段 | **保持最高优先级**，完成lottery.gov.cn真实SEALED Pilot | 开源库不能替代原始历史证据/权限 |
| 历史规模扩展与模型同时推进 | P1可复现walk-forward → P2三赛季合格后ML/Bayesian | 防止数据泄漏与无效模型工程 |
| 同时规划XGBoost/CatBoost/LightGBM/Ensemble | 先简单baseline+一个LightGBM；互补证据后才ensemble | 用最小模型集验证价值 |
| xG字段后直接开发xT/VAEP | 合法历史xG先试；事件/SPADL/xT/VAEP放P3 | 当前无事件源、权利/坐标/依赖成本高 |
| 赔率gap后扩展投注策略 | 先完整settlement/收益定义与独立授权需求 | gap不是Edge，Prediction不是Recommendation |
| 提前建设大model registry平台 | 第一个拟合模型时最小工件/Prediction契约 | 不建空抽象，不向第三方对象泄露业务契约 |

## 本轮交付与停点

只保存分析和GitHub/官方证据URL，不保存第三方源码、数据集、wheel或vendor目录。本轮未修改apps/api、apps/web、migrations、tests、pyproject.toml，也未修改既有PHASE4_SPEC/BACKLOG/ADR。下一步是人工复核本审计；没有自动集成任务、自动抓取或后台部署。
