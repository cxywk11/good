# OddsPapi · Sporttery 2041790 · Gate B

2026-10-02：**Gate A PASS / Gate B PASS（2/5 cutoff）/ Gate C BLOCKED**。
机器结果在 [RESEARCH_CURRENT_STATE.json](RESEARCH_CURRENT_STATE.json) 的 `oddspapi_qualification`。
新浪核验对象、旧 Dataset、research-replay-v1、D2A contract、analysis_visibility 未修改。

## 实际请求与映射

本机 `ODDSPAPI_API_KEY` 为 AVAILABLE，未输出或保存 key 内容。
The Odds API 的 `ODDS_PROVIDER_API_KEY` 仍为 NOT_AVAILABLE；该源未调用历史接口，本轮使用 OddsPapi。
用 Soccer 和 `2026-09-30T10:29:00Z` 至 `10:31:00Z` 的窄窗口查询 `/v4/fixtures`，真实响应恰好一场。
没有其他比赛的历史赔率采集，没有扩大赛季。

| 身份维度 | Sporttery 已核验目标 | OddsPapi 真实响应 |
|---|---|---|
| Match / fixture | `2041790` | `id1000186275066460` |
| 主队 | 乌兹别亚；canonical `2053` | Uzbekistan；participant1Id `49109` |
| 客队 | 日本亚；canonical `2060` | Japan；participant2Id `49055` |
| 计划开球 UTC | `2026-09-30T10:30:00Z` | `2026-09-30T10:30:00.000Z` |
| 赛事 / sport | 亚运会男足；Sporttery competition `83` | Asian Games `1862` / International Youth / Soccer `10` |

映射是对原官方目标的显式复核，不赋予外部源体彩开售核验权。
核对依据是官方已封存 getMatchHeadV1 的球队、赛事、主客顺序和时间，以及上表真实供应商字段，未采用模糊名称自动匹配。
fixture 的 `hasOdds=false` 不作无历史覆盖证明：随后确实取得历史记录。
响应中的 trueStartTime / trueEndTime 留在 Raw，不修改官方 kickoff，也不创建 Result 或开放 Gate C。

