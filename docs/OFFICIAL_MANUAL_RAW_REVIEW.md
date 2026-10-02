# 三份手工官方 Response 离线核验（2026-10-02）

**结论：BLOCKED_IDENTITY_AND_PROVENANCE_CONFLICT。** 三个文件均已实际读取、留存和校验，
但 Fixed Bonus 与 Match Head 正文属于 **2041789／周三001／韩国亚–中国亚／2:1**，
与用户提供的两个 `2041790` URL 及文件名冲突。列表内目标 **2041790／周三002** 则是
**乌兹别亚–日本亚／1:1**。不能把这两份详情正文归入目标 2041790，也不能自行改写来源 URL
或切换到 2041789 导入。

本轮没有联网、访问浏览器、读取第三方数据、扩大日期或运行模型。
没有修改 research-replay-v1、analysis_visibility、D2A contract/importer/repository。
没有创建 SPORTTERY_POOL 核验声明、VERIFIED Target、ResearchResult、ResearchImport 或 Dataset。
已完成的是 Raw 留存、身份/来源冲突检查、原始 HAD 解析、现有时间证据与 contract 复核。

## 1. Raw hash 与 provenance

三个原件位于 ignored `artifacts/manual-official/20261002/`，未修改。
`retrieved_at` 均采用用户明确提供的 **2026-10-02T09:52:21+08:00**，
规范化为 `2026-10-02T01:52:21+00:00`；没有采用文件修改时间或本轮 intake 时钟。
这里的 `+08:00` 只描述采集时间，不能证明业务 kickoff 或奖金发布时间的时区。

复用 `intake_official_evidence`：既有 secret guard → 原文独占落盘/fsync → 字段解析；
`retention=UNCHANGED`、`provenance=USER_EXPORTED_SINGLE_RESPONSE_BODY`。
`artifact_type=OFFICIAL_EVIDENCE_INTAKE`，没有提升为 `SPORTTERY_POOL`。
`source_authenticity=REQUIRES_REVIEW`；三份均含 `success=true`、`errorCode="0"`，
但仅凭 response body 不得补写 HTTP 状态，所以 `http_status=NULL`。

| 原件 | 字节数 | 原始文件 SHA-256 | canonical Raw hash（原文字符串） |
|---|---:|---|---|
| sporttery-match-list.json | 14432 | `af12eb1aa855b0a591b975a7b074f4728d51081a9e96d6e2a9c81400a9644ee6` | `17fa7a52216f267b541b4060993b73ece4fd67a77ad8db6519ff5a5c8f04ea79` |
| sporttery-fixed-bonus-2041790.json | 15127 | `0636b053cb71a1d75b5258c100027f16eb6acd0fb2fa2838ecb17b1268f187bf` | `7a17a6ef858ff1db403085773de971bdb96ee66e45c8c1d0477b0bf08e49dec2` |
| sporttery-match-head-2041790.json | 1371 | `8f5cf0ae532a54b880cf573dc98b7f4dff90392585d55f160de62be31087d6f6` | `8d27d9d5a21bd2d2c8dc87a5b7fd53e3566d25ea7162364dc40b15461e02d81a` |

用户提供的来源 URL 原样保留为 claimed provenance；后两项被正文身份核验判定为不匹配：

1. Match List：`https://webapi.sporttery.cn/gateway/uniform/football/getUniformMatchResultV1.qry?matchBeginDate=2026-09-30&matchEndDate=2026-10-02&leagueId=&pageSize=30&pageNo=1&isFix=0&matchPage=1&pcOrWap=1`
2. Fixed Bonus：`https://webapi.sporttery.cn/gateway/uniform/football/getFixedBonusV1.qry?clientCode=3001&matchId=2041790`
3. Match Head：`https://webapi.sporttery.cn/gateway/uniform/football/getMatchHeadV1.qry?source=web&sportteryMatchId=2041790`

Raw envelope 和 probe summary 保存于 ignored `artifacts/research-probes/20261002-manual-official/`。
[机器 provenance 清单](../artifacts/research-probes/20261002-manual-official/manifest.json)
包含完整 URL、Raw 路径、采集时间和两种 hash；
[本次核验结果](../artifacts/research-probes/20261002-manual-official/review.json)
单独记录身份冲突，不覆盖 intake 时的 UNVERIFIED 记录。

