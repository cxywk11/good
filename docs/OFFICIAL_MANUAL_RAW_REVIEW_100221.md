# 三份官方 Raw 更新核验（2026-10-02 10:02:21 +08:00）

> Current status: [docs/RESEARCH_CURRENT_STATE.json](RESEARCH_CURRENT_STATE.json).
> HISTORICAL SNAPSHOT: the report and its machine tables below retain their original observations.

> 后续已补足限定于 kickoff 的官方时区证据并完成 Gate A；见 [当前报告](SPORTTERY_GATE_A_REPORT.md)。
> 本文保留当时的核验结果，原 Raw、manifest 和 review.json 不改写。

**三 Raw 身份、球队、比分一致性 PASS；Gate A/C/B 仍 BLOCKED；没有创建或封存 Dataset。**
本批已经解除此前的 2041789/2041790 错配。当前目标是 **2041790／周三002／乌兹别亚–日本亚／1:1**。
HAD 实际 **18 条**，全部属于 2041790。kickoff 与发布时间仍缺充分的官方时区证据，真实 finished_at 也缺失。
本轮没有联网、访问第三方、扩大日期或修改 D2A/research-replay-v1/analysis_visibility。

本报告替代[上一批报告](OFFICIAL_MANUAL_RAW_REVIEW.md)作为当前状态；上一批 Raw envelope、hash、
provenance 和核验结果保留在 `artifacts/research-probes/20261002-manual-official/`，没有改写。
用户更新了输入目录中的文件，本轮将新批次独立保存在 `artifacts/research-probes/20261002-manual-official-100221/`。

## Raw 与 provenance

三个输入均来自 `artifacts/manual-official/20261002/`。采集时间全部采用用户提供的
**2026-10-02T10:02:21+08:00**，UTC 为 **2026-10-02T02:02:21+00:00**；不使用文件 mtime 或 intake 时钟替代。
列表字节与上一批完全相同，后两份正文已改变；相同列表正文仍单独保留本次采集声明，没有覆盖旧 metadata。

| 文件 | 字节数 | 原始字节 SHA-256 | canonical Raw hash（原文字符串） |
|---|---:|---|---|
| sporttery-match-list.json | 14432 | `af12eb1aa855b0a591b975a7b074f4728d51081a9e96d6e2a9c81400a9644ee6` | `17fa7a52216f267b541b4060993b73ece4fd67a77ad8db6519ff5a5c8f04ea79` |
| sporttery-fixed-bonus-2041790.json | 20861 | `5a2219730b1de410551ff84218ccee306ad3350fcc2d4fbbae069771899fc4ba` | `ccd34ebdc92a32fe9fb7e589355e8d2252ebd14c844855ed00a889e76a1cd498` |
| sporttery-match-head-2041790.json | 1374 | `1c37916dc5de6f7f78248577e75073c8d99ed72e7a026cda0871035916019916` | `f0e91dcb65434a1fe328cd59705448df0d4518937ee748f3813b5f370301d87a` |

来源 URL 延续用户明确提供的值，本批两个详情正文已与 URL 中的 2041790 一致：

1. `https://webapi.sporttery.cn/gateway/uniform/football/getUniformMatchResultV1.qry?matchBeginDate=2026-09-30&matchEndDate=2026-10-02&leagueId=&pageSize=30&pageNo=1&isFix=0&matchPage=1&pcOrWap=1`
2. `https://webapi.sporttery.cn/gateway/uniform/football/getFixedBonusV1.qry?clientCode=3001&matchId=2041790`
3. `https://webapi.sporttery.cn/gateway/uniform/football/getMatchHeadV1.qry?source=web&sportteryMatchId=2041790`

复用 `intake_official_evidence` 的 secret guard、独占写入/fsync 和 Raw-first 流程，均为
`retention=UNCHANGED`、`provenance=USER_EXPORTED_SINGLE_RESPONSE_BODY`、
`artifact_type=OFFICIAL_EVIDENCE_INTAKE`。没有凭不完整证据生成 SPORTTERY_POOL 核验声明。
三份业务标记均为 `success=true`、`errorCode="0"`；未提供 HTTP headers，故 `http_status=NULL`。
URL 及采集来源是用户提供的 provenance，不冒称本轮联网独立认证。

[机器 provenance/hash 清单](../artifacts/research-probes/20261002-manual-official-100221/manifest.json) ·
[完整核验与 18 条 HAD 证据](../artifacts/research-probes/20261002-manual-official-100221/review.json) ·
[保存页面/JS 的时区复查清单](../artifacts/research-probes/20261002-manual-official-100221/timezone-review.json)

## 身份与 namespace

列表 `value.matchResult` 实际 10 条，其中目标 2041790 恰好一条。

