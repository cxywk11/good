# P4-4D2B.5 Official HAD Publication Time & Match Availability Qualification

Current status: [docs/RESEARCH_CURRENT_STATE.json](RESEARCH_CURRENT_STATE.json).

本轮仅审查 Sporttery 2041790。结论：**publication timezone = UNVERIFIED；Match availability = UNVERIFIED；REPLAY_STILL_BLOCKED**。没有创建 publication normalization rule 或 Match availability attestation，没有创建新真实 Dataset。现有 `2041790-gate-a-v1` 保持 SEALED，Gate A PASS，Gate B/C BLOCKED。

## Existing Evidence Audit

先离线审查已保存的官方 HTML、JS、API Raw 和既有证据文档，再进行小范围官方研究。审查 41 个官方 Raw envelope、34 个唯一 payload；该阶段网络请求为 0。逐份复验 canonical hash，并对原样保留的 payload 复验原始响应 SHA-256。[审查清单](../artifacts/research-probes/20261002-official-had-qualification/existing-evidence-audit.json) 保留路径、URL、抓取时间、hash 和相关文本命中。

两项既有映射证据成立：

| 证据 | URL | 抓取时间（UTC） | 响应 SHA-256 | 含义 |
|---|---|---|---|---|
| 官方 JS，第 177–188 行 | [zqdz.js](https://static.sporttery.cn/res_1_0/jcw/default/jc/zqdz.js) | 2026-10-02T00:02:46.845155+00:00 | `4bf8a73a1fabff504371e93cf0ae107222d41a404416041ebf51e58065f0905b` | getFixedBonusV1 返回的 oddsHistory 直接赋值给页面 FBonus.oddsHistory |
| 官方 HTML，第 284–317 行 | [2041790 比赛详情模板](https://www.sporttery.cn/jc/zqdz/index.html?showType=3&mid=2041790) | 2026-10-02T00:05:47.705227+00:00 | `928c56a2154458b7d074d853e05062eadaa06deb7cf61d53dd888e9f780d7fdf` | HAD 表头为“发布时间”，hadList 同行直接显示 updateDate、updateTime、h/d/a，无前端时区转换 |

由此可验证**字段的 publication label**，不能验证其时区。模板本身也不能证明 2041790 在历史某时刻的可见性。2015/2020 官方文章中已通过的“北京时间”对应的是比赛开球时间；继续只支持 `SPORTTERY_SCHEDULE_TIME_V1` 的原有字段范围。WAF 页面中的浏览器时区指纹代码不是奖金发布时间规范。

## 有界官方补查与证据判定

仅定位官方域名资料，通过普通 HTTPS 保存 8 个响应，不自动跟随 302，不重试或绕过验证。完整 URL、抓取时间、响应 hash、HTTP 状态和本地 Raw 路径见 [机器核验结果](official-had-qualification.json) 的 `bounded_official_research`。

| URL | HTTP | 判定 |
|---|---|---|
| [帮助入口](https://www.sporttery.cn/bzzx/index.html) | 200 | 页面跳转说明，无发布时间时区证据 |
| [Sporttery 规则目录](https://www.sporttery.cn/bzzx/yxgz/) | 404 | 无可用规则正文 |
| [lottery.gov.cn 规则目录](https://www.lottery.gov.cn/bzzx/yxgz/) | 302 | 未自动跟随；不作为证据 |
| [历史胜平负规则](https://www.sporttery.cn/help/60328.html) | 200 | 说明奖金设定与公布方式，没有时间字段的时区定义 |
| [官方问答](https://www.sporttery.cn/help/2864.html?gid=5) | 200 | 没有 HAD 发布时间的时区约定 |
| [2014 固定奖金专题](https://www.sporttery.cn/football/spec/2014/1019/123787.html) | 200 | 说明固定奖金公布方式，没有 HAD 时间字段约定 |
| [帮助入口目标页](https://www.sporttery.cn/bzzx/20210207/3003229.html?gid=0) | 200 | 彩票管理规则，不是 HAD 时区说明 |
| [现行帮助中的胜平负规则页](https://www.sporttery.cn/bzzx/20210118/3060333.html?gid=3) | 200 | 初始奖金及变化由销售系统等方式公布；没有北京时间或 API updateTime 时区保证 |

最后一页抓取时间为 `2026-10-02T02:51:30.724993+00:00`，响应 SHA-256 为 `5aa711f8b5d1c8acbb8ee998b6d0439f940e48f019cc74bba36320b9f53dc910`。它提供了发布渠道的一般规则，未满足用户指定的 A/B/C 级时区证据，也未记录目标比赛在历史时点的发布事实。这里的不足结论仅限本轮审查到的资料，不声称所有官方资料均不存在该证据。

`SPORTTERY_HAD_EVIDENCE_AUDIT_V1` 是**证据审计格式版本**，不是 publication evidence version。后者继续 `NULL`；没有定义 `SPORTTERY_HAD_PUBLISHED_TIME_V1`，不能使用 `Asia/Shanghai`。审计器只接收 `getFixedBonusV1.value.oddsHistory.hadList`；其他市场、kickoff、finished_at、lastUpdateTime 均拒绝。kickoff 规则、D2A、research-replay-v1、analysis_visibility、Migration 009、LIVE providers 均未修改。

## 18 条 HAD 的重新解析

原始来源：[getFixedBonusV1，matchId=2041790](https://webapi.sporttery.cn/gateway/uniform/football/getFixedBonusV1.qry?clientCode=3001&matchId=2041790)。使用已保存的真实 Raw，本轮没有重抓该 API；原 provenance 的抓取时间为 `2026-10-02T02:02:21+00:00`。

- 响应 SHA-256：`5a2219730b1de410551ff84218ccee306ad3350fcc2d4fbbae069771899fc4ba`。
- canonical payload hash：`ccd34ebdc92a32fe9fb7e589355e8d2252ebd14c844855ed00a889e76a1cd498`。
- 程序计算：18 snapshots、18 complete、54 个 Decimal 价格值；正式 `ResearchOddsQuote` 数量为 **0**。
- 每条独立校验 updateDate/updateTime 和 HOME/DRAW/AWAY，不跨行拼接。原序升序；重复时间组 0、冲突组 0。
- 首个原始墙钟：`2026-09-29 09:55:48`，4.45 / 3.35 / 1.65；最后原始墙钟：`2026-09-30 17:50:30`，6.30 / 3.45 / 1.47。
- `source_timezone_rule / normalized_time / UTC / evidence_version / published_at / replay_available_at / availability_basis` 逐行保持 `NULL`。

[逐行审计](../artifacts/research-probes/20261002-official-had-qualification/had-evidence.json) 保留 raw_updateDate、raw_updateTime、raw_prices、Raw 内路径以及完整 snapshot。naive datetime 仅用于格式有效性检查和墙钟排序，不形成时间点，不与 kickoff 比较。

因此 first/last published_at、PREMATCH/POST_KICKOFF 数量均为 `NULL`，不能把 post-kickoff 数量报为 0。T-360、T-90、T-30、T-15、T-5、LAST_PREMATCH 全部 `BLOCKED_PUBLICATION_TIMEZONE`，未选择记录。用户列出的 cutoff 价格预期值没有被硬编码为计算结果。

## Match availability 独立判断

当前 `oddsHistory.matchId=2041790` 证明返回的历史列表现在与该 ID 关联。一般奖金公布规则没有证明当前返回的 identity 在第一行所述历史墙钟时刻已经公开，也没有提供该历史时刻的目标 ID 发布存档；该墙钟本身还没有经过时区资格认定。因此本轮不能仅由“历史市场存在”推导 Match 当时可见。

没有创建 `MATCH_AVAILABILITY_EVIDENCE_V1`；Match 的 `published_at / replay_available_at / availability_basis` 保持 `NULL`。未使用 kickoff、retrieved_at、比赛日期、下载时间或首次 HAD naive time 代填。读取旧真实 SEALED Dataset 后，在冻结 Replay 实现中实际尝试 T-360/T-90/T-30/T-15/T-5，全部返回 `MATCH_UNAVAILABLE_AT_CUTOFF`。未创建 Replay Run，未评价 Market Model。

## 不可变性与状态归一

对实际 PostgreSQL 旧 Dataset 只读：核对整个 header 及 sources/raw_artifacts/matches/odds_quotes/results 各表的成员数与 canonical hash，前后完全一致。仍是 1 Match、1 VERIFIED Target、7 Raw、0 Odds、0 Result；唯一版本是 `2041790-gate-a-v1`。

`dataset_key=jc-football-official-pilot`；旧 hash 保持 `2e7efbcc160e182b975c5918bcdea9ffefd9364d4aaf83529f4a1864a23f1e89`。没有追加成员或新建真实版本。验证脚本与前置基线见 [只读复核脚本](../artifacts/research-probes/20261002-official-had-qualification/check_qualification.py) 和 [baseline-before.json](../artifacts/research-probes/20261002-official-had-qualification/baseline-before.json)。

唯一当前状态为 [RESEARCH_CURRENT_STATE.json](RESEARCH_CURRENT_STATE.json)。旧报告顶部增加状态指针，旧阶段表明确作为 HISTORICAL SNAPSHOT；旧机器文件没有重写，其路径、历史分类和原始文件 hash 登记在当前状态的 `historical_snapshots` 中。

## 验证范围

新增审计回归验证严格字段范围、缺失/非法日期时间、完整快照、Decimal、原序/首尾/重复冲突保留、不能猜测时区或 availability、所有 cutoff 保持阻塞，以及真实报告与当前状态的一致性。

新增独立的 **synthetic capability control**：在测试数据库内使用显式声明的 aware publication instants，验证 18×3 Quote round-trip、Raw provenance、旧版本不可覆盖、封存 hash 稳定、1 VERIFIED Target、无 Match availability 时 fail closed、有独立 availability 时可以构建 Feature，以及 Sporttery HAD 不进入 external consensus。这些模拟测试不构成任何真实来源的资格证明，也没有产生真实新 Dataset。

因证据未通过，真实 publication normalization、54 Quote 导入、正式 cutoff acceptance、开球后分类、Match publication attestation、新真实 Dataset sealing 均为 **NOT RUN / BLOCKED**。不把这些条件性验收误报为通过。

全量 SQLite：**950 passed、1 skipped**；全量 PostgreSQL 17.11：**950 passed、1 skipped**。跳过的是需要显式开启的联网测试；两套都保留 1 条既有 Starlette 弃用警告。PostgreSQL 使用新建的空专用库 `jc_official_had_qualification_test`，完成后仅余空 `alembic_version` 表，未将真实 Dataset 所在库用作测试库。`ruff check apps/api/src tests` 通过；`mypy apps/api/src` 通过（52 个源文件）。

测试后再次执行只读真实核验，旧 Dataset header、全部成员、受保护文件、历史机器文件 hash 均未变化，仍无新真实版本。完整日志与 [validation.json](../artifacts/research-probes/20261002-official-had-qualification/validation.json) 保留在本轮输出目录。
