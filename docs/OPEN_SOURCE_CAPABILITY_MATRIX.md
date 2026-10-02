# Open Source Capability Matrix

基准：good main `52e9497a1c532270100bc32e5f63ccd8bbd07603`；调研日期2026-10-02。与 [主审计](OPEN_SOURCE_AUDIT.md) 使用同一组 **Exactly 20** 外部仓库、固定SHA和源码证据。列按Reuse Score排序，不能把✅理解为“适合生产”。

## 含义

- ✅ = **YES**：所审源码有对应可调用实现；不保证数据授权、时间正确性或本轮实测通过。
- 🟡 = **PARTIAL**：只有字段/底层能力、部分市场、通用基础函数，或关键口径不完整；详见下面限定。
- ❌ = **NO**：所审模块未核见满足该定义的实现，不等于对仓库每个未读文件作不存在证明。路线图/README计划不计实现。
- 模型λ/expected goals不等于shot-level xG；抓ClubElo不等于训练Elo；ECE诊断不等于校准拟合；保存pickle不等于可审计model registry；closing数据不等于CLV。
- “Odds history”按可定位报价时刻并可回放理解；单份season CSV不足以标✅。“AH settlement”要求投注结果状态及金额，不只盘口概率。“Correct score”包含竞彩官方其他比分聚合，因此只有格子查询时标🟡。
- 通用库只标所审路径的能力，例如SciPy Poisson/bootstrap；不会因为可编程就把它标成所有足球模型。

## 列索引