| 项目 | 列表目标 | Fixed Bonus | Match Head |
|---|---|---|---|
| Sporttery 比赛 ID | matchId=2041790 | oddsHistory.matchId=2041790；5 条 matchResultList 也全为 2041790 | sportteryMatchId=2041790 |
| 主队 Sporttery ID | homeTeamId=2053 | oddsHistory.homeTeamId=2053 | sportteryHomeTeamId=2053 |
| 客队 Sporttery ID | awayTeamId=2060 | oddsHistory.awayTeamId=2060 | sportteryAwayTeamId=2060 |
| 90 分钟比分 | sectionsNo999=1:1 | sectionsNo999=1:1 | fullCourtGoal=1:1 |
| 竞彩编号 | matchNumStr=周三002；matchNum=3002 | 无此字段 | matchNum=周三002 |

三份主客队名称也一致，联赛 Sporttery ID 均为 83；列表 `poolStatus=Payout`、`matchResultStatus=2`，
Fixed Bonus `isCancel=0`，HAD 开奖 `combination=D` 与 1:1 相符。
这是官方比赛池身份的原始证据；D2A VERIFIED 仍需完整带时区 kickoff 声明。

| namespace | match ID | home team ID | away team ID | tournament/league ID |
|---|---:|---:|---:|---:|
| Sporttery（canonical 候选） | 2041790 | 2053 | 2060 | 83 |
| Match Head 无前缀 | 2639184 | 17249 | 17231 | 76 |
| uniform | 2510139 | 55828 | 55821 | 106 |

只用 Sporttery 字段交叉验证；未把其余 namespace 当作体彩 canonical ID。

## HAD、字段语义与时区

实际解析 `value.oddsHistory.hadList`：**18 条、18 条完整**，按 h/d/a 映射 HOME/DRAW/AWAY；
所有原始 SP 用字符串保留、Decimal 校验，不跨发布时间拼接。原数组墙钟时间顺序已核验。
机器报告保留全部 18 条的 JSON path、墙钟时间、三项奖金及 `complete=true`，均为 evidence-only，正式导入 0 条。

| HAD | 原始墙钟时间（时区 UNVERIFIED） | HOME | DRAW | AWAY |
|---|---|---:|---:|---:|
| first | 2026-09-29 09:55:48 | 4.45 | 3.35 | 1.65 |
| last | 2026-09-30 17:50:30 | 6.30 | 3.45 | 1.47 |

kickoff 原文为 **2026-09-30 18:30**。未补写 `+08:00`；规范化 `kickoff_at=NULL`。

发布时间的证据链重新核对成立：

- 已保存 `zqdz.js` payload 第 177–188 行：以 `matchId=this.mid` 请求 getFixedBonusV1，
  直接赋值 `this.FBonus.oddsHistory = res.data.value.oddsHistory || []`。
  字节 SHA-256：`4bf8a73a1fabff504371e93cf0ae107222d41a404416041ebf51e58065f0905b`。
- 已保存详情 HTML payload 第 284–303 行：胜平负固定奖金表，表头“发布时间”，
  遍历 `FBonus.oddsHistory.hadList`，对应单元格显示 `obj.updateDate` 与 `obj.updateTime`；
  第 305/311/317 行分别显示 h/d/a。
  字节 SHA-256：`928c56a2154458b7d074d853e05062eadaa06deb7cf61d53dd888e9f780d7fdf`。
- 新 Fixed Bonus Raw 的上述字段和比赛身份均匹配。故“固定奖金发布时间”的字段语义可证明。

另行重验已保存的 32 份官方来源响应，对其中 21 份 HTTP 200 页面/JS/配置（含两份已脱敏 commonV1.js）
检查北京时间、东八区、时区、Asia/Shanghai、UTC/GMT +8、+08:00、timezone、getTimezoneOffset；
保留内容未发现充分的业务时区证据。详情模板对 kickoff 只做 `substring(0,16)`，没有可核验的时区转换。
新三 Raw 也没有提供对应时区或 offset。时区复查清单保留资产路径和 hash；此结论限于已保存内容。

因此 kickoff_timezone、publication_timezone 均 **UNVERIFIED**。
**PROVIDER_PUBLISHED_AT 不成立**，`published_at/replay_available_at/availability_basis` 全部 NULL。
用户采集时间的 `+08:00` 仅说明采集时间，不用于证明比赛或发布业务时间。

T-360、T-90、T-30、T-15、T-5、LAST_PREMATCH 均 BLOCKED；没有计算正式候选。
POST_KICKOFF 分类未执行、数量未知，没有将末条直接认定为 LAST_PREMATCH。
没有 HAD 进入赛前 Feature。

## D2A 与停止点

本轮用真实目标字段及真实无时区 kickoff 构造 ResearchMatch 的负向检查，现有 contract 实际拒绝：
**`Research timestamps require timezone-aware datetime`**（`research_replay.py:_utc`）。
没有构造成功的 ResearchMatch、SPORTTERY_POOL、SportteryVerificationInput(status=VERIFIED) 或 ResearchImport，
没有调用 validate_import/importer/seal 并冒称通过或失败。

