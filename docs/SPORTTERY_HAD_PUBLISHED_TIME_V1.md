# SPORTTERY_HAD_PUBLISHED_TIME_V1 — USER_ATTESTED

Current status: [docs/RESEARCH_CURRENT_STATE.json](RESEARCH_CURRENT_STATE.json).

本轮仅处理已核验的 Sporttery 2041790。HAD publication timezone 接受用户/项目责任人的明确确认，**证据类型为 USER_ATTESTED**。官方帮助文档对该字段时区的独立证明仍未取得；没有把用户确认改写成官方声明。此前 [资格审查](OFFICIAL_HAD_QUALIFICATION_REPORT.md) 及其 [机器结果](official-had-qualification.json) 保留为历史结论，不重写。

## 两条独立证据

| 事项 | 证据类型 | 结论与出处 |
|---|---|---|
| 字段语义 | `OFFICIAL_DOCUMENTED` | `publication_label_status=VERIFIED`；官方 HTML/JS 将 hadList 每行 updateDate + updateTime 直接显示为“发布时间”，同一行包含 h/d/a；[独立字段证据](sporttery-had-publication-label-v1.json) |
| 墙钟时区 | `USER_ATTESTED` | 用户确认“中国体育彩票官方业务时间采用 UTC+8，即北京时间”；`attested_by=USER`，实际记录时间 `2026-10-02T03:16:30.765525+00:00`；[独立用户确认](sporttery-had-published-time-v1.json) |