公司目录实际返回 `pinnacle`、`bet365`、`betfair-ex`，均非 clone。
市场目录实际返回 `101 = Full Time Result`、Soccer、fulltime、1x2、三项、非 player prop，
outcome `101/102/103 = 1/X/2 = HOME/DRAW/AWAY`。
对应 [官方市场文档](https://oddspapi.io/en/docs/get-markets)及 [官方示例中的 home/draw/away 映射](https://oddspapi.io/en/docs)。

首次合并三家公司请求 historical-odds 返回 HTTP 400，响应明确要求 Betfair 独立、单 outcome 查询。
按该真实错误说明调整后：Pinnacle+Bet365 三次，Betfair 三次，共 **6 个 HTTP 200 原始历史响应**。
每次只请求本场一个 1X2 outcome，不过滤 active，保留暂停记录；请求遵守历史端点冷却时间。
失败 Raw 也保留，但不参与 Dataset。

## 独立准入检查

| 检查 | 结论与范围 |
|---|---|
| Transport | VERIFIED：真实 authenticated HTTP 200；一次参数错误独立保留 |
| Schema | VERIFIED：fixtureId → bookmakers → markets → outcomes → players[0] → history[] |
| Match identity | VERIFIED：上述唯一 fixture、球队顺序、精确 kickoff、sport/competition、稳定 ID |
| Bookmaker identity | VERIFIED：实际目录 slug；规范身份为 `oddspapi:<slug>`，不计 clone |
| 1X2 mapping | VERIFIED：实际市场目录及官方映射；只归一化完整有效的三项 |
| Historical timestamp | VERIFIED：实际 ISO UTC `createdAt` 与官方“采录快照时间”说明一致 |
| Availability semantics | VERIFIED：合格记录使用 `SOURCE_SNAPSHOT_AT`，时间取原始 createdAt |
| License/use | VERIFIED：限定本场私有本地研究；官方导出研究教程与使用条款，禁止原始数据独立再分发 |
| Replay | PASS，范围仅 T-360、T-30；其余三个 cutoff 的完整性准入仍 BLOCKED |

[官方时间说明](https://oddspapi.io/blog/dynamic-odds-price-movement-python/)明确区分历史 `createdAt`（采录时刻）与 live `changedAt`。
OddsPapi 返回逐 outcome 的历史快照列表，**没有 The Odds API 的顶层 timestamp / previous_timestamp / next_timestamp envelope**。
本轮没有虚构这些字段，也没有使用今天的 retrieved_at 反填历史。
`createdAt` 的采用依据是 OddsPapi 自己的官方定义和真实响应，不从新浪 oddsTime 或字段名类推。

[官方 CSV/Excel 研究教程](https://oddspapi.io/blog/historical-odds-csv-excel-backtesting/)明确介绍将历史数据下载到本地 notebook / spreadsheet 研究；
[使用条款](https://oddspapi.io/en/legal/terms)禁止将数据作为独立产品再分发。
本次声明仅覆盖本场本地研究和私有保存，不主张开放数据、无限期保留或公开 Raw 再分发许可。
source verification 有明确时间、review note、文档 URL 和响应 hash，保存在新 Dataset 的 source metadata。

## 快照选择结果

身份键为 `(fixture, bookmaker, market, 精确 createdAt)`；相同瞬间的三条记录必须全部存在、active=true、Decimal price>1。
outcome-filtered HTTP 响应是获取切片，不是三个不同的历史快照：只有原始 createdAt 完全相同才合并。
不舍弃毫秒、不取最大时间统一补戳、不前向填充、不选择 closest-after。
先取每家公司 cutoff 之前最近的记录组，再检查完整性；最新组缺项则该公司在该 cutoff 阻塞，不回退到更旧的完整组。

| 公司 | 历史 outcome 条数 | 赛前 outcome 条数 | 完整有效赛前同时间组 | 本轮最终准入组 |
|---|---:|---:|---:|---:|
| Pinnacle | 1643 | 661 | 190 | 2 |
| Bet365 | 402 | 61 | 13 | 0 |
| Betfair Exchange | 10737 | 4278 | 79 | 0 |

上述 282 个完整赛前组不是本轮可用 cutoff 数量；正式导入仅选中的 2 组 / 6 quotes。
Betfair 未参与 consensus，无需假设历史 price 的手续费或成交语义。

| Cutoff | UTC 上限 | Pinnacle 最近记录 UTC | Pinnacle 完整性 | source_count | Gate B at cutoff |
|---|---|---|---|---:|---|
| T-360 | 04:30:00 | 04:26:24.271 | HOME/DRAW/AWAY | 1 | PASS |
| T-90 | 09:00:00 | 08:56:29.858 | 缺 HOME | 0 | BLOCKED |
| T-30 | 10:00:00 | 09:59:51.878 | HOME/DRAW/AWAY | 1 | PASS |
| T-15 | 10:15:00 | 10:12:18.411 | 缺 AWAY | 0 | BLOCKED |
| T-5 | 10:25:00 | 10:24:40.950 | 缺 DRAW | 0 | BLOCKED |

时间均为 2026-09-30。Bet365 和 Betfair 在五个 cutoff 的最近记录都不完整，source_count 均不包含它们。
被阻塞 cutoff 的 blocker class 为 `NO_DATA`，细分原因 `INCOMPLETE_SNAPSHOT`，不是没有历史数据或没有目标覆盖。

## 首次真实市场差异

数值顺序均为 HOME / DRAW / AWAY；展示四舍五入，机器结果保留原 Decimal 字符串。

| Cutoff | 外部 consensus 概率 | 官方 HAD no-vig 概率 | external − sporttery（百分点） |
|---|---|---|---|
| T-360 | 17.3934% / 24.0797% / 58.5270% | 15.6665% / 24.1187% / 60.2148% | +1.7269 / −0.0391 / −1.6878 |
| T-30 | 15.0519% / 24.8578% / 60.0904% | 14.0611% / 25.6769% / 60.2620% | +0.9907 / −0.8191 / −0.1716 |

其余三个 cutoff 的 p_market 和 gap 为 NULL。这只是 **market disagreement**；未计算 Edge、EV、Recommendation 或 staking。
只有一家有效 bookmaker，不将三项 outcome 计为三个 source。

## Dataset 与可复核路径

实际 Gate B 通过后，复用原 D2A importer 创建并 SEALED：

- key：`jc-football-official-pilot`
- version：`2041790-external-1x2-v1`
- hash：`4ddd648d9c90a1811c4235085cd38317c1932735104e23400b9da0106c944cce`
- 1 VERIFIED target；54 原官方 HAD quotes；6 合格 OddsPapi quotes；0 Result；16 Raw artifacts。
- 从 PostgreSQL 重新 load、核对 content hash、重新审查 Raw 并 replay，结果与封存前一致；重复导入幂等。

本轮入口是 `jc.research.oddspapi.assess_oddspapi_intake`：每次从保存的历史 Raw 重新选择最近记录组并验证完整性，
核对 normalized quotes 和 provenance，然后按 cutoff 交给已有 `assess_intake_gates` → `build_research_feature` → `build_market_data`。
必须使用该准入入口；单独对整个 Dataset 调用裸 replay-v1 会按各 series 选择较旧报价，不能证明本轮完整快照规则。
本轮没有修改冻结 replay-v1；adapter 的范围是指定目标、指定五个 cutoff 的 source admission。

新真实 Raw、历史列表、source declaration、封存记录和完整测试日志均在
`artifacts/research-probes/20261002-oddspapi-2041790/`（Git ignored）。
Git 仅增加适配器、synthetic tests、资格 metadata 和当前状态；没有新增真实 Raw fixture。
旧官方两个版本逐成员 hash 复核不变；新浪对象 hash 仍为
`4a2878d1175ff48af2c63d1c7dcba993fcd162533a9167dc8ac177ee5e774ecd`。

Gate C 保持 BLOCKED：本轮不进行 REGULATION Result 与 finished_at 准入。
余下 cutoff 的最短解阻路径是取得该供应商明确、完整的 as-of 三项快照；不能在当前规则下以异步价格前向填充替代。

## 最终验证

- SQLite `pytest -q`：1074 passed、1 skipped、1 warning，256.92 秒。
- 独立 PostgreSQL 17.11 全量 `pytest -q`：1074 passed、1 skipped、1 warning，213.21 秒；测试数据库清理完成。
- `ruff check apps/api/src tests`：PASS；`mypy apps/api/src`：PASS，55 个源文件。
- 跳过项为显式 opt-in 网络测试；warning 为既有 Starlette/httpx 弃用提示。
- 新增 21 项 synthetic provider 检查和 1 项当前状态检查；旧报告测试保留其历史结论，单独核验当前 Gate B。
- 首轮全量测试发现一处旧测试把当前状态绑定到历史 Gate B BLOCKED；修正后重新运行两套完整测试并全部通过。
- 两个旧 SEALED Dataset 的 header、source、Raw、match、quote、result 逐成员 hash 未变；冻结代码与历史报告文件 hash 未变。
- 所有新真实 Raw 均保存在 Git ignored artifacts；待提交文件的密钥检查通过。