VERIFIED 所需的 `sporttery_pool_evidence` 必须与比赛、主客队及带时区 kickoff 完全一致；
`contracts.py:validate_import` 对应约束为 **`Official raw evidence must identify this match, teams and kickoff`**。

**SEALED blocked by ResearchMatch.kickoff_at 的带时区必填约束及其对应的完整 SPORTTERY_POOL 声明缺失。**
当前 Match/Target-only Pilot 的直接剩余证据缺口是 **kickoff 的官方时区依据**。
发布时间时区是正式 cutoff 的额外条件；它不是 contract 对无可用性记录封存的强制条件。

三份正文未提供真实 finished_at。若导入 ResearchResult，必须有带时区结束时间且满足
**`Result finished_at must be strictly after match kickoff_at`**；未使用采集时间、开奖时间或 kickoff 加时长替代。
现有 `ResearchDataset` 与 `seal_dataset` 允许 `results=()`，所以缺 finished_at **不单独阻止无 Result 数据集封存**。
Gate B 另要求合格外部历史赔率，官方 SPORTTERY_HAD 不属于 external consensus。

## 要求的 30 项结果

| # | 项目 | 本批结果 |
|---|---|---|
| 1 | 三 Raw hash/provenance | 已核验，上表及机器清单；采集时间均为 10:02:21+08:00 |
| 2 | 三 Raw 身份一致 | PASS；比赛、主客队、比分及详情 URL ID 均一致 |
| 3 | official Sporttery match ID | 2041790 |
| 4 | 竞彩编号 | 周三002；列表 matchNum=3002，matchNumStr=周三002 |
| 5 | official Sporttery homeTeamId | 2053 |
| 6 | official Sporttery awayTeamId | 2060 |
| 7 | 其他 namespace 映射 | 无前缀 2639184/17249/17231；uniform 2510139/55828/55821，分别保存 |
| 8 | kickoff raw | 2026-09-30 18:30 |
| 9 | kickoff timezone 证据 | 不充分，UNVERIFIED；kickoff_at=NULL |
| 10 | 90 分钟比分 | 1:1，三 Raw 一致 |
| 11 | HAD 实际条数 | 18，完整 18，正式导入 0 |
| 12 | first HAD | 2026-09-29 09:55:48；HOME 4.45 / DRAW 3.35 / AWAY 1.65 |
| 13 | last HAD | 2026-09-30 17:50:30；HOME 6.30 / DRAW 3.45 / AWAY 1.47 |
| 14 | updateDate/updateTime 语义 | 已保存 HTML→JS→真实 Raw 的固定奖金发布时间映射成立 |
| 15 | 发布时间 timezone | UNVERIFIED |
| 16 | PROVIDER_PUBLISHED_AT | 不成立；published_at、replay_available_at、availability_basis 均 NULL |
| 17 | T-360 | BLOCKED，选中记录 NULL |
| 18 | T-90 | BLOCKED，选中记录 NULL |
| 19 | T-30 | BLOCKED，选中记录 NULL |
| 20 | T-15 | BLOCKED，选中记录 NULL |
| 21 | T-5 | BLOCKED，选中记录 NULL |
| 22 | LAST_PREMATCH | BLOCKED，选中记录 NULL |
| 23 | VERIFIED Target 是否建立 | 否，0 |
| 24 | Gate A | BLOCKED：kickoff 时区未核验，不能完成带时区 Match 与 SPORTTERY_POOL 声明 |
| 25 | Gate C | BLOCKED：真实 finished_at 缺失，且 VERIFIED Target 尚未建立 |
| 26 | Gate B | BLOCKED：没有合格外部历史赔率输入，官方 HAD 不替代外部共识 |
| 27 | Pilot Dataset 是否创建 | 否；jc-football-official-pilot 仍仅为目标名称 |
| 28 | 是否 SEALED | 否 |
| 29 | dataset version/hash | NULL / NULL |
| 30 | 当前唯一剩余阻塞 | Match/Target-only Pilot：kickoff 的官方时区证据。完整链路另有发布时间时区、Result finished_at 和 Gate B 外部证据缺口 |

## 实际验证

Raw/provenance/hash 复验、三 Raw 身份一致性、18 条完整性与顺序、namespace 区分、
已保存时区证据 hash 复验及无时区 kickoff 的 D2A 拒绝检查均通过。
没有新 mock、synthetic 字段、生产代码改动或数据库写入；未重复运行无关全量测试。

```powershell
$env:RESEARCH_NETWORK_ENABLED='0'
$env:PYTHONIOENCODING='utf-8'
.venv/Scripts/python.exe artifacts/research-probes/20261002-manual-official-100221/check_evidence.py
```

输出 `check=PASS, identity=PASS, had_row_count=18, status=BLOCKED_TIMEZONE_EVIDENCE`。
这里的检查 PASS 不表示 Gate A PASS。已按要求停在证据允许的边界，不补时区或 finished_at。