| 列 | Repository | Reuse Type | Source SHA |
|---|---|---|---|
| good | [cxywk11/good](https://github.com/cxywk11/good) | 自有可信数据与时态核心 | 52e9497a1c532270100bc32e5f63ccd8bbd07603 |
| PB | [martineastwood/penaltyblog](https://github.com/martineastwood/penaltyblog) | REFERENCE_IMPLEMENTATION | [72de6519e0c9](https://github.com/martineastwood/penaltyblog/tree/72de6519e0c9a357b8b1aa2a6441a454b18ff54e) |
| SP | [scipy/scipy](https://github.com/scipy/scipy) | DEPENDENCY_CANDIDATE | [3d18c8f13168](https://github.com/scipy/scipy/tree/3d18c8f1316850a21ee462bdd7268965c2509d90) |
| SK | [scikit-learn/scikit-learn](https://github.com/scikit-learn/scikit-learn) | DEPENDENCY_CANDIDATE | [6ad9bb9ed68b](https://github.com/scikit-learn/scikit-learn/tree/6ad9bb9ed68bb562bc74f3c49231d95c86b1055c) |
| SD | [probberechts/soccerdata](https://github.com/probberechts/soccerdata) | ARCHITECTURE_REFERENCE | [e120471e424a](https://github.com/probberechts/soccerdata/tree/e120471e424a173e83e8aeeaaf4d954ab9d38ee4) |
| EL | [wdm0006/elote](https://github.com/wdm0006/elote) | DEPENDENCY_CANDIDATE | [15741e6fff33](https://github.com/wdm0006/elote/tree/15741e6fff3336656a3743d9410c4538d2958ddc) |
| SH | [mberk/shin](https://github.com/mberk/shin) | DEPENDENCY_CANDIDATE | [ae460853fabe](https://github.com/mberk/shin/tree/ae460853fabeca7d512bbf7de8aaa55dc17f3485) |
| KL | [PySport/kloppy](https://github.com/PySport/kloppy) | DEPENDENCY_CANDIDATE | [0997cc777d03](https://github.com/PySport/kloppy/tree/0997cc777d03ac9472c79615f9225ea4b264cf44) |
| LG | [lightgbm-org/LightGBM](https://github.com/lightgbm-org/LightGBM) | DEPENDENCY_CANDIDATE | [750c4fb49ac6](https://github.com/lightgbm-org/LightGBM/tree/750c4fb49ac60b1b15b9d06439b185655f202c21) |
| SB | [georgedouzas/sports-betting](https://github.com/georgedouzas/sports-betting) | ARCHITECTURE_REFERENCE | [eb4cedf37666](https://github.com/georgedouzas/sports-betting/tree/eb4cedf376663fac68f508e50b83fd832e74dfd4) |
| SA | [ML-KULeuven/socceraction](https://github.com/ML-KULeuven/socceraction) | REFERENCE_IMPLEMENTATION | [93a1242d46c1](https://github.com/ML-KULeuven/socceraction/tree/93a1242d46c104889205753accaabadb00c45c6d) |
| GM | [opisthokonta/goalmodel](https://github.com/opisthokonta/goalmodel) | REFERENCE_IMPLEMENTATION | [84ecd6c2bbad](https://github.com/opisthokonta/goalmodel/tree/84ecd6c2bbad3ccb967abf88ef49e5bcd074e545) |
| IM | [opisthokonta/implied](https://github.com/opisthokonta/implied) | REFERENCE_IMPLEMENTATION | [1d1c5cd548dd](https://github.com/opisthokonta/implied/tree/1d1c5cd548dd71bc1b9addd733db5c2db8566b71) |
| BP | [anguswilliams91/bpl-next](https://github.com/anguswilliams91/bpl-next) | REFERENCE_IMPLEMENTATION | [a79b63f00ca5](https://github.com/anguswilliams91/bpl-next/tree/a79b63f00ca57e07d9730789181892bfab74be52) |
| NC | [EFS-OpenSource/calibration-framework](https://github.com/EFS-OpenSource/calibration-framework) | REFERENCE_IMPLEMENTATION | [34b677f42b83](https://github.com/EFS-OpenSource/calibration-framework/tree/34b677f42b83803aa35503c5b6fefb1387ea9167) |
| FB | [LeoEgidi/footBayes](https://github.com/LeoEgidi/footBayes) | REFERENCE_IMPLEMENTATION | [00540f5ae12b](https://github.com/LeoEgidi/footBayes/tree/00540f5ae12b9dd6a4d97c5be228fb72c4be4b0d) |
| DC | [dirichletcal/dirichlet_python](https://github.com/dirichletcal/dirichlet_python) | REFERENCE_IMPLEMENTATION | [b03f65fc6582](https://github.com/dirichletcal/dirichlet_python/tree/b03f65fc6582cad89497b977b3b33a3c4fe48e39) |
| SF | [oseymour/ScraperFC](https://github.com/oseymour/ScraperFC) | ARCHITECTURE_REFERENCE | [50f5df9fae41](https://github.com/oseymour/ScraperFC/tree/50f5df9fae4141f91174debdb14cf87fb8ed810a) |
| XG | [ML-KULeuven/soccer_xg](https://github.com/ML-KULeuven/soccer_xg) | REFERENCE_IMPLEMENTATION | [b9489d929e0f](https://github.com/ML-KULeuven/soccer_xg/tree/b9489d929e0fa34771267d429256366d0fda27ad) |
| ST | [hudl/statsbombpy](https://github.com/hudl/statsbombpy) | DO_NOT_USE | [a90d179b9e60](https://github.com/hudl/statsbombpy/tree/a90d179b9e60e6e3ac6844da1c1e3d418f77f502) |
| OC | [octosport/octopy](https://github.com/octosport/octopy) | REFERENCE_IMPLEMENTATION | [3f978fdfe92a](https://github.com/octosport/octopy/tree/3f978fdfe92a232e30147122e6180aa2aa44b77a) |

## 完整矩阵（good + 20 repos）

| Capability | good | PB | SP | SK | SD | EL | SH | KL | LG | SB | SA | GM | IM | BP | NC | FB | DC | SF | XG | ST | OC |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Football data ingestion | 🟡 | ✅ | ❌ | ❌ | ✅ | ❌ | ❌ | ✅ | ❌ | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ | 🟡 | ✅ | ❌ |
| Multi-provider | 🟡 | ✅ | ❌ | ❌ | ✅ | ❌ | ❌ | ✅ | ❌ | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ | 🟡 | ❌ | ❌ |
| Entity normalization | 🟡 | 🟡 | ❌ | ❌ | 🟡 | ❌ | ❌ | 🟡 | ❌ | 🟡 | 🟡 | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | 🟡 | 🟡 | 🟡 | ❌ |
| Caching | ✅ | ✅ | ❌ | ❌ | ✅ | ❌ | ❌ | ❌ | ❌ | 🟡 | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | 🟡 | ❌ | ✅ | ❌ |
| Raw-first / append-only provenance | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | 🟡 | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| cutoff + committed visibility | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Odds history | 🟡 | 🟡 | ❌ | ❌ | 🟡 | ❌ | ❌ | ❌ | ❌ | 🟡 | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Odds normalization | ✅ | 🟡 | ❌ | ❌ | 🟡 | ❌ | ❌ | ❌ | ❌ | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| De-vig | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ |
| Asian handicap（概率/盘口） | 🟡 | 🟡 | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| AH settlement / quarter / push / void | ❌ | 🟡 | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Totals / total-goals distribution | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | 🟡 | ❌ | ✅ | ❌ | 🟡 | ❌ | 🟡 | ❌ | ❌ | ❌ | ❌ | 🟡 |
| Correct score（含官方其他映射） | 🟡 | 🟡 | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | 🟡 | ❌ | 🟡 | ❌ | 🟡 | ❌ | ❌ | ❌ | ❌ | 🟡 |
| Poisson | ✅ | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ | ❌ | ✅ | ❌ | ✅ | ❌ | ❌ | ❌ | ❌ | ✅ |
| Dixon-Coles | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ | ❌ | ✅ | ❌ | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Bivariate Poisson | ❌ | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | 🟡 | ❌ | ❌ | ❌ | ❌ | ❌ |
| Attack/defense + home effect fitting | ❌ | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ | ❌ | ✅ | ❌ | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Time decay | ❌ | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ | ❌ | 🟡 | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| DC rho estimation | ❌ | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ | ❌ | ✅ | ❌ | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ |
| League / hierarchical priors | ❌ | 🟡 | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ | ❌ | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Elo | ❌ | ✅ | ❌ | ❌ | ❌ | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ |
| Pi | ❌ | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| xG（射门模型） | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ | ❌ | ❌ |
| xGA / xG字段 | 🟡 | ❌ | ❌ | ❌ | 🟡 | ❌ | ❌ | 🟡 | ❌ | ❌ | 🟡 | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | 🟡 | 🟡 | 🟡 | ❌ |
| xT | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| VAEP | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Bayesian | ❌ | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ | ❌ | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Calibration fitting | ❌ | ❌ | ❌ | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ | ❌ | ✅ | ❌ | ✅ | ❌ | ❌ |
| Platt / sigmoid | ❌ | ❌ | ❌ | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ | ❌ | ❌ | ❌ | ✅ | ❌ | ❌ |
| Isotonic | ❌ | ❌ | ❌ | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ | ❌ | ❌ | ❌ | ✅ | ❌ | ❌ |
| Dirichlet | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ | ❌ | ❌ | ❌ | ❌ |
| LogLoss | ✅ | 🟡 | ❌ | ✅ | ❌ | 🟡 | ❌ | ❌ | ✅ | ❌ | ❌ | ✅ | ❌ | ❌ | 🟡 | 🟡 | 🟡 | ❌ | 🟡 | ❌ | 🟡 |
| Brier | ✅ | ✅ | ❌ | ✅ | ❌ | 🟡 | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ | ❌ | ❌ | ❌ | ✅ | ❌ | ❌ | 🟡 | ❌ | ❌ |
| RPS | ❌ | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ | ❌ | ❌ | ❌ | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Backtest | 🟡 | 🟡 | ❌ | ❌ | ❌ | 🟡 | ❌ | ❌ | ❌ | 🟡 | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Walk-forward | 🟡 | 🟡 | ❌ | 🟡 | ❌ | 🟡 | ❌ | ❌ | ❌ | 🟡 | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| ROI / Yield | ❌ | 🟡 | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | 🟡 | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| CLV | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Max Drawdown | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Bootstrap CI | ❌ | ❌ | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Model registry | ❌ | ❌ | ❌ | ❌ | ❌ | 🟡 | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Prediction snapshot | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |

## 🟡/✅的关键限制与代码定位

| 对象 | 实际含义和比较边界 |
|---|---|
| good | Provider/Raw/UUID/append-only及数学已实现，但真实三赛季/官方Pilot未SEALED；xG/xGA只有字段；temporal_split/Replay不是完整walk-forward；AH只有line规范，CRS其他概率缺失 |
| PB | Poisson/DC/Bivariate/拟合真实存在；公开DC helper交叉项有缺陷，✅不意味着该入口正确。AH quarter是半注概率权重，不是完整settlement；LogLoss使用log2；回测按日/二值结算；没有竞彩OTHER |
| SP | Poisson分布为通用数学，不是球队拟合；bootstrap默认IID，paired不代表时间block；必须由good分组 |
| SK | 校准器和指标成熟；TimeSeriesSplit只按行，默认分类CV是非时序；不会解决available_at与同场快照隔离 |
| SD | 历史CSV、当前来源统计、字段规范与别名；不是严格赔率变动/观察日志；xGA为来源字段，未审出其自行训练shot模型 |
| EL | Elo期望得分不是HOME胜率；binary LogLoss/Brier跳过平局；period walk-forward有顺序但需补可见性；state导出只是registry的材料 |
| SH | 纯Shin去水；不管市场来源、时刻、完整性。收敛状态由caller确认 |
| KL | 多源解析/坐标标准化；provider IDs非体彩UUID；xG为源事件属性，不训练xG |
| LG | 提供多类LogLoss目标和概率输出；softmax输出不等于校准拟合，故Calibration ❌；不含足球数据/结算 |
| SB | RawPayload包含item和bytes，但没有good的提交可见性与append-only状态机；历史API快照与closing近似需qualify；market/line覆盖有限；回测不是完整资金/亚洲盘系统 |
| SA | SPADL、xT、VAEP为真实实现；loader获取的xG属性不是shot模型；VAEP默认事件随机验证必须改用外部时序实验设计 |
| GM | Poisson/DC/拟合/权重与Log/Brier/RPS可用；未裁剪p=0的LogScore为Inf，与good不同；格子概率不含官方OTHER |
| IM | 多去水方法及逆变换；无历史采集，GPL实现仅参考 |
| BP | Bayesian DC、层次prior、攻防/ρ拟合；截断网格/动态权重需要额外验证；所审不是Bivariate共享潜变量实现 |
| NC | 多种校准实现；主要ECE为top-label，不能充当good OVR macro同一指标；LogLoss仅所审实验/优化相关路径 |
| FB | Stan DC与层次prior；模型家族列出Bivariate但本次深读以DC为主，Bivariate保守标🟡。compare_foot实现Brier/RPS；pseudoR2涉及log概率但不是直接LogLoss列 |
| DC | FullDirichletCalibrator真实实现；训练内loss不等于独立泛化指标；示例随机split风险高 |
| SF | 能抓来源统计/shot数据但不自行训练xG/Elo；browser/cache及名称规范不构成时态proof |
| XG | shot-level模型与校准pipeline存在，现代Python依赖不可直接用；指标/示例时序边界需重建，不推荐整个包 |
| ST | 单一StatsBomb供应商客户端（public/API不算不同供应商）；源xG字段、缓存和事件IDs真实，但代码许可UNKNOWN，DO_NOT_USE |
| OC | Poisson/可微Elo/去水代码存在但旧；所谓LogLoss是mean(log p)，符号反向，🟡；不因“expected goals”notebook就标shot模型✅ |

## 使用矩阵的决策

矩阵回答“所审代码有什么”，[Gap分析](OPEN_SOURCE_GAP_ANALYSIS.md)回答“good缺什么且现在是否需要”，[复用计划](OPEN_SOURCE_REUSE_PLAN.md)回答“何时、以什么边界利用”。不要把42行全部勾完作为目标：当前需要先完成官方真实Pilot，而非一次性引入20个库。

具体file/class/function及固定提交链接集中在主审计每库的“Core modules / Code inspected”，机器状态为 [JSON capability字段](open-source-audit-data.json) 的YES/PARTIAL/NO。本轮没有运行外部包证明运行兼容。