## 2. 三 Raw 交叉一致性

列表实际有 10 条 `value.matchResult`。其中恰好各有一条 2041790 和 2041789。
以下比较的列表行始终是请求目标 2041790：

| 检查项 | 列表目标行 | Fixed Bonus 正文 | Match Head 正文 | 结论 |
|---|---|---|---|---|
| Sporttery match ID | `matchId=2041790` | `oddsHistory.matchId=2041789`；5 条 matchResultList 也全部是 2041789 | `sportteryMatchId=2041789` | FAIL |
| 竞彩编号 | `matchNumStr=周三002`，`matchNum=3002` | 没有编号字段 | `matchNum=周三001` | 不一致 |
| 主队 Sporttery ID | `homeTeamId=2053` | `oddsHistory.homeTeamId=2049` | `sportteryHomeTeamId=2049` | FAIL |
| 客队 Sporttery ID | `awayTeamId=2060` | `oddsHistory.awayTeamId=2069` | `sportteryAwayTeamId=2069` | FAIL |
| 主客队 | 乌兹别亚／日本亚 | 韩国亚／中国亚 | 韩国亚／中国亚 | FAIL |
| 90 分钟比分 | `sectionsNo999=1:1` | `sectionsNo999=2:1` | `fullCourtGoal=2:1` | FAIL |
| kickoff | 仅 `matchDate=2026-09-30`，无开赛时刻 | 无 | `matchDateTime=2026-09-30 14:00`，属于 2041789 | 目标 kickoff 缺失 |

Fixed Bonus/Match Head 的比赛、球队和比分与列表内 **另一条 2041789** 一致。
这是正文指向另一场比赛的证据，不是修正两个 URL 的授权，也不证明这两个正文确实来自所声明的 URL。
列表目标行的 `poolStatus=Payout`、`matchResultStatus=2`、竞彩编号和球队可作为入池候选证据保留，
但不满足本次三 Raw 验证及完整 D2A VERIFIED 条件。

Match Head 的其他 ID namespace 原样分开记录，均属于其正文中的 **2041789**：

| namespace | match | home team | away team | tournament/league |
|---|---:|---:|---:|---:|
| Sporttery | 2041789 | 2049 | 2069 | sportteryTournamentId=83 |
| 无前缀字段 | matchId=2639248 | homeTeamId=17240 | awayTeamId=17232 | tournamentId=76 |
| uniform | uniformMatchId=2510140 | uniformHomeTeamId=55824 | uniformAwayTeamId=55820 | uniformLeagueId=106 |

不能把无前缀或 uniform ID 当成 Sporttery canonical ID。本次真实头部没有先前聊天描述的
`sportteryMatchId=2041790`、`matchId=2639184`、`uniformMatchId=2510139` 那组映射；没有重建或补造。

## 3. HAD 与时间证据

从原件 `value.oddsHistory.hadList` 实际统计 **14 条**，同一行 HOME/DRAW/AWAY 完整的也是 **14 条**。
映射为 `h→HOME`、`d→DRAW`、`a→AWAY`，所有 SP 均以原始字符串保留并用 Decimal 核验，未跨行拼接。
原数组墙钟时间顺序已检查。**这 14 条全部属于 2041789；目标 2041790 的可归属历史未取得，正式导入为 0 条。**

| 记录 | 原始墙钟时间（时区未验证） | HOME | DRAW | AWAY |
|---|---|---:|---:|---:|
| first HAD（2041789） | 2026-09-29 09:55:48 | 1.22 | 4.70 | 10.50 |
| last HAD（2041789） | 2026-09-30 13:53:44 | 1.17 | 5.35 | 11.50 |

再次离线重验此前 **32 份官方来源响应**的 manifest/hash，其中 **21 份 HTTP 200 页面、JS、配置**进行了
时区标记检查（含两份已经脱敏的 commonV1.js）。检查了北京时间、东八区、时区、Asia/Shanghai、
UTC/GMT +8、+08:00、timezone、getTimezoneOffset；保留内容中没有匹配项。
三份新 Raw 同样没有这些时区标记；没有把缺少命中扩大解释为官方从未声明时区。