官方 [JS](https://static.sporttery.cn/res_1_0/jcw/default/jc/zqdz.js) 第 177–188 行请求 getFixedBonusV1，并将 oddsHistory 赋给 FBonus.oddsHistory；[页面模板](https://www.sporttery.cn/jc/zqdz/index.html?showType=3&mid=2041790) 第 297、302–317 行显示“发布时间”、updateDate/updateTime 与 h/d/a。两份原始证据的 URL、抓取时间、响应 SHA-256、canonical hash 和本地路径均保存在字段证据文件中。导入前再次复验了这些 hash 和实际代码片段。

用户确认原文存档的 SHA-256 为 `d200ced0e7f04a24e91523cf097c321d690e408f63ea87d132a886cd30c682d8`。`attested_at` 是记录确认的时间；它不参与任何历史 publication、cutoff 或 availability 计算。

## 严格字段范围

版本 `SPORTTERY_HAD_PUBLISHED_TIME_V1` 只接受以下完整字段对：

```text
getFixedBonusV1.value.oddsHistory.hadList[].updateDate
getFixedBonusV1.value.oddsHistory.hadList[].updateTime
```

格式为 `YYYY-MM-DD` 和 `HH:mm:ss`。将 naive 墙钟解释为 `Asia/Shanghai`，并要求该日期实际 offset 为 `+08:00`；返回 aware 时间及 UTC。HHA/HHAD、TTG、CRS、HAFU、lastUpdateTime、finished_at、kickoff、其他 API 字段均不适用。本轮 attestation scope 绑定 2041790，未扩展比赛。

每个 snapshot 保留 raw_updateDate、raw_updateTime、raw_prices、Raw 内路径、source_timezone、source_timezone_rule、timezone_evidence_type、evidence_version、normalized_time、UTC、published_at、replay_available_at 和 availability_basis。`published_at = replay_available_at`，basis 为 `PROVIDER_PUBLISHED_AT`；无固定延迟或 retrieved_at 代填。Decimal 只做既有 canonical 字符串序列化，原始价格文本另行保留。

解析复用原有 HAD 完整快照审计，不跨行拼接。重复时间、价格冲突、元数据冲突或不完整快照均拒绝进入正式 Quote，保留 Raw 等待审查。时间早于 kickoff 才为 PREMATCH；等于或晚于 kickoff 的 snapshot 只保留在证据中。六个 cutoff 均先限定 PREMATCH，再取 `published_at <= cutoff` 的最新完整 snapshot。

## Match availability 的独立复核

本轮明确采用 `MATCH_AVAILABILITY_FROM_OFFICIAL_HAD_V1`，类型为 `DERIVED_FROM_VERIFIED_OFFICIAL_MARKET_PUBLICATION`。该推导需要单独启用，不随 timezone normalization 自动开启；[独立证据及复核理由](match-2041790-availability-from-had-v1.json) 保存版本、身份、原始 hash/URL、首条路径、时区证据 hash 和复核时间。

推理依据是：已验真的官方 Raw 将完整历史 HAD 行绑定到 `oddsHistory.matchId=2041790` 和队伍 `2053/2060`；官方模板证明这些行带的是该市场的发布时间；用户确认补足了该时间的时区。发布一个明确识别该比赛的 HAD 市场，意味着提供方最迟在该次市场发布时已发布该比赛身份。采用最早可验证 snapshot 是保守的“最迟已发布”时间界限，不断言 Match 的真实首次发布事件就发生在那一秒。

> The match is provably available no later than the first verified provider-published Sporttery HAD snapshot explicitly bound to the same sporttery_match_id.

该结论以已验真历史发布记录及本次 USER_ATTESTED 时区为前提，不是从赛果、kickoff、当前下载时间推导，也不是 getMatchHeadV1 原生的 publication timestamp。不声称证明每次历史 MatchHead 修订或 LIVE_AS_OBSERVED 可见性；没有回填 analysis_visibility。Match 的队伍及 kickoff 继续使用已验收的 Gate A 证据。

新版本 Match 的 published_at 与 replay_available_at 均为 `2026-09-29T09:55:48+08:00`，UTC 为 `2026-09-29T01:55:48Z`；basis 为 `PROVIDER_PUBLISHED_AT`。如果未明确启用这份独立推导，代码保留 Match 的 NULL availability，冻结 Replay 继续 fail closed。ID 或队伍绑定不匹配时直接拒绝。

## 真实数据与 cutoff 验收

输入是原先保存的完整 getFixedBonusV1 Raw，不从测试 fixture 导入；本轮没有网络请求。原始响应 SHA-256 为 `5a2219730b1de410551ff84218ccee306ad3350fcc2d4fbbae069771899fc4ba`，canonical payload hash 为 `ccd34ebdc92a32fe9fb7e589355e8d2252ebd14c844855ed00a889e76a1cd498`。

程序重新计算出 **18 条完整 snapshot、54 个正式 Quote、18 PREMATCH、0 POST_KICKOFF**。首条发布时间 `2026-09-29T09:55:48+08:00`；末条 `2026-09-30T17:50:30+08:00`。数量、首尾和分类均从 Raw 推导，预期数值仅用于后置验收断言。

| 策略 | cutoff（2026-09-30，+08:00） | 选中 publication（同日，+08:00） | HOME / DRAW / AWAY |
|---|---|---|---|
| T-360 | 12:30:00 | 12:12:26 | 5.65 / 3.67 / 1.47 |
| T-90 | 17:00:00 | 16:48:02 | 6.00 / 3.66 / 1.45 |
| T-30 | 18:00:00 | 17:50:30 | 6.30 / 3.45 / 1.47 |
| T-15 | 18:15:00 | 17:50:30 | 6.30 / 3.45 / 1.47 |
| T-5 | 18:25:00 | 17:50:30 | 6.30 / 3.45 / 1.47 |
| LAST_PREMATCH | 严格早于 18:30:00 | 17:50:30 | 6.30 / 3.45 / 1.47 |

## 实际 D2A、封存及 Replay

使用原有 `validate_import → import_research_dataset → seal_dataset`，实际写入 PostgreSQL 的独立 research 表。新版本 `jc-football-official-pilot / 2041790-official-had-v1` 已 **SEALED**，hash 为 `ebf451127c7e49a308b2d75116607c2df67449e4a0cfc50d4fd003ed20fb2095`；1 Match、1 VERIFIED Target、54 Quote、7 Raw、0 Result、0 external odds。

新版本使用 source_name/provider=`sporttery`，bookmaker=`Sporttery`、market_type=`SPORTTERY_HAD`，满足既有 provenance/source identity 契约；旧版本的 source_name 和内容保持原样。官方原始 payload 没有改写。Match 与 Quote provenance 指向已验真的 fixed-bonus Raw，SPORTTERY_POOL 独立保留已验真的身份和 kickoff 证据；用户时区确认和独立 Match 推导保存在新 manifest/metadata，不伪装成官方 Raw 文本。

从数据库回读后，五个固定分钟策略实际调用 `build_research_feature`，均成功；selected Quote ID、价格及 publication 与 Raw 计算一致，连同 previous Quote 的全部输入时间都不晚于 cutoff 且严格早于 kickoff。LAST_PREMATCH 为独立 HAD 选择检查，没有给冻结 Replay 添加新的 cutoff kind。

对每个 Feature 调用既有市场函数仅核验隔离：Sporttery HAD 来源完整，`external_consensus.source_count=0`、`p_market=NULL`、`sporttery_external_gap=NULL`。没有模型评估结果或真实 LIVE Feature/Market snapshot 写入。

旧版本 `2041790-gate-a-v1` 的 hash 仍为 `2e7efbcc160e182b975c5918bcdea9ffefd9364d4aaf83529f4a1864a23f1e89`。整个 header、全部成员表、旧报告和受保护代码/证据均按前置 hash 复核；无成员追加、覆盖或冻结契约修改。Gate A PASS；Gate B 因缺合格 external historical odds 继续 BLOCKED；Gate C 因 finished_at=NULL 继续 BLOCKED；Market Model evaluable=false。

[完整机器结果](sporttery-2041790-official-had-v1-result.json) · [正式输入](../artifacts/research-probes/20261002-official-had-user-attested/research-import.json) · [逐行规范化](../artifacts/research-probes/20261002-official-had-user-attested/normalized-had.json) · [可重跑导入脚本](../artifacts/research-probes/20261002-official-had-user-attested/import_had.py)

## 回归

新增测试覆盖 USER_ATTESTED 与 OFFICIAL_DOCUMENTED 分离、严格字段与身份范围、完整 snapshot、Decimal、首尾、六个 cutoff、cutoff 等时刻纳入、kickoff 等时刻及之后排除、独立 Match availability opt-in、错误 ID/队伍拒绝、D2A 双版本不可变性、54 Quote round-trip、VERIFIED Target、Replay 和 external consensus 隔离。测试中的官方 Raw 摘录带原始来源 hash，仅用于回归；真实导入重新核验完整保存 Raw。

SQLite 全量 **991 passed / 1 skipped**；PostgreSQL 17.11 全量 **991 passed / 1 skipped**。唯一跳过项为需显式启用的联网测试；两套均保留既有 1 条 Starlette 弃用警告。Ruff 通过，Mypy 通过（53 个源文件）。专用 PostgreSQL 测试库 `jc_official_had_attested_test` 结束后只剩空 `alembic_version` 表，真实 Dataset 所在库不参与破坏性测试。

全量回归后再次通过相同输入执行 D2A 的既有幂等路径、回读和 Replay 检查，新版本 hash 稳定；旧 Dataset 的 header、全部成员及受保护文件仍与基线完全一致。完整日志与 [validation.json](../artifacts/research-probes/20261002-official-had-user-attested/validation.json) 保存在本轮输出目录。
