# P4-4D2B Historical Source Discovery

> P4-4D2B.1 更新见末尾。本文件前半保留原 D2B 探测事实；当前数字与 Gate 状态以
> `research-probe-manifest.json` 及 `PILOT_DATASET_REPORT.md` 的机器表为准。

核验日期：2026-10-01。实际本机 HTTP 探测窗口：09:46:11～09:56:23 UTC。
本轮候选历史窗口为 2026-09-26～28，未取得官方销售日成员证据。
**ACCEPTED 的真实数据源为 0；Pilot 被官方 Target Pool 证据阻塞。**

所有下面的 HTTP 状态来自本机直接访问提供方。搜索仅用于定位文档，没有将搜索摘要导入 Raw。
`FETCHED` 只表示收到可保留的 HTTP 成功响应，不表示数据正确、具有历史权限或已 VERIFIED。
来源能力分为官方文档/页面脚本声明与实际数据响应，二者不能互换。

## 来源登记

| Source | Purpose | URL/API family | Historical coverage | Timestamp semantics | Stable IDs | Markets | Access status | Verification date | License/ToS note | Limitations | Decision |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 中国体育彩票官方 | 唯一 Target Pool 证明、SP、90 分钟赛果 | sporttery.cn 页面、static.sporttery.cn JS、webapi.sporttery.cn/gateway/uniform/football | 前端提供历史日期查询；服务端历史范围未验证 | 页面 lastUpdateTime、赔率 updateDate/updateTime 的真实语义与时区未核实 | JS 引用 matchId、homeTeamId、awayTeamId、leagueId；尚无真实响应 ID | HAD、HHAD、TTG；历史玩法完整性未知 | HTML/JS 200；历史及当日数据 API 567 | 2026-10-01 | 公开官方信息；未获得批量下载/再分发许可声明；不绕过验证 | 没有取得官方历史比赛、SP 或赛果 | BLOCKED |
| The Odds API（带连字符的官方域名） | 外部历史赔率快照 | api.the-odds-api.com/v4/historical/sports | 文档：featured 自 2020-06-06；具体 sport/bookmaker/market 从加入时起 | 响应 timestamp 是所请求 date 之前或相等的快照；不是今天下载时间 | 标准 odds schema 有 event id、球队名称；未取得可用的稳定 team id | h2h、spreads、totals | 文档 200；本机缺密钥；无凭据请求 401/MISSING_KEY | 2026-10-01 | 条款允许研究及保留，限制作为原始数据产品再分发；本轮无订阅数据 | 付费历史权限及本窗口公司/市场覆盖无法验证 | BLOCKED |
| football-data.org | 候选赛果及球队 ID | api.football-data.org/v4/matches；docs.football-data.org/general/v4/match.html | 文档支持日期过滤；本窗口匿名响应为空 | utcDate 是开球；lastUpdated 是记录更新，不能当 finished_at 或原始发布证据 | 文档有 match/homeTeam/awayTeam id；本次未获得实际 ID | 结果；非赔率源 | 文档 200；请求 200，matches=[]，permission=null | 2026-10-01 | 账号、历史覆盖与使用权限待核验；空匿名响应不能证明授权 | 未取得 REGULATION 结果、真实结束时间或身份映射 | UNVERIFIED |
| Football-Data.co.uk | 候选 CSV 赛果、开盘后/收盘价格 | football-data.co.uk/data.php、notes.txt | 提供方描述多赛季文件；本轮只读取页面与字段说明，未下载赛季 | Date/Time 是比赛时间；收盘 C 列没有逐条快照时间 | 文档是 HomeTeam/AwayTeam 名称，无 canonical team id 证据 | 1X2、AH、总进球按文件覆盖 | canonical 域名页面/notes 200；早期 www 请求 302 未自动跟随 | 2026-10-01 | 页面称免费且限定用途，不等于开放再分发许可；本轮仅本地发现 | 缺赔率时间、稳定球队 ID、finished_at；无法用于本轮严格回放 | PILOT_ONLY（来源研究）；作为 cutoff 赔率源 REJECTED |

没有第三方被赋予体彩开售核验权。没有用供应商公开示例或已有 Mock fixture 填充 Pilot。

## 体彩：实际发现链与接口

