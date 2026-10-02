# P4-4D2B.4 Official lottery.gov.cn Evidence Qualification

> Current status: [docs/RESEARCH_CURRENT_STATE.json](RESEARCH_CURRENT_STATE.json).
> HISTORICAL SNAPSHOT: the report and its machine tables below retain their original observations.

核验日期：2026-10-02（Asia/Shanghai）。**Gate A / Gate C / Gate B 均为 BLOCKED。**
官方页面确实能显示目标比赛和历史固定奖金；本机直接请求业务 API 得到 HTTP 567，
目前没有可保存并核验的成功业务 JSON，不能用浏览器 DOM、截图或第三方响应替代。
本轮没有生成 Sporttery VERIFIED、ResearchImport、ResearchResult、正式 HAD snapshot 或 SEALED Dataset。

## 官方来源链与实际 API

入口是 [中国体彩网足球赛果开奖](https://www.lottery.gov.cn/jc/zqsgkj/)。
以下关系全部来自本轮先保存后检查的 HTTP HTML/JS：

1. 入口配置 `webApi=//webapi.sporttery.cn`、`resDomain=//static.sporttery.cn`，
   同时列出 lottery.gov.cn 和 sporttery.cn 的官方页面域。
2. 入口通过 `commonV1Fun.loadHtml` 加载 `/htmlfrag/991.html`；该片段引用
   `/res_1_0/jcw/default/jc/sgkj/jc_sgkj.js`，不是此前研究的 `_gz.js`。
3. `jc_sgkj.js` 以普通 GET 调用历史列表，并用 `matchInfo.matchId` 构造
   `https://www.sporttery.cn/jc/zqdz/index.html?showType=3&mid=<matchId>`。
4. 详情 HTML 引用 `zqdz.js`，后者分别调用头部和固定奖金接口。
   浏览器已观察到这两条实际资源请求，与保存的 JS 一致。
5. `/htmlfrag/769.html` 页脚声明赛程、赛果、奖金由国家体育总局体育彩票管理中心发布。
   详情页另有“部分数据来源于第三方”提示，因此不能把该页面所有技术统计都认证为体彩原始数据。

| 用途 | 实际 HTTPS API | 参数 / 数据路径 | 本机 HTTP |
|---|---|---|---|
| 历史列表 | `https://webapi.sporttery.cn/gateway/uniform/football/getUniformMatchResultV1.qry` | `matchBeginDate, matchEndDate, leagueId, pageSize, pageNo, isFix, matchPage, pcOrWap` | 三个单日均 567 |
| 比赛详情头部 | `https://webapi.sporttery.cn/gateway/uniform/football/getMatchHeadV1.qry` | `source=web&sportteryMatchId=<ID>` | 两场均 567 |
| 五玩法开奖及历史固定奖金 | `https://webapi.sporttery.cn/gateway/uniform/football/getFixedBonusV1.qry` | `clientCode=3001&matchId=<ID>`；JS 读取 `value.matchResultList` 和 `value.oddsHistory` | 两场均 567 |

本轮实际详情的 HAD 历史来自 **getFixedBonusV1** 的 `value.oddsHistory.hadList`。
没有把其他页面中的 `getOddsHistoryV1` 误报为本详情实际请求，也没有猜测额外 API host。
`static.sporttery.cn`、`webapi.sporttery.cn`、`www.sporttery.cn` 经上述官方引用链确认后才访问。
`appgw.sporttery.cn` 虽出现在配置中，本轮没有使用或新增到 allowlist；没有第三方域网络研究。

历史请求均固定 `leagueId=`、`pageSize=30`、`pageNo=1`、`isFix=0`、`matchPage=1`、`pcOrWap=1`。
只请求每个单日第一页，没有连续分页或扩大赛季。

## Raw 与审计

[机器证据清单](lottery-official-probe-manifest.json) 保存完整 URL、实际 UTC、HTTP 状态、响应字节 SHA-256、
canonical Raw hash、保留状态、secret scan 结果及本机相对路径；不包含业务正文。
来源登记为 `source_type=OFFICIAL_SPORTTERY_HISTORY`、`provider_name=sporttery`、`source_name=sporttery`，
`verification_status=UNVERIFIED`。这是来源类别登记，不是身份认证成功。

本机 ignored 原件目录：`artifacts/research-probes/20261002-lottery-qualification/`。
共 18 次直接 HTTP 请求：11 个 HTTP 200 页面/脚本，7 个 HTTP 567 业务接口拦截响应。
17 份 UNCHANGED，`commonV1.js` 的 1 份按既有 guard 脱敏为 REDACTED。
全部原件复用 D2A secret guard 和独占创建/fsync；正文业务解析和字段检查均在 Raw 落盘之后。
既有安全步骤在落盘前扫描/脱敏，然后计算字节 hash 并保存 ResearchRawArtifactInput；
因此没有宣称实现“未经扫描的响应先写磁盘”的字面顺序。
离线审计再次校验 secret、URL、路径边界、summary/Raw 一致性、canonical hash；
UNCHANGED 原件按保存的 encoding 还原字节，重新计算响应 SHA-256。

本轮 API 响应都是拦截页，`official_json_count=0`。HTTP 200 的详情 HTML 仅含 Vue 模板，
两场页面字节 hash 相同，不是两场业务详情的原始 JSON。
浏览器的普通导航能够显示比赛，但工具的 `pageAssets.bundle` 明确不支持导出 XHR JSON；
没有以 DOM 文本重新包装成“HTTP response”。没有提取 Cookie、访问控制绕过、重试轮换或代理。
浏览器日历筛选后的表格未确认刷新，旧的十行不能当作新日期查询返回数量。

## 字段：公开模板证据与业务 Raw 分开

下表都是**已保存 HTML/JS 的字段映射**，不是已经取得成功 API JSON 的声明。

| 语义 | 模板 / JS 字段 | 业务 Raw 结论 |
|---|---|---|
| 官方比赛 ID | 列表 `matchId` → 详情 `mid` → `sportteryMatchId / matchId` 请求参数 | 未取得，稳定性未核验 |
| 赛事日期 | 列表 `matchDate` | 未取得；不能等同销售日 |
| 竞彩编号 | 列表 `matchNumStr`；保留原文，不按日历重算 | 未取得；`matchNum` 是否另有值待业务 Raw |
| 主队 | `homeTeam / allHomeTeam` | 未取得 |
| 客队 | `awayTeam / allAwayTeam` | 未取得 |
| kickoff | 详情 `pageTitle.matchDateTime`，显示 `substring(0,16)` | 未取得；不能用截断显示值补造秒或时区 |
| 半场比分 | `sectionsNo1` | 未取得 |
| 全场 90 分钟比分 | `sectionsNo999`，对应列表“全场比分（90分钟）”列 | 未取得；还需状态/取消和比赛身份核验 |
| HAD HOME / DRAW / AWAY | `value.oddsHistory.hadList[i].h / d / a` | 未取得，不改变原始 SP |
| 发布时间 | 同一 `hadList[i]` 的 `updateDate` + `updateTime` | 模板列名已确认，业务 Raw 尚缺 |
| 五玩法开奖 | `value.matchResultList`，按 `code.toLowerCase()` 分到 `had/hhad/crs/ttg/hafu`；`combinationDesc/odds` | 仅 AVAILABLE_ON_OFFICIAL_DETAIL，不全面解析其他玩法 |
| 球队 ID | 浏览器链接中有 `tid` 候选；API 的 `homeTeamId/awayTeamId` 本轮未见 | 不把链接 ID 自动认证成稳定 canonical team ID |

`/htmlfrag/989.html` 明确解释 90 分钟比分包含伤停补时。
但 D2A `ResearchResult.finished_at` 必须是真实且晚于 kickoff 的带时区时间；
本轮没有这份结束时间证据，不能用 kickoff + 90 分钟、开奖时间或 retrieved_at 替代。

已检查入口、详情、列表和详情业务 JS、相关片段及服务说明，未找到可把 HAD
`updateDate/updateTime` 明确解释为北京时间的证据；没有成功 API 的 UTC/offset 字段可交叉核对。
`timezone=NULL`、`published_at=NULL`、`replay_available_at=NULL`、`availability_basis=NULL`。
目前 **不能设置 PROVIDER_PUBLISHED_AT**：页面列语义和 JS 映射已有，真实业务字段与时区尚缺。
不会因为中国站点、服务器时钟或第三方 +08 对齐关系而补写 Asia/Shanghai。

## 两场浏览器观察（仅发现线索）

| 页面链接 ID | 页面编号 | 主队 / 客队 | 页面 kickoff | 列表 90 分钟比分 | 详情 |
|---|---|---|---|---|---|
| 2041789 | 周三001 | 韩国亚 / 中国亚 | 2026-09-30 14:00 | 2:1（半场 1:1） | 可见五玩法开奖和 HAD 历史 |
| 2041790 | 周三002 | 乌兹别亚 / 日本亚 | 2026-09-30 18:30 | 1:1（半场 1:0） | 可见五玩法开奖和 HAD 历史 |

第一场对应用户韩国 U23 / 中国 U23 线索，但页面实际编号为**周三001**。
不沿用截图文字中的“周二001”，也不把举例的 `4.45 / 3.35 / 1.65` 当作这场 HAD。
第一场浏览器表格可见 14 行 HAD，首行显示 `2026-09-29 09:55:48`，
末行显示 `2026-09-30 13:53:44`。这些仍是 UI 观察，**Raw 可用历史行数为 0**；
不能把末行直接认证为 LAST_PREMATCH。

## 极小历史范围测试

| tested_dates | matches_returned（业务 Raw） | status | 说明 |
|---|---|---|---|
| 2026-09-30 | NULL | BLOCKED | HTTP 567；不是“0 场” |
| 2026-09-29 | NULL | BLOCKED | HTTP 567；不是“0 场” |
| 2025-09-30 | NULL | BLOCKED | HTTP 567；不能证明或否定跨年覆盖 |

`oldest_tested_date=2025-09-30`；`oldest_successful_raw_date=NULL`。
浏览器初次默认范围为 2026-09-30～2026-10-02，显示十场；这不是上述三个单日 API 的成功 Raw。
没有证明跨年 match ID 稳定，也没有取得 2025 年比赛 ID 去请求详情。

## 与既有 Sina / VIPC 原件交叉检查

仅离线读取、重验此前保存的 Raw，没有新增 Sina/VIPC 网络请求。

| 来源 | ID / 编号候选 | 主客队 | kickoff 字段 | score |
|---|---|---|---|---|
| 官方浏览器线索 | 链接 ID 2041789，周三001 | 韩国亚 / 中国亚 | 显示 2026-09-30 14:00 | 2:1 |
| 已保存 Sina Raw | `matchId=3867328`，`tiCaiId=2041789`，`matchNo=周三001` | `team1=韩国亚`，`team2=中国亚` | `matchTime=1790748000`，`matchTimeFormat=2026-09-30 14:00:00` | `score1=2`，`score2=1` |
| 已保存 VIPC Raw | `matchId=498257749`，`issue=202609303001`；`matchNo` 未见 | `home=韩国U23`，`guest=中国U23` | `matchTime=2026-09-30 14:00:00` | `homeScore=2`，`guestScore=1` |

可见字段与同场候选相符；由于官方业务 Raw 缺失，三方正式身份交叉核验仍未完成。
Sina `tiCaiId`、VIPC `issue` 仅为 mapping candidate，不反向认证官方比赛。
名称别名不能自动确认跨源 Team Entity Mapping。
VIPC 冻结状态保持 `UNVERIFIED / RESTRICTED / Gate A BLOCKED / Gate B BLOCKED`。

## Gate、cutoff 与 Dataset

| 检查项 | 本轮结论 |
|---|---|
| 官方 VERIFIED Target | 0；无满足 D2A 条件的 SPORTTERY_POOL Raw |
| Gate A | BLOCKED；未建立 SportteryVerificationInput(status=VERIFIED)，没有绕过 validate_import |
| Gate C | BLOCKED；没有 VERIFIED Target + 官方 REGULATION Raw + 合法结束时间/provenance |
| Gate B | BLOCKED；官方 SPORTTERY_HAD 不属于 external_consensus；外部源冻结状态未改变 |
| 正式 HAD 历史行数 | 0；提供方实际总数未知，UI 可见数不代替 Raw 数 |
| 最早发布时间（已核验） | NULL |
| T-360M / T-90M / T-30M / T-15M / T-5M | 全部 BLOCKED，未计算正式候选 |
| LAST_PREMATCH | BLOCKED |
| 真实 SEALED Pilot | 未创建 |
| Dataset key | `jc-football-official-pilot` 仅为预定名称，没有数据库记录 |
| Dataset version / content hash | NULL / NULL |
| Goals Baseline | 未运行，没有补历史、默认 lambda 或降低 MIN_MATCHES_PER_TEAM |
| 扩大数据规模 | 不适合，停止于本次小范围资格核验 |

获得真实 Raw 后仍必须遵守：每条官方发布记录同一时间具备完整 HOME/DRAW/AWAY，
缺项为 `complete=false`，不跨时间拼接；以原始 SP 建立 `SPORTTERY_HAD`。
有时间证据后，`published_at >= kickoff` 统一 POST_KICKOFF，只留证，
不进入任何赛前 Feature、T-cutoff、LAST_PREMATCH 或 Market Snapshot。
cutoff 取 `published_at <= cutoff` 且严格早于 kickoff 的最近完整三项；本轮没有放宽规则。

## 实现、测试与未完成项

代码只补充 lottery.gov.cn / www.lottery.gov.cn 精确域 allowlist，以及失败关闭测试。
复用现有 Raw、secret guard、hash/provenance 和 manifest 工具；没有新增依赖或假设业务 schema 的 adapter。
新增测试覆盖官方域准入不等于 VERIFIED、仿冒/未核验子域拒绝、HTTP 页面与预期 JSON 字段
不能认证 Target/发布时间、Raw hash 保留、source_type/provider_name 登记。
既有测试继续覆盖 Raw-first、存盘失败不解析、原件篡改拒绝、显式网络 opt-in、D2A 官方证据约束。

用户要求的成功业务解析、时区/PROVIDER_PUBLISHED_AT、完整 HAD 快照、POST_KICKOFF、
各 cutoff、真实 Target/Result 导入成功路径测试，本轮**没有实现或冒称通过**：
它们依赖尚未取得的业务 Raw 和语义证据。测试里的 synthetic 只检查边界，不是官方成功响应 fixture。
当前阻塞条件下没有伪造这三类“正常 Raw”来完成测试清单。

| 验证 | 结果 |
|---|---|
| SQLite 全量 | **874 passed、1 skipped**，138.68 秒 |
| PostgreSQL 全量 | **874 passed、1 skipped**，131.68 秒；PostgreSQL 17.11，127.0.0.1:55433，新建空库 `jc_lottery_qualification_test` |
| 收尾补充测试 | 最终 `test_official_evidence.py` **64 passed**；包括全量结束后新增的机器清单来源登记检查 |
| Ruff | `ruff check apps/api/src tests` 通过 |
| mypy | `mypy apps/api/src` 通过，50 个源文件 |
| 冻结模块 | research-replay-v1、analysis_visibility、D2A contracts/importer/repository、LIVE providers、VIPC 模块均未修改 |

两套全量均设置 `RESEARCH_NETWORK_ENABLED=0`，唯一跳过项是显式 opt-in 的真实网络测试。
各有一条既有 Starlette/httpx 弃用警告。日志在 ignored
`artifacts/lottery-qualification-sqlite-tests.txt` 与 `artifacts/lottery-qualification-postgres-tests.txt`。
PostgreSQL 测试后仅剩空的 `alembic_version`，没有导入研究数据；`git diff --check` 通过。

离线重验原件（无网络）：

```powershell
$env:RESEARCH_NETWORK_ENABLED='0'
.venv/Scripts/python.exe -m jc.research.probe_manifest --input artifacts/research-probes/20261002-lottery-qualification --output artifacts/lottery-official-manifest-recheck.json
```

解阻只需要正常浏览器已经合法取得的**单个 HTTP response body**及其 URL/采集时间，
或直接接口恢复普通访问；不需要截图、Cookie、请求头或完整 HAR。
本轮已请求该缺失输入；在它到达前不认证、导入或扩大采集。