发布时间的页面语义链可确认：

- 保存的详情 HTML `.../20261002T000547727045Z-df40ee88cc68475194a3d7957ba0240e.json`：
  payload 第 284–303 行为“胜平负固定奖金”表，表头“发布时间”，遍历 `FBonus.oddsHistory.hadList`，
  对应单元格直接显示 `obj.updateDate` 和 `obj.updateTime`；305/311/317 行对应 h/d/a。
  字节 SHA-256 为 `928c56a2154458b7d074d853e05062eadaa06deb7cf61d53dd888e9f780d7fdf`。
- 保存的 `zqdz.js`：`.../20261002T000246849924Z-2c8419c6d18f48beaf7b20583c4d6c43.json`，
  payload 第 177–188 行请求 getFixedBonusV1，并直接赋值
  `this.FBonus.oddsHistory = res.data.value.oddsHistory || []`。
  字节 SHA-256 为 `4bf8a73a1fabff504371e93cf0ae107222d41a404416041ebf51e58065f0905b`。
- 本次 Fixed Bonus Raw 确实存在上述路径和字段，但其正文比赛为 2041789，来源 URL 身份存在冲突。

上述两个保存文件均位于 `artifacts/research-probes/20261002-lottery-qualification/`。
“固定奖金发布时间”的字段映射成立，不等于时区已成立。
kickoff 的页面也只是直接显示 `pageTitle.matchDateTime.substring(0,16)`，没有可认证的时区转换。

因此 `kickoff_timezone=UNVERIFIED`、`publication_timezone=UNVERIFIED`；
`published_at=NULL`、`replay_available_at=NULL`、`availability_basis=NULL`。
**PROVIDER_PUBLISHED_AT 不成立**。没有用 retrieved_at 的 +08:00、列表 lastUpdateTime、
国内站点或机器时区补足业务时间。

T-360、T-90、T-30、T-15、T-5、LAST_PREMATCH 全部 BLOCKED，选中记录均 NULL。
POST_KICKOFF 分类未执行，数量未知，不能报为 0。
所有 HAD 仅保留证据，没有进入任何赛前 Feature。

## 4. D2A 与封存的精确边界

- `ResearchMatch.kickoff_at` 是必填带时区 datetime；`research_replay.py:_utc` 对缺时区报错
  **`Research timestamps require timezone-aware datetime`**。
  本次使用真实 Match Head 自己的身份和原始无时区时间执行内存负向检查，确认被既有 contract 拒绝；
  未把该时间赋给 2041790，没有创建成功的 ResearchMatch。
- `contracts.py:validate_import` 要求 VERIFIED 对应已核验官方来源的 `SPORTTERY_POOL`，
  且 metadata 中 sporttery_match_id、home_team_id、away_team_id、kickoff_at 与 Match 完全一致；
  不满足时报 **`Official raw evidence must identify this match, teams and kickoff`**。
  本次没有制造核验 metadata，也没有构造 ResearchImport 去调用 validate_import 或 importer。
- `ResearchResult.finished_at` 必填带时区；`ResearchDataset.__post_init__` 要求
  **`Result finished_at must be strictly after match kickoff_at`**。
  三份正文没有真实 finished_at；列表 lastUpdateTime、奖金发布时间、采集时间均不作替代。
- `ResearchDataset` 允许 `results=()`；`repository.py:seal_dataset` 重建并校验输入，
  没有要求 result_count > 0。因此只含合法 Match/Target 的数据集可以按现有 contract 封存，
  **缺少 finished_at 仅阻止 Result，不单独阻止这种无 Result 数据集**。

**SEALED blocked by**：本次无法取得目标 2041790 合法的 `ResearchMatch.kickoff_at`，
也无法建立身份与 provenance 一致的 `SPORTTERY_POOL` / VERIFIED 声明。
这是适用 contract 与前置证据缺口；没有声称发生过 importer/seal 的实际失败调用。