1. [官方赛果页](https://www.sporttery.cn/jc/zqsgkj/) 本机 200，页面配置 `webApi=//webapi.sporttery.cn`。
2. 页面引用的 [jc_sgkj_gz.js](https://static.sporttery.cn/res_1_0/jcw/default/jc/sgkj/jc_sgkj_gz.js) 本机 200，实际包含：

```text
GET https://webapi.sporttery.cn/gateway/uniform/football/getUniformMatchResultV1.qry
  matchBeginDate=2026-09-26
  matchEndDate=2026-09-28
  leagueId=
  pageSize=30
  pageNo=1
  isFix=0
  matchPage=1
  pcOrWap=1
```

该请求在 **2026-10-01T09:48:07.936055Z 返回 HTTP 567**，内容为验证拦截 HTML，没有比赛 JSON。
只请求了一页；没有继续翻页、轮换身份、代理、Cookie 或安全验证绕过。
这证明本机此时访问受阻，不证明接口关闭或只允许今日，也不证明所查日期没有比赛。

脚本使用 `errorCode`、`value.matchResult`、`value.total/pages/pageNo/lastUpdateTime`；行字段包括
`matchId/matchNum/matchNumStr/matchDate`、`leagueId/leagueName`、
`homeTeamId/awayTeamId/homeTeam/awayTeam/allHomeTeam/allAwayTeam`、
`sectionsNo1/sectionsNo999/matchResultStatus/goalLine/h/d/a/bettingSingle`。
**这些是当前前端期待的字段，实际 API 返回字段只有拦截 HTML，不能宣称已实测 JSON schema。**
`matchBeginDate/matchEndDate` 不等同已证明的 `businessDate` 销售日；不能从 matchDate 倒推销售日。

其他实际读取的官方脚本：

| 页面脚本 | 发现的接口/参数 | 已验证程度 |
|---|---|---|
| [jc_szsc_gz.js](https://static.sporttery.cn/res_1_0/jcw/default/jc/szsc/jc_szsc_gz.js) | `getMatchListV1.qry?clientCode=3001` | 本机 API 567；businessDate、球队 ID、开售字段仅有脚本证据 |
| [dataTransfer.js](https://static.sporttery.cn/res_1_0/jcw/default/jc/jsq/dataTransfer.js) | `getMatchCalculatorV1.qry?channel=c` | 当前计算器入口得到确认；本轮没有据此声称获得历史 SP |
| 同上 | `getOddsHistoryV1.qry?matchId=<真实ID>&poolCode=<玩法>` | 确认前端存在历史价格入口、引用 updateDate/updateTime；没有真实 ID，未编造 ID 请求 |
| [zqdz.js](https://static.sporttery.cn/res_1_0/jcw/default/jc/zqdz.js) | `getMatchHeadV1.qry?source=web&sportteryMatchId=<ID>`；`getFixedBonusV1.qry?clientCode=3001&matchId=<ID>` | 确认赛事头部和开奖详情入口，脚本引用 matchResultList/oddsHistory；未取得实际数据 |

因此“能否取得历史赔率变化、最早历史日期、SP 时间语义、是否只能最终价格”均仍为 **UNVERIFIED**。
不能将入口名称或 JS 中的 `oddsHistory` 当成服务可用证明。未取得官方 90 分钟结果规则与真实响应的配对证据。

## 海外赔率：文档能力与账户实测分开

[官方历史文档](https://the-odds-api.com/historical-odds-data/)、
[v4 文档](https://the-odds-api.com/liveapi/guides/v4/) 均已直接下载并保存。
历史 odds endpoint 是 `/v4/historical/sports/{sport}/odds`，需要 date 和身份凭据；
可以请求 `markets=h2h,spreads,totals`，按 regions 或 bookmakers 选择公司。
历史调用属于付费功能，本机 `.env` 与进程环境均未提供 `ODDS_PROVIDER_API_KEY`。
无凭据实际请求返回 401、`error_code=MISSING_KEY`，**不是已确认账号未购买套餐**；账号权限无从验证。

文档给出 featured markets 自 2020-06-06、早期 10 分钟间隔、2022-09 起 5 分钟间隔；
EPL 列出的最早快照为 `2020-06-06T10:05:00Z`。实际覆盖只能由成功授权响应验证。
`date` 是查询条件，响应 `timestamp` 才是选中的快照时间；`previous_timestamp/next_timestamp` 是相邻快照。
市场/公司的 `last_update` 应另存为供应商更新语义，不能替代原件快照证据，更不能设成今天的 retrieved_at。

[公司目录](https://the-odds-api.com/sports-odds-data/bookmaker-apis.html) 当前列出 EU Pinnacle、UK/EU William Hill。
Bet365 AU 在目录中限付费且描述为 AFL/NRL；没有证明可提供本 Pilot 足球。
旧 LIVE 配置中的 `pinnacle,bet365,macau,williamhill` 不能视为实际支持承诺。
具体三市场语义参见 [市场目录](https://the-odds-api.com/sports-odds-data/betting-markets.html)；足球让球的符号、线和选项仍须按真实响应核验。
本轮取得的海外历史赔率条目 **0**。

[服务条款](https://the-odds-api.com/terms-and-conditions.html) 的页面更新日期为 2026-08-31；
研究存储与独立原始数据分发的约束不同。Raw 仅留在本机 ignored artifacts，没有发布到 GitHub。

## 候选赛果与身份源

[football-data.org Match 文档](https://docs.football-data.org/general/v4/match.html) 中有
`status=FINISHED`、`score.duration=REGULAR`、`score.fullTime` 与球队 ID 的示例。
实际匿名请求 `/v4/matches?dateFrom=2026-09-26&dateTo=2026-09-28` 返回：

```json
{"filters":{"dateFrom":"2026-09-26","dateTo":"2026-09-28","permission":null},"resultSet":{"count":0},"matches":[]}
```

这不是成功取得赛果或球队 ID。文档的 `lastUpdated` 不证明终场时刻，不能写入 `finished_at`，也不能加固定延迟。
未来需核验结果 scope、真实终场 chronology 和可用性；目前不实现 results adapter。

[Football-Data.co.uk 数据说明](https://football-data.co.uk/data.php) 与 [字段说明](https://football-data.co.uk/notes.txt)
可读，提供 Date/Time、球队名称、FTHG/FTAG/FTR 和赔率列的说明。
开盘后采样/收盘标签没有逐条时刻；CSV 修改时间、比赛时间或页面发布日期都不能证明 odds snapshot。
即使未来取得这些价格，raw market coverage 与 T-30M/T-90M/T-360M coverage 必须分开，缺证据的后者保持 0。
未下载完整赛季文件，未把页面内示例当本 Pilot 数据。

## 时间及身份处理

| 字段 | 本轮处理 | 未来准入条件 |
|---|---|---|
| published_at | 未知即 null | 有对应记录的供应商明确发布证据 |
| effective_at | 未知即 null | 明确生效/更新语义；不能把赛期或文件时间移入 |
| retrieved_at | 实际 HTTP 完成后的 UTC 采集时钟 | 永不倒填历史 |
| replay_available_at | 所有 probe Raw 为 null | 只有成功取得并核验的来源时间证据可用于 frozen v1 |
| availability_basis | null | 与时间严格配对；真正存档快照才可用 VERIFIED_ARCHIVE_TIMESTAMP |

The Odds API 的真实历史响应 timestamp 若经核验可采用 `SOURCE_SNAPSHOT_AT`，并保留原始 envelope；
本轮没有这样的响应，所以没有赋值。JS updateDate/updateTime 的精度、时区和意义都没有得到实际记录验证。

映射工件在本机 `entity-mapping.json`，目前 mappings=[]，状态 BLOCKED_NO_VERIFIED_TARGETS。
没有取得 provider team ID，不做模糊名称确认，也没有构造 canonical ID。
未来显式 manifest 必须包含 provider、external_team_id、canonical_team_id 和核验依据；无法证明保持 UNRESOLVED。
成功导入时 manifest/Raw/provenance 必须进入 D2A dataset hash，修正必须新 dataset version。

## Probe 原件与复现

本机 `artifacts/research-probes/20261001-discovery/` 已被仓库现有 `artifacts/` 规则忽略。
最终汇总为 `pilot-report-v2.json`；先前 `pilot-report.json` 为追加发现前的中间报告，未覆盖。
共 **26 个 source_probe、25 个 HTTP response Raw**，另 1 个缺密钥配置阻塞无 HTTP/hash。
这些是发现用原件，不是 25 场比赛，也不是 Research Dataset Raw。

关键原始响应 SHA-256（脱敏正文另有 D2A canonical payload hash，二者不同）：

| Probe | HTTP | UTC | response_sha256 |
|---|---|---|---|
| 官方历史 2026-09-26～28 | 567 | 09:48:07.936055 | `68b2a9bf3d6783d9f1356fae8f3ca07d438ef499452f72d3c662f340bca21814` |
| 官方当日 schedule | 567 | 09:48:08.401494 | `060baca2c4b908a0d351fa4ad36a9ad8cda9e1d2a4e3d0184847da0661ec6fd6` |
| Odds historical 无凭据 | 401 | 09:50:00.402926 | `2141792e2ef818edfee9c2d33ddc76a7c7cec150d853c5d1942e090acad0aa09` |
| football-data.org 日期请求 | 200/空 | 09:49:58.479052 | `5482a314a6753a0b9e31f4c86258efa17ea45dcc3548b5683a8dc549082caf26` |

`jc.research.providers.probe` 执行 HTTP → D2A ResearchRawArtifactInput → 本地独占创建/fsync → 字段检查 → probe summary。
非 JSON、403/567/429、空数组也保留；网络异常无响应时仅存安全异常类型，不捏造 response hash。
不保存请求头。URL 去掉敏感参数；正文做脱敏并复用 D2A secret guard，不能安全保留时仅留 WITHHELD 和哈希。
官方页面在浏览器工具中也曾报错；这不替代本机上述独立 HTTP 证据。

可复现的**小范围发现命令**（一次官方一页；有密钥时最多再查询一个 EPL 快照，可能消耗账号额度）：

```powershell
$env:RESEARCH_NETWORK_ENABLED = '1'
.venv/Scripts/python.exe -m jc.research.pilot --start-date 2026-09-26 --end-date 2026-09-28
```

缺开关即拒绝网络；仅接受已经结束的 1～3 个日期，每次使用新输出目录，BLOCKED 退出码为 2。
命令不会自动把 200 响应认证为官方历史开售记录，也不会自动导入、运行空 Evaluation 或扩大日期。
首次恢复数据访问后，必须先审核保存的响应再写独立历史 Adapter；随后严格走
`ResearchImport → import_research_dataset → SEALED → verified_sporttery_targets → 三个独立 Research Run`。
本轮没有可验证的成功数据响应，因此按要求未提前实现 sporttery_history/odds_history/results_history 解析器。

## P4-4D2B.1 Source Unblock（2026-10-01）

本次仍查询 2026-09-26～28，一次官方普通 HTTP 请求得到 567，随后停止该接口请求。
用户确认暂无正常浏览器导出的单个 response body。没有自动操纵浏览器，也没有修改请求伪装绕过验证。
进程环境和 `.env` 都没有 Odds credential，本次没有再次发送匿名历史请求。
`BLOCKED_MISSING_CREDENTIAL` 与“账户没有历史套餐”不是同一结论；后者尚未验证。
真实官方 Target、官方赔率历史、外部历史 envelope 均未取得；所有 Gate 与累计 probe 数由机器表报告。

新增候选只调查明确带价格时刻的历史源：

| 候选 | 时间与市场依据 | 研究使用及访问 | 决策 |
|---|---|---|---|
| odds-api.net（与 The Odds API 是不同服务） | [历史文档](https://www.odds-api.net/historical-odds-api) 定义 `tick_ts` 为价格点记录时刻；按 event/selection 和 UTC 窗口查询。[市场说明](https://www.odds-api.net/betting-markets) 列出三项赛果、handicap、total；具体足球场次和三选项完整性还需实测 | [许可](https://www.odds-api.net/terms) 允许内部分析、回测及留存，限制原始数据分发。历史访问要求付费基础计划和 History add-on；本机未提供该源凭据，未取得真实数据 | 数据准入 BLOCKED；仅候选文档发现，不能 ACCEPTED |
| Betfair Historical Data | [官方格式说明](https://historicdata.betfair.com/Betfair-Historical-Data-Feed-Specification.pdf) 定义 `pt` 为 epoch 毫秒发布时间，提供 exchange 历史变化记录。它不是博彩公司三项赔率的直接等价替换；实际足球 MATCH_ODDS、三项价格、时刻及映射仍需真实文件核验 | [研究访问说明](https://support.developer.betfair.com/hc/en-us/articles/30553823020444-Does-Betfair-provide-historical-data-for-academic-research) 要求经官网、已注册且所在地区支持的 Betfair.com 账号；[下载说明](https://support.developer.betfair.com/hc/en-us/articles/12859956891932-How-Can-I-Make-HTTP-Requests-to-the-Historical-Data-API) 要求已购并在 My Data 的数据。未提供账号或已授权文件，未验证本项目许可 | BLOCKED；不绕过账号、地区或授权限制 |

上述四个 HTML 页面（odds-api.net history/markets/terms、Betfair research access）进行了本机单次公开 probe。
HTTP 200 仅证实文档可达。包含前端或凭据示例的正文经 guard 脱敏，retention 如实进入 manifest；没有拿文档里的示例当真实赔率。
Betfair PDF 格式及下载说明仅用官方网页工具核阅，未宣称其属于本机 response Raw。
不下载无逐条 snapshot timestamp 的 closing/opening CSV；这类数据三个 cutoff coverage 一律为 0。

新增工具为 `jc.research.official_evidence` 和 `jc.research.probe_manifest`。
Inspector 的 `EXPECTED_FROM_JS` 与 `OBSERVED_IN_REAL_RESPONSE` 分离；只报告保存后的实际字段及路径，不生成完整历史 Adapter。
未出现的字段保持 missing；观察到 matchDate 不证明销售日；观察到 updateDate/updateTime 也不证明时区或历史可用性。
有真实响应后需逐字段复核，再通过现有 D2A evidence/import/Seal 路径。没有降低 D2A 条件，也没有用文件名或 host 声明直接认证官方身份。

Manifest 从本地 summaries/Raw 机器构建，稳定排序并重算 canonical hash；绝不包括正文、HTTP 请求头或凭据。
早期原件若缺 `text_encoding`，标明 `LEGACY_BYTE_ENCODING_UNVERIFIED`；旧报告中“全部原始字节均可复算”的说法在这些文件上不再成立。
详见 [当前 Pilot 报告](PILOT_DATASET_REPORT.md) 和 [可提交审计清单](research-probe-manifest.json)。

后续用户反馈项目“立即同步”成功：只读核查到 2026-10-01 北京时间 18:51:13/14 的比赛/赔率
同步均为 SUCCESS，但关联 Raw 明确为 `mock=true`、`fixture://sporttery.json`，当前配置为演示模式。
这两次本地 fixture 导入不增加真实数据计数。10:54:01.764998 UTC 按原历史日期参数单次复测官方 API
仍得 HTTP 567；新增 probe 已进入 manifest，未操纵浏览器或修改访问身份。

## 新浪开奖页实测（2026-10-01，用户提供入口）

入口：[新浪竞彩足球开奖页](https://lotto.sina.cn/open/openDetailJc.d.html?lottId=301&gameTypes=rqspf&date=2026-10-01)。
普通 HTTPS 返回 200；页面通过公开脚本 `openDetailJc.js` / `chunk-common.js` 查询历史数据。
未使用账号、Cookie、代理、浏览器自动化或访问控制绕过。

页面脚本明确引用：

```text
GET https://alpha.lottery.sina.com.cn/gateway/index/entry
format=json&__caller__=wap&__version__=1.0.0&__verno__=10000
cat1=jczqMatches&gameTypes=rqspf&date=<date>&isPrized=&isAll=1&dpc=1
```

另一脚本配置域名 mix 未被额外探测。请求的业务参数均来自上述公开页面代码。
脚本字段只作线索；以下是 Raw 保存后实际解析出的响应，非 JS 推断：

| 查询日期 | HTTP | result.status | 实际 data 行数 | matchesPrizedCount |
|---|---|---|---:|---:|
| 2026-09-26 | 200 | code=0 / success | 24 | 24 |
| 2026-10-01 | 200 | code=0 / success | 0 | 0 |
| 2025-09-26 | 200 | code=0 / success | 18 | 18 |

三个响应的 `result.date` 都与查询日期一致。只抽查这三个日期，未批量抓取赛季，未验证连续覆盖或最早日期。
虽然页面 `dates` 列表本次只列 2026-09-21～2026-10-06，直接使用页面的同一 date 参数仍返回了 2025-09-26 的真实记录。
2026-10-01 返回空列表只代表该次来源响应，不断言当日实际没有竞彩比赛。

实际结构为 `result.{_timestamp,data,date,dates,gameTypes,isPrized,matchesCount,matchesPrizedCount,status}`。
行字段观测到：

```text
matchId, tiCaiId, matchNo, matchNoValue, league, leagueOfficial,
team1, team2, matchTime, matchTimeFormat,
score1, score2, halfScore1, halfScore2,
spf, rqspf, bf, jq, bqc,
spfPrize, rqspfPrize, bfPrize, jqPrize, bqcPrize,
spfSellStatus, rqspfSellStatus, bfSellStatus, jqSellStatus, bqcSellStatus,
showSellStatus, showSellStatusCn
```

这证明能取得第三方历史比赛、比分及页面展示的五类竞彩 SP / 开奖奖金。
存在 `tiCaiId` 可作后续官方匹配线索；它仍是新浪声明，不能代替 Sporttery 官方 Raw 认证。
行中没有双方稳定 team ID、真实 finished_at、逐条赔率 snapshot timestamp 或赔率变动序列。
`matchTime` / `matchTimeFormat` 是比赛时间字段，不能用于赔率回放。
2026-09-26 的响应 `_timestamp=1790852576`，换算为 2026-10-01T11:02:56Z，
与实际 retrieved_at=2026-10-01T11:02:56.172933Z 对齐；它不能证明 9 月 26 日赛前赔率可用。
不把开奖奖金自动认定为开盘、收盘或 T-30M 快照，不把请求 date 自动认证成官方销售日。

来源决策：**UNVERIFIED**，可作为候选赛果、竞彩 SP 和官方 ID 线索；
原始数据留存/再分发许可、常规时间结果语义及映射仍待核验。
本段的 `jczqMatches` 开奖接口不是外部博彩公司历史赔率接口，也不能独立通过 Gate A。
后续指数页的独立赔率变动接口见下段。没有生成 ResearchMatch、ResearchResult 或 SEALED Dataset。

本地原件位于 `artifacts/research-probes/20261001-sina-discovery/`。
公共 common JS 含授权模板，首次按既有 guard 标为 WITHHELD；随后单独删除 Bearer 模板文本后重新经过同一 guard，保存为 REDACTED。
该操作只处理公开响应的本地存储，没有更改请求身份；业务 JSON 原件均为 UNCHANGED，UTF-8 无替换字符。
响应 SHA-256、canonical sanitized hash、retention 与路径均由 manifest 自动汇总，原始正文不提交 Git。

## 新浪指数与公司赔率变动实测（2026-10-01）

根据用户截图继续检查[比赛指数页](https://lotto.sina.cn/ai/football/match_indicators.d.html?matchId=3867328)。
`jczqMatches(date=2026-09-30)` 实际返回 2 场，其中 `matchId=3867328`、`tiCaiId=2041789`，
韩国亚 vs 中国亚、比分 2:1、半场 1:1；来源开球时间为 2026-09-30T14:00:00+08:00。
与用户截图对应。这里只做单场有界探测，没有扩大赛季。

已保存的页面引用 `footballIndicators.js`，其公司行点击动作调用公开 common JS 中以下接口。
`EXPECTED_FROM_JS` 仅用于确定请求；下列市场和条数均为 Raw 保存后实际读取的 `OBSERVED_IN_REAL_RESPONSE`。

```text
GET https://alpha.lottery.sina.com.cn/gateway/index/entry
format=json&__caller__=wap&__version__=1.0.0&__verno__=10000&dpc=1
matchId=3867328
cat1=footballMatchOddsEuro / footballMatchOddsAsia / footballMatchOddsTotals

公司变动明细：cat1 末尾增加 Change，companyId=2&offerId=1
```

三个概览均为 HTTP 200 / `result.status.code=0`：胜平负 31 行、让球 14 行、总进球 17 行。
胜平负包含新浪标记的“竞彩官方”和“官方(-1)”行，不能把所有行计为外部公司；这些名称也不能认证体彩官方来源。
概览实际字段含 `companyId,companyName,offerId,o1Ini,o2Ini,o3Ini,oddsTimeIni,o1New,o2New,o3New,oddsTimeNew`。
让球/总进球另有盘口显示值 `o3IniStr/o3NewStr`。

选取三个市场共有的同一来源公司 `companyId=2`、显示名 `36*`、`offerId=1`，取得以下真实变动明细：

| 市场 | 实际记录数 | 早于来源开球时间 | 等于或晚于来源开球时间 | 最早时刻（UTC） | 最晚时刻（UTC） |
|---|---:|---:|---:|---|---|
| 胜平负 | 12 | 11 | 1 | 2026-09-28T06:46:39Z | 2026-09-30T06:00:11Z |
| 让球 | 42 | 41 | 1 | 2026-09-28T06:47:05Z | 2026-09-30T06:00:12Z |
| 总进球 | 49 | 48 | 1 | 2026-09-28T06:47:05Z | 2026-09-30T06:00:12Z |

明细真实字段为 `o1,o2,o3,oddsTime`；让球/总进球另有 `o3Str,o3Cn`。
胜平负的页面列顺序明确是主胜、平局、客胜；让球/总进球的 `o3` 是盘口，不能套用胜平负三选项映射。
公司全名未由响应确认，保留来源 ID 和 `36*` 原名，不自行扩写成其他供应商的公司身份。

例如胜平负原始 `oddsTime=1790577999` 对应 2026-09-28T06:46:39Z（北京时间 14:46:39），
主/平/客为 1.200 / 5.500 / 12.000；最后一条为 1.280 / 4.330 / 13.000，
`oddsTime=1790748011` 对应来源开球后 11 秒。因此本入口已取得真实带时间的历史外部赔率候选，
不能继续笼统称为“完全没有历史赔率”或“只有无时刻 opening/closing”。

时间编码有页面代码与真实记录配对证据：`footballIndicators.js` 将 `oddsTime * 1000` 传给
common JS 的 `new Date()`，显示为“时间”列；这确认页面按 Unix 秒处理，格式化显示使用浏览器本地时区。
保留完整秒值并换算 UTC，不能从 UI 的 `MM-dd hh:mm` 文本猜年份或固定时区。
这证明新浪把该值用作赔率变动记录时间；尚不能证明它是上游公司发布、采集或修订的哪一种时刻，
也没有证明历史记录完整、未追补以及在该时刻已对外可见。`replay_available_at/availability_basis` 仍为 NULL。

进一步质量检查：让球存在 8 个重复时刻、总进球存在 5 个重复时刻；例如让球首个时刻同时出现 -1.25 和 -1.75。
不能只按时间去重并任取一行，需先确认并行盘口和顺序语义。三个明细最新值均跨过来源开球时间。
仅按时间排序时，T-30M/T-90M 最近候选都是北京时间 09:54:31（1.20 / 5.00 / 15.00），
T-360M 最近候选是 06:41:45（1.22 / 5.25 / 12.00）；这些只是候选检索，未证明连续有效性，不计正式 coverage。

来源决策仍为 **UNVERIFIED**：可以继续作外部历史赔率证据复核，正式准入仍需研究使用许可、
历史可用性时间语义、实体映射及体彩官方 Target。公开响应成功不等于批量使用/再分发许可。
Gate A 仍缺官方证据；Gate B 不能仅因拿到新浪时间字段自动 PASS。不改 replay v1，不做三赛季采集。

本轮 9 次响应及其 Raw 位于 `artifacts/research-probes/20261001-sina-indicators/`，均为 UNCHANGED；
明细检查结果另存该目录的 `sina_history_inspection` 本地报告（不另计 probe）。
manifest 对三个变动响应记录 `SINA_ODDS_HISTORY_OBSERVED_REVIEW_REQUIRED`：仅确认非空成功结构及字段存在，
不会认证时间有效性、来源许可、公司身份或 Replay。`sina_odds_history_response_count` 是响应份数，不是快照/公司数。