## 5. 要求的 30 项结论

| # | 项目 | 结果 |
|---|---|---|
| 1 | 三 Raw hash/provenance | 上述两种 hash 已核验；采集时间均采用用户提供值；后两份 URL/body 身份冲突 |
| 2 | 三 Raw 身份一致 | 否，2041790 对 2041789 |
| 3 | 官方 Sporttery match ID | 目标列表为 2041790；两份详情正文为 2041789，不混用 |
| 4 | 竞彩编号 | 目标周三002（列表 matchNum=3002）；实际头部周三001 |
| 5 | 目标官方主队 ID | 2053；详情实际为 2049 |
| 6 | 目标官方客队 ID | 2060；详情实际为 2069 |
| 7 | 其他 namespace | 见上表；实际头部无前缀 2639248/17240/17232，uniform 2510140/55824/55820 |
| 8 | kickoff raw | 实际头部为 2026-09-30 14:00（2041789）；2041790 原件缺开赛时刻 |
| 9 | kickoff timezone 证据 | 不充分，UNVERIFIED |
| 10 | 90 分钟比分 | 列表目标 1:1；两份详情 2:1，不一致 |
| 11 | HAD 实际条数 | 14，全部属 2041789；目标 2041790 历史未取得 |
| 12 | first HAD | 2041789：2026-09-29 09:55:48，1.22/4.70/10.50 |
| 13 | last HAD | 2041789：2026-09-30 13:53:44，1.17/5.35/11.50 |
| 14 | updateDate/updateTime 语义 | 页面固定奖金“发布时间”的直接映射成立；本次正文身份冲突另行保留 |
| 15 | 发布时间 timezone | UNVERIFIED |
| 16 | PROVIDER_PUBLISHED_AT | 不成立；三个可用性字段均 NULL |
| 17 | T-360 | BLOCKED，NULL |
| 18 | T-90 | BLOCKED，NULL |
| 19 | T-30 | BLOCKED，NULL |
| 20 | T-15 | BLOCKED，NULL |
| 21 | T-5 | BLOCKED，NULL |
| 22 | LAST_PREMATCH | BLOCKED，NULL |
| 23 | VERIFIED Target 建立 | 否，0 |
| 24 | Gate A | BLOCKED：比赛/球队/比分冲突、URL/body 冲突、目标 kickoff 缺失及业务时区未核验 |
| 25 | Gate C | BLOCKED：无 VERIFIED Target、缺目标一致赛果链及真实 finished_at |
| 26 | Gate B | BLOCKED：没有合格外部历史赔率；官方 SPORTTERY_HAD 不是 external consensus |
| 27 | Pilot Dataset 创建 | 否，jc-football-official-pilot 仍仅是目标名称 |
| 28 | SEALED | 否 |
| 29 | dataset version/hash | NULL / NULL |
| 30 | 当前唯一剩余阻塞 | 不能宣称只剩一项。首要是两份详情正文/URL错配；另有 kickoff/发布时区证据、Result finished_at、Gate B 外部证据缺口 |

## 6. 本轮验证与停止点

三个原件与保存 Raw 的字节、SHA-256、canonical hash、URL 和采集时间均完成复验。
复用了既有 manifest 校验器；实际身份冲突和无时区 kickoff 拒绝均有可运行的原件检查，
没有 mock、synthetic 字段或新依赖。业务代码和数据库未修改，未运行无关全量测试。

复验命令（只读原件，首次生成 review.json；再次运行比较既有报告）：

```powershell
$env:RESEARCH_NETWORK_ENABLED='0'
$env:PYTHONIOENCODING='utf-8'
.venv/Scripts/python.exe artifacts/research-probes/20261002-manual-official/check_evidence.py
```

输出 `check=PASS` 表示证据保留、冲突识别和 contract 拒绝检查通过，**不是 Gate A PASS**。
核验在此停止。下一次需要与 2041790 对应的 Fixed Bonus、Match Head 正文，以及各自真实来源 URL、
真实保存时间；请使用新的保存位置保留本次冲突原件。正确正文到达也不会自动解决业务时区或 finished_at。
